#!/usr/bin/env python3
"""
verifier_draft_encode.py - Pourquoi une video reste en brouillon ?
==================================================================
Hypothese : Pod refuse de publier (is_draft=False) une video qui n'est PAS
encore encodee -> le PATCH passe (HTTP 200) mais le serveur reimpose draft.

Ce script, sur UNE video :
  1. Lit son etat : is_draft, is_restricted, encoded, encoding_in_progress,
     get_encoding_step, restrict_access_to_groups.
  2. PATCH is_draft=False SEUL -> code HTTP.
  3. Relit is_draft : a-t-il vraiment change ?
  => Si is_draft revient a True, c'est le serveur qui refuse (encodage).

Lancer avec un token SUPERUTILISATEUR.
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
    print("  Sonde : une video reste-t-elle en brouillon faute d'encodage ?")
    print("=" * 70)

    url = input(f"\nURL de l'instance [{DEFAULT_URL}] : ").strip() or DEFAULT_URL
    url = url.rstrip("/")
    token = input("Token SUPERUTILISATEUR : ").strip()
    if not token:
        return
    ref = input("Slug (ou id) de la video qui RESTE en brouillon : ").strip()
    rest = f"{url}/rest"
    headers = {"Authorization": f"Token {token}", "Accept": "application/json"}

    # Résoudre la vidéo
    vurl = f"{rest}/videos/{ref}/"
    status, v = req("GET", vurl, headers)
    if status != 200:
        status, data = req("GET", f"{rest}/videos/", headers,
                           params={"search": ref, "limit": 50})
        res = data.get("results", []) if isinstance(data, dict) else []
        v = next((x for x in res if x.get("slug") == ref), None)
        if v:
            vurl = v.get("url")
    if not isinstance(v, dict):
        print("   [X] Video introuvable.")
        return

    print(f"\n> 1. Etat actuel de {v.get('slug')!r} :")
    for k in ("is_draft", "is_restricted", "encoded", "encoding_in_progress",
              "get_encoding_step", "restrict_access_to_groups"):
        print(f"   {k:26} = {json.dumps(v.get(k), ensure_ascii=False)}")

    print("\n> 2. PATCH is_draft=False (seul) ...")
    status, body = req("PATCH", vurl, headers, json={"is_draft": False})
    print(f"   PATCH -> HTTP {status}")
    if status and status >= 400:
        print(f"   corps : {json.dumps(body, ensure_ascii=False)[:300]}")

    print("\n> 3. Relecture de is_draft ...")
    status, v2 = req("GET", vurl, headers)
    after = v2.get("is_draft") if isinstance(v2, dict) else None
    print(f"   is_draft apres = {after}")

    print("\n" + "=" * 70)
    if after is False:
        print("  => Le serveur ACCEPTE de publier : is_draft est bien passe a False.")
        print("     Le souci venait donc d'ailleurs (version, ou PATCH non envoye).")
    else:
        print("  => Le serveur REFUSE/REIMPOSE le brouillon (is_draft toujours True).")
        print("     Cause probable : la video n'est pas ENCODEE (voir 'encoded' a l'etape 1).")
        print("     Il faut l'encoder d'abord, puis elle pourra etre publiee/restreinte.")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    input("\nAppuyez sur Entree pour fermer...")
