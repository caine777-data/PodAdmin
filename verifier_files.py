#!/usr/bin/env python3
"""
verifier_files.py - Comment deposer un fichier dans /rest/files/ ?
==================================================================
Dernier maillon avant le module Sous-titres. On sait que /rest/tracks/ pointe
vers un fichier via `src` = URL d'un /rest/files/<id>/. Pour creer ce fichier,
/rest/files/ exige `file`, `name`, `folder` (requis) et `created_by` (requis).
Ce script eclaircit le format attendu de `folder` et `created_by`.

Verifie, en LECTURE SEULE (OPTIONS + GET) :
  1. Schema POST de /files/ (format de folder / created_by).
  2. Exemples de fichiers existants (notamment ceux references par des tracks)
     -> format reel de folder et created_by.
  3. Existe-t-il un endpoint de DOSSIERS (/folders/, /userfolders/...) pour
     savoir quel `folder` utiliser, et comment le trouver pour une video donnee.

NE CREE / NE MODIFIE RIEN. Sans danger pour la production.

Lancer avec un token SUPERUTILISATEUR :  python verifier_files.py
"""

__author__      = "Cédric MONNA"
__contact__     = "cedricmonna@gmail.com"
__institution__ = "Université de Toulouse — MFCA"
__version__     = "0.1.0"
__date__        = "2026"

import json
import requests

DEFAULT_URL = "https://videos.utoulouse.fr"

# Endpoints candidats pour les dossiers (folder)
FOLDER_CANDIDATES = ["/folders/", "/folder/", "/userfolders/", "/userfolder/",
                     "/user_folders/", "/myfolders/"]


def get(url, headers, params=None):
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        try:
            return r.status_code, (r.json() if r.text else None)
        except ValueError:
            return r.status_code, r.text[:200]
    except Exception as e:
        return None, {"_error": str(e)}


def main():
    print("=" * 70)
    print("  Sonde : depot de fichiers /rest/files/ (pour les sous-titres)")
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
    # 1) Schema POST de /files/
    # ------------------------------------------------------------------ #
    print("\n> 1. OPTIONS de /files/ (champs folder / created_by) ...")
    try:
        r = requests.options(f"{rest}/files/", headers=headers, timeout=20)
        post = (r.json() or {}).get("actions", {}).get("POST", {})
    except Exception as e:
        print(f"   [X] Echec OPTIONS : {e}")
        post = {}
    for field in ("folder", "name", "file", "created_by"):
        meta = post.get(field, {})
        print(f"   [{field:11}] type={meta.get('type')}  requis={meta.get('required')}"
              f"  read_only={meta.get('read_only')}")
        if meta.get("choices"):
            print(f"       choices (extrait) : "
                  f"{[c.get('value') for c in meta['choices'][:5]]} ...")

    # ------------------------------------------------------------------ #
    # 2) Fichiers existants : format reel de folder / created_by
    # ------------------------------------------------------------------ #
    print("\n> 2. Fichiers existants (format reel de folder / created_by) ...")
    status, data = get(f"{rest}/files/", headers, {"limit": 5})
    results = data.get("results", []) if isinstance(data, dict) else (data or [])
    if not results:
        print("   (aucun fichier listable)")
    for f in results:
        print(f"   - id={f.get('id')}  name={f.get('name')!r}")
        print(f"       folder     = {f.get('folder')!r}")
        print(f"       created_by = {f.get('created_by')!r}")
        print(f"       file       = {f.get('file')!r}")

    # Inspecter precisement un fichier reference par un track (ex. /files/9/)
    print("\n   Detail d'un fichier reference par un track (ex. /files/9/) :")
    status, f9 = get(f"{rest}/files/9/", headers)
    if isinstance(f9, dict):
        print(f"     {json.dumps(f9, ensure_ascii=False)[:400]}")
    else:
        print(f"     (HTTP {status})")

    # ------------------------------------------------------------------ #
    # 3) Endpoint de dossiers ?
    # ------------------------------------------------------------------ #
    print("\n> 3. Endpoint de DOSSIERS (pour connaitre 'folder') ...")
    folder_ep = None
    for ep in FOLDER_CANDIDATES:
        status, data = get(f"{rest}{ep}", headers, {"limit": 3})
        tag = {200: "[OK] existe", 401: "[401]", 403: "[403]",
               404: "[--] absent", None: "[err]"}.get(status, f"[{status}]")
        print(f"   {ep:16} -> {tag}")
        if status == 200 and not folder_ep:
            folder_ep = ep
            results = data.get("results", []) if isinstance(data, dict) else (data or [])
            for fo in results[:3]:
                print(f"       ex: {json.dumps(fo, ensure_ascii=False)[:200]}")
            # Champs filtrables ?
            try:
                ro = requests.options(f"{rest}{ep}", headers=headers, timeout=15)
                print(f"       Allow : {ro.headers.get('Allow','(non fourni)')}")
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    print("\n" + "=" * 70)
    print("  A RECOLLER : etape 1 (folder/created_by), etape 2 (formats reels),")
    print("  etape 3 (endpoint de dossiers + exemple).")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    input("\nAppuyez sur Entree pour fermer...")
