#!/usr/bin/env python3
"""
verifier_encodage_500.py - Localiser le HTTP 500 et faire l'etat des encodages
==============================================================================
Symptome : le scan de l'onglet Encodage s'arrete avec
    HTTP 500 sur https://videos.utoulouse.fr/rest/videos/?limit=100
=> le serveur Pod plante en serialisant une page de videos. Souvent une SEULE
   video « cassee » (proprietaire supprime, relation manquante, upload
   interrompu...) fait echouer TOUTE la page, donc tout le scan.

Ce script :
  1. Pagine /rest/videos/ page par page (limit=100) et repere la 1re page
     qui renvoie 500 (offset fautif).
  2. Sur cette page fautive, teste enregistrement par enregistrement
     (limit=1, offset croissant) pour isoler LA video qui declenche le 500.
  3. Sur toutes les videos LISIBLES, fait l'etat des encodages
     (encodee / en cours / a probleme / brouillon) et liste les non-encodees.

100 % LECTURE SEULE (aucune modification). Token superutilisateur recommande.
"""

__author__      = "Cédric MONNA"
__contact__     = "cedricmonna@gmail.com"
__institution__ = "Université de Toulouse — MFCA"
__version__     = "0.1.0"
__date__        = "2026"

import requests

DEFAULT_URL = "https://videos.utoulouse.fr"
PAGE = 100


def get(url, headers, params=None):
    try:
        r = requests.get(url, headers=headers, params=params, timeout=40)
        try:
            body = r.json() if r.text else None
        except ValueError:
            body = r.text[:300]
        return r.status_code, body
    except Exception as e:
        return None, {"_error": str(e)}


def encode_state(v):
    if v.get("encoded"):
        return "encodee"
    if v.get("encoding_in_progress"):
        return "en cours"
    if v.get("is_draft"):
        return "brouillon"
    return "a probleme"


def main():
    print("=" * 70)
    print("  Sonde : localiser le HTTP 500 + etat des encodages")
    print("=" * 70)

    url = input(f"\nURL de l'instance [{DEFAULT_URL}] : ").strip() or DEFAULT_URL
    url = url.rstrip("/")
    token = input("Token SUPERUTILISATEUR : ").strip()
    if not token:
        return
    rest = f"{url}/rest"
    headers = {"Authorization": f"Token {token}", "Accept": "application/json"}
    videos_url = f"{rest}/videos/"

    # 1) Total declare
    print("\n> 1. Total declare par l'API :")
    status, data = get(videos_url, headers, {"limit": 1})
    total = data.get("count") if isinstance(data, dict) else None
    print(f"   count = {total}   (HTTP {status})")

    # 2) Pagination page par page
    print(f"\n> 2. Parcours page par page (limit={PAGE}) :")
    good = []
    bad_offset = None
    offset = 0
    while True:
        status, data = get(videos_url, headers, {"limit": PAGE, "offset": offset})
        if status == 200 and isinstance(data, dict):
            res = data.get("results", [])
            good.extend(res)
            print(f"   offset {offset:5} -> OK ({len(res)} videos)")
            if not data.get("next"):
                break
            offset += PAGE
        else:
            print(f"   offset {offset:5} -> HTTP {status}  <== PAGE FAUTIVE")
            bad_offset = offset
            break
        if total and offset > total + PAGE:
            break

    # 3) Isolation dans la page fautive
    if bad_offset is not None:
        print(f"\n> 3. Isolation de la video fautive (entre offset {bad_offset} "
              f"et {bad_offset + PAGE}) :")
        faulty = []
        probe_offset = bad_offset
        checked = 0
        while probe_offset < bad_offset + PAGE and checked < PAGE:
            s, d = get(videos_url, headers, {"limit": 1, "offset": probe_offset})
            if s == 200 and isinstance(d, dict):
                res = d.get("results", [])
                if res:
                    good.append(res[0])
                    mark = f"ok  ({res[0].get('slug')})"
                else:
                    mark = "ok (vide)"
            else:
                mark = f"HTTP {s}  <== FAUTIVE"
                faulty.append(probe_offset)
            print(f"   offset {probe_offset:5} (limit=1) -> {mark}")
            probe_offset += 1
            checked += 1
        if faulty:
            print(f"\n   >>> Enregistrement(s) fautif(s) a l'offset : {faulty}")
            print("       C'est cette (ces) video(s) qui fait planter la serialisation")
            print("       cote serveur. A corriger dans l'admin Django (ou via la DSI)")
            print("       en regardant les logs Django pour l'erreur exacte.")
    else:
        print("\n> 3. Aucune page fautive : tout est lisible via l'API.")

    # 4) Etat des encodages
    print(f"\n> 4. Etat des encodages ({len(good)} videos lisibles) :")
    counts = {"encodee": 0, "en cours": 0, "a probleme": 0, "brouillon": 0}
    non_encodees = []
    for v in good:
        st = encode_state(v)
        counts[st] = counts.get(st, 0) + 1
        if st in ("a probleme", "en cours"):
            non_encodees.append((v.get("slug"), st))
    print(f"   [OK]  encodees   : {counts['encodee']}")
    print(f"   [..]  en cours   : {counts['en cours']}")
    print(f"   [XX]  a probleme : {counts['a probleme']}")
    print(f"   [DR]  brouillons : {counts['brouillon']}")
    if non_encodees:
        print("\n   Videos non encodees / en cours (slug, etat) :")
        for slug, st in non_encodees[:40]:
            print(f"     - {slug}  [{st}]")
        if len(non_encodees) > 40:
            print(f"     ... +{len(non_encodees) - 40} autres")

    print("\n" + "=" * 70)
    if bad_offset is not None:
        print("  A RECOLLER : etape 2 (ou ca casse), etape 3 (offset fautif), etape 4.")
    else:
        print("  A RECOLLER : etape 4 (etat des encodages).")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    input("\nAppuyez sur Entree pour fermer...")
