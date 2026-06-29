#!/usr/bin/env python3
"""
verifier_accessgroups_cycle.py - Cycle de vie complet d'un groupe d'acces
=========================================================================
Avant de coder une gestion des groupes d'acces (creation / membres /
suppression), on teste TOUT le cycle de vie via l'API, en mode REVERSIBLE :
on cree un groupe JETABLE de test, on le manipule, puis on le supprime.

Etapes testees :
  1. LISTER les groupes d'acces (rappel) + sonder leurs URLs par id.
  2. LISTER des owners (format /rest/owners/<id>/) pour avoir des membres a tester.
  3. CREER un groupe jetable (POST /accessgroups/) avec code_name + sites
     (+ users au passage). On note s'il recoit une url/id.
  4. CIBLER le groupe cree : trouver son URL adressable (id) en re-sondant.
  5. AJOUTER / RETIRER des membres : on teste plusieurs methodes
     (PATCH, PUT) sur le champ `users` pour voir si l'une est acceptee.
  6. SUPPRIMER le groupe jetable (DELETE) pour ne rien laisser trainer.

⚠️ Cree reellement un groupe nomme 'zz_test_podadmin' puis le supprime.
   N'utilise QUE ce groupe jetable, jamais un groupe reel.

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
TEST_CODE = "zz_test_podadmin"     # code_name du groupe jetable
MAX_ID = 80


def req(method, url, headers, **kw):
    try:
        r = requests.request(method, url, headers=headers, timeout=30, **kw)
        try:
            body = r.json() if r.text else None
        except ValueError:
            body = r.text[:400]
        return r.status_code, body
    except Exception as e:
        return None, {"_error": str(e)}


def norm_urls(val):
    if not val:
        return []
    if isinstance(val, str):
        val = [val]
    return [x.get("url") if isinstance(x, dict) else x for x in val]


def find_group_url_by_code(rest, headers, code, max_id=MAX_ID):
    """Sonde /accessgroups/<n>/ pour retrouver l'URL adressable d'un code_name."""
    for n in range(1, max_id + 1):
        u = f"{rest}/accessgroups/{n}/"
        status, body = req("GET", u, headers)
        if status == 200 and isinstance(body, dict) and body.get("code_name") == code:
            return u
    return None


def main():
    print("=" * 70)
    print("  Sonde : cycle de vie d'un groupe d'acces (creation/membres/suppression)")
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
    # 1) Lister groupes + sites
    # ------------------------------------------------------------------ #
    print("\n> 1. Groupes d'acces existants :")
    status, data = req("GET", f"{rest}/accessgroups/", headers, params={"limit": 50})
    groups = data.get("results", []) if isinstance(data, dict) else (data or [])
    for g in groups:
        print(f"   - {g.get('code_name')}")
    # Un site est requis a la creation
    status, sdata = req("GET", f"{rest}/sites/", headers, params={"limit": 5})
    sites = sdata.get("results", []) if isinstance(sdata, dict) else (sdata or [])
    site_url = sites[0].get("url") if sites else None
    print(f"   Site utilise pour la creation : {site_url}")
    if not site_url:
        print("   [X] Pas de site -> creation impossible. Abandon.")
        return

    # ------------------------------------------------------------------ #
    # 2) Lister des owners (membres potentiels)
    # ------------------------------------------------------------------ #
    print("\n> 2. Quelques owners (format des membres) :")
    status, odata = req("GET", f"{rest}/owners/", headers, params={"limit": 5})
    owners = odata.get("results", []) if isinstance(odata, dict) else (odata or [])
    for o in owners[:5]:
        print(f"   - {o.get('url')}  (user={o.get('user')})")
    owner_a = owners[0].get("url") if len(owners) > 0 else None
    owner_b = owners[1].get("url") if len(owners) > 1 else None
    print(f"   Membre A (creation+ajout) : {owner_a}")
    print(f"   Membre B (ajout)          : {owner_b}")

    # ------------------------------------------------------------------ #
    # 3) Creer un groupe jetable
    # ------------------------------------------------------------------ #
    print(f"\n> 3. Creation d'un groupe jetable '{TEST_CODE}' (POST) ...")
    body_create = {
        "code_name": TEST_CODE,
        "display_name": "ZZ Test PodAdmin (a supprimer)",
        "sites": [site_url],
    }
    if owner_a:
        body_create["users"] = [owner_a]      # on tente de mettre un membre des la creation
    status, created = req("POST", f"{rest}/accessgroups/", headers, json=body_create)
    print(f"   POST -> HTTP {status}")
    print(f"   reponse : {json.dumps(created, ensure_ascii=False)[:300]}")
    if status not in (200, 201):
        print("   [X] Creation refusee -> on s'arrete (rien a nettoyer).")
        return
    # Le POST a-t-il renvoye une url/id ?
    gurl = created.get("url") if isinstance(created, dict) else None
    members_at_create = norm_urls(created.get("users")) if isinstance(created, dict) else []
    print(f"   url renvoyee par le POST : {gurl or '(aucune)'}")
    print(f"   membres a la creation    : {members_at_create}  "
          f"=> membre pris des la creation ? {'OUI' if members_at_create else 'NON'}")

    # ------------------------------------------------------------------ #
    # 4) Cibler le groupe cree (retrouver son URL si non fournie)
    # ------------------------------------------------------------------ #
    if not gurl:
        print("\n> 4. Recherche de l'URL adressable du groupe cree ...")
        gurl = find_group_url_by_code(rest, headers, TEST_CODE)
        print(f"   URL trouvee : {gurl or '(introuvable)'}")

    # ------------------------------------------------------------------ #
    # 5) Ajouter / retirer des membres (PATCH puis PUT)
    # ------------------------------------------------------------------ #
    if gurl:
        print("\n> 5. Gestion des membres sur le groupe cree :")
        # Etat courant
        status, g = req("GET", gurl, headers)
        cur = norm_urls(g.get("users")) if isinstance(g, dict) else []
        print(f"   membres actuels : {cur}")

        # 5a) Tenter d'AJOUTER le membre B via PATCH
        if owner_b:
            new = list(dict.fromkeys(cur + [owner_b]))
            status, body = req("PATCH", gurl, headers, json={"users": new})
            print(f"   [PATCH +B] -> HTTP {status}  "
                  f"{'' if status==200 else json.dumps(body, ensure_ascii=False)[:120]}")
            # 5b) Si PATCH refuse, tenter PUT (remplacement complet)
            if status != 200 and isinstance(g, dict):
                put_body = {
                    "code_name": g.get("code_name"),
                    "display_name": g.get("display_name"),
                    "sites": norm_urls(g.get("sites")),
                    "users": new,
                }
                status, body = req("PUT", gurl, headers, json=put_body)
                print(f"   [PUT  +B] -> HTTP {status}  "
                      f"{'' if status==200 else json.dumps(body, ensure_ascii=False)[:120]}")
            # Verif
            status, g2 = req("GET", gurl, headers)
            after = norm_urls(g2.get("users")) if isinstance(g2, dict) else []
            print(f"   membres apres ajout : {after}  "
                  f"=> AJOUT PRIS ? {'OUI' if owner_b and owner_b.rstrip('/') in [u.rstrip('/') for u in after] else 'NON'}")

            # 5c) Tenter de RETIRER le membre B (PATCH puis PUT)
            back = [u for u in after if u.rstrip("/") != owner_b.rstrip("/")]
            status, body = req("PATCH", gurl, headers, json={"users": back})
            if status != 200:
                put_body = {
                    "code_name": g2.get("code_name"),
                    "display_name": g2.get("display_name"),
                    "sites": norm_urls(g2.get("sites")),
                    "users": back,
                }
                status, body = req("PUT", gurl, headers, json=put_body)
            status, g3 = req("GET", gurl, headers)
            after2 = norm_urls(g3.get("users")) if isinstance(g3, dict) else []
            print(f"   membres apres retrait : {after2}  "
                  f"=> RETRAIT PRIS ? {'OUI' if owner_b.rstrip('/') not in [u.rstrip('/') for u in after2] else 'NON'}")
    else:
        print("\n> 5. (URL du groupe introuvable -> gestion des membres non testable)")

    # ------------------------------------------------------------------ #
    # 6) Supprimer le groupe jetable
    # ------------------------------------------------------------------ #
    print("\n> 6. Suppression du groupe jetable (DELETE) ...")
    if gurl:
        status, body = req("DELETE", gurl, headers)
        print(f"   DELETE {gurl} -> HTTP {status}")
        # Verif
        check = find_group_url_by_code(rest, headers, TEST_CODE)
        print(f"   => SUPPRESSION {'OK (groupe disparu)' if not check else 'NON (groupe encore present !)'}")
        if check:
            print(f"   ⚠️  Le groupe '{TEST_CODE}' existe encore : {check}")
            print("      Supprimez-le a la main dans l'admin Django si besoin.")
    else:
        print("   (pas d'URL -> suppression impossible ; verifiez l'admin Django)")

    print("\n" + "=" * 70)
    print("  A RECOLLER : etapes 3 (creation), 4 (url), 5 (ajout/retrait membres),")
    print("  6 (suppression). C'est la carte complete pour decider quoi coder.")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    input("\nAppuyez sur Entree pour fermer...")
