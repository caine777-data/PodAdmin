#!/usr/bin/env python3
"""
verifier_champ_360.py — Sonde : confirmer le champ « vidéo 360 » de l'API Pod
=============================================================================
Avant d'ajouter l'option « vidéo 360 » à PodAdmin, on VÉRIFIE sur l'instance
le nom EXACT du champ et son type, plutôt que de le supposer. Dans Esup-Pod,
ce champ s'appelle très probablement « is_360 » (booléen), mais le seul juge
de paix est l'instance elle-même.

La sonde fait deux choses, sans rien modifier :
  1. OPTIONS sur /rest/videos/ → liste les champs déclarés (nom, type, requis) ;
     on y cherche tout champ contenant « 360 ».
  2. GET d'une vidéo réelle → montre la valeur effective du champ, pour lever
     tout doute sur son nom tel qu'il est sérialisé.

Sonde autonome. Filet anti-fermeture en fin de script.
"""

__author__  = "Cédric MONNA"
__version__ = "1.0.0"

import json


def run():
    import requests

    base = input("URL de l'instance [https://videos.utoulouse.fr] : ").strip() \
        or "https://videos.utoulouse.fr"
    base = base.rstrip("/")
    token = input("Token (Bearer) : ").strip()
    if not token:
        print("[X] Token vide — impossible d'interroger l'API.")
        return

    rest = f"{base}/rest"
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Token {token}",
                         "Accept": "application/json"})

    # ── 1. OPTIONS : schéma de la ressource vidéo ────────────────────────────
    print("\n> 1. OPTIONS /rest/videos/ (schéma des champs)…")
    try:
        r = sess.options(f"{rest}/videos/", timeout=30)
        print(f"   HTTP {r.status_code}")
        data = r.json()
        actions = (data.get("actions") or {}).get("POST") \
            or (data.get("actions") or {}).get("PUT") or {}
        if not actions:
            print("   (Aucun schéma d'action exposé — l'instance restreint peut-être OPTIONS.)")
        # Chercher les champs contenant « 360 »
        champs_360 = {nom: meta for nom, meta in actions.items() if "360" in nom.lower()}
        if champs_360:
            print("   ✅ Champ(s) « 360 » trouvé(s) :")
            for nom, meta in champs_360.items():
                t = meta.get("type", "?")
                req = meta.get("required", False)
                lbl = meta.get("label", "")
                print(f"      • {nom}  (type={t}, requis={req})  {lbl}")
        else:
            print("   ⚠ Aucun champ contenant « 360 » dans le schéma POST.")
            print("     Champs booléens disponibles (candidats) :")
            for nom, meta in actions.items():
                if meta.get("type") == "boolean":
                    print(f"      • {nom}")
    except Exception as e:
        print(f"   [X] Échec OPTIONS : {e}")

    # ── 2. GET d'une vidéo réelle : voir la valeur effective ─────────────────
    print("\n> 2. GET /rest/videos/?limit=1 (valeur réelle du champ)…")
    try:
        r = sess.get(f"{rest}/videos/", params={"limit": 1}, timeout=30)
        print(f"   HTTP {r.status_code}")
        results = r.json().get("results", [])
        if results:
            v = results[0]
            cle_360 = [k for k in v.keys() if "360" in k.lower()]
            if cle_360:
                for k in cle_360:
                    print(f"   ✅ Champ présent dans la réponse : {k} = {v.get(k)!r}")
            else:
                print("   ⚠ Aucune clé « 360 » dans la vidéo renvoyée. Clés disponibles :")
                print("     " + ", ".join(sorted(v.keys())))
        else:
            print("   (Aucune vidéo pour l'échantillon.)")
    except Exception as e:
        print(f"   [X] Échec GET : {e}")

    print("\n" + "-" * 64)
    print("Conclusion : le champ à utiliser dans PodAdmin est celui affiché en")
    print("« ✅ » ci-dessus (attendu : is_360, booléen). Une fois confirmé, on")
    print("l'ajoute au panneau de détail de l'onglet Vidéos.")
    print("-" * 64)


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
