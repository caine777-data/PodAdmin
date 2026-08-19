"""
Tests de la logique pure de PodAdmin
====================================
Ces tests couvrent les fonctions qui ne dépendent NI du réseau NI de l'interface
graphique. Ce sont précisément celles qui ont déjà causé des régressions par le
passé (relations dict/URL, détection de doublons, conversion de sous-titres…).

Lancement :
    pip install pytest
    python -m pytest tests/ -v

Note : les méthodes de la classe `App` testées ici sont statiques ou n'utilisent
pas `self` — on les appelle donc sans instancier l'interface, ce qui permet de
tester sans Tk ni serveur.
"""

import os
import sys
from datetime import datetime

import pytest

# Permettre l'import des modules du dossier parent
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ══════════════════════════════════════════════════════════════════════════
#  pod_api : fonctions sans réseau
# ══════════════════════════════════════════════════════════════════════════

class TestSrtToVtt:
    """Conversion des sous-titres SRT → WebVTT (exigée par Pod)."""

    def test_entete_webvtt_ajoute(self):
        from pod_api import srt_to_vtt
        srt = "1\n00:00:01,000 --> 00:00:04,000\nBonjour\n"
        assert srt_to_vtt(srt).startswith("WEBVTT")

    def test_virgules_converties_en_points(self):
        """SRT utilise la virgule pour les millisecondes, WebVTT le point."""
        from pod_api import srt_to_vtt
        srt = "1\n00:00:01,500 --> 00:00:04,250\nTexte\n"
        out = srt_to_vtt(srt)
        assert "00:00:01.500 --> 00:00:04.250" in out
        assert ",500" not in out

    def test_texte_conserve(self):
        from pod_api import srt_to_vtt
        srt = "1\n00:00:01,000 --> 00:00:02,000\nAccents : éàü\n"
        assert "Accents : éàü" in srt_to_vtt(srt)

    def test_entree_vide(self):
        from pod_api import srt_to_vtt
        assert srt_to_vtt("").startswith("WEBVTT")


class TestDetectionVideos:
    """Critères de tri utilisés par l'Explorateur."""

    def test_video_non_encodee(self):
        from pod_api import PodAPI
        assert PodAPI.is_unencoded({"encoded": False}) is True
        assert PodAPI.is_unencoded({"encoded": True}) is False

    def test_brouillon_ancien(self):
        from pod_api import PodAPI
        vieux = {"is_draft": True, "date_added": "2020-01-15"}
        recent = {"is_draft": True, "date_added": "2030-01-15"}
        assert PodAPI.is_stale_draft(vieux, "2025-01-01") is True
        assert PodAPI.is_stale_draft(recent, "2025-01-01") is False

    def test_video_publiee_jamais_brouillon_ancien(self):
        """Une vidéo publiée ne doit jamais être proposée au nettoyage."""
        from pod_api import PodAPI
        publiee = {"is_draft": False, "date_added": "2020-01-15"}
        assert PodAPI.is_stale_draft(publiee, "2025-01-01") is False


# ══════════════════════════════════════════════════════════════════════════
#  app : normalisation des relations (source de bugs avérés)
# ══════════════════════════════════════════════════════════════════════════

class TestRelUrls:
    """`_rel_urls` normalise les relations de l'API, qui arrivent sous trois
    formes différentes selon le sérialiseur. Un traitement incomplet avait
    provoqué un bug réel : aucun membre de chaîne n'était détecté, donc aucun
    retrait n'était jamais appliqué."""

    @staticmethod
    def _f():
        import app
        return app.App._rel_urls

    def test_url_seule(self):
        assert self._f()("https://v.fr/rest/channels/3/") == ["https://v.fr/rest/channels/3"]

    def test_liste_d_urls(self):
        entree = ["https://v.fr/c/3/", "https://v.fr/c/4/"]
        assert self._f()(entree) == ["https://v.fr/c/3", "https://v.fr/c/4"]

    def test_liste_d_objets_imbriques(self):
        """LE cas qui avait cassé : objets {url, title} au lieu d'URLs."""
        entree = [{"url": "https://v.fr/c/3/", "title": "Chaîne 3"}]
        assert self._f()(entree) == ["https://v.fr/c/3"]

    def test_objet_seul(self):
        assert self._f()({"url": "https://v.fr/c/9/"}) == ["https://v.fr/c/9"]

    def test_valeurs_vides(self):
        assert self._f()(None) == []
        assert self._f()([]) == []
        assert self._f()("") == []

    def test_sans_normalisation_garde_la_barre(self):
        """Pour un PATCH, l'URL doit être renvoyée telle quelle."""
        entree = [{"url": "https://v.fr/c/3/"}]
        assert self._f()(entree, normalise=False) == ["https://v.fr/c/3/"]

    def test_appartenance_a_une_chaine(self):
        """Reproduction du bug : détecter qu'une vidéo est dans une chaîne."""
        f = self._f()
        cible = "https://v.fr/rest/channels/3"
        video_objet = {"channel": [{"url": "https://v.fr/rest/channels/3/"}]}
        video_url = {"channel": ["https://v.fr/rest/channels/3/"]}
        video_hors = {"channel": []}
        assert cible in f(video_objet.get("channel"))
        assert cible in f(video_url.get("channel"))
        assert cible not in f(video_hors.get("channel"))


class TestProprietaire:
    """`_video_owner_id` doit gérer tous les formats de propriétaire."""

    @staticmethod
    def _f(video):
        import app
        return app.App._video_owner_id(None, video)

    def test_owner_url(self):
        assert self._f({"owner": "https://v.fr/u/42/"}) == "https://v.fr/u/42/"

    def test_owner_objet(self):
        assert self._f({"owner": {"url": "https://v.fr/u/42/",
                                  "username": "jdupont"}}) == "https://v.fr/u/42/"

    def test_owner_objet_sans_url(self):
        assert self._f({"owner": {"username": "jdupont"}}) == "jdupont"

    def test_owner_absent(self):
        assert self._f({}) == ""


class TestEtatEncodage:
    """Classement des vidéos dans l'onglet Encodage."""

    @staticmethod
    def _f(v):
        import app
        return app.App._encode_state(v)

    def test_encodee(self):
        assert self._f({"encoded": True}) == "ok"

    def test_en_cours(self):
        assert self._f({"encoded": False, "encoding_in_progress": True}) == "running"

    def test_brouillon(self):
        assert self._f({"encoded": False, "is_draft": True}) == "draft"

    def test_priorite_encodee_sur_le_reste(self):
        """Une vidéo encodée reste « ok » même si d'autres drapeaux traînent."""
        assert self._f({"encoded": True, "is_draft": True}) == "ok"


class TestDoublons:
    """Détection des titres en double (outil de nettoyage)."""

    @staticmethod
    def _f(vids):
        import app
        return app.App._duplicate_title_videos(None, vids)

    def test_aucun_doublon(self):
        vids = [{"title": "Cours A"}, {"title": "Cours B"}]
        assert self._f(vids) == []

    def test_doublon_simple(self):
        vids = [{"title": "Cours A"}, {"title": "Cours A"}, {"title": "Cours B"}]
        assert len(self._f(vids)) == 2

    def test_insensible_a_la_casse_et_aux_espaces(self):
        vids = [{"title": "Cours A"}, {"title": "  cours a  "}]
        assert len(self._f(vids)) == 2

    def test_titres_vides_ignores(self):
        """Deux vidéos sans titre ne sont pas des doublons à signaler."""
        vids = [{"title": ""}, {"title": ""}, {"title": None}]
        assert self._f(vids) == []


class TestMoisPrecedents:
    """`_months_ago_iso` sert aux filtres « plus vieux que N mois »."""

    @staticmethod
    def _f(mois):
        import app
        return app.App._months_ago_iso(None, mois)

    def test_format_iso(self):
        import re
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", self._f(6))

    def test_zero_mois_donne_aujourdhui(self):
        assert self._f(0) == datetime.now().date().isoformat()

    def test_recul_d_un_an(self):
        resultat = self._f(12)
        assert int(resultat[:4]) == datetime.now().year - 1

    def test_passage_d_annee(self):
        """24 mois en arrière = 2 ans, sans erreur de calcul sur les mois."""
        assert int(self._f(24)[:4]) == datetime.now().year - 2


# ══════════════════════════════════════════════════════════════════════════
#  Garde-fous de l'API (sans réseau : on simule les réponses)
# ══════════════════════════════════════════════════════════════════════════

class TestPaginationTronquee:
    """Une pagination tronquée doit être SIGNALÉE : sans cela, l'Inventaire
    affiche des totaux faux sans que rien ne l'indique."""

    def test_drapeau_leve_si_pages_restantes(self):
        from pod_api import PodAPI
        api = PodAPI.__new__(PodAPI)          # sans __init__ (pas de réseau)
        api.last_scan_truncated = False
        # Simulation : il restait une page à lire
        url_restante = "https://v.fr/rest/videos/?page=4"
        api.last_scan_truncated = bool(url_restante)
        assert api.last_scan_truncated is True

    def test_drapeau_baisse_si_tout_lu(self):
        from pod_api import PodAPI
        api = PodAPI.__new__(PodAPI)
        api.last_scan_truncated = bool(None)   # plus de 'next'
        assert api.last_scan_truncated is False


class TestErreurApi:
    """`PodAPIError` doit transporter le code HTTP et le corps de la réponse."""

    def test_attributs_conserves(self):
        from pod_api import PodAPIError
        err = PodAPIError("Échec", 404, "introuvable")
        assert err.status == 404
        assert err.body == "introuvable"
        assert "Échec" in str(err)

    def test_valeurs_par_defaut(self):
        from pod_api import PodAPIError
        err = PodAPIError("Erreur simple")
        assert err.status == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


# ══════════════════════════════════════════════════════════════════════════
#  Groupes d'accès : sondage des ids (lot 2 de l'audit)
# ══════════════════════════════════════════════════════════════════════════

class _Rep:
    """Fausse réponse HTTP."""
    def __init__(self, code, data=None):
        self.status_code = code
        self._d = data

    def json(self):
        if self._d is None:
            raise ValueError()
        return self._d


class _Session:
    """Fausse session : groupes aux ids choisis, avec ou sans endpoint liste."""
    def __init__(self, ids, avec_liste=True):
        self.ids = ids
        self.avec_liste = avec_liste
        self.appels = 0

    def get(self, url, **kw):
        self.appels += 1
        if url.rstrip("/").endswith("accessgroups"):
            if not self.avec_liste:
                return _Rep(404)
            return _Rep(200, {"count": len(self.ids)})
        n = int(url.rstrip("/").split("/")[-1])
        if n in self.ids:
            return _Rep(200, {"code_name": f"grp{n}", "display_name": f"Groupe {n}"})
        return _Rep(404)


def _api_factice(ids, avec_liste=True):
    from pod_api import PodAPI
    api = PodAPI.__new__(PodAPI)
    api.rest = "https://v.fr/rest"
    api.verify_ssl = True
    api._access_groups_cache = None
    api.session = _Session(ids, avec_liste)
    return api


class TestGroupesAcces:
    """Le sondage s'arrêtait à l'id 60 : tout groupe au-delà devenait
    DÉFINITIVEMENT invisible dans l'application, sans erreur."""

    def test_groupe_au_dela_de_l_ancien_plafond(self):
        api = _api_factice([1, 2, 75])
        noms = [g["code_name"] for g in api.get_access_groups()]
        assert "grp75" in noms, "un groupe d'id > 60 doit être trouvé"

    def test_tous_les_groupes_trouves(self):
        api = _api_factice([3, 17, 42, 90])
        assert len(api.get_access_groups()) == 4

    def test_resultat_trie_par_nom(self):
        api = _api_factice([5, 1])
        noms = [g["code_name"] for g in api.get_access_groups()]
        assert noms == sorted(noms)

    def test_cache_evite_de_resonder(self):
        api = _api_factice([1, 2])
        api.get_access_groups()
        avant = api.session.appels
        api.get_access_groups()
        assert api.session.appels == avant, "le 2e appel doit venir du cache"

    def test_invalidation_du_cache(self):
        api = _api_factice([1, 2])
        api.get_access_groups()
        avant = api.session.appels
        api.invalidate_access_groups_cache()
        api.get_access_groups()
        assert api.session.appels > avant, "après invalidation, il faut re-sonder"

    def test_repli_sans_endpoint_liste(self):
        """Si l'endpoint liste est indisponible, on retombe sur l'heuristique."""
        api = _api_factice([1, 2, 3], avec_liste=False)
        noms = [g["code_name"] for g in api.get_access_groups()]
        assert {"grp1", "grp2", "grp3"} <= set(noms)

    def test_aucun_groupe(self):
        api = _api_factice([], avec_liste=False)
        assert api.get_access_groups() == []
