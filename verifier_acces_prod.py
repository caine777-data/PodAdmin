#!/usr/bin/env python3
"""
verifier_acces_prod.py - Restriction par groupe (instance videos.utoulouse.fr)
==============================================================================
On SAIT desormais le format attendu (lu sur une vraie video) :
    restrict_access_to_groups = ["https://videos.utoulouse.fr/rest/accessgroups/<id>/"]

Mais la LISTE /accessgroups/ n'expose pas l'id. Ce script :
  1. Scanne les videos et collecte toutes les URLs d'accessgroups deja
     utilisees (-> on obtient les id reellement valides sur CETTE instance).
  2. Tente d'associer chaque URL d'accessgroup a un code_name lisible
     (en testant le GET de detail ; si indisponible, on garde juste l'URL).
  3. TEST REEL REVERSIBLE : PATCH d'une de ces URLs sur une video de TEST
     pour confirmer que l'ECRITURE passe (HTTP 200), puis remet l'etat initial.

Lancer avec un token SUPERUTILISATEUR, sur l'instance de PRODUCTION.
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


def norm_urls(val):
    if not val:
        return []
    if isinstance(val, str):
        val = [val]
    return [x.get("url") if isinstance(x, dict) else x for x in val]


def main():
    print("=" * 70)
    print("  Sonde PROD : restriction par groupe d'acces")
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
    # 1) Collecter les URLs d'accessgroups deja utilisees sur des videos
    # ------------------------------------------------------------------ #
    print("\n> 1. Collecte des URLs d'accessgroups depuis les videos ...")
    used = {}                       # url -> nb d'usages
    next_url, params, pages = f"{rest}/videos/", {"limit": 100}, 0
    while next_url and pages < 80:
        status, data = req("GET", next_url, headers, params=(params if pages == 0 else None))
        if not isinstance(data, dict):
            break
        for v in data.get("results", []):
            for g in norm_urls(v.get("restrict_access_to_groups")):
                used[g] = used.get(g, 0) + 1
        next_url = data.get("next")
        pages += 1
    if used:
        print(f"   {len(used)} URL(s) d'accessgroup trouvee(s) en usage :")
        for g, n in sorted(used.items()):
            print(f"     {g}   (sur {n} video(s))")
    else:
        print("   Aucune URL d'accessgroup en usage (aucune video restreinte a un groupe).")

    # ------------------------------------------------------------------ #
    # 2) Associer chaque URL a un code_name (best effort) + lister les groupes
    # ------------------------------------------------------------------ #
    print("\n> 2. Groupes d'acces disponibles (liste, sans id) :")
    status, data = req("GET", f"{rest}/accessgroups/", headers, params={"limit": 50})
    groups = data.get("results", []) if isinstance(data, dict) else (data or [])
    for g in groups:
        print(f"     code_name={g.get('code_name')!r}  display={g.get('display_name')!r}")
    # Tenter d'associer URL->code_name via le GET de detail (peut echouer)
    print("\n   Association URL -> code_name (si le GET de detail repond) :")
    url_to_code = {}
    for g in sorted(used.keys()):
        status, body = req("GET", g, headers)
        code = body.get("code_name") if isinstance(body, dict) else None
        url_to_code[g] = code
        print(f"     {g} -> {code if code else '(GET detail indisponible : HTTP %s)' % status}")

    # ------------------------------------------------------------------ #
    # 3) TEST REEL REVERSIBLE : ecrire une de ces URLs sur une video de test
    # ------------------------------------------------------------------ #
    print("\n> 3. Test reel d'ecriture (reversible)")
    if not used:
        print("   (pas d'URL d'accessgroup connue -> impossible de tester l'ecriture)")
        return
    print("   URLs disponibles :")
    for g in sorted(used.keys()):
        print(f"     {g}")
    target = input("   URL d'accessgroup a ecrire (copiez ci-dessus) : ").strip()
    vslug = input("   Slug (ou id) d'une video de TEST : ").strip()
    if not target or not vslug:
        print("   (test saute)")
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
    payload = {"restrict_access_to_groups": list(dict.fromkeys(init_g + [target])),
               "is_restricted": True}
    status, body = req("PATCH", vurl, headers, json=payload)
    print(f"   PATCH -> HTTP {status}")
    if status and status >= 400:
        print(f"   corps : {json.dumps(body, ensure_ascii=False)[:300]}")
    status, v2 = req("GET", vurl, headers)
    after = norm_urls(v2.get("restrict_access_to_groups")) if isinstance(v2, dict) else []
    took = target.rstrip("/") in [u.rstrip("/") for u in after]
    print(f"   groups apres = {after}")
    print(f"   => ECRITURE ACCEPTEE ? {'OUI 🎉' if took else 'NON'}")
    req("PATCH", vurl, headers,
        json={"restrict_access_to_groups": init_g, "is_restricted": init_restr})
    print("   (etat initial remis)")

    print("\n" + "=" * 70)
    if took:
        print("  CONFIRME : on peut affecter un groupe d'acces a une video par l'API.")
        print("  Reste a relier chaque URL a un nom lisible (etape 2) pour l'interface.")
    print("  A RECOLLER : etapes 1, 2 et le verdict de l'etape 3.")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    input("\nAppuyez sur Entree pour fermer...")
