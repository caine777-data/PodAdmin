#!/usr/bin/env python3
"""
verifier_chaine_video.py - Le champ `channel` d'une video est-il MODIFIABLE ?
=============================================================================
Diagnostique pourquoi l'ajout d'une video a une chaine depuis PodAdmin ne
prend pas effet cote serveur.

Verifie, en LECTURE SEULE :
  1. Le format reel du champ `channel` d'une video (liste d'URLs ? d'objets ?).
  2. Si `channel` est MODIFIABLE (present dans actions.PUT, non read_only)
     d'apres OPTIONS sur la video.
  3. La liste des chaines (pour avoir leurs URLs).

Puis, en OPTIN (on tape OUI), un TEST REEL reversible :
  - lit la chaine actuelle de la video,
  - PATCH pour y ajouter une chaine cible,
  - relit pour voir si ca a pris,
  - REMET l'etat initial.

Lancer avec un token SUPERUTILISATEUR :  python verifier_chaine_video.py
"""

__author__      = "Cédric MONNA"
__contact__     = "cedricmonna@gmail.com"
__institution__ = "Université de Toulouse — MFCA"
__version__     = "0.1.0"
__date__        = "2026"

import json
import requests

DEFAULT_URL = "https://videos.utoulouse.fr"


def get(url, headers, params=None):
    r = requests.get(url, headers=headers, params=params, timeout=20)
    try:
        return r.status_code, (r.json() if r.text else None)
    except ValueError:
        return r.status_code, r.text[:300]


def main():
    print("=" * 70)
    print("  Sonde : modification du champ `channel` d'une video")
    print("=" * 70)

    url = input(f"\nURL de l'instance [{DEFAULT_URL}] : ").strip() or DEFAULT_URL
    url = url.rstrip("/")
    token = input("Token SUPERUTILISATEUR : ").strip()
    if not token:
        print("[X] Pas de token. Abandon.")
        return
    slug = input("Slug de la video a tester (ex. 0061-video10) : ").strip()
    if not slug:
        print("[X] Pas de slug. Abandon.")
        return

    rest = f"{url}/rest"
    headers = {"Authorization": f"Token {token}", "Accept": "application/json"}
    vurl = f"{rest}/videos/{slug}/"

    # ------------------------------------------------------------------ #
    # 1) Etat actuel de la video : champ channel + is_draft
    # ------------------------------------------------------------------ #
    print(f"\n> 1. GET de la video {slug} ...")
    status, v = get(vurl, headers)
    if status != 200 or not isinstance(v, dict):
        print(f"   [X] HTTP {status} - video introuvable ? {v}")
        return
    print(f"   is_draft       = {v.get('is_draft')}")
    print(f"   channel (brut) = {json.dumps(v.get('channel'), ensure_ascii=False)}")
    ch_val = v.get("channel")
    if isinstance(ch_val, list):
        kinds = {type(x).__name__ for x in ch_val}
        print(f"   -> liste de : {kinds or 'vide'}")
    else:
        print(f"   -> type : {type(ch_val).__name__}")

    # ------------------------------------------------------------------ #
    # 2) OPTIONS : channel est-il modifiable ?
    # ------------------------------------------------------------------ #
    print("\n> 2. OPTIONS sur la video (champ channel modifiable ?) ...")
    r = requests.options(vurl, headers=headers, timeout=20)
    print(f"   Allow : {r.headers.get('Allow', '(non fourni)')}")
    writable = None
    try:
        actions = (r.json() or {}).get("actions", {})
        put = actions.get("PUT", {})
        if "channel" in put:
            meta = put["channel"]
            writable = not meta.get("read_only", False)
            print(f"   'channel' present dans actions.PUT : OUI")
            print(f"   read_only : {meta.get('read_only')}  | type : {meta.get('type')}  "
                  f"| required : {meta.get('required')}")
            print(f"   => MODIFIABLE : {writable}")
        else:
            print("   'channel' ABSENT de actions.PUT")
            print("   => probablement NON modifiable via PATCH (lecture seule).")
            writable = False
    except Exception as e:
        print(f"   (impossible de lire le schema OPTIONS : {e})")

    # ------------------------------------------------------------------ #
    # 3) Liste des chaines disponibles
    # ------------------------------------------------------------------ #
    print("\n> 3. Chaines disponibles ...")
    status, data = get(f"{rest}/channels/", headers, {"limit": 100})
    channels = data.get("results", []) if isinstance(data, dict) else (data or [])
    for c in channels[:20]:
        print(f"   - {c.get('title'):30} visible={c.get('visible')}  {c.get('url')}")
    if not channels:
        print("   (aucune chaine)")

    # ------------------------------------------------------------------ #
    # 4) TEST REEL optionnel (reversible)
    # ------------------------------------------------------------------ #
    print("\n> 4. Test reel d'ajout a une chaine (OPTIONNEL, reversible)")
    print("-" * 70)
    print("  Ce test va PATCHer la video pour y ajouter une chaine, verifier,")
    print("  puis REMETTRE l'etat initial. Tapez OUI pour lancer.")
    if input("  > ").strip() != "OUI":
        print("  -> Ignore.")
    else:
        target = input("  URL exacte de la chaine a ajouter (copiez ci-dessus) : ").strip()
        if target:
            # Etat initial (on normalise en liste d'URLs si possible)
            initial = v.get("channel") or []
            if isinstance(initial, str):
                initial = [initial]
            # Si ce sont des objets, on tente d'extraire l'url
            init_urls = []
            for x in initial:
                if isinstance(x, dict):
                    init_urls.append(x.get("url"))
                else:
                    init_urls.append(x)
            print(f"   Etat initial channel = {init_urls}")
            new_list = list(dict.fromkeys(init_urls + [target]))
            print(f"   PATCH channel = {new_list}")
            pr = requests.patch(vurl, headers=headers, json={"channel": new_list}, timeout=20)
            print(f"   Reponse PATCH : HTTP {pr.status_code}")
            # Relecture
            _, v2 = get(vurl, headers)
            after = v2.get("channel") if isinstance(v2, dict) else None
            print(f"   channel APRES = {json.dumps(after, ensure_ascii=False)}")
            took = bool(after) and (len(after) > len(initial))
            print(f"   => L'ajout a-t-il PRIS ? {'OUI' if took else 'NON'}")
            # Remise a l'etat initial
            requests.patch(vurl, headers=headers, json={"channel": init_urls}, timeout=20)
            print("   (etat initial remis)")

    # ------------------------------------------------------------------ #
    print("\n" + "=" * 70)
    print("  VERDICT")
    print("=" * 70)
    if writable is True:
        print("  Le champ `channel` est MODIFIABLE -> le souci vient du FORMAT")
        print("  envoye par l'appli (liste d'URLs vs objets). Corrigeable.")
    elif writable is False:
        print("  Le champ `channel` n'est PAS modifiable via l'API REST cote video.")
        print("  => L'ajout video<->chaine n'est pas faisable ainsi. Il faudra")
        print("     une autre voie (cote chaine, ou hors API). Recolle ce verdict.")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    input("\nAppuyez sur Entree pour fermer...")
