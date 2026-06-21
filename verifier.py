#!/usr/bin/env python3
"""
verifier.py — Test de connexion + DÉCOUVERTE de l'API (version Windows)
Équivalent natif de scripts/00_test_connexion.sh, sans bash.

Lancement :  python verifier.py
(ou double-clic sur le fichier si Python est associé aux .py)
"""

import sys
import requests

DEFAULT_URL = "https://videos.utoulouse.fr"


def main():
    print("=" * 64)
    print("  Pod Téléverseur — Vérification de l'API")
    print("=" * 64)

    url = input(f"\nURL de l'instance [{DEFAULT_URL}] : ").strip() or DEFAULT_URL
    url = url.rstrip("/")
    print("\nCollez votre token ci-dessous (clic droit pour coller dans le terminal),")
    token = input("Token de service : ").strip()

    if not token:
        print("\n❌ Aucun token saisi. Abandon.")
        return

    rest = f"{url}/rest"
    headers = {"Authorization": f"Token {token}", "Accept": "application/json"}

    # 1) Le token fonctionne-t-il ?
    print("\n▶ 1. Test du token (GET /rest/videos/) ...")
    try:
        r = requests.get(f"{rest}/videos/", headers=headers,
                         params={"limit": 1}, timeout=20)
    except Exception as e:
        print(f"   ❌ Connexion impossible : {e}")
        return

    if r.status_code == 200:
        count = r.json().get("count", "?")
        print(f"   ✅ Connexion OK — {count} vidéo(s) accessibles avec ce token.")
    else:
        print(f"   ❌ Échec (HTTP {r.status_code}). Vérifiez l'URL et le token.")
        print(f"      Réponse : {r.text[:300]}")
        return

    # 2) DÉCOUVERTE : champs requis pour l'upload (méthode OPTIONS)
    print("\n▶ 2. Champs attendus par POST /rest/videos/ (OPTIONS) ...")
    try:
        r = requests.options(f"{rest}/videos/", headers=headers, timeout=20)
        post = r.json().get("actions", {}).get("POST", {})
        if not post:
            print("   (Le schéma n'est pas exposé — ouvrez "
                  f"{rest}/videos/ dans un navigateur connecté en admin.)")
        else:
            for name, meta in post.items():
                req = "★ REQUIS  " if meta.get("required") else "  optionnel"
                typ = meta.get("type", "?")
                print(f"   {req} {name:24} ({typ})")
    except Exception as e:
        print(f"   (Impossible de lire le schéma : {e})")

    # 3) Endpoints présents ?
    print("\n▶ 3. Endpoints disponibles ...")
    for ep in ["users", "types", "videos", "channels", "contributors"]:
        try:
            rr = requests.get(f"{rest}/{ep}/", headers=headers,
                             params={"limit": 1}, timeout=15)
            mark = "✅" if rr.status_code == 200 else "⚠️ "
            print(f"   {mark} /rest/{ep}/   (HTTP {rr.status_code})")
        except Exception as e:
            print(f"   ❌ /rest/{ep}/   ({e})")

    # 4) Types de vidéo disponibles (utile pour le réglage "Type")
    print("\n▶ 4. Types de vidéo ...")
    try:
        r = requests.get(f"{rest}/types/", headers=headers, timeout=15)
        for t in r.json().get("results", []):
            print(f"   • {t.get('title','?'):24} → {t.get('url','?')}")
    except Exception as e:
        print(f"   (non listés : {e})")

    # 5) DIAGNOSTIC de /rest/users/ (liste des utilisateurs)
    print("\n▶ 5. Contenu de /rest/users/ (diagnostic liste utilisateurs) ...")
    try:
        r = requests.get(f"{rest}/users/", headers=headers,
                         params={"limit": 5}, timeout=20)
        print(f"   HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict):
                print(f"   count total = {data.get('count')}")
                results = data.get("results", [])
                print(f"   {len(results)} entrée(s) sur cette page")
                if results:
                    print(f"   Champs disponibles : {list(results[0].keys())}")
                    for u in results:
                        print(f"     - username={u.get('username','?')} | "
                              f"url={u.get('url','(AUCUNE)')} | email={u.get('email','(absent)')}")
                else:
                    print("   ⚠️  Liste VIDE. Le compte rattaché au token n'a probablement")
                    print("       pas le droit de lister les utilisateurs (il faut un compte")
                    print("       superutilisateur / staff).")
            elif isinstance(data, list):
                print(f"   Réponse = liste de {len(data)} élément(s)")
                if data:
                    print(f"   Champs : {list(data[0].keys())}")
            else:
                print(f"   Réponse inattendue : {str(data)[:300]}")
        elif r.status_code in (401, 403):
            print("   ⚠️  Accès refusé : le compte du token n'a pas le droit de lister")
            print("       les utilisateurs. Utilisez un token d'un compte superutilisateur.")
        else:
            print(f"   Réponse : {r.text[:300]}")
    except Exception as e:
        print(f"   Erreur : {e}")

    print("\n" + "=" * 64)
    print("  Terminé. Notez les champs ★ REQUIS : ils doivent tous être")
    print("  envoyés par l'application (déjà le cas pour les champs standards).")
    print("=" * 64)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    # Pause pour que la fenêtre ne se ferme pas si lancé par double-clic
    input("\nAppuyez sur Entrée pour fermer...")
