#!/usr/bin/env python3
"""
verifier_remplace_source.py - Peut-on remplacer le fichier d'une video + reencoder ?
====================================================================================
Objectif : verifier si l'API REST de Pod permet de REMPLACER le fichier source
d'une video EXISTANTE (en gardant slug / metadonnees / chaines / groupes), puis
de relancer l'encodage. Question ouverte : le champ `video` est-il modifiable
apres creation, ou en lecture seule ?

⚠️ POTENTIELLEMENT DESTRUCTIF : le test 3 remplace reellement le fichier d'une
   video. N'utiliser QUE sur une video JETABLE (creee pour le test), JAMAIS sur
   une vraie video. Le script propose d'abord un test NON destructif (OPTIONS),
   puis demande une confirmation explicite avant tout envoi de fichier.

Etapes :
  1. OPTIONS sur /videos/<id>/ : le champ `video` est-il present en PUT/PATCH,
     avec read_only=? required=? -> dit si le remplacement est meme envisageable.
  2. Lecture de l'etat avant (video, encoded, encoding_in_progress).
  3. (Optionnel, destructif) PATCH multipart avec un NOUVEAU fichier sur la video
     de test -> code HTTP + relecture (le champ `video` a-t-il change ?).
  4. (Optionnel) Relance de l'encodage (launch_encode_view) + relecture etat.

Lancer avec un token SUPERUTILISATEUR.
"""

__author__      = "Cédric MONNA"
__contact__     = "cedricmonna@gmail.com"
__institution__ = "Université de Toulouse — MFCA"
__version__     = "0.1.0"
__date__        = "2026"

import json
import os
import tempfile
import requests

DEFAULT_URL = "https://videos.utoulouse.fr"


def req(method, url, headers, **kw):
    try:
        r = requests.request(method, url, headers=headers, timeout=120, **kw)
        try:
            body = r.json() if r.text else None
        except ValueError:
            body = r.text[:400]
        return r.status_code, body
    except Exception as e:
        return None, {"_error": str(e)}


def main():
    print("=" * 70)
    print("  Sonde : remplacer le fichier d'une video existante + reencoder ?")
    print("=" * 70)

    url = input(f"\nURL de l'instance [{DEFAULT_URL}] : ").strip() or DEFAULT_URL
    url = url.rstrip("/")
    token = input("Token SUPERUTILISATEUR : ").strip()
    if not token:
        return
    rest = f"{url}/rest"
    headers = {"Authorization": f"Token {token}"}
    hj = dict(headers); hj["Accept"] = "application/json"

    ref = input("Slug (ou id) d'une video de TEST (jetable) : ").strip()
    if not ref:
        return
    vurl = f"{rest}/videos/{ref}/"
    status, v = req("GET", vurl, hj)
    if status != 200:
        status, data = req("GET", f"{rest}/videos/", hj, params={"search": ref, "limit": 50})
        res = data.get("results", []) if isinstance(data, dict) else []
        v = next((x for x in res if x.get("slug") == ref), None)
        if v:
            vurl = v.get("url")
    if not isinstance(v, dict):
        print("   [X] Video introuvable.")
        return
    slug = v.get("slug")
    print(f"\n   Video ciblee : {slug}   (url={vurl})")

    # ------------------------------------------------------------------ #
    # 1) OPTIONS : le champ `video` est-il modifiable ?
    # ------------------------------------------------------------------ #
    print("\n> 1. Schema OPTIONS du champ `video` :")
    status, opt = req("OPTIONS", vurl, hj)
    found = False
    if isinstance(opt, dict):
        actions = opt.get("actions", {})
        for verb in ("PUT", "PATCH", "POST"):
            fields = actions.get(verb, {})
            if "video" in fields:
                meta = fields["video"]
                print(f"   [{verb}] video : type={meta.get('type')}  "
                      f"required={meta.get('required')}  read_only={meta.get('read_only')}")
                found = True
        if not found:
            print("   Le champ `video` n'apparait PAS dans les actions PUT/PATCH/POST.")
            print("   (Souvent signe qu'il n'est pas modifiable apres creation.)")
            # Afficher quand meme les champs modifiables connus
            put = actions.get("PUT", {}) or actions.get("POST", {})
            if put:
                print("   Champs proposes :", ", ".join(sorted(put.keys()))[:300])
    else:
        print(f"   (OPTIONS indisponible : HTTP {status})")

    # ------------------------------------------------------------------ #
    # 2) Etat avant
    # ------------------------------------------------------------------ #
    print("\n> 2. Etat avant :")
    for k in ("video", "encoded", "encoding_in_progress", "get_encoding_step"):
        print(f"   {k:22} = {json.dumps(v.get(k), ensure_ascii=False)[:90]}")

    # ------------------------------------------------------------------ #
    # 3) Test destructif (optionnel) : PATCH avec un nouveau fichier
    # ------------------------------------------------------------------ #
    print("\n> 3. Test de REMPLACEMENT du fichier (DESTRUCTIF)")
    print("   ⚠️  Ceci envoie un nouveau fichier sur la video de test.")
    go = input("   Taper EXACTEMENT 'REMPLACER' pour tester (sinon Entree pour sauter) : ").strip()
    if go == "REMPLACER":
        src = input("   Chemin d'un fichier video a envoyer (Entree = petit fichier "
                    "bidon genere) : ").strip()
        tmp = None
        if not src:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            tmp.write(os.urandom(200000)); tmp.close()   # ~200 Ko (bidon)
            src = tmp.name
            print(f"   (fichier bidon genere : {src} — ne sera pas un vrai .mp4 encodable)")
        if os.path.isfile(src):
            fname = os.path.basename(src)
            with open(src, "rb") as fh:
                files = {"video": (fname, fh, "application/octet-stream")}
                status, body = req("PATCH", vurl, headers, files=files)
            print(f"   PATCH (nouveau fichier) -> HTTP {status}")
            if status and status >= 400:
                print(f"      corps : {json.dumps(body, ensure_ascii=False)[:300]}")
            # Relecture
            s2, v2 = req("GET", vurl, hj)
            print(f"   video apres = {json.dumps(v2.get('video') if isinstance(v2, dict) else None, ensure_ascii=False)[:90]}")
            changed = (isinstance(v2, dict) and v2.get("video") != v.get("video"))
            print(f"   => FICHIER REMPLACE ? {'OUI' if changed else 'NON (inchange)'}")
        else:
            print("   [X] Fichier introuvable.")
        if tmp:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

        # -------------------------------------------------------------- #
        # 4) Relancer l'encodage (optionnel)
        # -------------------------------------------------------------- #
        enc = input("\n> 4. Relancer l'encodage maintenant ? (o/N) : ").strip().lower()
        if enc == "o":
            s, b = req("GET", f"{rest}/launch_encode_view/", hj, params={"slug": slug})
            print(f"   launch_encode_view -> HTTP {s}  {json.dumps(b, ensure_ascii=False)[:150]}")
            s2, v3 = req("GET", vurl, hj)
            if isinstance(v3, dict):
                print(f"   encoding_in_progress apres = {v3.get('encoding_in_progress')}")
    else:
        print("   (test destructif saute — on garde juste le diagnostic OPTIONS)")

    print("\n" + "=" * 70)
    print("  A RECOLLER : etape 1 (le champ `video` est-il en PUT/PATCH, read_only ?)")
    print("  et, si teste, etape 3 (HTTP + fichier remplace ?) et 4 (encodage).")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    input("\nAppuyez sur Entree pour fermer...")
