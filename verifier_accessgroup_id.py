#!/usr/bin/env python3
"""
verifier_accessgroup_id.py - Adresser un groupe d'acces par ID + restreindre
============================================================================
Recoupement doc + tests : restrict_access_to_groups d'une video attend une
URL d'ACCESSGROUP (et non /groups/), tres probablement par ID numerique
(/rest/accessgroups/<id>/) et NON par code_name (qui donnait 404 / objet
introuvable). La liste n'expose pas l'id ; on le decouvre en sondant les
routes de detail numeriques.

Etapes :
  1. Liste les accessgroups (code_name).
  2. Sonde /rest/accessgroups/<n>/ pour n = 1..MAX :
     - 200 => on note l'id et le code_name correspondant (on a enfin l'URL !).
  3. Pour le code_name demande, recupere l'URL /accessgroups/<id>/ trouvee.
  4. TEST REEL REVERSIBLE : PATCH restrict_access_to_groups=[cette URL] +
     is_restricted=True sur une video de test, verifie, puis remet l'etat initial.

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
MAX_ID = 40   # plage d'ids a sonder


def req(method, url, headers, **kw):
    try:
        r = requests.request(method, url, headers=headers, timeout=20, **kw)
        try:
            body = r.json() if r.text else None
        except ValueError:
            body = r.text[:300]
        return r.status_code, body
    except Exception as e:
        return None, {"_error": str(e)}


def norm_urls(val):
    if not val:
        return []
    if isinstance(val, str):
        val = [val]
    return [x.get("url") if isinstance(x, dict) else x for x in val]


def main():
    print("=" * 70)
    print("  Sonde : id adressable d'un accessgroup + restriction video")
    print("=" * 70)

    url = input(f"\nURL de l'instance [{DEFAULT_URL}] : ").strip() or DEFAULT_URL
    url = url.rstrip("/")
    token = input("Token SUPERUTILISATEUR : ").strip()
    if not token:
        print("[X] Pas de token. Abandon.")
        return
    rest = f"{url}/rest"
    headers = {"Authorization": f"Token {token}", "Accept": "application/json"}

    # 1) Liste
    print("\n> 1. Accessgroups (liste) :")
    status, data = req("GET", f"{rest}/accessgroups/", headers, params={"limit": 50})
    groups = data.get("results", []) if isinstance(data, dict) else (data or [])
    for g in groups:
        print(f"   - {g.get('code_name')}")

    # 2) Sonde des routes de detail numeriques
    print(f"\n> 2. Sonde des routes /accessgroups/<id>/ (1..{MAX_ID}) :")
    id_to_code = {}
    for n in range(1, MAX_ID + 1):
        gurl = f"{rest}/accessgroups/{n}/"
        status, body = req("GET", gurl, headers)
        if status == 200 and isinstance(body, dict):
            code = body.get("code_name")
            id_to_code[n] = code
            print(f"   id={n:<3} -> 200  code_name={code!r}  url={gurl}")
    if not id_to_code:
        print("   Aucune route /accessgroups/<id>/ ne repond. L'adressage par id")
        print("   est donc exclu lui aussi -> on relancera autrement.")
        return

    # 3) Choisir le code_name a restreindre
    code = input("\n> 3. code_name du groupe a tester (ex. eformation) : ").strip()
    target_url = None
    for n, c in id_to_code.items():
        if c == code:
            target_url = f"{rest}/accessgroups/{n}/"
            break
    if not target_url:
        print(f"   [X] '{code}' introuvable parmi les ids sondes. Ids vus : {id_to_code}")
        return
    print(f"   URL d'adressage trouvee : {target_url}")

    # 4) Test reel reversible sur une video
    vslug = input("\n> 4. Slug (ou id) d'une video de TEST : ").strip()
    if not vslug:
        return
    vurl = f"{rest}/videos/{vslug}/"
    status, v = req("GET", vurl, headers)
    if status != 200:
        status, data = req("GET", f"{rest}/videos/", headers,
                           params={"search": vslug, "limit": 50})
        res = data.get("results", []) if isinstance(data, dict) else []
        v = next((x for x in res if x.get("slug") == vslug), None)
        if v:
            vurl = v.get("url")
    if not isinstance(v, dict):
        print("   (video introuvable)")
        return
    init_restr = v.get("is_restricted")
    init_g = norm_urls(v.get("restrict_access_to_groups"))
    print(f"   etat initial : is_restricted={init_restr}  groups={init_g}")
    payload = {"restrict_access_to_groups": list(dict.fromkeys(init_g + [target_url])),
               "is_restricted": True}
    status, body = req("PATCH", vurl, headers, json=payload)
    print(f"   PATCH -> HTTP {status}")
    if status and status >= 400:
        print(f"   corps : {json.dumps(body, ensure_ascii=False)[:300]}")
    status, v2 = req("GET", vurl, headers)
    after = norm_urls(v2.get("restrict_access_to_groups")) if isinstance(v2, dict) else []
    took = len(after) > len(init_g)
    print(f"   groups apres = {after}")
    print(f"   => GROUPE ACCEPTE SUR LA VIDEO ? {'OUI 🎉' if took else 'NON'}")
    # Remise initiale
    req("PATCH", vurl, headers,
        json={"restrict_access_to_groups": init_g, "is_restricted": init_restr})
    print("   (etat initial remis)")

    print("\n" + "=" * 70)
    if took:
        print("  VICTOIRE : restrict_access_to_groups accepte /accessgroups/<id>/.")
        print("  => On peut coder la restriction d'une video (et d'une chaine entiere")
        print("     par propagation) a un groupe d'acces.")
    else:
        print("  Toujours refuse. Recolle le corps d'erreur, on ajustera le format.")
    print("=" * 70)
    print("  A RECOLLER : etape 2 (ids->code_name) et etape 4 (verdict).")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    input("\nAppuyez sur Entree pour fermer...")
