"""Refonte 1.11.0, étape 2 : une demande Aristote par partie, côté serveur.

Le serveur de l'éditeur lance, suit et reprend des demandes SÉPARÉES
(« meta », « quiz », « trad:en »…). Faux Aristote en mémoire, dossier de
projets temporaire. Aucun réseau.
"""

import json
import os
import sys
import threading
import time
import urllib.request
from types import SimpleNamespace

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)


class FauxAristote:
    """Chaque demande attend qu'on la libère (`liberer`), puis renvoie ce
    qui a été demandé, et seulement cela (constat de la sonde)."""

    def __init__(self):
        self.envois, self.portes, self.echecs = [], {}, set()

    def langues(self):
        return [
            {"code": "fr", "name": "Français"},
            {"code": "en", "name": "Anglais"},
            {"code": "pt", "name": "Portugais"},
        ]

    def enrichir_sous_titres(
        self,
        vtt,
        nom,
        langue="fr",
        traduire_vers=None,
        metadonnees=True,
        quiz=True,
        disciplines=None,
        types_media=None,
    ):
        eid = f"e{len(self.envois) + 1}"
        self.envois.append(
            {
                "eid": eid,
                "traduire_vers": traduire_vers,
                "metadonnees": metadonnees,
                "quiz": quiz,
                "langue": langue,
                "vtt": vtt,
            }
        )
        self.portes[eid] = threading.Event()
        return eid

    def liberer(self, eid):
        self.portes.setdefault(eid, threading.Event()).set()

    def attendre(self, eid, rappel=None, **k):
        if rappel:
            rappel("IN_PROGRESS", {})
        if not self.portes.setdefault(eid, threading.Event()).wait(10):
            raise TimeoutError("porte jamais ouverte")
        if eid in self.echecs:
            raise ConnectionError("Max retries exceeded with url: /api/v1/enrichments")
        return {"status": "SUCCESS"}

    def version_finale(self, eid):
        e = next(
            (x for x in self.envois if x["eid"] == eid),
            {"traduire_vers": "en", "metadonnees": True, "quiz": True},
        )
        v = {"multipleChoiceQuestions": [], "enrichmentVersionMetadata": None, "transcript": {}}
        if e["metadonnees"]:
            v["enrichmentVersionMetadata"] = {
                "title": "Titre IA",
                "description": "D",
                "topics": ["néolithique"],
                "discipline": "Archéologie",
                "mediaType": "Cours",
            }
        if e["quiz"]:
            v["multipleChoiceQuestions"] = [
                {
                    "question": f"Question de la demande {eid} sur les toits ?",
                    "explanation": "",
                    "choices": [
                        {"optionText": "oui", "correctAnswer": True},
                        {"optionText": "non"},
                    ],
                }
            ]
        if e["traduire_vers"]:
            v["transcript"] = {
                "translatedSentences": [
                    {"start": 0, "end": 6, "text": "Hello everyone. We walk on the roofs."}
                ]
            }
        return v


@pytest.fixture
def banc(tmp_path, monkeypatch):
    import app as A
    from enrichissement import editeur, projet

    monkeypatch.setattr(projet, "DOSSIER_PROJETS", str(tmp_path / "projets"))
    p = projet.nouveau(str(tmp_path / "cours.mp4"), "fr")
    p["sous_titres"] = [
        {"start": 0, "end": 3, "text": "Bonjour à tous."},
        {"start": 3, "end": 6, "text": "On circule par les toits."},
    ]
    p["etat"] = "a_corriger"
    projet.enregistrer(p)
    aristote = FauxAristote()
    enregistres = []
    srv = editeur.ServeurEditeur(
        client=lambda: aristote,
        message_erreur=A.message_editeur,
        sur_enregistrement=enregistres.append,
    )
    yield SimpleNamespace(
        srv=srv, aristote=aristote, pid=p["id"], pj=projet, enregistres=enregistres, editeur=editeur
    )
    srv.arreter()


def attendre(condition, delai=5):
    fin = time.time() + delai
    while time.time() < fin:
        if condition():
            return True
        time.sleep(0.02)
    return False


def etat(banc, partie):
    return banc.pj.etat_partie(banc.pj.charger(banc.pid), partie)


class TestDemandesSeparees:
    def test_une_demande_par_partie_avec_un_seul_drapeau(self, banc):
        for cle in ("meta", "quiz", "trad:en"):
            banc.srv.lancer_demande(banc.pid, cle)
        envois = banc.aristote.envois
        assert [(e["metadonnees"], e["quiz"], e["traduire_vers"]) for e in envois] == [
            (True, False, None),
            (False, True, None),
            (False, False, "en"),
        ]
        assert all(e["langue"] == "fr" for e in envois)
        assert {etat(banc, c)["etat"] for c in ("meta", "quiz", "trad:en")} == {"en_cours"}
        for e in envois:
            banc.aristote.liberer(e["eid"])
        assert attendre(
            lambda: all(etat(banc, c)["etat"] == "pret" for c in ("meta", "quiz", "trad:en"))
        )
        e = banc.pj.enrichissement(banc.pj.charger(banc.pid))
        assert e["metadonnees"]["titre"] == "Titre IA" and len(e["quiz"]) == 1
        assert e["traductions"]["en"]

    def test_meme_partie_refusee_tant_qu_elle_est_chez_aristote(self, banc):
        banc.srv.lancer_demande(banc.pid, "quiz")
        with pytest.raises(ValueError, match="déjà chez Aristote"):
            banc.srv.lancer_demande(banc.pid, "quiz")
        banc.srv.lancer_demande(banc.pid, "meta")  # une AUTRE partie reste possible
        assert len(banc.aristote.envois) == 2

    def test_autres_questions_s_ajoutent(self, banc):
        banc.srv.lancer_demande(banc.pid, "quiz")
        banc.aristote.liberer("e1")
        assert attendre(lambda: etat(banc, "quiz")["etat"] == "pret")
        banc.srv.lancer_demande(banc.pid, "quiz")
        banc.aristote.liberer("e2")
        assert attendre(lambda: etat(banc, "quiz")["detail"].startswith("2 questions"))
        quiz = banc.pj.enrichissement(banc.pj.charger(banc.pid))["quiz"]
        assert [q["nouvelle"] for q in quiz] == [False, True]

    @pytest.mark.parametrize(
        "cle, motif",
        [
            ("trad:es", "ne traduit pas"),
            ("trad:fr", "ne traduit pas"),
            ("notes", "inconnue"),
            ("", "inconnue"),
        ],
    )
    def test_demandes_refusees(self, banc, cle, motif):
        with pytest.raises(ValueError, match=motif):
            banc.srv.lancer_demande(banc.pid, cle)
        assert banc.aristote.envois == []

    def test_sans_sous_titres(self, banc):
        p = banc.pj.charger(banc.pid)
        p["sous_titres"] = []
        banc.pj.enregistrer(p)
        with pytest.raises(ValueError, match="Pas encore de sous-titres"):
            banc.srv.lancer_demande(banc.pid, "meta")

    def test_echec_lisible_et_sans_effet_sur_les_autres(self, banc):
        banc.srv.lancer_demande(banc.pid, "meta")
        banc.srv.lancer_demande(banc.pid, "quiz")
        banc.aristote.echecs.add("e1")
        banc.aristote.liberer("e1")
        banc.aristote.liberer("e2")
        assert attendre(
            lambda: etat(banc, "meta")["etat"] == "erreur" and etat(banc, "quiz")["etat"] == "pret"
        )
        assert etat(banc, "meta")["detail"].startswith("Instance injoignable"), etat(banc, "meta")

    def test_corrections_faites_pendant_l_attente_preservees(self, banc):
        banc.srv.lancer_demande(banc.pid, "meta")
        with banc.srv.verrou:  # comme la page, qui passe par la route HTTP
            p = banc.pj.charger(banc.pid)
            p["sous_titres"][0]["text"] = "Bonjour à toutes et à tous."
            banc.pj.enregistrer(p)
        banc.aristote.liberer("e1")
        assert attendre(lambda: etat(banc, "meta")["etat"] == "pret")
        p = banc.pj.charger(banc.pid)
        assert p["sous_titres"][0]["text"] == "Bonjour à toutes et à tous."
        assert etat(banc, "meta")["perime"], "texte changé pendant la demande : à signaler"

    def test_ancienne_route_groupee_eclatee(self, banc):
        banc.srv.lancer_enrichissement(banc.pid, "pt", True, False)
        assert [
            (e["traduire_vers"], e["metadonnees"], e["quiz"]) for e in banc.aristote.envois
        ] == [("pt", False, False), (None, True, False)]


class TestEcrituresSimultanees:
    def test_plusieurs_fils_enregistrent_le_meme_projet(self, banc):
        """Avec un fichier temporaire commun, deux fils s'écrasaient
        mutuellement (FileNotFoundError, puis projet perdu). Puis, sous charge,
        une seconde de tentatives ne suffisait pas (« Accès refusé », audit O7)."""
        p = banc.pj.charger(banc.pid)
        p["mots"] = [["mot", 0, 1]] * 20000  # ~ une heure de vidéo
        banc.pj.enregistrer(p)
        erreurs = []

        def ecrire(n):
            try:
                for i in range(50):
                    p = banc.pj.charger(banc.pid)
                    p[f"fil{n}"] = i
                    banc.pj.enregistrer(p)
            except Exception as e:  # noqa: BLE001
                erreurs.append(repr(e))

        fils = [threading.Thread(target=ecrire, args=(n,)) for n in range(6)]
        for f in fils:
            f.start()
        for f in fils:
            f.join()
        assert erreurs == []
        assert banc.pj.charger(banc.pid)["id"] == banc.pid
        reste = [
            f
            for f in os.listdir(os.path.dirname(banc.pj.chemin_projet(banc.pid)))
            if f.endswith(".tmp")
        ]
        assert reste == [], "fichiers temporaires abandonnés"


class TestReprise:
    def test_demandes_reprises_apres_redemarrage(self, banc):
        # Demandes laissées sur disque par une session fermée : AUCUN fil ne
        # les suit plus (lancer_demande en aurait démarré un, qui masquait
        # une reprise incomplète).
        p = banc.pj.charger(banc.pid)
        for eid, cle, envoi in (
            ("e1", "meta", {"metadonnees": True, "quiz": False, "traduire_vers": None}),
            ("e2", "trad:pt", {"metadonnees": False, "quiz": False, "traduire_vers": "pt"}),
        ):
            banc.pj.nouvelle_demande(p, cle, eid, [cle], groupes=p["sous_titres"])
            banc.aristote.envois.append({"eid": eid, **envoi})
        banc.pj.enregistrer(p)
        autre = banc.editeur.ServeurEditeur(client=lambda: banc.aristote)
        try:
            assert autre.reprendre(banc.pid) == 2
            for eid in ("e1", "e2"):
                banc.aristote.liberer(eid)
            assert attendre(
                lambda: (
                    etat(banc, "meta")["etat"] == "pret" and etat(banc, "trad:pt")["etat"] == "pret"
                )
            )
        finally:
            autre.arreter()

    def test_ancienne_demande_groupee_reprise(self, banc):
        p = banc.pj.charger(banc.pid)
        p["enrichissement"] = {
            "etat": "en_cours",
            "eid": "vieux",
            "traduire_vers": "en",
            "groupes": [{"start": 0, "end": 6, "text": "Bonjour à tous. On circule…"}],
            "metadonnees": {},
            "quiz": [],
            "traductions": {},
        }
        banc.pj.enregistrer(p)
        assert banc.srv.reprendre(banc.pid) == 1
        banc.aristote.liberer("vieux")
        assert attendre(
            lambda: all(etat(banc, c)["etat"] == "pret" for c in ("meta", "quiz", "trad:en"))
        )

    def test_sans_identifiants_rien_n_est_repris(self, banc):
        banc.srv.lancer_demande(banc.pid, "meta")
        muet = banc.editeur.ServeurEditeur(client=lambda: None)
        try:
            assert muet.reprendre(banc.pid) == 0
        finally:
            muet.arreter()

    def test_l_onglet_reprend_les_demandes_par_partie(self, banc):
        """PanneauEnrichissement.reprendre_travaux lit les demandes séparées."""
        import app as A

        banc.srv.lancer_demande(banc.pid, "quiz")
        lignes, reprises = [], []
        faux = SimpleNamespace(
            journal=lignes.append,
            serveur=SimpleNamespace(reprendre=reprises.append),
            hote=SimpleNamespace(_run=lambda *a: None),
            _client=lambda: None,
            _maj_ligne=lambda p: None,
        )
        A.PanneauEnrichissement.reprendre_travaux(faux)
        assert reprises == [banc.pid]
        assert lignes == ["Reprise du suivi Aristote : cours.mp4 (quiz)"]


class TestVueEtRoutes:
    def _appel(self, banc, chemin, corps=None):
        url = f"http://127.0.0.1:{banc.srv.port}/api/{banc.pid}{chemin}?t={banc.srv.jeton}"
        data = None if corps is None else json.dumps(corps).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="GET" if corps is None else "POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_vue_d_ensemble_pour_la_page_actuelle(self, banc):
        banc.srv.lancer_demande(banc.pid, "meta")
        vue = banc.srv.vue_enrichissement(banc.pj.charger(banc.pid))
        assert vue["etat"] == "en_cours"
        assert set(vue["parties"]) == {"sous_titres", "meta", "quiz", "trad:en", "trad:pt"}

    def test_route_demander(self, banc):
        code, d = self._appel(banc, "/demander", {"cle": "trad:en"})
        assert code == 200 and d["parties"]["trad:en"]["etat"] == "en_cours"
        code, d = self._appel(banc, "/demander", {"cle": "trad:en"})
        assert code == 400 and "déjà chez Aristote" in d["erreur"]

    def test_route_relu(self, banc):
        code, d = self._appel(banc, "/relu", {})
        assert code == 200 and d["etat"] == "relu"
        assert banc.enregistres == [banc.pid], "l'onglet doit rafraîchir sa carte"

    def test_lecture_complete_contient_les_parties(self, banc):
        code, d = self._appel(banc, "")
        assert code == 200 and d["enrichissement"]["parties"]["sous_titres"]["etat"] == "a_relire"
