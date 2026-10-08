"""Onglet « Enrichissement IA » (refonte 1.11.0, étape 4 : trois cartes).

Le scénario tourne dans un PROCESSUS SÉPARÉ : une seule instance Tk, un dossier
personnel temporaire (USERPROFILE / HOME), et des faux pour Aristote, le
serveur de l'éditeur et le client Pod. Ni réseau, ni coffre-fort, ni données
réelles de l'utilisateur.
"""
import ast
import os
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)


def _source_app() -> str:
    return open(os.path.join(RACINE, "app.py"), encoding="utf-8").read()


def _methode(nom: str) -> ast.FunctionDef:
    arbre = ast.parse(_source_app())
    return next(n for n in ast.walk(arbre) if isinstance(n, ast.FunctionDef) and n.name == nom)


def test_rien_n_est_construit_au_demarrage():
    """L'onglet doit rester vide au démarrage : ni widgets, ni lecture des
    projets, ni serveur, pour chaque lancement et chaque administrateur."""
    appels = {n.func.id for n in ast.walk(_methode("_build_tab_enrich"))
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "PanneauEnrichissement" not in appels


def test_la_reprise_du_suivi_attend_la_connexion():
    """La reprise interroge Aristote : elle passe par le chargement
    automatique, qui n'agit qu'une fois PodAdmin connecté."""
    table = next(n for n in ast.walk(_methode("_auto_loaders")) if isinstance(n, ast.Dict))
    chargeurs = {k.value: ast.unparse(v) for k, v in zip(table.keys, table.values)}
    assert chargeurs.get("enrich") == "self._enrich_reprendre"
    assert "reprendre_travaux" not in ast.unparse(_methode("_enrich_construire"))


def test_le_panneau_n_a_plus_de_journal_propre_ni_d_identifiants_a_saisir():
    source = _source_app()
    debut = source.index("class PanneauEnrichissement")
    fin = source.index("class FenetreVideoPod")
    panneau = source[debut:fin]
    assert "CTkTextbox" not in panneau, "second journal : tout doit aller au Journal de PodAdmin"
    assert "Reprendre un ID" not in panneau
    assert "bell()" not in panneau


SCENARIO = r'''
import os, sys, time, json, threading
sys.path.insert(0, RACINE)
import customtkinter as ctk
import app as A
from enrichissement import projet as P
for nom in ("_auto_connect", "_verifier_maj", "_surveiller_blocage"):
    setattr(A.App, nom, lambda s, *a, **k: None)
assert P.DOSSIER_PROJETS.startswith(os.environ["USERPROFILE"]), "vrai dossier de projets"

# — Faux : serveur de l'éditeur, Aristote, messages —
ouvertures, demandes, clients, avertissements, questions = [], [], [], [], []
porte_7 = threading.Event()
class FauxServeur:
    def __init__(self, **kw): self.kw = kw
    def ouvrir(self, pid, partie="st"): ouvertures.append((pid, partie)); return False
    def reprendre(self, pid): ouvertures.append(("reprise", pid))
    def lancer_demande(self, pid, cle): demandes.append((pid, cle))
class FauxAristote:
    def __init__(self, cid, secret, url):
        clients.append(url)
    def envoyer_lien(self, mp3, langue, identifiant_utilisateur=None):
        assert langue == "fr"; return "eid-" + identifiant_utilisateur.rsplit("-", 1)[1]
    def attendre(self, eid, rappel=None, **k):
        if eid == "eid-7": assert porte_7.wait(15), "porte de la vidéo 7 jamais ouverte"
        return {"initialVersionId": "v1"}
    def transcription(self, eid, version):
        return {"language": "fr", "sentences": [{"text": "Bonjour à tous.", "start": 0.0, "end": 2.0,
                "words": [{"word": "Bonjour", "start": 0.0, "end": 0.8},
                          {"word": "à", "start": 0.8, "end": 1.0},
                          {"word": "tous.", "start": 1.0, "end": 2.0}]}]}
A.ServeurEditeur = FauxServeur
A.AristoteAPI = FauxAristote
A.messagebox.showwarning = lambda *a, **k: avertissements.append(a[0])
A.messagebox.showerror = lambda *a, **k: avertissements.append(a[0])
A.messagebox.askyesno = lambda *a, **k: questions.append(a[0]) or True
A.messagebox.askyesnocancel = lambda *a, **k: questions.append(a[0]) or True

def attendre(cond, delai=8):
    fin = time.time() + delai
    while time.time() < fin and not cond():
        a.update(); time.sleep(0.05)
    a.update()
    return cond()

# — Projets laissés par une session précédente —
p = P.nouveau("ancien cours.mp4", "fr"); p["etat"] = "a_corriger"
p["sous_titres"] = [{"start": 0, "end": 2, "text": "Bonjour."}]; P.enregistrer(p)
q = P.nouveau("chez aristote.mp4", "fr"); q["etat"] = "attente"; q["enrichment_id"] = "eid-ancien"
P.enregistrer(q)
r = P.nouveau("envoi coupe.mp4", "fr"); r["etat"] = "envoi"; P.enregistrer(r)

a = A.App(); a.update()
assert a.enrich_panneau is None and not ouvertures and not clients, "travail au démarrage"
assert list(a.nav_btns).index("enrich") == list(a.nav_btns).index("browse") + 1

# — Première ouverture, PodAdmin non connecté : affichage seul —
a._show_tab("enrich"); a.update()
pan = a.enrich_panneau
assert pan is not None and pan.winfo_manager() == "pack"
assert set(pan.lignes) == {p["id"], q["id"], r["id"]}
assert pan.depart.winfo_manager() and not pan.selection.winfo_manager(), "départ d'abord"
assert not ouvertures and not clients, "réseau ou serveur sans connexion"
pan.choisir_video_pod(); a.update()
assert avertissements == ["Non connecté"]

# — Connexion : la reprise du suivi part —
class FauxPod:
    def __init__(self):
        self.videos = {
            202: {"id": 202, "url": "https://videos.exemple.fr/rest/videos/202/",
                  "slug": "0202-les-metropoles", "title": "Les métropoles du Néolithique",
                  "owner": "https://videos.exemple.fr/rest/users/1/", "duration": 3725,
                  "is_draft": True, "date_added": "2026-09-25"},
            7: {"id": 7, "url": "https://videos.exemple.fr/rest/videos/7/", "slug": "0007-chimie",
                "title": "Chimie organique", "owner": "https://videos.exemple.fr/rest/users/1/",
                "duration": 600, "date_added": "2026-01-01"}}
    def lien_public(self, v): return f"https://videos.exemple.fr/video/{v['slug']}/"
    def get_user(self, url): return {"first_name": "Cédric", "last_name": "Monna"}
    def pistes(self, v):
        return [{"url": "https://videos.exemple.fr/rest/tracks/9/", "lang": "fr", "kind": "subtitles",
                 "src": "https://videos.exemple.fr/rest/files/9/"}] if v["id"] == 202 else []
    def mp3(self, v): return f"https://videos.exemple.fr/media/{v['id']}.mp3"
    def mp4(self, v): return f"https://videos.exemple.fr/media/{v['id']}.mp4"
    def references(self): return {"disciplines": {"Histoire": "u1"}, "types": {"Cours": "u2"}}
    def lire_piste(self, piste): return "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nTexte de Pod.\n"
    def video(self, ident): return self.videos[ident]
api = FauxPod()
a.api = api
a.videos[:] = list(api.videos.values())
a._on_connexion_etablie()
assert attendre(lambda: P.charger(q["id"])["etat"] == "a_corriger"), "suivi Aristote non repris"
assert P.charger(r["id"])["etat"] == "erreur", "envoi coupé non signalé"
assert clients and all(u == "https://stt.ilaas.fr/api" for u in clients)

def tous(w, acc):
    for e in w.winfo_children():
        if isinstance(e, ctk.CTkButton): acc.append(e)
        tous(e, acc)
    return acc

# — La fenêtre de recherche CHOISIT la vidéo, rien de plus —
avant = set(a.winfo_children())
pan.choisir_video_pod(); a.update()
fen = [w for w in a.winfo_children() if w not in avant and isinstance(w, ctk.CTkToplevel)][0]
for requete in ("metropoles neolithique", "Néolithique MÉTROPOLES"):   # accents ou non
    fen.entree.delete(0, "end"); fen.entree.insert(0, requete)
    fen.chercher(); a.update()
    assert "1 vidéo" in fen.statut.cget("text"), (requete, fen.statut.cget("text"))
fen.ouvrir_fiche(api.videos[202])
assert attendre(lambda: fen.fiche is not None)
colores = [b for b in tous(fen.cadre_fiche, []) if b.cget("fg_color") == A.C_ACTION]
assert [b.cget("text") for b in colores] == ["Choisir cette vidéo"], [b.cget("text") for b in colores]
fen.bouton_defaut.invoke(); a.update()
assert not fen.winfo_exists(), "la fenêtre reste ouverte"
assert pan.selection.winfo_manager() and not pan.depart.winfo_manager()
assert pan.fiche["video"]["id"] == 202 and pan.pid_courant is None
assert "Les métropoles du Néolithique" in pan.sel_titre.cget("text")

def carte(nom):
    w = pan.cartes[nom]
    return {"pastille": w["pastille"].cget("text"), "action": w["action"]["action"],
            "colore": w["bouton"].winfo_manager() != "" and w["bouton"].cget("fg_color") == A.C_ACTION,
            "action2": w["action"]["action2"] if w["bouton2"].winfo_manager() else ""}
c = {n: carte(n) for n in ("st", "meta", "quiz")}
assert c["st"]["action"] == "transcrire" and c["st"]["colore"] and c["st"]["action2"] == "depuis_piste", c
assert c["meta"]["action"] == "demander_meta" and not c["meta"]["colore"], c
assert sum(x["colore"] for x in c.values()) == 1, "un seul bouton coloré"

# — Partir des sous-titres de Pod (seconde action de la carte) —
pan.cartes["st"]["bouton2"].invoke()
assert attendre(lambda: "pod202" in pan.lignes), "piste de Pod non reprise"
assert P.charger("pod202")["sous_titres"][0]["text"] == "Texte de Pod."
assert ("pod202", "st") in ouvertures and pan.pid_courant == "pod202"
c = {n: carte(n) for n in ("st", "meta", "quiz")}
assert c["st"]["action"] == "relire_st" and c["st"]["colore"], c

# — Une carte ouvre SA partie de l'éditeur —
pan.cartes["st"]["bouton"].invoke(); a.update()
assert ouvertures[-1] == ("pod202", "st")

# — Métadonnées demandées sur des sous-titres non relus : avertissement, sans blocage —
n = len(questions)
pan.cartes["meta"]["bouton"].invoke()
assert attendre(lambda: ("pod202", "meta") in demandes)
assert questions[n:] == ["Sous-titres non relus"], questions[n:]

# — Résultat pendant qu'on est ailleurs : pastille sur la barre latérale —
a._show_tab("browse"); a.update()
pan.evenements.put(("resultat", "pod202", "meta", True))
assert attendre(lambda: a.nav_btns["enrich"].cget("text").endswith("●"))
a._show_tab("enrich"); a.update()
assert not a.nav_btns["enrich"].cget("text").endswith("●"), "pastille non levée"
pan.evenements.put(("resultat", "pod202", "meta", True))      # on est déjà sur l'onglet
attendre(lambda: False, 0.5)
assert not a.nav_btns["enrich"].cget("text").endswith("●"), "pastille alors qu'on regarde l'onglet"

# — Vidéo sans sous-titres : la carte Quiz lance la transcription, puis le quiz —
pan.selectionner_fiche({"video": api.videos[7], "lien": "l7", "mp4": "m7", "mp3": api.mp3(api.videos[7]),
                        "proprietaire": "C", "disciplines": [], "types": [], "pistes": []})
a.update()
c = {n: carte(n) for n in ("st", "meta", "quiz")}
assert c["st"]["action2"] == "", "pas de piste sur Pod : pas de seconde action"
n = len(questions)
pan.cartes["quiz"]["bouton"].invoke()
assert questions[n:] == ["Transcrire d'abord"], questions[n:]
assert attendre(lambda: P.existe("pod7") and P.charger("pod7").get("etat") == "attente")
assert P.charger("pod7")["a_enchainer"] == ["quiz"]
# Pendant la transcription, la carte Métadonnées propose « Demander après la transcription ».
assert attendre(lambda: carte("meta")["action"] == "enchainer_meta"), carte("meta")
pan.cartes["meta"]["bouton"].invoke(); a.update()
assert P.charger("pod7")["a_enchainer"] == ["meta", "quiz"]
assert carte("meta")["pastille"] == "demandé après la transcription"
porte_7.set()
assert attendre(lambda: ("pod7", "quiz") in demandes and ("pod7", "meta") in demandes), demandes
assert "a_enchainer" not in P.charger("pod7"), "enchaînement rejoué au redémarrage"
assert P.charger("pod7")["etat"] == "a_corriger"

# — « Afficher » d'une ligne : la vidéo devient la vidéo choisie —
pan.lignes[p["id"]]["afficher"].invoke(); a.update()
assert pan.pid_courant == p["id"] and pan.fiche is None
assert carte("meta")["action"] == "associer", "vidéo du poste : métadonnées après association"

# — Bouton « Enrichir… » de l'onglet Vidéos : l'onglet s'ouvre sur cette vidéo —
a._show_tab("browse"); a.update()
a._enrichir_video(api.videos[202])
assert attendre(lambda: pan.fiche is not None and pan.fiche["video"]["id"] == 202), "fiche non lue"
assert a.onglet_courant == "enrich" and pan.pid_courant == "pod202", "projet existant non retrouvé"
assert pan.fiche["proprietaire"] == "Cédric Monna" and pan.selection.winfo_manager()

# — Changer de vidéo : retour au départ —
pan.revenir_au_choix(); a.update()
assert pan.depart.winfo_manager() and not pan.selection.winfo_manager()

# — Réglages de l'onglet —
avant = set(a.winfo_children())
pan.ouvrir_reglages(); a.update()
reg = [w for w in a.winfo_children() if w not in avant and isinstance(w, ctk.CTkToplevel)][0]
reg.champs["car_par_ligne"].delete(0, "end"); reg.champs["car_par_ligne"].insert(0, "40")
reg.bouton_defaut.invoke(); a.update()
prefs = json.load(open(os.path.join(os.environ["USERPROFILE"], ".soustitreur", "config.json"),
                       encoding="utf-8"))
assert prefs["decoupage"]["car_par_ligne"] == 40

# — Le journal de PodAdmin a bien reçu les messages du panneau —
journal = a.log_box.get("1.0", "end")
assert "Reprise du suivi" in journal and "reçus d'Aristote" in journal
print("SCENARIO OK")
a.destroy()
'''


def test_onglet_de_bout_en_bout(tmp_path):
    script = tmp_path / "scenario.py"
    script.write_text(f"RACINE = {RACINE!r}\n" + SCENARIO, encoding="utf-8")
    env = {**os.environ, "USERPROFILE": str(tmp_path), "HOME": str(tmp_path), "PYTHONUTF8": "1"}
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                       timeout=120, env=env, cwd=RACINE)
    assert r.returncode == 0 and "SCENARIO OK" in r.stdout, r.stdout[-3000:] + r.stderr[-3000:]
