"""Intégration de SousTitreur, étape 4 : l'onglet « Enrichissement IA ».

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
import os, sys, time, json
sys.path.insert(0, RACINE)
import customtkinter as ctk
import app as A
from enrichissement import projet as P
for nom in ("_auto_connect", "_verifier_maj", "_surveiller_blocage"):
    setattr(A.App, nom, lambda s, *a, **k: None)
assert P.DOSSIER_PROJETS.startswith(os.environ["USERPROFILE"]), "vrai dossier de projets"

# — Faux : serveur de l'éditeur, Aristote, messages —
ouvertures, clients, avertissements = [], [], []
class FauxServeur:
    def __init__(self, **kw): ouvertures.append("demarre")
    def ouvrir(self, pid): ouvertures.append(pid)
    def reprendre(self, pid): ouvertures.append("reprise-" + pid)
class FauxAristote:
    def __init__(self, cid, secret, url):
        clients.append(url); self.url = url
    def envoyer_lien(self, mp3, langue, identifiant_utilisateur=None):
        assert langue == "fr"; return "eid-nouveau"
    def attendre(self, eid, rappel=None, **k): return {"initialVersionId": "v1"}
    def transcription(self, eid, version):
        return {"language": "fr", "sentences": [{"text": "Bonjour à tous.", "start": 0.0, "end": 2.0,
                "words": [{"word": "Bonjour", "start": 0.0, "end": 0.8},
                          {"word": "à", "start": 0.8, "end": 1.0},
                          {"word": "tous.", "start": 1.0, "end": 2.0}]}]}
A.ServeurEditeur = FauxServeur
A.AristoteAPI = FauxAristote
A.messagebox.showwarning = lambda *a, **k: avertissements.append(a[0])
A.messagebox.askyesno = lambda *a, **k: True

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
assert str(pan.lignes[p["id"]]["corriger"].cget("state")) == "normal"
assert not ouvertures and not clients, "réseau ou serveur sans connexion"
pan.choisir_video_pod(); a.update()
assert avertissements == ["Non connecté"]

# — Connexion : la reprise du suivi part —
class FauxPod:
    def __init__(self):
        self.video = {"id": 202, "url": "https://videos.exemple.fr/rest/videos/202/",
                      "slug": "0202-les-metropoles", "title": "Les métropoles du Néolithique",
                      "owner": "https://videos.exemple.fr/rest/users/1/", "duration": 3725,
                      "is_draft": True, "date_added": "2026-09-25"}
    def lien_public(self, v): return "https://videos.exemple.fr/video/0202-les-metropoles/"
    def get_user(self, url): return {"first_name": "Cédric", "last_name": "Monna"}
    def pistes(self, v): return [{"url": "https://videos.exemple.fr/rest/tracks/9/", "lang": "fr",
                                  "kind": "subtitles", "src": "https://videos.exemple.fr/rest/files/9/"}]
    def mp3(self, v): return "https://videos.exemple.fr/media/202.mp3"
    def mp4(self, v): return "https://videos.exemple.fr/media/202.mp4"
    def references(self): return {"disciplines": {"Histoire": "u1"}, "types": {"Cours": "u2"}}
    def lire_piste(self, piste): return "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nTexte de Pod.\n"
    def video(self, ident): return self.video
api = FauxPod()
a.api = api
a.videos[:] = [api.video, {"id": 7, "title": "Chimie organique", "slug": "0007-chimie",
                           "date_added": "2026-01-01"}]
a._on_connexion_etablie()
fin = time.time() + 8
while time.time() < fin and P.charger(q["id"])["etat"] != "a_corriger":
    a.update(); time.sleep(0.05)
a.update()
assert P.charger(q["id"])["etat"] == "a_corriger", "suivi Aristote non repris"
assert P.charger(r["id"])["etat"] == "erreur", "envoi coupé non signalé"
assert clients and all(u == "https://stt.ilaas.fr/api" for u in clients)

# — Choix d'une vidéo par le magasin partagé —
avant = set(a.winfo_children())
pan.choisir_video_pod(); a.update()
fen = [w for w in a.winfo_children() if w not in avant and isinstance(w, ctk.CTkToplevel)][0]
for requete in ("metropoles neolithique", "Néolithique MÉTROPOLES"):   # accents ou non
    fen.entree.delete(0, "end"); fen.entree.insert(0, requete)
    fen.chercher(); a.update()
    assert "1 vidéo" in fen.statut.cget("text"), (requete, fen.statut.cget("text"))
fen.ouvrir_fiche(api.video)
fin = time.time() + 5
while time.time() < fin and fen.fiche is None:
    a.update(); time.sleep(0.05)
assert fen.fiche and fen.fiche["proprietaire"] == "Cédric Monna"
boutons = []
def tous(w):
    for e in w.winfo_children():
        if isinstance(e, ctk.CTkButton): boutons.append(e)
        tous(e)
tous(fen.cadre_fiche)
colores = [b for b in boutons if b.cget("fg_color") == A.C_ACTION]
assert len(colores) == 1, "une seule action colorée par fiche"
depuis = [b for b in boutons if "existants" in b.cget("text")][0]
depuis.invoke()
fin = time.time() + 5
while time.time() < fin and "pod202" not in pan.lignes:
    a.update(); time.sleep(0.05)
assert "pod202" in pan.lignes and "pod202" in ouvertures, "piste de Pod non reprise"
assert P.charger("pod202")["sous_titres"][0]["text"] == "Texte de Pod."

# — Fiche d'une vidéo DÉJÀ commencée : « Rouvrir » est la seule action colorée —
avant = set(a.winfo_children())
pan.choisir_video_pod(); a.update()
fen = [w for w in a.winfo_children() if w not in avant and isinstance(w, ctk.CTkToplevel)][0]
fen.ouvrir_fiche(api.video)
fin = time.time() + 5
while time.time() < fin and fen.fiche is None:
    a.update(); time.sleep(0.05)
boutons = []
tous(fen.cadre_fiche)
colores = [b.cget("text") for b in boutons if b.cget("fg_color") == A.C_ACTION]
assert len(colores) == 1 and "Rouvrir" in colores[0], colores
fen.destroy()

# — Nouvelle transcription (même vidéo : remplace la correction) —
fiche = {"video": api.video, "lien": "l", "mp4": "m", "mp3": "https://x/202.mp3",
         "proprietaire": "C", "disciplines": [], "types": [], "pistes": []}
pan.transcrire_pod(fiche)
fin = time.time() + 5
while time.time() < fin and P.charger("pod202").get("enrichment_id") != "eid-nouveau":
    a.update(); time.sleep(0.05)
assert P.charger("pod202")["enrichment_id"] == "eid-nouveau"

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
assert "Reprise du suivi" in a.log_box.get("1.0", "end")
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
