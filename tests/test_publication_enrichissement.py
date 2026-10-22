"""Intégration de SousTitreur, étape 5 : publication sur Pod depuis l'éditeur.

L'éditeur (enrichissement/editeur.py) publie avec le client Pod fusionné. On
vérifie ce que PodAdmin y raccorde : une ligne dans SON Journal pour chaque
écriture, des erreurs lisibles dans la page, la liste des vidéos tenue à jour.
Faux serveur Pod en mémoire (repris de test_pod_enrichissement) ; dossier
personnel temporaire (conftest.py). Aucun réseau.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_pod_enrichissement import BASE, VTT, FauxPod  # noqa: E402,F401


@pytest.fixture
def banc(tmp_path, monkeypatch):
    """Projet rattaché à la vidéo 202, client Pod sur faux serveur, éditeur."""
    import app as A
    from enrichissement import editeur, journal, projet
    from pod_api import PodAPI

    monkeypatch.setattr(projet, "DOSSIER_PROJETS", str(tmp_path / "projets"))
    monkeypatch.setattr(journal, "CHEMIN", str(tmp_path / "journal_pod.jsonl"))
    api = PodAPI(BASE, "jeton")
    api.session = FauxPod()
    v = api.session.video
    p = projet.nouveau_pod(v, "lien", "mp4", "Cédric", [], [], "fr")
    p["dossier"] = str(tmp_path / "exports")
    p["sous_titres"] = [{"start": 0, "end": 2, "text": "Bonjour à tous."}]
    p["etat"] = "corrige"
    projet.enregistrer(p)
    lignes, modifiees = [], []
    srv = editeur.ServeurEditeur(
        pod=lambda: api,
        message_erreur=A.message_editeur,
        journal_hote=lignes.append,
        sur_video_modifiee=modifiees.append,
    )
    yield SimpleNamespace(
        srv=srv,
        api=api,
        pid=p["id"],
        lignes=lignes,
        modifiees=modifiees,
        jsonl=tmp_path / "journal_pod.jsonl",
    )
    srv.arreter()


class TestPublicationDesPistes:
    def test_ajout_journalise_des_deux_cotes(self, banc):
        r = banc.srv.publier_pod(
            banc.pid, [{"source": "original", "lang": "en", "kind": "subtitles"}]
        )
        assert r[0]["ok"] and r[0]["lang"] == "fr", "la correction va TOUJOURS en « fr »"
        assert len(banc.lignes) == 1 and "sous-titres « fr » ajoutés" in banc.lignes[0]
        assert "n° 202" in banc.lignes[0]
        noter = [json.loads(l) for l in banc.jsonl.read_text(encoding="utf-8").splitlines()]
        assert noter[-1]["action"] == "piste_ajoutee"

    def test_refus_lisible_dans_la_page_et_detaille_au_journal(self, banc):
        banc.api.session.ajouter_piste(
            "fr", "subtitles"
        )  # piste déjà là, pas de remplacement demandé
        r = banc.srv.publier_pod(banc.pid, [{"source": "original", "kind": "subtitles"}])
        assert not r[0]["ok"]
        assert r[0]["erreur"].startswith("Les pistes « fr / subtitles » ont changé"), r[0]["erreur"]
        assert "refusée" in banc.lignes[0] and "PodAPIError" in banc.lignes[0]

    def test_coupure_reseau_traduite(self, banc, monkeypatch):
        def coupure(*a, **k):
            raise ConnectionError("Max retries exceeded with url: /rest/files/")

        monkeypatch.setattr(banc.api, "upload_subtitle_file", coupure)
        r = banc.srv.publier_pod(banc.pid, [{"source": "original", "kind": "subtitles"}])
        assert r[0]["erreur"].startswith("Instance injoignable"), r[0]["erreur"]


class TestMarquagePublie:
    """Refonte 1.11.0 : une publication réussie fait passer la partie à
    « fait » ; un refus ne la marque pas."""

    def test_sous_titres_publies(self, banc):
        from enrichissement import projet

        banc.srv.publier_pod(banc.pid, [{"source": "original", "kind": "subtitles"}])
        assert projet.etat_partie(projet.charger(banc.pid), "sous_titres")["etat"] == "fait"

    def test_refus_non_marque(self, banc):
        from enrichissement import projet

        banc.api.session.ajouter_piste("fr", "subtitles")
        banc.srv.publier_pod(banc.pid, [{"source": "original", "kind": "subtitles"}])
        assert projet.etat_partie(projet.charger(banc.pid), "sous_titres")["etat"] != "fait"

    def test_metadonnees_publiees(self, banc):
        from enrichissement import projet

        p = projet.charger(banc.pid)
        projet.enrichissement(p)["metadonnees"] = {"titre": "Nouveau titre"}
        projet.enregistrer(p)
        avant = banc.srv.metadonnees_pod(banc.pid)["pod"]
        banc.srv.publier_metadonnees(banc.pid, avant, {"titre": "Nouveau titre"})
        assert projet.etat_partie(projet.charger(banc.pid), "meta")["etat"] == "fait"


class TestPublicationDesMetadonnees:
    def test_journal_et_liste_des_videos_mis_a_jour(self, banc):
        avant = banc.srv.metadonnees_pod(banc.pid)["pod"]
        banc.srv.publier_metadonnees(
            banc.pid, avant, {"titre": "Nouveau titre", "ajout_discipline": "Archéologie"}
        )
        assert "métadonnées modifiées sur Pod (titre, discipline ajoutée)" in banc.lignes[-1]
        assert banc.modifiees and banc.modifiees[0]["title"] == "Nouveau titre"

    def test_refus_journalise_puis_relaye(self, banc):
        avant = banc.srv.metadonnees_pod(banc.pid)["pod"]
        banc.api.session.video["title"] = "Changé entre-temps"
        with pytest.raises(Exception):
            banc.srv.publier_metadonnees(banc.pid, avant, {"titre": "Mon titre"})
        assert "non modifiées" in banc.lignes[-1] and not banc.modifiees

    def test_l_onglet_videos_recoit_la_modification(self):
        """Le raccordement passe par `_sync_video_caches`, point d'accroche
        unique des modifications de vidéos dans PodAdmin."""
        import app as A

        recues = []
        hote = SimpleNamespace(
            _sync_video_caches=lambda slug, payload: recues.append((slug, payload))
        )
        A.PanneauEnrichissement._video_modifiee(
            SimpleNamespace(hote=hote),
            {"slug": "0202-x", "title": "T", "tags": "a b", "url": "u", "owner": "o"},
        )
        assert recues == [("0202-x", {"title": "T", "tags": "a b"})]


class TestRoutesHTTP:
    def _post(self, banc, chemin, corps):
        url = f"http://127.0.0.1:{banc.srv.port}/api/{banc.pid}/{chemin}?t={banc.srv.jeton}"
        req = urllib.request.Request(
            url,
            data=json.dumps(corps).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_non_connecte_message_clair(self, banc):
        banc.srv.pod = lambda: None
        code, d = self._post(banc, "pod/publier", {"pistes": []})
        assert code == 400 and d["erreur"].startswith("PodAdmin n'est pas connecté"), d

    def test_refus_http_traduit(self, banc, monkeypatch):
        from pod_api import PodAPIError

        def refus(*a, **k):
            raise PodAPIError("HTTP 403 sur https://videos.exemple.fr/rest/videos/202/", status=403)

        monkeypatch.setattr(banc.api, "video", refus)
        code, d = self._post(banc, "pod/metadonnees", {"avant": {}, "nouveau": {"titre": "x"}})
        assert code == 400 and d["erreur"].startswith("Droits insuffisants"), d
        assert "https://" not in d["erreur"]


class TestMessageEditeur:
    def test_messages_ecrits_pour_l_utilisateur_conserves(self):
        import app as A
        from pod_api import PodAPIError

        assert A.message_editeur(ValueError("langue invalide")) == "langue invalide"
        assert (
            A.message_editeur(A.AristoteErreur("Aristote a échoué : x")) == "Aristote a échoué : x"
        )
        assert A.message_editeur(PodAPIError("Les pistes ont changé")) == "Les pistes ont changé"

    def test_codes_http_traduits(self):
        import app as A
        from pod_api import PodAPIError

        assert A.message_editeur(PodAPIError("HTTP 401 sur u", status=401)).startswith(
            "Jeton refusé"
        )
