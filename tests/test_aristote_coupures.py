"""Audit O1 : une coupure pendant l'attente ne fait plus échouer une demande.

Avant : une micro-coupure Wi-Fi ou un 502 de la passerelle d'ILaaS faisait
passer la demande en « échec » alors qu'Aristote continuait, et son identifiant
était perdu ; « Réessayer » renvoyait tout. Faux réseau en mémoire.
"""
import os
import sys
import threading
import time
from types import SimpleNamespace

import pytest
import requests

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from enrichissement import aristote_api as AA     # noqa: E402


class Reponse:
    def __init__(self, code=200, donnees=None):
        self.status_code, self._d, self.text = code, donnees or {}, ""

    def json(self):
        return self._d


class FauxReseau:
    """`suite` : réponses ou exceptions rendues, dans l'ordre, par les GET."""

    def __init__(self, suite):
        self.suite, self.get_appels, self.post_appels = list(suite), 0, 0
        self.headers = {}

    def post(self, url, **k):
        self.post_appels += 1
        if url.endswith("/token"):
            return Reponse(200, {"access_token": "j", "expires_in": 3600})
        raise requests.ConnectionError("coupure")

    def get(self, url, **k):
        self.get_appels += 1
        r = self.suite.pop(0) if self.suite else Reponse(200, {"status": "SUCCESS"})
        if isinstance(r, Exception):
            raise r
        return r


def client(suite):
    c = AA.AristoteAPI("id", "secret", "https://stt.exemple.fr/api")
    c.session = FauxReseau(suite)
    c.pauses_reprise = (0, 0)
    return c


COUPURE = requests.ConnectionError("Max retries exceeded")


class TestLecture:
    def test_reprises_par_defaut(self):
        """Le banc met les pauses à zéro : on vérifie ici celles du client réel.
        Au moins deux nouvelles tentatives, sans figer l'attente plus de 10 s."""
        pauses = AA.AristoteAPI("id", "secret").pauses_reprise
        assert len(pauses) >= 2 and sum(pauses) <= 10

    def test_lecture_reessayee_apres_coupure(self):
        c = client([COUPURE, Reponse(502), Reponse(200, {"status": "IN_PROGRESS"})])
        assert c.etat("e1")["status"] == "IN_PROGRESS"
        assert c.session.get_appels == 3

    def test_erreur_qui_dit_quelque_chose_non_reessayee(self):
        c = client([Reponse(404, {"errors": [{"message": "inconnu"}]})])
        with pytest.raises(AA.AristoteErreur) as e:
            c.etat("e1")
        assert c.session.get_appels == 1 and e.value.status == 404 and not AA.est_passagere(e.value)

    def test_un_envoi_n_est_jamais_rejoue(self, tmp_path):
        """Rejouer un POST créerait une seconde demande chez Aristote."""
        f = tmp_path / "a.vtt"
        f.write_text("WEBVTT\n", encoding="utf-8")
        c = client([])
        with pytest.raises(requests.ConnectionError):
            c.envoyer_fichier(str(f), "fr")
        assert c.session.post_appels == 2      # le jeton, puis UN envoi


class TestAttente:
    def test_panne_toleree_puis_reprise(self):
        etats = []
        c = client([Reponse(200, {"status": "IN_PROGRESS"}), COUPURE, COUPURE, COUPURE,
                    COUPURE, Reponse(503), Reponse(200, {"status": "SUCCESS"})])
        d = c.attendre("e1", intervalle=0, jusqu_au_bout=True, rappel=lambda s, _d: etats.append(s))
        assert d["status"] == "SUCCESS"
        assert "RECONNEXION" in etats and etats[-1] == "SUCCESS"

    def test_panne_trop_longue_erreur_passagere(self):
        c = client([COUPURE] * 1000)
        with pytest.raises(AA.AristoteErreur) as e:
            c.attendre("e1", intervalle=0.01, tolerance_panne=0.1)
        assert e.value.passagere and AA.est_passagere(e.value)
        assert "reprendra son suivi" in str(e.value)

    def test_echec_d_aristote_n_est_pas_une_panne(self):
        c = client([Reponse(200, {"status": "FAILURE", "failureCause": "fichier illisible"})])
        with pytest.raises(AA.AristoteErreur) as e:
            c.attendre("e1", intervalle=0)
        assert not AA.est_passagere(e.value) and "fichier illisible" in str(e.value)

    def test_panne_comptee_en_continu_seulement(self):
        """Des coupures espacées, entrecoupées de réponses, ne s'additionnent pas."""
        suite = []
        for _ in range(6):
            suite += [COUPURE] * 3 + [Reponse(200, {"status": "IN_PROGRESS"})]
        c = client(suite + [Reponse(200, {"status": "SUCCESS"})])
        c.pauses_reprise = ()                  # chaque coupure remonte jusqu'à attendre()
        debut = time.time()
        # Chaque épisode (3 coupures, ~0,06 s) reste sous la tolérance ; leur
        # total (~0,4 s) la dépasse largement.
        assert c.attendre("e1", intervalle=0.02, tolerance_panne=0.2, jusqu_au_bout=True)["status"] == "SUCCESS"
        assert time.time() - debut > 0.2, "le banc ne teste rien"


class TestDemandeReprenable:
    def test_reessayer_reprend_le_suivi_sans_nouvel_envoi(self, tmp_path, monkeypatch):
        from enrichissement import editeur, projet as pj
        monkeypatch.setattr(pj, "DOSSIER_PROJETS", str(tmp_path / "projets"))
        p = pj.nouveau(str(tmp_path / "c.mp4"), "fr")
        p["sous_titres"] = [{"start": 0, "end": 2, "text": "Bonjour."}]
        p["etat"] = "a_corriger"
        pj.enregistrer(p)
        envois, suivis, porte = [], [], threading.Event()

        class FauxAristote:
            def langues(self):
                return [{"code": "fr"}, {"code": "en"}]

            def enrichir_sous_titres(self, *a, **k):
                envois.append(k)
                return "e1"

            def attendre(self, eid, **k):
                suivis.append(eid)
                if len(suivis) == 1:
                    raise AA.AristoteErreur("Connexion à Aristote perdue", passagere=True)
                porte.set()
                return {"status": "SUCCESS"}

            def version_finale(self, eid):
                return {"enrichmentVersionMetadata": {"title": "T"}}

        srv = editeur.ServeurEditeur(client=lambda: FauxAristote())
        try:
            srv.lancer_demande(p["id"], "meta")
            fin = time.time() + 5
            while time.time() < fin and pj.etat_partie(pj.charger(p["id"]), "meta")["etat"] != "erreur":
                time.sleep(0.02)
            d = pj.enrichissement(pj.charger(p["id"]))["demandes"]["meta"]
            assert d["etat"] == "erreur" and d["reprenable"] is True
            srv.lancer_demande(p["id"], "meta")             # « Reprendre le suivi »
            assert porte.wait(5)
            fin = time.time() + 5
            while time.time() < fin and pj.etat_partie(pj.charger(p["id"]), "meta")["etat"] != "pret":
                time.sleep(0.02)
            assert pj.etat_partie(pj.charger(p["id"]), "meta")["etat"] == "pret"
            assert len(envois) == 1 and suivis == ["e1", "e1"], "la demande a été renvoyée"
        finally:
            srv.arreter()


class TestTranscription:
    def test_echec_passager_rend_la_transcription_reprenable(self, tmp_path, monkeypatch):
        import app as A
        from enrichissement import projet as pj
        monkeypatch.setattr(pj, "DOSSIER_PROJETS", str(tmp_path / "projets"))
        p = pj.nouveau(str(tmp_path / "c.mp4"), "fr")
        p.update(etat="attente", enrichment_id="t1", pod={"id": 7})
        evenements = []
        faux = SimpleNamespace(evenements=SimpleNamespace(put=evenements.append),
                               _signaler=lambda *a, **k: None, pid_courant=None,
                               hote=SimpleNamespace(_ui=lambda *a: None, _log=lambda *a: None))
        A.PanneauEnrichissement._echec(faux, p, AA.AristoteErreur("perdue", passagere=True))
        assert p["etat"] == "erreur" and p["reprenable"] is True
        cartes = A.cartes_ia(p, True)
        assert cartes["st"]["action"] == "reessayer_st" and cartes["st"]["libelle"] == "Reprendre le suivi"
        A.PanneauEnrichissement._echec(faux, p, AA.AristoteErreur("Aristote a échoué : illisible"))
        assert p["reprenable"] is False, "un vrai échec ne se reprend pas"



def test_aristote_voit_podadmin():
    """Audit O8 : nom vu dans les journaux d'ILaaS."""
    from __version__ import __version__
    assert AA.AristoteAPI("id", "s").session.headers["User-Agent"] == f"PodAdmin/{__version__}"
