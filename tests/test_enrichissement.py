"""Tests de l'enrichissement : traduction, quiz Moodle (sans réseau)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from enrichissement import projet as pj                                              # noqa: E402
from enrichissement import sous_titres as st                                         # noqa: E402


class TestTraduction(unittest.TestCase):
    def test_regroupement_en_phrases(self):
        sts = [st.SousTitre(0, 2, "Aujourd'hui, nous allons"),
               st.SousTitre(2.1, 4, "voir ensemble\ncomment faire."),
               st.SousTitre(4.5, 6, "Très bien.")]
        g = st.regrouper_phrases(sts)
        self.assertEqual([x.texte for x in g],
                         ["Aujourd'hui, nous allons voir ensemble comment faire.", "Très bien."])
        self.assertEqual((g[0].debut, g[0].fin), (0, 4))

    def test_traduction_redecoupee_aux_normes(self):
        groupes = [st.SousTitre(0, 9, "x"), st.SousTitre(10, 12, "y")]
        textes = ["Today we are going to see together how to organise the different "
                  "stages of an educational project, from needs analysis to final evaluation.",
                  "Very good."]
        sts = st.decouper_traduction(groupes, textes, st.Parametres())
        self.assertGreater(len(sts), 2)
        for s in sts:
            for l in s.texte.split("\n"):
                self.assertLessEqual(len(l), 42, l)
        self.assertEqual(sts[-1].texte, "Very good.")
        self.assertGreaterEqual(sts[-1].debut, 10)

    def test_application_au_projet(self):
        p = pj.nouveau("video.mp4", "fr")
        p["sous_titres"] = [{"start": 0, "end": 3, "text": "Bonjour à tous."}]
        e = pj.enrichissement(p)
        e["groupes"] = [{"start": 0, "end": 3, "text": "Bonjour à tous."}]
        version = {
            "enrichmentVersionMetadata": {"title": "T", "description": "D",
                                          "topics": ["a", "b"], "discipline": "Arts"},
            "multipleChoiceQuestions": [{"question": "Q ?", "explanation": "E",
                                         "choices": [{"optionText": "oui", "correctAnswer": True},
                                                     {"optionText": "non"}]}],
            "transcript": {"translatedSentences": [{"start": 0, "end": 3, "text": "Hello everyone."}]},
        }
        pj.appliquer_enrichissement(p, version, "en", st.Parametres())
        self.assertEqual(e["metadonnees"]["mots_cles"], ["a", "b"])
        self.assertEqual(e["quiz"][0]["choix"][0], {"texte": "oui", "correct": True})
        self.assertEqual(e["traductions"]["en"][0]["text"], "Hello everyone.")
        self.assertEqual(e["etat"], "termine")


class TestGift(unittest.TestCase):
    def test_format_et_echappement(self):
        quiz = [{"question": "Combien font 2+2 = ?", "explication": "Voir {cours}.",
                 "choix": [{"texte": "4", "correct": True}, {"texte": "5 ~ 6", "correct": False}]}]
        g = pj.quiz_vers_gift(quiz, "Mon cours")
        self.assertIn("$CATEGORY: $course$/Mon cours", g)
        self.assertIn(r"::Q1:: Combien font 2+2 \= ? {", g)
        self.assertIn("\t=4", g)
        self.assertIn(r"	~5 \~ 6", g)
        self.assertIn(r"####Voir \{cours\}.", g)
        self.assertTrue(g.rstrip().endswith("}"))

    def test_question_vide_ignoree(self):
        self.assertEqual(pj.quiz_vers_gift([{"question": "", "choix": []}]).strip(), "")


if __name__ == "__main__":
    unittest.main()
