#!/usr/bin/env python3
"""
verifier_diff_restriction.py - Comparer deux videos pour trouver le champ manquant
==================================================================================
Symptome : une chaine restreinte a un groupe via PodAdmin (is_restricted=True +
restrict_access_to_groups) laisse ses videos INVISIBLES. L'admin Django montre
un champ « visibilite » obligatoire (etoile rouge) non rempli.

Methode (la plus sure) : LIRE tous les champs de DEUX videos et comparer :
  A = une video qui MARCHE   (restreinte correctement, ex. via l'admin Django)
  B = une video qui NE MARCHE PAS (restreinte via PodAdmin)
La/les difference(s) revelent le champ manquant et sa valeur attendue.

Affiche aussi le schema OPTIONS (PUT) en marquant les champs REQUIS (required),
pour reperer un eventuel champ obligatoire qu'on n'envoie pas.

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


def resolve_video(rest, headers, ref):
    """Retourne le dict complet d'une video a partir d'un slug ou id."""
    vurl = f"{rest}/videos/{ref}/"
    status, v = req("GET", vurl, headers)
    if status == 200 and isinstance(v, dict):
        return vurl, v
    status, data = req("GET", f"{rest}/videos/", headers,
                       params={"search": ref, "limit": 50})
    res = data.get("results", []) if isinstance(data, dict) else []
    v = next((x for x in res if x.get("slug") == ref), None)
    return (v.get("url") if v else None), v


def short(val):
    """Représentation courte et lisible d'une valeur."""
    s = json.dumps(val, ensure_ascii=False)
    return s if len(s) <= 80 else s[:77] + "…"


def main():
    print("=" * 70)
    print("  Sonde : comparer deux videos (trouver le champ 'visibilite' manquant)")
    print("=" * 70)

    url = input(f"\nURL de l'instance [{DEFAULT_URL}] : ").strip() or DEFAULT_URL
    url = url.rstrip("/")
    token = input("Token SUPERUTILISATEUR : ").strip()
    if not token:
        print("[X] Pas de token. Abandon.")
        return
    rest = f"{url}/rest"
    headers = {"Authorization": f"Token {token}", "Accept": "application/json"}

    print("\nIndiquez DEUX videos a comparer :")
    ref_a = input("  A) video qui MARCHE (restriction OK)      : ").strip()
    ref_b = input("  B) video qui NE MARCHE PAS (via PodAdmin)  : ").strip()

    vurl_a, va = resolve_video(rest, headers, ref_a)
    vurl_b, vb = resolve_video(rest, headers, ref_b)
    if not isinstance(va, dict) or not isinstance(vb, dict):
        print("   [X] Une des deux videos est introuvable.")
        return

    print(f"\n  A = {va.get('slug')!r}")
    print(f"  B = {vb.get('slug')!r}")

    # ------------------------------------------------------------------ #
    # 1) Différences champ par champ
    # ------------------------------------------------------------------ #
    print("\n> 1. DIFFERENCES entre A (marche) et B (ne marche pas) :")
    keys = sorted(set(va.keys()) | set(vb.keys()))
    diffs = []
    for k in keys:
        a_val = va.get(k)
        b_val = vb.get(k)
        if json.dumps(a_val, ensure_ascii=False, sort_keys=True) != \
           json.dumps(b_val, ensure_ascii=False, sort_keys=True):
            diffs.append(k)
            print(f"   ≠ {k}")
            print(f"       A = {short(a_val)}")
            print(f"       B = {short(b_val)}")
    if not diffs:
        print("   (aucune différence — les deux vidéos ont les mêmes champs/valeurs)")

    # ------------------------------------------------------------------ #
    # 2) Focus sur les champs « visibilité / accès » connus ou suspects
    # ------------------------------------------------------------------ #
    print("\n> 2. Champs d'accès/visibilité (valeurs sur A puis B) :")
    suspects = [k for k in keys if any(w in k.lower() for w in
                ("restrict", "visib", "access", "draft", "password", "group", "public"))]
    for k in suspects:
        print(f"   {k}")
        print(f"       A = {short(va.get(k))}")
        print(f"       B = {short(vb.get(k))}")

    # ------------------------------------------------------------------ #
    # 3) Schéma OPTIONS : champs REQUIS (étoile rouge probable)
    # ------------------------------------------------------------------ #
    print("\n> 3. Schéma OPTIONS (champs requis = candidats 'etoile rouge') :")
    status, opt = req("OPTIONS", vurl_b or vurl_a, headers)
    put = (opt or {}).get("actions", {}).get("PUT", {}) if isinstance(opt, dict) else {}
    if put:
        for name, meta in put.items():
            if meta.get("required"):
                print(f"   * REQUIS : {name}  (type={meta.get('type')})")
                if meta.get("choices"):
                    vals = [c.get("value") for c in meta["choices"][:8]]
                    print(f"       valeurs possibles : {vals}")
        # Lister aussi les champs ressemblant a 'visibilite' meme non requis
        for name, meta in put.items():
            if any(w in name.lower() for w in ("visib", "restrict", "access")):
                print(f"   - champ d'accès : {name}  required={meta.get('required')}  "
                      f"type={meta.get('type')}")
                if meta.get("choices"):
                    vals = [c.get("value") for c in meta["choices"][:8]]
                    print(f"       valeurs possibles : {vals}")
    else:
        print("   (schéma OPTIONS indisponible)")

    print("\n" + "=" * 70)
    print("  A RECOLLER : etape 1 (toutes les differences) et etape 3")
    print("  (les champs requis). Le champ manquant y apparaitra.")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    input("\nAppuyez sur Entree pour fermer...")
