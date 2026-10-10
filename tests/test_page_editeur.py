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
        appel(serveur.srv, serveur.pid, "/etat")                   # la page se signale
        assert serveur.srv.ouvrir(serveur.pid, "meta") is True
        assert serveur.fenetres == [], "seconde fenêtre ouverte"
        assert appel(serveur.srv, serveur.pid, "/etat")["commande"] == "meta"
        assert appel(serveur.srv, serveur.pid, "/etat")["commande"] == "", "ordre rejoué"

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
const appels = [];
const fetch = async url => { appels.push(url); const d = JSON.parse(JSON.stringify(SERVEUR));
  if (url === "etat") return {ok: true, json: async () => ({parties: d.parties, versions: d.versions, commande: ""})};
  return {ok: true, json: async () => d}; };
""" + fonctions + """
interroger().then(async () => {
  const premier = {en: (E.traductions.en || []).length, version: VERSIONS["trad:en"], rendues, messages, appels: [...appels]};
  appels.length = 0;
  await interroger();                       // rien de nouveau : la route légère seule
  console.log(JSON.stringify({...premier, ensuite: appels}));
});
"""
        f = tmp_path / "banc.js"
        f.write_text(banc, encoding="utf-8")
        r = subprocess.run(["node", str(f)], capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr
        sortie = json.loads(r.stdout)
        assert sortie["en"] == 1 and sortie["version"] == 1, sortie
        assert sortie["rendues"] == ["st"] and len(sortie["messages"]) == 1, sortie
        # Audit O2 : le bloc complet n'est relu que si une version a changé.
        assert sortie["appels"] == ["etat", "enrichissement"], sortie
        assert sortie["ensuite"] == ["etat"], sortie

    @pytest.mark.skipif(not shutil.which("node"), reason="Node.js absent")
    def test_script_syntaxiquement_valide(self, tmp_path):
        f = tmp_path / "page.js"
        f.write_text(SCRIPT, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


class TestFichierExporteRetrouvable:
    """Audit I6 : le chemin du fichier exporté disparaissait avec le message."""

    def test_export_note_au_journal(self, serveur):
        lignes = []
        serveur.srv.journal_hote = lignes.append
        d = appel(serveur.srv, serveur.pid, "/exporter", {"formats": [], "quiz": True})
        assert lignes == [f"✔ cours.mp4 : exporté vers {d['fichiers'][0]}"], lignes

    def test_ouvrir_le_dossier_du_projet(self, serveur, monkeypatch):
        from enrichissement import editeur
        ouverts = []
        monkeypatch.setattr(editeur, "_ouvrir_dossier", ouverts.append)
        assert appel(serveur.srv, serveur.pid, "/ouvrir_dossier", {"chemin": "C:/Windows"}) == {"ok": True}
        assert ouverts == [serveur.dossier], "le chemin vient du projet, jamais de la page"

    def test_dossier_absent_documents(self, tmp_path):
        from enrichissement import editeur
        assert editeur.dossier_exports({"dossier": str(tmp_path / "disparu")}).endswith("Documents")

    def test_les_deux_exports_proposent_le_dossier(self):
        assert SCRIPT.count("OUVRIR_DOSSIER);") == 2


class TestInterrogationLegere:
    """Audit O2 et O3 : moins de lectures, d'écritures et d'octets."""

    def test_route_legere(self, serveur):
        p = pj.charger(serveur.pid)
        # Le volume vient des traductions (une heure : ~800 sous-titres par langue).
        pj.enrichissement(p)["traductions"]["en"] = [
            {"start": i, "end": i + 1, "text": "Hello everyone."} for i in range(800)]
        pj.enregistrer(p)
        url = f"http://127.0.0.1:{serveur.srv.port}/api/{serveur.pid}"
        leger = urllib.request.urlopen(f"{url}/etat?t={serveur.srv.jeton}").read()
        complet = urllib.request.urlopen(f"{url}/enrichissement?t={serveur.srv.jeton}").read()
        d = json.loads(leger)
        assert set(d) == {"parties", "versions", "commande", "theme"}
        assert len(leger) < 3000 and len(complet) > 20 * len(leger), (len(leger), len(complet))

    def test_projet_relu_seulement_s_il_a_change(self, serveur, monkeypatch):
        lectures = []
        vrai = pj.charger
        monkeypatch.setattr(pj, "charger", lambda pid: lectures.append(pid) or vrai(pid))
        for _ in range(5):
            serveur.srv.projet_en_lecture(serveur.pid)
        assert len(lectures) == 1
        p = vrai(serveur.pid)
        p["sous_titres"].append({"start": 9, "end": 10, "text": "Nouveau."})
        pj.enregistrer(p)
        assert serveur.srv.projet_en_lecture(serveur.pid)["sous_titres"][-1]["text"] == "Nouveau."
        assert len(lectures) == 2

    def test_suivi_n_ecrit_que_les_changements(self, serveur, monkeypatch):
        from enrichissement import editeur
        ecritures = []
        vrai = pj.enregistrer
        monkeypatch.setattr(pj, "enregistrer", lambda p: ecritures.append(1) or vrai(p))

        class FauxAristote:
            def attendre(self, eid, rappel=None, **k):
                for statut in ["IN_PROGRESS"] * 10 + ["SUCCESS"]:
                    rappel(statut, {})
                return {"status": "SUCCESS"}

            def version_finale(self, eid):
                return {"enrichmentVersionMetadata": {"title": "T2"}}
        p = pj.charger(serveur.pid)
        pj.nouvelle_demande(p, "meta", "e9", ["meta"])
        vrai(p)
        serveur.srv._suivre(serveur.pid, FauxAristote(), "meta", "e9")
        # Deux changements d'état (en cours, terminé), puis le résultat : 3 au plus.
        assert len(ecritures) <= 3, len(ecritures)

    def test_ecriture_ignoree_si_rien_ne_change(self, serveur, monkeypatch):
        """Première protection, testée seule : la mise à jour d'une demande."""
        p = pj.charger(serveur.pid)
        pj.nouvelle_demande(p, "meta", "e8", ["meta"])
        pj.enregistrer(p)
        ecritures = []
        vrai = pj.enregistrer
        monkeypatch.setattr(pj, "enregistrer", lambda q: ecritures.append(1) or vrai(q))
        for _ in range(5):
            serveur.srv._maj_demande(serveur.pid, "meta", "e8", detail="En cours")
        assert len(ecritures) == 1

    def test_suivi_ne_transmet_que_les_changements_d_etat(self, serveur, monkeypatch):
        """Seconde protection, testée seule : le rappel du suivi."""
        appels = []
        monkeypatch.setattr(serveur.srv, "_maj_demande", lambda *a, **k: appels.append(k.get("detail")))

        class FauxAristote:
            def attendre(self, eid, rappel=None, **k):
                for statut in ["PENDING"] * 3 + ["IN_PROGRESS"] * 6:
                    rappel(statut, {})
                raise RuntimeError("fin du banc")
        serveur.srv._suivre(serveur.pid, FauxAristote(), "meta", "e7")
        # Deux changements d'état, puis l'enregistrement de l'échec du banc.
        assert appels == ["PENDING", "IN_PROGRESS", ""], appels



class TestFinitionPage:
    def test_la_page_suit_le_theme_de_podadmin(self, serveur):
        """Audit I10 : le thème venait des préférences de SousTitreur, où
        PodAdmin ne l'écrit pas ; la page s'ouvrait toujours en sombre."""
        serveur.srv.reglages = lambda: {"theme": "light"}
        assert appel(serveur.srv, serveur.pid, "/etat")["theme"] == "light"
        corps = SCRIPT[SCRIPT.index("async function interroger"):SCRIPT.index("function recevoir")]
        assert "document.documentElement.dataset.theme = d.theme" in corps

    def test_l_onglet_transmet_le_vrai_theme(self):
        src = open(os.path.join(RACINE, "app.py"), encoding="utf-8").read()
        assert '"theme": ctk.get_appearance_mode().lower()' in src

    def test_clavier(self):
        """Audit I9 : Alt+1, 2, 3 et flèches dans le choix de langue."""
        assert 'e.altKey && ["1", "2", "3"].includes(e.key)' in SCRIPT
        assert '"ArrowLeft", "ArrowRight"' in SCRIPT
        assert "<kbd>1</kbd> <kbd>2</kbd> <kbd>3</kbd>" in PAGE

    def test_entete_etroit_et_poubelle_visible(self):
        """Audits I7 et I8."""
        assert "@media (max-width:1150px){#parties button small{display:none}" in PAGE
        assert "text-overflow:ellipsis;max-width:30vw" in PAGE
        assert "button.poubelle{color:var(--texte);border-color:var(--bord)}" in PAGE
