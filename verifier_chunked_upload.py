#!/usr/bin/env python3
"""
verifier_chunked_upload.py - Trouver et tester l'upload par morceaux (chunked)
==============================================================================
Constat : un POST monobloc (tout le fichier d'un coup) est coupe par le
serveur/proxy sur les GROS fichiers (SSLEOFError vers la fin), alors que
l'interface web de Pod, elle, passe -> elle televerse en MORCEAUX (chunks).
Esup-Pod utilise tres probablement 'drf-chunked-upload'.

Protocole drf-chunked-upload :
  1. PUT du 1er morceau sur l'endpoint chunké, en-tete
     Content-Range: bytes {debut}-{fin}/{total}, fichier dans files={'file': ...}
     -> le serveur renvoie {id, url, offset}.
  2. PUT des morceaux suivants sur l'URL renvoyee (.../<id>/), meme en-tete.
  3. POST final sur cette URL avec le md5 hex du fichier complet -> upload fini.

Ce script :
  A. Explore /rest/ pour DECOUVRIR l'endpoint chunké (mot-cle 'chunk').
  B. Si trouve, teste le protocole complet sur un PETIT fichier (genere ici),
     de facon reversible autant que possible (on n'attache a aucune video Pod ;
     drf-chunked-upload cree juste un upload temporaire cote serveur).

Lancer avec un token SUPERUTILISATEUR.
"""

__author__      = "Cédric MONNA"
__contact__     = "cedricmonna@gmail.com"
__institution__ = "Université de Toulouse — MFCA"
__version__     = "0.1.0"
__date__        = "2026"

import hashlib
import json
import os
import tempfile
import requests

DEFAULT_URL = "https://videos.utoulouse.fr"
CHUNK = 1024 * 1024          # 1 Mo par morceau (petit, pour le test)


def req(method, url, headers, **kw):
    try:
        r = requests.request(method, url, headers=headers, timeout=60, **kw)
        try:
            body = r.json() if r.text else None
        except ValueError:
            body = r.text[:400]
        return r.status_code, body
    except Exception as e:
        return None, {"_error": str(e)}


def main():
    print("=" * 70)
    print("  Sonde : upload par morceaux (chunked) d'Esup-Pod")
    print("=" * 70)

    url = input(f"\nURL de l'instance [{DEFAULT_URL}] : ").strip() or DEFAULT_URL
    url = url.rstrip("/")
    token = input("Token SUPERUTILISATEUR : ").strip()
    if not token:
        return
    rest = f"{url}/rest"
    headers = {"Authorization": f"Token {token}"}
    hj = dict(headers); hj["Accept"] = "application/json"

    # ------------------------------------------------------------------ #
    # A) Decouverte de l'endpoint chunké via la racine /rest/
    # ------------------------------------------------------------------ #
    print("\n> A. Exploration de /rest/ pour trouver l'endpoint chunké ...")
    status, root = req("GET", f"{rest}/", hj)
    candidates = []
    if isinstance(root, dict):
        for name, link in root.items():
            if "chunk" in name.lower() or "chunk" in str(link).lower():
                candidates.append((name, link))
        print("   Endpoints de la racine :")
        for name, link in root.items():
            mark = "  <-- CHUNK ?" if ("chunk" in name.lower()) else ""
            print(f"     {name:30} {link}{mark}")
    # Repli : chemins classiques a tester
    guesses = [f"{rest}/chunked_upload/", f"{rest}/chunkedupload/",
               f"{rest}/dash/", f"{url}/podfile/chunk_upload/"]
    if candidates:
        chunk_url = candidates[0][1]
    else:
        chunk_url = None
        print("\n   Aucun endpoint 'chunk' evident. Test de chemins classiques :")
        for g in guesses:
            s, _ = req("OPTIONS", g, hj)
            print(f"     OPTIONS {g} -> HTTP {s}")
            if s and s < 400:
                chunk_url = g
                break
    if not chunk_url:
        chunk_url = input("\n   Endpoint chunké introuvable. Collez-le si vous le "
                          "connaissez (ou Entree pour arreter) : ").strip()
        if not chunk_url:
            print("   Abandon : pas d'endpoint chunké.")
            return
    print(f"\n   Endpoint chunké utilise : {chunk_url}")

    # ------------------------------------------------------------------ #
    # B) Test du protocole sur un petit fichier genere
    # ------------------------------------------------------------------ #
    print("\n> B. Test du protocole sur un petit fichier (3 Mo) ...")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
    try:
        data = os.urandom(3 * CHUNK)      # 3 Mo -> 3 morceaux d'1 Mo
        tmp.write(data); tmp.close()
        total = len(data)
        md5 = hashlib.md5(data).hexdigest()
        fname = "test_chunk_podadmin.bin"

        upload_url = chunk_url
        offset = 0
        first = True
        with open(tmp.name, "rb") as fh:
            while True:
                chunk = fh.read(CHUNK)
                if not chunk:
                    break
                start = offset
                end = offset + len(chunk) - 1
                crange = f"bytes {start}-{end}/{total}"
                h = dict(headers)
                h["Content-Range"] = crange
                # 1er morceau -> PUT sur l'endpoint ; suivants -> PUT sur l'URL renvoyee
                s, body = req("PUT", upload_url, h,
                              data={"filename": fname},
                              files={"file": (fname, chunk, "application/octet-stream")})
                print(f"   PUT {crange} -> HTTP {s}")
                if s and s >= 400:
                    print(f"      corps : {json.dumps(body, ensure_ascii=False)[:250]}")
                    print("   [X] Un morceau est refuse -> on stoppe. (Recolle le corps.)")
                    break
                if isinstance(body, dict):
                    if first and body.get("url"):
                        upload_url = body["url"]     # bascule sur l'URL de l'upload
                    if body.get("offset") is not None:
                        offset = body["offset"]
                    else:
                        offset = end + 1
                else:
                    offset = end + 1
                first = False
            else:
                # Finalisation : POST md5
                s, body = req("POST", upload_url, hj, data={"md5": md5})
                print(f"   POST (finalisation md5) -> HTTP {s}")
                print(f"      reponse : {json.dumps(body, ensure_ascii=False)[:250]}")
                if s and s < 400:
                    print("\n   => LE PROTOCOLE CHUNKED FONCTIONNE 🎉")
                    print("      On peut reimplementer l'upload en morceaux dans PodAdmin.")
                    # Nettoyage : DELETE de l'upload temporaire si possible
                    if isinstance(body, dict) and body.get("url"):
                        ds, _ = req("DELETE", body["url"], hj)
                        print(f"      (nettoyage DELETE -> HTTP {ds})")
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

    print("\n" + "=" * 70)
    print("  A RECOLLER : etape A (liste des endpoints /rest/) et etape B")
    print("  (les codes HTTP des PUT + le POST final).")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    input("\nAppuyez sur Entree pour fermer...")
