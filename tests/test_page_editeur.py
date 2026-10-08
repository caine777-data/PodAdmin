"""Refonte 1.11.0, étape 3 : la page de l'éditeur en parties.

Côté serveur : enregistrement par la page sans écraser ce qu'Aristote a
livré entre-temps, une seule fenêtre par vidéo, export partie par partie.
Côté page : contrôles statiques (la page elle-même a été vérifiée dans un
navigateur, avec un faux Aristote).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from types import SimpleNamespace

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from enrichissement import projet as pj          # noqa: E402

PAGE = open(os.path.join(RACINE, "assets", "editeur.html"), encoding="utf-8").read()
SCRIPT = re.search(r"<script>(.*)</script>", PAGE, re.S).group(1)


def q(texte, **k):
    return pj._completer_question({"question": texte, "choix": [{"texte": "a", "correct": True},
                                                                 {"texte": "b", "correct": False}], **k})


class TestFusionDepuisLaPage:
    def test_questions_arrivees_pendant_la_saisie_conservees(self):
        e = pj.enrichissement({"sous_titres": []})
        e["quiz"] = [q("Première ?"), q("Deuxième ?")]
        page = [dict(x) for x in e["quiz"]]
        vus = [x["id"] for x in page]
        e["quiz"].append(q("Arrivée pendant la saisie ?"))      # Aristote livre
        page[0]["question"] = "Première, corrigée ?"             # la page modifie
        pj.fusionner_page(e, {"quiz": page, "quiz_vus": vus})
        assert [x["question"] for x in e["quiz"]] == [
            "Première, corrigée ?", "Deuxième ?", "Arrivée pendant la saisie ?"]

    def test_suppression_par_la_page_respectee(self):
        e = pj.enrichissement({"sous_titres": []})
        e["quiz"] = [q("Gardée ?"), q("Supprimée ?")]
        vus = [x["id"] for x in e["quiz"]]
        pj.fusionner_page(e, {"quiz": [dict(e["quiz"][0])], "quiz_vus": vus})
        assert [x["question"] for x in e["quiz"]] == ["Gardée ?"]

    def test_question_redigee_dans_la_page_recoit_ses_champs(self):
        e = pj.enrichissement({"sous_titres": []})
        pj.fusionner_page(e, {"quiz": [{"id": "abc12345", "question": "Rédigée ?", "origine": "redigee",
                                        "choix": [{"texte": "a", "correct": True}]}], "quiz_vus": ["abc12345"]})
        assert e["quiz"][0]["origine"] == "redigee" and e["quiz"][0]["retenue"] is True

    def test_saisie_sur_une_ancienne_version_ignoree(self):
        p = {"sous_titres": [{"start": 0, "end": 1, "text": "x"}]}
        e = pj.enrichissement(p)
        pj.nouvelle_demande(p, "meta", "e1", ["meta"])
        pj.appliquer_demande(p, "meta", {"enrichmentVersionMetadata": {"title": "Nouveau"}}, pj.st.Parametres())
        ignorees = pj.fusionner_page(e, {"metadonnees": {"titre": "Saisie sur l'ancienne"}, "versions": {}})
        assert ignorees == ["meta"] and e["metadonnees"]["titre"] == "Nouveau"
        ignorees = pj.fusionner_page(e, {"metadonnees": {"titre": "Saisie à jour"}, "versions": {"meta": 1}})
        assert ignorees == [] and e["metadonnees"]["titre"] == "Saisie à jour"

    def test_traduction_par_langue(self):
        p = {"sous_titres": [{"start": 0, "end": 1, "text": "x"}]}
        e = pj.enrichissement(p)
        e["versions"]["trad:en"] = 2
        ignorees = pj.fusionner_page(e, {"traductions": {"en": [{"start": 0, "end": 1, "text": "y"}],
                                                         "pt": [{"start": 0, "end": 1, "text": "z"}]},
                                         "versions": {"trad:en": 1}})
        assert ignorees == ["trad:en"] and e["traductions"] == {"pt": [{"start": 0, "end": 1, "text": "z"}]}


class TestGift:
    def test_reponses_vides_ecartees(self):
        quiz = [{"question": "Q ?", "choix": [{"texte": "oui", "correct": True}, {"texte": "  ", "correct": False},
                                              {"texte": "non", "correct": False}]}]
        g = pj.quiz_vers_gift(quiz, "Cours")
        assert g.count("\t~") == 1 and "\t=oui" in g


@pytest.fixture
def serveur(tmp_path, monkeypatch):
    from enrichissement import editeur
    monkeypatch.setattr(pj, "DOSSIER_PROJETS", str(tmp_path / "projets"))
    p = pj.nouveau(str(tmp_path / "cours.mp4"), "fr")
    p["sous_titres"] = [{"start": 0, "end": 3, "text": "Bonjour."}]
    p["etat"] = "a_corriger"
    p["dossier"] = str(tmp_path / "exports")
    os.makedirs(p["dossier"])
    e = pj.enrichissement(p)
    e["metadonnees"] = {"titre": "T", "description": "D"}
    e["quiz"] = [q("Q ?")]
    pj.enregistrer(p)
    fenetres = []
    monkeypatch.setattr(editeur, "_navigateurs_app", lambda: [])
    monkeypatch.setattr(editeur.webbrowser, "open", fenetres.append)
    srv = editeur.ServeurEditeur()
    yield SimpleNamespace(srv=srv, pid=p["id"], fenetres=fenetres, dossier=p["dossier"])
    srv.arreter()


def appel(srv, pid, chemin, corps=None):
    url = f"http://127.0.0.1:{srv.port}/api/{pid}{chemin}?t={srv.jeton}"
    data = None if corps is None else json.dumps(corps).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="GET" if corps is None else "POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


class TestUneFenetreParVideo:
    def test_ouverture_sur_une_partie(self, serveur):
        assert serveur.srv.ouvrir(serveur.pid, "quiz") is False
        assert len(serveur.fenetres) == 1 and serveur.fenetres[0].endswith("&partie=quiz")

    def test_page_ouverte_recoit_l_ordre_au_lieu_d_une_nouvelle_fenetre(self, serveur):
        appel(serveur.srv, serveur.pid, "/enrichissement")         # la page se signale
        assert serveur.srv.ouvrir(serveur.pid, "meta") is True
        assert serveur.fenetres == [], "seconde fenêtre ouverte"
        assert appel(serveur.srv, serveur.pid, "/enrichissement")["commande"] == "meta"
        assert appel(serveur.srv, serveur.pid, "/enrichissement")["commande"] == "", "ordre rejoué"

    def test_page_fermee_nouvelle_fenetre(self, serveur):
        appel(serveur.srv, serveur.pid, "/enrichissement")
        serveur.srv.vues[serveur.pid] -= serveur.srv.DELAI_PAGE_VIVANTE + 1
        assert serveur.srv.ouvrir(serveur.pid) is False and len(serveur.fenetres) == 1

    def test_partie_inconnue(self, serveur):
        serveur.srv.ouvrir(serveur.pid, "n'importe")
        assert serveur.fenetres[0].endswith("&partie=st")


class TestExportParPartie:
    def test_quiz_seul_sans_sous_titres(self, serveur):
        d = appel(serveur.srv, serveur.pid, "/exporter", {"formats": [], "quiz": True})
        assert [os.path.basename(f) for f in d["fichiers"]] == ["cours.quiz-moodle.gift.txt"]
        p = pj.charger(serveur.pid)
        assert p["etat"] == "a_corriger", "exporter le quiz n'exporte pas les sous-titres"
        assert pj.etat_partie(p, "quiz")["etat"] == "fait"

    def test_metadonnees_seules(self, serveur):
        d = appel(serveur.srv, serveur.pid, "/exporter", {"formats": [], "metadonnees": True})
        assert [os.path.basename(f) for f in d["fichiers"]] == ["cours.metadonnees.txt"]

    def test_rien_de_coche_reste_un_export_vtt(self, serveur):
        d = appel(serveur.srv, serveur.pid, "/exporter", {"formats": []})
        assert [os.path.basename(f) for f in d["fichiers"]] == ["cours.fr.vtt"]

    def test_enregistrement_par_la_page_renvoie_les_arrivees(self, serveur):
        p = pj.charger(serveur.pid)
        vus = [x["id"] for x in pj.enrichissement(p)["quiz"]]
        pj.enrichissement(p)["quiz"].append(q("Arrivée ?"))
        pj.enregistrer(p)
        d = appel(serveur.srv, serveur.pid, "/enrichissement",
                  {"quiz": [], "quiz_vus": vus, "metadonnees": {"titre": "T2"}, "versions": {}})
        assert [x["question"] for x in d["quiz"]] == ["Arrivée ?"] and d["ignorees"] == []


class TestPageStatique:
    def test_plus_de_soustitreur_ni_de_fenetre_groupee(self):
        visible = re.sub(r'localStorage\.\w+Item\("soustitreur-apparence"[^)]*\)', "", PAGE)
        assert "SousTitreur" not in visible
        for disparu in ("d-enrichir", "b-ouvrir-enrichir", "enr-langue", "langueTraduite", "#onglets"):
            assert disparu not in PAGE, disparu

    def test_trois_parties_et_routes_separees(self):
        html = PAGE[:PAGE.index("<script>")]
        assert re.findall(r'data-partie="(\w+)"', html) == ["st", "meta", "quiz"]
        for route in ('apiAction("demander")', 'apiAction("relu")', "quiz_vus", "VERSIONS"):
            assert route in SCRIPT, route

    def test_les_resultats_se_reperent_a_leur_version(self):
        """Guetter le passage « en cours » → « terminé » manquait un résultat
        quand une autre action rafraîchissait l'état (vu dans le navigateur)."""
        corps = SCRIPT[SCRIPT.index("async function interroger"):SCRIPT.index("function recevoir")]
        assert "versions" in corps and "VERSIONS[k]" in corps

    @pytest.mark.skipif(not shutil.which("node"), reason="Node.js absent")
    def test_resultat_charge_meme_si_l_etat_a_deja_ete_rafraichi(self, tmp_path):
        """Le cas vu dans le navigateur : une autre demande a déjà rafraîchi
        l'état (« traduction prête ») avant l'interrogation. La traduction doit
        quand même être chargée dans la page. On exécute les VRAIES fonctions
        de la page, avec un serveur simulé."""
        fonctions = "\n".join(re.search(rf"(?:async )?function {nom}\(.*?\n}}\n", SCRIPT, re.S).group(0)
                              for nom in ("interroger", "recevoir"))
        banc = """
let E = {traductions: {}, quiz: [], metadonnees: {},
         parties: {"trad:en": {etat: "pret", detail: "", perime: false}}};
let VERSIONS = {}, QUIZ_VUS = new Set(), minuterieEnr = null, rendues = [], messages = [];
const SERVEUR = {commande: "", versions: {"trad:en": 1}, traductions: {en: [{start: 0, end: 2, text: "Hello."}]},
                 metadonnees: {}, quiz: [], parties: {"trad:en": {etat: "pret", detail: "", perime: false}}};
const apiAction = a => a, toast = m => messages.push(m), majParties = () => {}, montrerPartie = () => {};
const rendrePartie = p => rendues.push(p), partieDeCle = k => k.startsWith("trad:") ? "st" : k;
const libelleCle = k => k, sauverEnrichissement = async () => {};
const fetch = async () => ({ok: true, json: async () => JSON.parse(JSON.stringify(SERVEUR))});
""" + fonctions + """
interroger().then(() => console.log(JSON.stringify({en: (E.traductions.en || []).length, version: VERSIONS["trad:en"],
                                                       rendues, messages})));
"""
        f = tmp_path / "banc.js"
        f.write_text(banc, encoding="utf-8")
        r = subprocess.run(["node", str(f)], capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr
        sortie = json.loads(r.stdout)
        assert sortie["en"] == 1 and sortie["version"] == 1, sortie
        assert sortie["rendues"] == ["st"] and len(sortie["messages"]) == 1, sortie

    @pytest.mark.skipif(not shutil.which("node"), reason="Node.js absent")
    def test_script_syntaxiquement_valide(self, tmp_path):
        f = tmp_path / "page.js"
        f.write_text(SCRIPT, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
