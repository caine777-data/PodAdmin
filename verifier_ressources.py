#!/usr/bin/env python3
"""
verifier_ressources.py — Sonde : que reste-t-il à exploiter dans l'API ?
========================================================================
PodAdmin utilise aujourd'hui 15 des 31 ressources exposées par l'API Esup-Pod.
Cette sonde examine les 16 autres pour répondre à trois questions par ressource :

  1. EXISTE-T-ELLE vraiment et est-elle lisible avec ce compte ?
  2. CONTIENT-ELLE des données ? (une ressource vide ne justifie aucun
     développement — c'est le critère le plus utile)
  3. EST-ELLE MODIFIABLE, ou seulement consultable ?

Elle affiche aussi un échantillon réel, pour juger de l'intérêt concret.

MODE : LECTURE SEULE. Rien n'est créé ni modifié.

AUTONOME : ce fichier se suffit à lui-même, aucun autre fichier du projet n'est
nécessaire. Seule dépendance : la bibliothèque « requests ».

    python verifier_ressources.py

Objectif : décider où investir l'effort de développement sur des faits plutôt
que sur des suppositions.
"""

__author__ = "Cédric MONNA"
__version__ = "1.0.0"

import json

# Ressources non exploitées par PodAdmin, regroupées par intérêt pressenti.
A_EXAMINER = [
    # (nom, pourquoi c'est intéressant)
    ("view_count",       "Statistiques de consultation — le plus prometteur : "
                         "transformerait l'Inventaire en outil de pilotage"),
    ("playlists",        "Listes de lecture créées par les enseignants"),
    ("playlist_videos",  "Contenu des listes de lecture"),
    ("chapters",         "Chapitrage des vidéos"),
    ("enrichments",      "Enrichissements pédagogiques (quiz, documents…)"),
    ("overlays",         "Incrustations affichées sur la vidéo"),
    ("discipline",       "Classement par discipline"),
    ("groups",           "Groupes Django (distincts des groupes d'accès)"),
    ("documents",        "Documents joints"),
    ("mainfiles",        "Fichiers principaux"),
    ("mainimages",       "Images principales"),
    ("encodings_video",  "Détail des encodages vidéo (diagnostic)"),
    ("encodings_audio",  "Détail des encodages audio"),
    ("renditions",       "Qualités d'encodage configurées"),
    ("recording",        "Enregistrements automatisés (amphis équipés)"),
    ("recorder",         "Matériel d'enregistrement déclaré"),
]


def charger_requests():
    """Importe `requests`, en proposant de l'installer si nécessaire."""
    try:
        import requests
        return requests
    except ImportError:
        pass
    print("La bibliothèque « requests » est nécessaire et n'est pas installée.")
    if input("L'installer maintenant ? (o/N) : ").strip().lower() not in ("o", "oui", "y"):
        print("\nInstallation manuelle :   pip install requests")
        return None
    import subprocess
    import sys as _sys
    try:
        subprocess.check_call([_sys.executable, "-m", "pip", "install", "requests"])
        import requests
        return requests
    except Exception as e:
        print(f"[X] Installation impossible : {e}")
        return None


def examiner(sess, rest: str, nom: str, interet: str) -> dict:
    """Examine une ressource : accès, volume, champs, modifiabilité."""
    bilan = {"nom": nom, "accessible": False, "nombre": None,
             "modifiable": False, "champs": [], "exemple": None}

    print(f"\n{'─' * 68}")
    print(f"  {nom.upper()}")
    print(f"  {interet}")
    print("─" * 68)

    # 1. Lecture : la ressource répond-elle, et combien contient-elle ?
    try:
        r = sess.get(f"{rest}/{nom}/", params={"limit": 3}, timeout=30)
        if r.status_code != 200:
            print(f"   ❌ GET → HTTP {r.status_code} — inaccessible avec ce compte.")
            return bilan
        bilan["accessible"] = True
        data = r.json()
        if isinstance(data, dict):
            bilan["nombre"] = data.get("count")
            echantillon = data.get("results") or []
        else:
            echantillon = data or []
            bilan["nombre"] = len(echantillon)

        n = bilan["nombre"]
        if n == 0:
            print("   ⚠  Ressource VIDE — aucun développement ne se justifie.")
        else:
            print(f"   ✅ {n if n is not None else '?'} élément(s) sur l'instance.")

        if echantillon:
            ex = echantillon[0]
            if isinstance(ex, dict):
                bilan["champs"] = sorted(ex.keys())
                bilan["exemple"] = ex
                print(f"\n   Champs ({len(ex)}) : " + ", ".join(bilan["champs"]))
                print("\n   Exemple :")
                for k, v in sorted(ex.items()):
                    apercu = json.dumps(v, ensure_ascii=False)[:62]
                    print(f"      {k:22} = {apercu}")
    except Exception as e:
        print(f"   ❌ Lecture impossible : {e}")
        return bilan

    # 2. Écriture : la ressource accepte-t-elle des modifications ?
    try:
        r = sess.options(f"{rest}/{nom}/", timeout=20)
        if r.status_code == 200:
            actions = (r.json().get("actions") or {})
            if actions.get("POST"):
                bilan["modifiable"] = True
                champs = actions["POST"]
                requis = [k for k, v in champs.items()
                          if v.get("required") and not v.get("read_only")]
                print(f"\n   ✏  MODIFIABLE — {len(champs)} champ(s) en écriture.")
                if requis:
                    print(f"      Champs obligatoires : {', '.join(sorted(requis))}")
            else:
                print("\n   👁  LECTURE SEULE (consultation uniquement).")
    except Exception:
        pass

    return bilan


def synthese(bilans: list):
    """Récapitule les ressources par intérêt réel, pour décider de la suite."""
    print(f"\n{'=' * 68}\n  SYNTHÈSE — où investir l'effort\n{'=' * 68}\n")

    exploitables, vides, fermees = [], [], []
    for b in bilans:
        if not b["accessible"]:
            fermees.append(b)
        elif b["nombre"] in (0, None) and not b["champs"]:
            vides.append(b)
        elif b["nombre"] == 0:
            vides.append(b)
        else:
            exploitables.append(b)

    if exploitables:
        print("   EXPLOITABLES (données présentes) :")
        for b in sorted(exploitables, key=lambda x: -(x["nombre"] or 0)):
            mode = "modifiable" if b["modifiable"] else "lecture seule"
            print(f"      • {b['nom']:18} {str(b['nombre']):>6} élément(s)   [{mode}]")
    if vides:
        print("\n   VIDES — aucun développement à prévoir :")
        print("      " + ", ".join(b["nom"] for b in vides))
    if fermees:
        print("\n   INACCESSIBLES avec ce compte :")
        print("      " + ", ".join(b["nom"] for b in fermees))

    print("""
   COMMENT LIRE CE BILAN
   • Une ressource VIDE ne justifie aucun développement, si prometteuse
     soit-elle sur le papier.
   • Une ressource en LECTURE SEULE permet d'AFFICHER (inventaire, diagnostic)
     mais pas de piloter.
   • Le nombre d'éléments indique l'usage réel qu'en font les enseignants :
     c'est le meilleur critère de priorité.

   Transmettez cette sortie complète.
""")


def run():
    requests = charger_requests()
    if requests is None:
        return

    base = (input("URL de l'instance [https://videos.utoulouse.fr] : ").strip()
            or "https://videos.utoulouse.fr").rstrip("/")
    token = input("Token (compte superutilisateur de préférence) : ").strip()
    if not token:
        print("[X] Token vide.")
        return

    rest = f"{base}/rest"
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Token {token}",
                         "Accept": "application/json"})

    print(f"\n{'=' * 68}")
    print(f"  EXPLORATION DE {len(A_EXAMINER)} RESSOURCES NON EXPLOITÉES")
    print(f"  Instance : {base}")
    print(f"{'=' * 68}")

    bilans = []
    for nom, interet in A_EXAMINER:
        bilans.append(examiner(sess, rest, nom, interet))

    synthese(bilans)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    except Exception:
        import traceback
        print("\n[ERREUR] La sonde a rencontré un problème :\n")
        traceback.print_exc()
    input("\nAppuyez sur Entrée pour fermer…")
