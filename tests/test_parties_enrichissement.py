"""Refonte 1.11.0, étape 1 : un état par partie dans le projet.

Une demande Aristote par partie (traduction par langue, métadonnées, quiz),
détection des contenus périmés, quiz avec origine / questions retenues /
doublons, export GIFT lisible dans la banque Moodle. Sans réseau ni disque.
"""

import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from enrichissement import projet as pj  # noqa: E402
from enrichissement import sous_titres as st  # noqa: E402

PARAMS = st.Parametres()


def projet():
    p = pj.nouveau("cours.mp4", "fr")
    p["sous_titres"] = [
        {"start": 0, "end": 3, "text": "Bonjour à tous."},
        {"start": 3, "end": 6, "text": "On circule par les toits."},
    ]
    p["etat"] = "a_corriger"
    return p


def version_quiz(*questions):
    return {
        "multipleChoiceQuestions": [
            {
                "question": q,
                "explanation": "E",
                "choices": [{"optionText": "oui", "correctAnswer": True}, {"optionText": "non"}],
            }
            for q in questions
        ]
    }


VERSION_META = {
    "enrichmentVersionMetadata": {
        "title": "T",
        "description": "D",
        "topics": ["a"],
        "discipline": "Archéologie",
        "mediaType": "Cours",
    }
}
VERSION_TRAD = {
    "transcript": {
        "translatedSentences": [
            {"start": 0, "end": 3, "text": "Hello everyone."},
            {"start": 3, "end": 6, "text": "We walk on the roofs."},
        ]
    }
}


class TestDemandesSeparees:
    def test_chaque_demande_ne_touche_que_sa_partie(self):
        p = projet()
        pj.nouvelle_demande(p, "meta", "e1", ["meta"])
        pj.nouvelle_demande(p, "trad:en", "e2", ["trad:en"], groupes=p["sous_titres"])
        assert pj.etat_partie(p, "meta")["etat"] == "en_cours"
        assert pj.etat_partie(p, "quiz")["etat"] == "vide"
        pj.appliquer_demande(p, "meta", VERSION_META, PARAMS)
        assert pj.etat_partie(p, "meta")["etat"] == "pret"
        assert pj.etat_partie(p, "trad:en")["etat"] == "en_cours", "une autre demande a été close"
        pj.appliquer_demande(p, "trad:en", VERSION_TRAD, PARAMS)
        e = pj.enrichissement(p)
        assert e["traductions"]["en"][0]["text"] == "Hello everyone."
        assert e["metadonnees"]["discipline"] == "Archéologie"
        assert [d["cle"] for d in pj.demandes_en_cours(p)] == []

    def test_reponse_vide_dite_en_clair(self):
        p = projet()
        pj.nouvelle_demande(p, "quiz", "e1", ["quiz"])
        pj.appliquer_demande(p, "quiz", {"multipleChoiceQuestions": []}, PARAMS)
        etat = pj.etat_partie(p, "quiz")
        assert etat["etat"] == "vide" and "rien" in etat["detail"]

    def test_echec_garde_le_contenu_precedent(self):
        p = projet()
        pj.nouvelle_demande(p, "meta", "e1", ["meta"])
        pj.appliquer_demande(p, "meta", VERSION_META, PARAMS)
        pj.nouvelle_demande(p, "meta", "e2", ["meta"])
        pj.echec_demande(p, "meta", "Aristote a échoué : délai")
        etat = pj.etat_partie(p, "meta")
        assert etat["etat"] == "pret" and "délai" in etat["detail"]
        assert pj.enrichissement(p)["metadonnees"]["titre"] == "T"

    def test_echec_sans_contenu(self):
        p = projet()
        pj.nouvelle_demande(p, "quiz", "e1", ["quiz"])
        pj.echec_demande(p, "quiz", "refus")
        assert pj.etat_partie(p, "quiz") == {"etat": "erreur", "detail": "refus", "perime": False}


class TestPerime:
    def test_sous_titres_modifies_apres_la_demande(self):
        p = projet()
        pj.nouvelle_demande(p, "trad:en", "e1", ["trad:en"], groupes=p["sous_titres"])
        pj.appliquer_demande(p, "trad:en", VERSION_TRAD, PARAMS)
        assert not pj.etat_partie(p, "trad:en")["perime"]
        p["sous_titres"][1]["text"] = "On circulait par les toits."
        assert pj.etat_partie(p, "trad:en")["perime"]

    def test_minutage_compte_aussi(self):
        p = projet()
        pj.nouvelle_demande(p, "meta", "e1", ["meta"])
        pj.appliquer_demande(p, "meta", VERSION_META, PARAMS)
        p["sous_titres"][0]["end"] = 2.5
        assert pj.etat_partie(p, "meta")["perime"]

    def test_nouveau_contenu_annule_la_publication(self):
        p = projet()
        pj.nouvelle_demande(p, "meta", "e1", ["meta"])
        pj.appliquer_demande(p, "meta", VERSION_META, PARAMS)
        pj.marquer_fait(p, "meta")
        assert pj.etat_partie(p, "meta")["etat"] == "fait"
        pj.nouvelle_demande(p, "meta", "e2", ["meta"])
        pj.appliquer_demande(p, "meta", VERSION_META, PARAMS)
        assert pj.etat_partie(p, "meta")["etat"] == "pret"


class TestSousTitres:
    def test_cycle(self):
        p = pj.nouveau("cours.mp4", "fr")
        assert pj.etat_partie(p, "sous_titres")["etat"] == "en_cours"
        p.update(projet())
        assert pj.etat_partie(p, "sous_titres")["etat"] == "a_relire"
        pj.marquer_relu(p)
        assert pj.etat_partie(p, "sous_titres") == {"etat": "relu", "detail": "", "perime": False}
        p["sous_titres"][0]["text"] = "Bonjour."
        assert pj.etat_partie(p, "sous_titres")["detail"] == "modifiés depuis la relecture"
        pj.marquer_fait(p, "sous_titres")
        assert pj.etat_partie(p, "sous_titres")["etat"] == "fait"

    def test_corrige_ne_veut_pas_dire_relu(self):
        """« corrige » = exporté une fois (SousTitreur), pas relu."""
        p = projet()
        p["etat"] = "corrige"
        assert pj.etat_partie(p, "sous_titres")["etat"] == "a_relire"


class TestMigration:
    def test_ancienne_demande_groupee_en_cours(self):
        p = projet()
        p["enrichissement"] = {
            "etat": "en_cours",
            "eid": "vieux",
            "traduire_vers": "en",
            "groupes": p["sous_titres"],
            "metadonnees": {},
            "quiz": [],
            "traductions": {},
        }
        e = pj.enrichissement(p)
        d = e["demandes"]["groupe"]
        assert d["eid"] == "vieux" and d["etat"] == "en_cours"
        assert set(d["parties"]) == {"meta", "quiz", "trad:en"}
        assert [x["eid"] for x in pj.demandes_en_cours(p)] == ["vieux"]
        for partie in ("meta", "quiz", "trad:en"):
            assert pj.etat_partie(p, partie)["etat"] == "en_cours"
        pj.appliquer_demande(
            p, "groupe", {**VERSION_META, **version_quiz("Q ?"), **VERSION_TRAD}, PARAMS
        )
        assert pj.etat_partie(p, "trad:en")["etat"] == "pret"
        assert pj.etat_partie(p, "quiz")["detail"] == "1 question, 1 retenue"

    def test_contenu_ancien_conserve_et_jamais_perime(self):
        p = projet()
        p["enrichissement"] = {
            "etat": "termine",
            "eid": "vieux",
            "traduire_vers": "",
            "metadonnees": {"titre": "Ancien"},
            "traductions": {},
            "quiz": [{"question": "Q ?", "choix": [{"texte": "a", "correct": True}]}],
        }
        e = pj.enrichissement(p)
        assert e["quiz"][0]["origine"] == "ia" and e["quiz"][0]["retenue"] is True
        assert pj.etat_partie(p, "meta") == {"etat": "pret", "detail": "", "perime": False}


class TestQuiz:
    def test_les_questions_s_ajoutent_sans_effacer(self):
        p = projet()
        e = pj.enrichissement(p)
        e["quiz"].append({**pj.question_redigee(), "question": "Ma question ?"})
        pj.nouvelle_demande(p, "quiz", "e1", ["quiz"])
        pj.appliquer_demande(
            p, "quiz", version_quiz("Vers quelle date apparaissent les villes ?"), PARAMS
        )
        assert [q["origine"] for q in e["quiz"]] == ["redigee", "ia"]
        assert e["quiz"][1]["nouvelle"] is True

    def test_premier_quiz_sans_marque_nouvelle(self):
        p = projet()
        pj.nouvelle_demande(p, "quiz", "e1", ["quiz"])
        pj.appliquer_demande(p, "quiz", version_quiz("A ?", "B, une autre idée ?"), PARAMS)
        assert not any(q["nouvelle"] for q in pj.enrichissement(p)["quiz"])

    def test_doublon_reformule_arrive_decoche(self):
        """Cas réel de la sonde : même question, un verbe changé."""
        e = pj.enrichissement(projet())
        pj.ajouter_questions(
            e,
            _questions(
                "Quelle était la principale façon de se déplacer dans l’agglomération "
                "néolithique de Çatal Höyük ?"
            ),
        )
        pj.ajouter_questions(
            e,
            _questions(
                "Quelle était la principale façon de circuler dans l'agglomération de "
                "Çatal Höyük au Néolithique ?",
                "En quelle année la première ville apparaît-elle en Mésopotamie ?",
            ),
        )
        assert (e["quiz"][1]["retenue"], e["quiz"][1]["ressemble_a"]) == (False, 1)
        assert (e["quiz"][2]["retenue"], e["quiz"][2]["ressemble_a"]) == (True, 0)

    def test_question_redigee_modele(self):
        q = pj.question_redigee()
        assert q["origine"] == "redigee" and q["retenue"]
        assert [c["correct"] for c in q["choix"]] == [True, False]


def _questions(*textes):
    return pj._questions(version_quiz(*textes))


class TestGift:
    def test_seules_les_retenues_partent_numerotees_sans_trou(self):
        quiz = [
            {"question": "Première ?", "choix": [{"texte": "a", "correct": True}]},
            {"question": "Écartée ?", "retenue": False, "choix": [{"texte": "b", "correct": True}]},
            {"question": "Troisième ?", "choix": [{"texte": "c", "correct": True}]},
        ]
        g = pj.quiz_vers_gift(quiz, "Les métropoles du Néolithique")
        assert "Écartée" not in g
        assert "::Les métropoles du Néolithique 01, Première ?::" in g
        assert "::Les métropoles du Néolithique 02, Troisième ?::" in g

    def test_nom_coupe_sur_un_mot_et_echappe(self):
        q = {
            "question": "Vrai ou faux : à Çatal Höyük, on circulait principalement "
            "par les toits plutôt que par les rues ?",
            "choix": [{"texte": "a", "correct": True}],
        }
        g = pj.quiz_vers_gift([q], "Cours")
        nom = re.search(r"^::(.*?[^\\])::", g, re.M).group(1)
        assert nom.endswith("…") and r"Vrai ou faux \: à" in nom
        assert len(nom) < 80

    def test_export_nomme_d_apres_la_video_pas_d_apres_l_ia(self, tmp_path):
        p = projet()
        p["pod"] = {"titre": "Les métropoles du Néolithique"}
        e = pj.enrichissement(p)
        e["metadonnees"] = {"titre": "Titre proposé par Aristote"}
        e["quiz"] = [
            pj._completer_question({"question": "Q ?", "choix": [{"texte": "a", "correct": True}]})
        ]
        (chemin,) = pj.exporter(p, [], dossier=str(tmp_path), quiz=True)[-1:]
        texte = open(chemin, encoding="utf-8").read()
        assert "$CATEGORY: $course$/Les métropoles du Néolithique" in texte
        assert "Aristote" not in texte
        assert pj.etat_partie(p, "quiz")["etat"] == "fait"


class TestVerrouFichiers:
    """Audit O7 : sous Windows, remplacer un fichier qu'un autre fil lit
    échoue. Lecture et remplacement se font sous le même verrou (contrôle
    déterministe ; la charge à six fils est dans test_demandes_editeur)."""

    def test_lecture_et_remplacement_sous_verrou(self, tmp_path, monkeypatch):
        import builtins

        monkeypatch.setattr(pj, "DOSSIER_PROJETS", str(tmp_path))
        constats = []
        vrai_open, vrai_replace = builtins.open, pj.os.replace

        def ouvrir(chemin, mode="r", *a, **k):
            if str(chemin).endswith(".json") and "r" in mode:
                constats.append(("lecture", pj._VERROU_FICHIERS.locked()))
            return vrai_open(chemin, mode, *a, **k)

        def remplacer(src, dst):
            constats.append(("remplacement", pj._VERROU_FICHIERS.locked()))
            return vrai_replace(src, dst)

        monkeypatch.setattr(pj, "open", ouvrir, raising=False)
        monkeypatch.setattr(pj.os, "replace", remplacer)
        p = projet()
        pj.enregistrer(p)
        pj.charger(p["id"])
        assert constats == [("remplacement", True), ("lecture", True)], constats
        assert not pj._VERROU_FICHIERS.locked(), "verrou resté pris"


class TestPhrasesOubliees:
    """Audit O5 : les phrases envoyées ne restent pas dans le projet."""

    def test_videes_une_fois_le_resultat_range(self):
        p = projet()
        pj.nouvelle_demande(p, "trad:en", "e1", ["trad:en"], groupes=p["sous_titres"])
        assert pj.enrichissement(p)["demandes"]["trad:en"]["groupes"]
        pj.appliquer_demande(p, "trad:en", VERSION_TRAD, PARAMS)
        # Dictionnaire BRUT : enrichissement() nettoie aussi à la lecture, ce qui
        # masquerait un oubli dans appliquer_demande.
        assert p["enrichissement"]["demandes"]["trad:en"]["groupes"] == []
        assert p["enrichissement"]["traductions"]["en"], "la traduction, elle, est gardée"

    def test_gardees_tant_que_la_demande_peut_reprendre(self):
        p = projet()
        pj.nouvelle_demande(p, "trad:en", "e1", ["trad:en"], groupes=p["sous_titres"])
        pj.echec_demande(p, "trad:en", "coupure")
        assert pj.enrichissement(p)["demandes"]["trad:en"]["groupes"]

    def test_anciens_projets_nettoyes_a_la_lecture(self):
        p = projet()
        p["enrichissement"] = {
            "metadonnees": {},
            "quiz": [],
            "traductions": {},
            "sources": {},
            "faits": {},
            "versions": {},
            "demandes": {
                "trad:en": {
                    "cle": "trad:en",
                    "etat": "termine",
                    "parties": ["trad:en"],
                    "groupes": [{"start": 0, "end": 1, "text": "x"}],
                }
            },
        }
        assert pj.enrichissement(p)["demandes"]["trad:en"]["groupes"] == []
