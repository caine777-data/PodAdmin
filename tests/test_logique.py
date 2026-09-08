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


class TestInvalidationCacheGroupes:
    """Créer ou supprimer un groupe doit PÉRIMER le cache, sinon le nouveau
    groupe n'apparaît nulle part jusqu'au redémarrage de l'application.

    Régression réelle : l'invalidation avait été placée par erreur dans la
    fonction voisine (`set_access_group_members`), si bien que la CRÉATION ne
    rafraîchissait rien."""

    @staticmethod
    def _api():
        from pod_api import PodAPI
        api = PodAPI.__new__(PodAPI)
        api.rest = "https://v.fr/rest"
        api.verify_ssl = True
        api._access_groups_cache = [{"code_name": "ancien"}]   # cache pré-rempli

        class _R:
            status_code = 201
            text = "{}"

            def json(self):
                return {}

        class _S:
            def post(self, *a, **kw):
                return _R()

            def patch(self, *a, **kw):
                return _R()

        api.session = _S()
        api._delete = lambda url: True
        return api

    def test_creation_invalide_le_cache(self):
        api = self._api()
        api.create_access_group("nouveau", ["https://v.fr/rest/sites/1/"])
        assert api._access_groups_cache is None, \
            "après création, le cache doit être vidé"

    def test_suppression_invalide_le_cache(self):
        api = self._api()
        api.delete_access_group("https://v.fr/rest/accessgroups/1/")
        assert api._access_groups_cache is None, \
            "après suppression, le cache doit être vidé"

    def test_changement_de_membres_invalide_le_cache(self):
        """Les membres sont stockés avec le groupe dans le cache."""
        api = self._api()
        api.set_access_group_members("https://v.fr/rest/accessgroups/1/", [])
        assert api._access_groups_cache is None


class TestDetectionCoupureReseau:
    """Distinguer une COUPURE de connexion d'un REFUS du serveur.

    Cas réel : l'envoi direct d'une vidéo était coupé par la passerelle après
    environ une minute (« SSLEOFError: EOF occurred in violation of protocol »).
    Réessayer à l'identique échouait invariablement ; l'application bascule
    désormais sur l'envoi par morceaux. Mais UNIQUEMENT en cas de coupure : un
    refus métier (champ manquant, droits insuffisants) échouerait pareil en
    chunké, et le rejouer risquerait de créer un doublon."""

    @staticmethod
    def _f(err):
        import app
        return app.App._est_coupure_reseau(err)

    def test_erreur_reelle_ssl_eof(self):
        from pod_api import PodAPIError
        err = PodAPIError(
            "Échec après 3 tentatives (coupure réseau/SSL). Dernière erreur : "
            "HTTPSConnectionPool(host='videos.utoulouse.fr', port=443): Max retries "
            "exceeded with url: /rest/videos/ (Caused by SSLError(SSLEOFError(8, "
            "'EOF occurred in violation of protocol (_ssl.c:2427)')))", 0, "")
        assert self._f(err) is True

    def test_connexion_reinitialisee(self):
        from pod_api import PodAPIError
        assert self._f(PodAPIError("Connection reset by peer", 0, "")) is True

    def test_passerelle_504(self):
        from pod_api import PodAPIError
        assert self._f(PodAPIError("Gateway timeout", 504, "max retries exceeded")) is True

    def test_refus_400_pas_de_repli(self):
        """Un champ manquant échouerait aussi en chunké : ne pas rejouer."""
        from pod_api import PodAPIError
        assert self._f(PodAPIError("HTTP 400 : champ sites requis", 400, "required")) is False

    def test_droits_insuffisants_pas_de_repli(self):
        from pod_api import PodAPIError
        assert self._f(PodAPIError("HTTP 403 interdit", 403, "forbidden")) is False

    def test_token_invalide_pas_de_repli(self):
        from pod_api import PodAPIError
        assert self._f(PodAPIError("HTTP 401", 401, "invalid token")) is False


class TestComparaisonVersions:
    """La comparaison de versions doit être NUMÉRIQUE, pas alphabétique :
    comparer des chaînes ferait passer « 1.10.0 » pour antérieure à « 1.9.0 »,
    et l'application ne proposerait jamais la mise à jour."""

    @staticmethod
    def _c(a, b):
        from maj import comparer_versions
        return comparer_versions(a, b)

    def test_egalite(self):
        assert self._c("1.0.0", "1.0.0") == 0

    def test_anterieure(self):
        assert self._c("1.0.0", "1.0.1") == -1

    def test_posterieure(self):
        assert self._c("1.0.1", "1.0.0") == 1

    def test_piege_dix_contre_neuf(self):
        """LE piège : « 1.10.0 » est POSTÉRIEURE à « 1.9.0 »."""
        assert self._c("1.9.0", "1.10.0") == -1
        assert self._c("1.10.0", "1.9.0") == 1

    def test_longueurs_differentes(self):
        assert self._c("1.2", "1.2.0") == 0

    def test_suffixe_ignore(self):
        assert self._c("1.0.0", "1.0.0-beta") == 0

    def test_valeurs_absurdes(self):
        assert self._c("", "1.0.0") == -1
        assert self._c("abc", "0.0.0") == 0


class TestEtatMiseAJour:
    """La vérification ne doit JAMAIS bloquer ni signaler à tort."""

    def test_deja_a_jour_aucun_signalement(self, monkeypatch):
        import maj
        monkeypatch.setattr(maj, "recuperer_info", lambda u, t=5, journal=None: {"version": "1.0.0"})
        assert maj.etat_mise_a_jour("1.0.0", "http://x") is None

    def test_version_locale_plus_recente(self, monkeypatch):
        """Compilation locale en avance : pas de bandeau."""
        import maj
        monkeypatch.setattr(maj, "recuperer_info", lambda u, t=5, journal=None: {"version": "1.0.0"})
        assert maj.etat_mise_a_jour("1.5.0", "http://x") is None

    def test_mise_a_jour_disponible(self, monkeypatch):
        import maj
        monkeypatch.setattr(maj, "recuperer_info",
                            lambda u, t=5, journal=None: {"version": "1.1.0", "url": "http://dl"})
        info = maj.etat_mise_a_jour("1.0.0", "http://x")
        assert info["version"] == "1.1.0"
        assert info["urgent"] is False

    def test_version_perimee_marquee_urgente(self, monkeypatch):
        import maj
        monkeypatch.setattr(maj, "recuperer_info",
                            lambda u, t=5, journal=None: {"version": "2.0.0", "version_minimale": "1.5.0"})
        assert maj.etat_mise_a_jour("1.0.0", "http://x")["urgent"] is True

    def test_reseau_indisponible_silence(self, monkeypatch):
        import maj
        monkeypatch.setattr(maj, "recuperer_info", lambda u, t=5, journal=None: None)
        assert maj.etat_mise_a_jour("1.0.0", "http://x") is None

    def test_url_vide_desactive_la_verification(self):
        import maj
        assert maj.recuperer_info("") is None


class TestConsultations:
    """Agrégation des vues (`_compute_views`) : fonction pure, sans réseau."""

    VIDEOS = [
        {"url": "https://v/rest/videos/1/", "title": "Cours A",
         "owner": "https://v/rest/users/6/", "channel": ["https://v/rest/channels/3/"]},
        {"url": "https://v/rest/videos/2/", "title": "Cours B",
         "owner": "https://v/rest/users/9/", "channel": []},
    ]
    VUES = [
        {"video": "https://v/rest/videos/1/", "date": "2026-05-20", "count": 8},
        {"video": "https://v/rest/videos/1/", "date": "2026-06-02", "count": 12},
        {"video": "https://v/rest/videos/2/", "date": "2026-06-15", "count": 30},
        {"video": "https://v/rest/videos/1/", "date": "2026-06-20", "count": 0},
    ]
    USERS = {"https://v/rest/users/6": "alice", "https://v/rest/users/9": "bob"}
    CHANS = {"https://v/rest/channels/3": "eformation"}

    def _calc(self, vues=None):
        import app
        return app.App._compute_views(self.VIDEOS,
                                      self.VUES if vues is None else vues,
                                      self.USERS, self.CHANS)

    def test_total(self):
        assert self._calc()["total"] == 50

    def test_entree_a_zero_ignoree(self):
        """Une entrée à 0 vue ne doit pas compter comme une vidéo consultée."""
        assert self._calc()["videos_vues"] == 2

    def test_classement_decroissant(self):
        top = self._calc()["top"]
        assert top[0]["titre"] == "Cours B"
        assert top[0]["vues"] == 30
        assert [e["vues"] for e in top] == sorted([e["vues"] for e in top], reverse=True)

    def test_proprietaire_resolu(self):
        assert self._calc()["top"][0]["proprio"] == "bob"

    def test_regroupement_par_mois(self):
        par_mois = self._calc()["par_mois"]
        assert par_mois["2026-05"] == 8
        assert par_mois["2026-06"] == 42

    def test_mois_par_ordre_chronologique(self):
        """L'évolution doit être chronologique, pas triée par volume."""
        mois = list(self._calc()["par_mois"].keys())
        assert mois == sorted(mois)

    def test_par_chaine_et_hors_chaine(self):
        par_chaine = self._calc()["par_chaine"]
        assert par_chaine["eformation"] == 20
        assert par_chaine["(hors chaîne)"] == 30

    def test_par_proprietaire(self):
        par_proprio = self._calc()["par_proprio"]
        assert par_proprio["alice"] == 20
        assert par_proprio["bob"] == 30

    def test_periode_couverte(self):
        assert self._calc()["periode"] == ("2026-05-20", "2026-06-15")

    def test_video_supprimee_comptee_mais_hors_classement(self):
        """Les vues d'une vidéo supprimée comptent dans le total (activité
        réelle) mais n'apparaissent pas au classement (plus consultable)."""
        vues = self.VUES + [{"video": "https://v/rest/videos/99/",
                             "date": "2026-07-01", "count": 5}]
        r = self._calc(vues)
        assert r["total"] == 55
        assert len(r["top"]) == 2

    def test_aucune_vue(self):
        r = self._calc([])
        assert r["total"] == 0
        assert r["top"] == []
        assert r["periode"] == ("", "")


class TestTracabiliteMiseAJour:
    """Un échec de vérification doit laisser une trace.

    Sans elle, une panne est indétectable : l'utilisateur ne voit simplement
    jamais de bandeau, sans pouvoir en connaître la raison. C'est ce qui a rendu
    difficile le diagnostic d'une panne sur macOS (certificats TLS introuvables
    dans l'application compilée)."""

    def test_echec_reseau_trace(self):
        import maj
        messages = []
        maj.recuperer_info("https://adresse-inexistante-xyz.invalid/v.json",
                           timeout=2, journal=messages.append)
        assert messages, "un échec doit être consigné"

    def test_url_vide_silencieuse(self):
        """Vérification désactivée : pas de message inutile."""
        import maj
        messages = []
        assert maj.recuperer_info("", journal=messages.append) is None
        assert messages == []

    def test_journal_facultatif(self):
        """L'absence de journal ne doit rien casser."""
        import maj
        assert maj.recuperer_info("https://adresse-inexistante-xyz.invalid/v.json",
                                  timeout=2) is None


class TestNonRenvoiDesVideosDejaEnvoyees:
    """Une vidéo déjà téléversée ne doit pas repartir au clic suivant.

    Bug réel : le libellé posé après un envoi réussi était « ✅ terminé », alors
    que la condition testait l'égalité avec « terminé ». L'émoji faisait échouer
    la comparaison, et TOUT le lot était renvoyé dès qu'on ajoutait un fichier —
    créant des doublons sur la plateforme.

    La correction s'appuie sur un indicateur booléen `done`, insensible au
    libellé affiché."""

    @staticmethod
    def _item(tmp_path, nom="v.mp4"):
        import app
        p = tmp_path / nom
        p.write_bytes(b"0" * 2048)
        return app.UploadItem(str(p))

    def test_indicateur_faux_au_depart(self, tmp_path):
        assert self._item(tmp_path).done is False

    def test_libelle_avec_emoji_ne_vaut_pas_egalite(self):
        """Illustre la cause du bug : la comparaison de texte échouait."""
        assert ("✅ terminé" == "terminé") is False
        assert "✅ terminé".endswith("terminé") is True

    def test_indicateur_independant_du_libelle(self, tmp_path):
        """L'indicateur ne dépend pas du texte affiché : c'est tout l'intérêt."""
        it = self._item(tmp_path)
        it.status = "✅ terminé"
        assert it.done is False          # le libellé seul ne suffit pas
        it.done = True
        it.status = "n'importe quel libellé"
        assert it.done is True           # l'indicateur fait foi


class TestTroncatureParRessource:
    """Une alerte de liste incomplète ne doit pas pouvoir être effacée par un
    autre scan.

    Défaut d'origine : `last_scan_truncated` était un attribut de l'objet
    `PodAPI`, partagé par tous les onglets et remis à zéro à chaque appel. Deux
    scans qui se chevauchent — cas courant — et le dernier terminé imposait son
    verdict. L'alerte disparaissait alors qu'une liste était bien tronquée."""

    @staticmethod
    def _api():
        from pod_api import PodAPI
        api = PodAPI.__new__(PodAPI)
        api.troncatures = {}
        return api

    def test_scan_complet_pas_d_alerte(self):
        api = self._api()
        api.troncatures["/videos/"] = False
        assert api.est_tronque() is False

    def test_scan_tronque_leve_l_alerte(self):
        api = self._api()
        api.troncatures["/videos/"] = True
        assert api.est_tronque() is True

    def test_un_scan_complet_n_efface_pas_l_alerte_d_un_autre(self):
        """LE cas du bug : les comptes sont tronqués, les vidéos non.

        Avec le drapeau unique, le second scan écrasait le verdict du premier
        et l'alerte était perdue."""
        api = self._api()
        api.troncatures["/users/"] = True
        api.troncatures["/videos/"] = False
        assert api.est_tronque() is True, (
            "l'alerte des comptes a été effacée par le scan des vidéos")

    def test_interrogation_ciblee(self):
        """On peut demander l'état d'une ressource précise."""
        api = self._api()
        api.troncatures["/users/"] = True
        api.troncatures["/videos/"] = False
        assert api.est_tronque("/videos/") is False
        assert api.est_tronque("/users/") is True
        assert api.est_tronque("/videos/", "/users/") is True

    def test_ressource_jamais_lue(self):
        api = self._api()
        assert api.est_tronque("/inconnue/") is False


class TestNomenclatures:
    """Onglet « Types & disciplines » — deux ressources voisines, quatre
    conventions différentes.

    Toutes établies par sonde sur videos.utoulouse.fr :

                         TYPE                      DISCIPLINE
      champ site         « sites », LISTE          « site », CHAÎNE
      obligatoire        OUI                       non
      sur la vidéo       une seule URL             une LISTE d'URLs
      au départ          4 entrées, 73 vidéos      table vide

    Envoyer une liste là où une chaîne est attendue donne un HTTP 400 :
    « Type incorrect. Attendait une URL, a reçu list. » C'est le refus qu'a
    essuyé la sonde d'écriture avant de trouver la bonne forme. Ces tests
    empêchent qu'on « harmonise » les deux appels."""

    class FauxAPI:
        """Refuse la mauvaise forme, exactement comme le serveur réel."""

        def __init__(self):
            self.appels = []

        def create_type(self, title, site_urls, description=""):
            assert isinstance(site_urls, list), (
                "« sites » doit être une LISTE pour un type")
            self.appels.append(("type", title, site_urls))

        def create_discipline(self, title, site_url="", description=""):
            assert isinstance(site_url, str), (
                "« site » doit être une CHAÎNE pour une discipline")
            self.appels.append(("discipline", title, site_url))

    def test_le_type_recoit_une_liste(self):
        api = self.FauxAPI()
        api.create_type("Colloque", ["https://exemple.invalid/rest/sites/1/"])
        assert api.appels[0][2] == ["https://exemple.invalid/rest/sites/1/"]

    def test_la_discipline_recoit_une_chaine(self):
        api = self.FauxAPI()
        api.create_discipline("Odontologie", "https://exemple.invalid/rest/sites/1/")
        assert isinstance(api.appels[0][2], str)

    def test_les_deux_formes_ne_sont_pas_interchangeables(self):
        """Le cœur du sujet : intervertir les deux formes doit échouer."""
        import pytest
        api = self.FauxAPI()
        with pytest.raises(AssertionError):
            api.create_type("X", "une chaîne au lieu d'une liste")
        with pytest.raises(AssertionError):
            api.create_discipline("Y", ["une liste au lieu d'une chaîne"])

    def test_les_deux_methodes_api_restent_distinctes(self):
        """Garde-fou sur la source : `create_type` doit envoyer « sites » et
        `create_discipline` « site ». Les confondre est invisible à la
        relecture, les deux mots ne différant que d'une lettre."""
        import inspect

        import pod_api
        source_type = inspect.getsource(pod_api.PodAPI.create_type)
        source_disc = inspect.getsource(pod_api.PodAPI.create_discipline)
        assert '"sites": list(site_urls)' in source_type, (
            "create_type doit envoyer « sites » sous forme de liste")
        assert '"site"' in source_disc and '"sites"' not in source_disc, (
            "create_discipline doit envoyer « site » au singulier")


class TestContrastesAccessibilite:
    """Toute teinte de texte doit atteindre 4,5:1 sur TOUTE l'échelle de
    surfaces, dans les DEUX modes (WCAG 2.1 niveau AA, texte normal).

    Ces teintes avaient été réglées quand le mode sombre était le seul
    disponible ; le volet clair en avait été déduit à l'œil. Mesure faite,
    cinq des sept étaient sous le seuil en clair — et trois l'étaient aussi en
    sombre, ce qu'un premier examen visuel n'avait pas vu.

    ⚠️ Le calcul porte sur le PIRE fond de l'échelle. Une première correction
    a été calculée en oubliant S_PUCE dans la liste : elle semblait suffisante
    (4,54) et plafonnait en réalité à 4,11. C'est précisément l'erreur que ce
    test empêche de reproduire — d'où le fait qu'il lise les surfaces depuis
    le module plutôt que de les recopier."""

    SEUIL = 4.5

    @staticmethod
    def _luminance(valeur: str) -> float:
        """Luminance relative WCAG d'une teinte « grayNN » ou « #rrggbb »."""
        def canal(c):
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        if valeur.startswith("gray"):
            return canal(int(valeur[4:]) / 100)
        h = valeur.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)

    @classmethod
    def _ratio(cls, a: str, b: str) -> float:
        la, lb = cls._luminance(a), cls._luminance(b)
        return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

    @staticmethod
    def _surfaces(indice: int):
        """Toutes les surfaces de l'échelle, lues DEPUIS le module.

        Les recopier ici reproduirait l'oubli d'origine : une surface ajoutée
        plus tard échapperait au test sans que personne ne s'en aperçoive."""
        import app as module_app
        noms = ("S_FOND", "S_BARRE", "S_CARTE", "S_LIGNE", "S_LIGNE_ALT",
                "S_PUCE")
        return {n: getattr(module_app, n)[indice] for n in noms
                if hasattr(module_app, n)}

    @staticmethod
    def _textes(indice: int):
        import app as module_app
        noms = ("T_SECONDAIRE", "T_DISCRET", "T_SUCCES", "T_ALERTE",
                "T_ERREUR", "T_CHAMP", "T_SUR_NEUTRE")
        return {n: getattr(module_app, n)[indice] for n in noms
                if hasattr(module_app, n)}

    def _verifier(self, indice: int, mode: str):
        surfaces = self._surfaces(indice)
        assert len(surfaces) >= 5, "l'échelle de surfaces n'a pas été lue"
        fautifs = []
        for nom_texte, teinte in self._textes(indice).items():
            for nom_fond, fond in surfaces.items():
                r = self._ratio(teinte, fond)
                if r < self.SEUIL:
                    fautifs.append(f"{nom_texte} sur {nom_fond} = {r:.2f}")
        assert not fautifs, (
            f"contrastes insuffisants en mode {mode} (seuil {self.SEUIL}) : "
            + " ; ".join(fautifs))

    def test_mode_clair(self):
        self._verifier(0, "clair")

    def test_mode_sombre(self):
        self._verifier(1, "sombre")

    def test_texte_blanc_sur_les_boutons_colores(self):
        """Les boutons d'action portent du texte blanc : eux aussi doivent
        atteindre le seuil."""
        import app as module_app
        fautifs = []
        for nom in ("C_ACTION", "C_SUCCES", "C_ALERTE", "C_DESTRUCTIF",
                    "C_ACCENT"):
            couple = getattr(module_app, nom, None)
            if couple is None:
                continue
            for i, mode in ((0, "clair"), (1, "sombre")):
                r = self._ratio(couple[i], "#ffffff")
                if r < self.SEUIL:
                    fautifs.append(f"{nom} ({mode}) = {r:.2f}")
        assert not fautifs, f"texte blanc illisible sur : {fautifs}"


class TestMessagesDErreur:
    """Une exception ne doit jamais être montrée telle quelle à l'utilisateur.

    Vingt endroits affichaient `f"❌  {e}"`. Un collègue du support pouvait
    lire « HTTPSConnectionPool(host=…): Max retries exceeded with url… », qui
    ne dit ni ce qui s'est passé, ni quoi faire.

    Le détail technique n'est pas perdu : il part au Journal. C'est justement
    ce que `_signaler` garantit — écran ET journal en un seul appel, pour
    qu'on ne puisse plus faire l'un sans l'autre."""

    def _traduire(self, e):
        import app as module_app
        return module_app.message_utilisateur(e)

    def _erreur_api(self, statut=0, corps="", message="erreur"):
        import pod_api
        return pod_api.PodAPIError(message, statut, corps)

    def test_les_codes_http_connus_sont_traduits(self):
        attendus = {401: "Jeton", 403: "Droits", 404: "introuvable",
                    409: "utilisé ailleurs", 500: "difficulté", 503: "difficulté"}
        for statut, extrait in attendus.items():
            texte = self._traduire(self._erreur_api(statut))
            assert extrait.lower() in texte.lower(), (
                f"HTTP {statut} mal traduit : {texte}")
            assert "HTTP" not in texte, (
                f"le code technique fuit dans le message : {texte}")

    def test_le_motif_dun_refus_est_extrait_du_json(self):
        """Django REST renvoie {"champ": ["motif"]} ; affiché brut, cela donne
        des accolades au milieu d'une phrase."""
        texte = self._traduire(self._erreur_api(
            400, '{"sites":["Ce champ est obligatoire."]}'))
        assert "Ce champ est obligatoire" in texte
        assert "{" not in texte and "[" not in texte, (
            f"le JSON brut apparaît encore : {texte}")

    def test_les_noms_techniques_de_django_sont_masques(self):
        """« detail » et « non_field_errors » n'apprennent rien à personne."""
        for corps in ('{"detail":"Non authentifié."}',
                      '{"non_field_errors":["Requête invalide."]}'):
            texte = self._traduire(self._erreur_api(400, corps))
            assert "detail" not in texte and "non_field" not in texte, texte

    def test_les_pannes_reseau_sont_reconnues(self):
        """Ce message-ci est celui que voyait l'utilisateur, en entier."""
        e = Exception("HTTPSConnectionPool(host='videos.utoulouse.fr', port=443): "
                      "Max retries exceeded with url: /rest/videos/")
        texte = self._traduire(e)
        assert "injoignable" in texte.lower()
        assert "HTTPSConnectionPool" not in texte

    def test_un_cas_inconnu_reste_honnete(self):
        """Faute de savoir, on renvoie vers le Journal plutôt que d'inventer
        une cause."""
        texte = self._traduire(ValueError("quelque chose d'inattendu"))
        assert "Journal" in texte
        assert "quelque chose d'inattendu" in texte

    def test_aucun_message_brut_ne_subsiste(self):
        """Garde-fou sur la source : c'est la forme exacte qui posait
        problème."""
        import app as module_app
        source = open(module_app.__file__.replace(".pyc", ".py"),
                      encoding="utf-8").read()
        assert 'text=f"❌  {e}"' not in source, (
            "une exception est encore affichée telle quelle")

    def test_signaler_journalise_le_detail(self):
        """Le détail technique doit rester disponible pour le support."""
        import inspect

        import app as module_app
        source = inspect.getsource(module_app.App._signaler)
        assert "self._log(" in source, (
            "`_signaler` n'écrit pas dans le Journal : le détail serait perdu")
        assert "body" in source, "le corps de la réponse n'est pas journalisé"


class TestBannieres:
    """Une bannière presque carrée occupe plus d'un écran de haut.

    Pod affiche la bannière d'une chaîne sur TOUTE LA LARGEUR, et pas seulement
    sur la page de la chaîne : elle apparaît au-dessus de CHAQUE vidéo. Un logo
    de 606×595 y occupe environ 1 178 px de haut sur un écran de 1200 — il faut
    faire défiler pour atteindre le lecteur. Le problème est connu du projet
    Esup-Pod, qui recommande d'orienter les propriétaires vers un format plus
    ergonomique."""

    def _image(self, taille, mode="RGB"):
        import tempfile
        from PIL import Image
        chemin = tempfile.mktemp(suffix=".png")
        couleur = 200 if mode == "L" else (255, 255, 255)
        Image.new(mode, taille, couleur).save(chemin)
        return chemin

    def test_le_chiffre_parlant_est_la_hauteur_a_l_ecran(self):
        """« 606×595 » n'alarme personne, « 1178 px de haut » si."""
        import app as module_app
        assert module_app.hauteur_affichee(606, 595) == 1178
        assert module_app.hauteur_affichee(1600, 400) == 300

    def test_l_adaptation_ramene_au_format_vise(self):
        import os
        import tempfile

        import app as module_app
        for taille in ((606, 595), (300, 900), (3000, 500), (20, 20)):
            src = self._image(taille)
            out = tempfile.mktemp(suffix=".jpg")
            try:
                assert module_app.adapter_en_banniere(src, out) == (
                    module_app.BANNIERE_LARGEUR, module_app.BANNIERE_HAUTEUR)
            finally:
                for f in (src, out):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

    def test_les_modes_exotiques_passent(self):
        """Niveaux de gris et transparence ne doivent pas faire échouer le
        dépôt : l'utilisateur choisit l'image qu'il a."""
        import os
        import tempfile

        import app as module_app
        for mode in ("L", "RGBA", "P"):
            src = self._image((400, 400), mode)
            out = tempfile.mktemp(suffix=".jpg")
            try:
                module_app.adapter_en_banniere(src, out)
                assert os.path.getsize(out) > 0
            finally:
                for f in (src, out):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

    def test_l_image_source_n_est_jamais_modifiee(self):
        """L'original de l'utilisateur doit être retrouvé intact."""
        import os

        import app as module_app
        src = self._image((606, 595))
        avant = open(src, "rb").read()
        out = src.replace(".png", "_out.jpg")
        try:
            module_app.adapter_en_banniere(src, out)
            assert open(src, "rb").read() == avant, "l'image source a été modifiée"
        finally:
            for f in (src, out):
                try:
                    os.remove(f)
                except Exception:
                    pass

    def test_le_seuil_epargne_les_images_deja_larges(self):
        """⚠️ Adapter une image DÉJÀ large la dégraderait : un 3000×500 passe
        de 200 px à 300 px de haut. Le seuil doit donc gouverner la
        proposition, pas seulement l'avertissement."""
        import app as module_app
        assert 3000 / 500 >= module_app.BANNIERE_RAPPORT_MINI
        assert 606 / 595 < module_app.BANNIERE_RAPPORT_MINI
        assert 300 / 900 < module_app.BANNIERE_RAPPORT_MINI

    def test_le_fichier_temporaire_est_nettoye(self):
        """Sans le `finally`, chaque dépôt laisserait un fichier derrière lui."""
        import inspect

        import app as module_app
        source = inspect.getsource(module_app.BannerPicker._deposer)
        assert "finally:" in source and "remove(temporaire)" in source, (
            "le fichier temporaire d'adaptation n'est pas supprimé")
        assert "mktemp" in source, (
            "l'adaptation doit écrire dans un fichier temporaire, jamais "
            "écraser l'original de l'utilisateur")
