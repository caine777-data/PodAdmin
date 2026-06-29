#!/usr/bin/env python3
"""
verifier_lecture_restriction.py - Apprendre le format de restrict_access_to_groups
==================================================================================
Toutes nos tentatives d'ECRITURE ont echoue (code_name, id, /groups/, /accessgroups/).
La methode la plus sure : LIRE une video qui a DEJA une restriction par groupe.
Le format renvoye en lecture = le format attendu en ecriture.

Ce script :
  1. Scanne toutes les videos et repere celles dont restrict_access_to_groups
     est NON vide -> affiche le format EXACT (brut).
  2. Si aucune n'est trouvee, vous pourrez saisir le slug d'une video que vous
     aurez restreinte a un groupe DANS L'ADMIN DJANGO de Pod, et le script lira
     son champ pour reveler le format.

Lancer avec un token SUPERUTILISATEUR.

>>> PREPARATION (a faire une fois dans l'admin Django de Pod) :
    - Choisissez une video de test.
    - Cochez « Acces restreint » et ajoutez un groupe d'acces (ex. eformation).
    - Enregistrez.
    Puis lancez ce script et donnez le slug de cette video a l'etape 2.
"""

__author__      = "Cédric MONNA"
__contact__     = "cedricmonna@gmail.com"
__institution__ = "Université de Toulouse — MFCA"
__version__     = "0.1.0"
__date__        = "2026"

import json
import requests

DEFAULT_URL = "https://videos.utoulouse.fr"


def req(method, url, headers, **kw):
    try:
        r = requests.request(method, url, headers=headers, timeout=30, **kw)
        try:
            return r.status_code, (r.json() if r.text else None)
        except ValueError:
            return r.status_code, r.text[:300]
    except Exception as e:
        return None, {"_error": str(e)}


def main():
    print("=" * 70)
    print("  Sonde : format reel de restrict_access_to_groups (par lecture)")
    print("=" * 70)

    url = input(f"\nURL de l'instance [{DEFAULT_URL}] : ").strip() or DEFAULT_URL
    url = url.rstrip("/")
    token = input("Token SUPERUTILISATEUR : ").strip()
    if not token:
        print("[X] Pas de token. Abandon.")
        return
    rest = f"{url}/rest"
    headers = {"Authorization": f"Token {token}", "Accept": "application/json"}

    # ------------------------------------------------------------------ #
    # 1) Scan : chercher une video deja restreinte a un groupe
    # ------------------------------------------------------------------ #
    print("\n> 1. Recherche d'une video deja restreinte a un groupe ...")
    found = []
    next_url = f"{rest}/videos/"
    params = {"limit": 100}
    pages = 0
    while next_url and pages < 50:
        status, data = req("GET", next_url, headers, params=(params if pages == 0 else None))
        if not isinstance(data, dict):
            break
        for v in data.get("results", []):
            rag = v.get("restrict_access_to_groups")
            if rag:                       # non vide
                found.append(v)
        next_url = data.get("next")
        pages += 1
    if found:
        print(f"   {len(found)} video(s) avec restriction par groupe. Exemple(s) :")
        for v in found[:3]:
            print(f"\n   slug = {v.get('slug')}")
            print(f"   is_restricted             = {v.get('is_restricted')}")
            print(f"   restrict_access_to_groups = "
                  f"{json.dumps(v.get('restrict_access_to_groups'), ensure_ascii=False)}")
        print("\n   >>> Le contenu ci-dessus est LE FORMAT a reutiliser en ecriture.")
    else:
        print("   Aucune video restreinte a un groupe trouvee dans le scan.")

    # ------------------------------------------------------------------ #
    # 2) Lecture ciblee d'une video (a restreindre au prealable dans l'admin)
    # ------------------------------------------------------------------ #
    print("\n> 2. Lecture ciblee d'une video précise (Entree pour sauter)")
    print("    (Restreignez-la d'abord a un groupe DANS L'ADMIN DJANGO, puis donnez son slug.)")
    slug = input("    Slug (ou id) : ").strip()
    if slug:
        vurl = f"{rest}/videos/{slug}/"
        status, v = req("GET", vurl, headers)
        if status != 200:
            status, data = req("GET", f"{rest}/videos/", headers,
                               params={"search": slug, "limit": 50})
            res = data.get("results", []) if isinstance(data, dict) else []
            v = next((x for x in res if x.get("slug") == slug), None)
        if isinstance(v, dict):
            print(f"\n   slug = {v.get('slug')}")
            print(f"   is_restricted             = {v.get('is_restricted')}")
            print(f"   restrict_access_to_groups = "
                  f"{json.dumps(v.get('restrict_access_to_groups'), ensure_ascii=False)}")
            rag = v.get("restrict_access_to_groups")
            if rag:
                print("\n   >>> VOILA LE FORMAT EXACT attendu par l'API pour ce champ.")
            else:
                print("\n   (champ vide : la restriction n'a peut-etre pas ete enregistree,")
                print("    ou n'est pas exposee en lecture par l'API.)")
        else:
            print("   (video introuvable)")

    print("\n" + "=" * 70)
    print("  A RECOLLER : tout contenu de restrict_access_to_groups affiche")
    print("  (c'est la cle pour coder l'ecriture).")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    input("\nAppuyez sur Entree pour fermer...")
