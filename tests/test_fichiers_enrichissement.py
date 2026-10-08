"""Intégration de SousTitreur, étape 6 : les fichiers du poste, sans ffmpeg.

Une vidéo ou un son part ENTIER chez Aristote (pas d'extraction du son), sous
la limite mesurée sur ILaaS ; au-delà, refus AVANT l'envoi. Un VTT / SRT est
importé et redécoupé, sans rien envoyer.

Scénario dans un PROCESSUS SÉPARÉ (une seule instance Tk, dossier personnel
temporaire), avec un faux Aristote. Aucun réseau.
"""
import ast
import os
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)


def test_rien_n_importe_ffmpeg_ni_le_module_media():
    """ffmpeg (imageio-ffmpeg) n'est pas embarqué : aucun import ne doit le
    réclamer, sans quoi l'application compilée planterait à l'envoi."""
    fichiers = ["app.py"] + [os.path.join("enrichissement", f)
                             for f in os.listdir(os.path.join(RACINE, "enrichissement"))
                             if f.endswith(".py")]
    for f in fichiers:
        arbre = ast.parse(open(os.path.join(RACINE, f), encoding="utf-8").read())
        for n in ast.walk(arbre):
            noms = ([a.name for a in n.names] if isinstance(n, ast.Import)
                    else [n.module or ""] + [a.name for a in n.names] if isinstance(n, ast.ImportFrom)
                    else [])
            for nom in noms:
                assert not any(x in nom for x in ("imageio", "ffmpeg", "media")), (f, nom)


def test_la_limite_reste_sous_le_refus_mesure():
    """La sonde a vu ILaaS refuser à partir de 811 Mo : la limite doit rester
    en dessous, marge comprise pour l'enveloppe multipart."""
    from enrichissement import reglages
    assert 700 * 1024 * 1024 <= reglages.LIMITE_ENVOI_OCTETS < 795 * 1024 * 1024


SCENARIO = r'''
import os, sys, time
sys.path.insert(0, RACINE)
import app as A
from enrichissement import projet as P, reglages as R
for nom in ("_auto_connect", "_verifier_maj", "_surveiller_blocage"):
    setattr(A.App, nom, lambda s, *a, **k: None)
assert P.DOSSIER_PROJETS.startswith(os.environ["USERPROFILE"]), "vrai dossier de projets"

envoyes, ouvertures, avertissements = [], [], []
class FauxServeur:
    def __init__(self, **kw): pass
    def ouvrir(self, pid, partie="st"): ouvertures.append(pid); return False
    def reprendre(self, pid): pass
class FauxAristote:
    def __init__(self, *a): pass
    def envoyer_fichier(self, chemin, langue="fr", nom_original=None, progression=None, **k):
        envoyes.append((chemin, langue, nom_original))
        if "refus" in chemin:
            raise A.AristoteErreur("Envoi refusé (413) : Request Entity Too Large")
        if progression: progression(5, 10); progression(10, 10)
        return "eid-" + os.path.basename(chemin)
    def attendre(self, eid, rappel=None, **k): return {"initialVersionId": "v1"}
    def transcription(self, eid, version):
        return {"language": "fr", "sentences": [{"text": "Bonjour à tous.", "start": 0.0, "end": 2.0}]}
A.ServeurEditeur = FauxServeur
A.AristoteAPI = FauxAristote
A.messagebox.showwarning = lambda *a, **k: avertissements.append(a[0])
R.LIMITE_ENVOI_OCTETS = 1000            # « gros.mp4 » (2 000 octets) la dépasse

d = os.path.join(os.environ["USERPROFILE"], "videos")
os.makedirs(d)
def fichier(nom, contenu=b"x" * 100):
    c = os.path.join(d, nom)
    open(c, "wb").write(contenu)
    return c
cours = fichier("cours.mp4")
son = fichier("entretien.mp3")
gros = fichier("gros.mp4", b"x" * 2000)
refus = fichier("refus.mp4")
pdf = fichier("notes.pdf")
vtt = fichier("cours.fr.vtt", "WEBVTT\n\n00:00:00.000 --> 00:00:03.000\nPremière phrase. Deuxième phrase du cours.\n".encode("utf-8"))
casse = fichier("casse.srt", b"1\n00:00:00,000 --> 00:00:01,000\nAccent cass\xe9\n")

a = A.App(); a.update()
a._show_tab("enrich"); a.update()
pan = a.enrich_panneau

# — Boîte de dialogue : les extensions proposées sont celles reconnues —
vus = {}
def dialogue(**k):
    vus.update(k); return (cours, son, gros, refus, pdf)
A.filedialog.askopenfilenames = dialogue
pan.choisir_fichiers()
motif = vus["filetypes"][0][1]
assert "*.mp4" in motif and "*.mp3" in motif and "*.vtt" in motif and "*.srt" in motif, motif

fin = time.time() + 8
def etat(chemin): return P.charger(P.identifiant(chemin))["etat"] if P.existe(P.identifiant(chemin)) else None
while time.time() < fin and not (etat(cours) == etat(son) == "a_corriger" and etat(refus) == "erreur"):
    a.update(); time.sleep(0.05)
a.update()

# Fichier ENTIER, chemin d'origine, toujours en français.
chemins = [c for c, _l, _n in envoyes]
assert sorted(chemins) == sorted([cours, son, refus]), chemins
assert all(l == "fr" for _c, l, _n in envoyes)
assert {n for _c, _l, n in envoyes} == {"cours.mp4", "entretien.mp3", "refus.mp4"}
assert etat(cours) == etat(son) == "a_corriger", (etat(cours), etat(son))
assert P.charger(P.identifiant(son))["audio"] == son, "un son sert lui-même de piste audio"
assert P.charger(P.identifiant(cours))["audio"] == ""

# Trop lourd : refusé avant tout envoi, sans projet créé.
assert gros not in chemins and not P.existe(P.identifiant(gros))
assert avertissements == ["Fichier trop lourd"], avertissements

# 413 malgré la limite : message clair, pas le code brut.
assert P.charger(P.identifiant(refus))["erreur"] == A.MESSAGE_TROP_LOURD_IA

# — Sous-titres du poste : importés, redécoupés, rattachés à la vidéo du même nom —
pan.ajouter([vtt, casse])
a.update()
pv = P.charger(P.identifiant(vtt))
assert pv["media"] == cours and pv["langue"] == "fr" and pv["sous_titres"], pv
assert pv["id"] != P.identifiant(cours), "l'import écraserait la transcription Aristote"
assert P.identifiant(vtt) in ouvertures, "la correction s'ouvre après l'import"
assert not P.existe(P.identifiant(casse))
assert len(envoyes) == 3, "un sous-titre ne part jamais chez Aristote"

journal = a.log_box.get("1.0", "end")
assert "Ignoré (format non pris en charge) : notes.pdf" in journal
assert "casse.srt : fichier illisible" in journal
assert "importé et redécoupé" in journal
print("SCENARIO OK")
a.destroy()
'''


def test_fichiers_du_poste_de_bout_en_bout(tmp_path):
    script = tmp_path / "scenario.py"
    script.write_text(f"RACINE = {RACINE!r}\n" + SCENARIO, encoding="utf-8")
    env = {**os.environ, "USERPROFILE": str(tmp_path), "HOME": str(tmp_path), "PYTHONUTF8": "1"}
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                       timeout=120, env=env, cwd=RACINE)
    assert r.returncode == 0 and "SCENARIO OK" in r.stdout, r.stdout[-3000:] + r.stderr[-3000:]
