"""Refonte 1.11.0, étape 4 : la logique des trois cartes de l'onglet.

`cartes_ia` est une fonction pure : chaque état d'un projet donne, pour
chaque carte, une pastille, un texte et UNE action dont le libellé suit
l'état. Testée sans fenêtre.
"""
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import app as A                                   # noqa: E402
from enrichissement import projet as pj           # noqa: E402

PRM = pj.st.Parametres()


def projet(pod=True, etat="a_corriger"):
    p = pj.nouveau("cours.mp4", "fr")
    p["etat"] = etat
    if etat in ("a_corriger", "corrige"):
        p["sous_titres"] = [{"start": 0, "end": 2, "text": "Bonjour à tous."}]
    if pod:
        p["pod"] = {"id": 202, "titre": "Cours"}
    return p


def actions(c):
    return {n: c[n]["action"] for n in ("st", "meta", "quiz")}


class TestVideoSansProjet:
    def test_transcrire_ou_partir_de_pod(self):
        c = A.cartes_ia(None, True, ["fr"])
        assert actions(c) == {"st": "transcrire", "meta": "demander_meta", "quiz": "demander_quiz"}
        assert c["st"]["action2"] == "depuis_piste" and "fr" in c["st"]["detail"]
        assert "transcrira d'abord" in c["meta"]["detail"]
        assert A.carte_principale_ia(c) == "st"

    def test_sans_piste_sur_pod(self):
        assert A.cartes_ia(None, True, [])["st"]["action2"] == ""


class TestTranscription:
    def test_en_cours_rien_a_cliquer_sauf_enchainer(self):
        p = projet(etat="attente")
        c = A.cartes_ia(p, True)
        assert c["st"]["action"] == "" and c["st"]["teinte"] == "cours"
        assert c["meta"]["action"] == "enchainer_meta"
        p["a_enchainer"] = ["meta"]
        c = A.cartes_ia(p, True)
        assert c["meta"]["action"] == "" and c["meta"]["pastille"] == "demandé après la transcription"
        assert c["quiz"]["action"] == "enchainer_quiz"

    def test_echec(self):
        p = projet(etat="erreur")
        p["erreur"] = "Aristote a échoué"
        c = A.cartes_ia(p, True)
        assert c["st"]["action"] == "reessayer_st" and c["st"]["detail"] == "Aristote a échoué"
        assert c["meta"]["action"] == "" and "d'abord des sous-titres" in c["meta"]["detail"]
        assert A.carte_principale_ia(c) == "st"


class TestParcours:
    def test_a_relire_puis_relu(self):
        p = projet()
        c = A.cartes_ia(p, True)
        assert c["st"]["action"] == "relire_st" and c["st"]["pastille"] == "à relire"
        assert A.carte_principale_ia(c) == "st"
        pj.marquer_relu(p)
        c = A.cartes_ia(p, True)
        assert c["st"]["action"] == "ouvrir_st" and c["st"]["teinte"] == "ok"
        assert A.carte_principale_ia(c) == "meta", "étape suivante : les métadonnées"

    def test_demande_en_cours_puis_resultat_a_relire(self):
        p = projet()
        pj.marquer_relu(p)
        pj.nouvelle_demande(p, "meta", "e1", ["meta"])
        c = A.cartes_ia(p, True)
        assert c["meta"]["action"] == "" and c["meta"]["teinte"] == "cours"
        pj.appliquer_demande(p, "meta", {"enrichmentVersionMetadata": {"title": "T"}}, PRM)
        c = A.cartes_ia(p, True)
        assert c["meta"]["action"] == "relire_meta" and c["meta"]["libelle"] == "Relire et publier…"
        assert A.carte_principale_ia(c) == "meta"
        pj.marquer_fait(p, "meta")
        c = A.cartes_ia(p, True)
        assert c["meta"]["action"] == "ouvrir_meta" and c["meta"]["pastille"] == "publiées"

    def test_perime_signale(self):
        p = projet()
        pj.nouvelle_demande(p, "meta", "e1", ["meta"])
        pj.appliquer_demande(p, "meta", {"enrichmentVersionMetadata": {"title": "T"}}, PRM)
        pj.marquer_fait(p, "meta")
        p["sous_titres"][0]["text"] = "Bonjour à toutes et à tous."
        c = A.cartes_ia(p, True)
        assert c["meta"]["teinte"] == "alerte" and "à revoir" in c["meta"]["pastille"]

    def test_quiz_compte_et_autres_questions(self):
        p = projet()
        pj.nouvelle_demande(p, "quiz", "e1", ["quiz"])
        pj.appliquer_demande(p, "quiz", {"multipleChoiceQuestions": [
            {"question": "Q ?", "choices": [{"optionText": "a", "correctAnswer": True}]}]}, PRM)
        c = A.cartes_ia(p, True)
        assert c["quiz"]["pastille"] == "1 question, 1 retenue"
        assert c["quiz"]["action2"] == "demander_quiz"

    def test_traductions_resumees(self):
        p = projet()
        pj.nouvelle_demande(p, "trad:en", "e1", ["trad:en"], groupes=p["sous_titres"])
        pj.appliquer_demande(p, "trad:en", {"transcript": {"translatedSentences": [
            {"start": 0, "end": 2, "text": "Hello everyone."}]}}, PRM)
        pj.nouvelle_demande(p, "trad:pt", "e2", ["trad:pt"])
        assert "anglais (prête), portugais (en cours)" in A.cartes_ia(p, True)["st"]["detail"]


class TestVideoDuPoste:
    def test_metadonnees_apres_association(self):
        c = A.cartes_ia(projet(pod=False), False)
        assert c["meta"]["action"] == "associer"
        assert c["meta"]["pastille"] == "disponible une fois la vidéo sur Pod"
        assert c["quiz"]["action"] == "demander_quiz", "le quiz, lui, reste possible"


class TestUnSeulBoutonColore:
    def test_rien_a_recommander(self):
        p = projet()
        pj.marquer_relu(p)
        for cle in ("meta", "quiz"):
            pj.nouvelle_demande(p, cle, cle, [cle])
        assert A.carte_principale_ia(A.cartes_ia(p, True)) == ""


class TestBoutonEnrichirDansVideos:
    def test_present_dans_le_detail_et_neutre(self):
        """Raccourci de l'onglet Vidéos vers l'onglet Enrichissement IA
        (décision de Cédric) : neutre, ce n'est pas l'action de l'écran."""
        import ast
        src = open(os.path.join(RACINE, "app.py"), encoding="utf-8").read()
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "_browse_construire_detail")
        bouton = next(n for n in ast.walk(fn) if isinstance(n, ast.Call)
                      and any(k.arg == "text" and isinstance(k.value, ast.Constant)
                              and "Enrichir" in str(k.value.value) for k in n.keywords))
        code = ast.unparse(bouton)
        assert "_enrichir_video" in code and "fg_color=C_NEUTRE" in code, code
