#!/usr/bin/env python3
"""
verifier_soustitres.py - L'API Esup-Pod expose-t-elle les SOUS-TITRES ?
=======================================================================
Determine si l'on peut gerer les sous-titres (WebVTT/SRT) depuis PodAdmin :
les lister, en deposer, les remplacer, les supprimer par video.

Verifie, en LECTURE SEULE (GET / OPTIONS) :
  1. Le token est valide.
  2. Parmi une liste d'endpoints CANDIDATS (tracks, subtitles, captions,
     completion, enrichment...), lesquels existent reellement sur l'instance.
  3. Pour ceux qui existent : leur schema OPTIONS (methodes autorisees,
     champs attendus : video, lang, fichier...). C'est ce qui dira si l'on
     peut DEPOSER un sous-titre par API ou seulement les LIRE.
  4. Liste aussi l'index racine /rest/ pour reperer tout endpoint dont le
     nom evoque les sous-titres et qu'on n'aurait pas devine.

NE MODIFIE RIEN. Sans danger pour la production.

Lancer avec un token SUPERUTILISATEUR :  python verifier_soustitres.py
"""

__author__      = "Cédric MONNA"
__contact__     = "cedricmonna@gmail.com"
__institution__ = "Université de Toulouse — MFCA"
__version__     = "0.1.0"
__date__        = "2026"

import json
import requests

DEFAULT_URL = "https://videos.utoulouse.fr"

# Endpoints candidats : noms plausibles pour des sous-titres / pistes / completion.
# On ne sait pas lesquels existent : on teste, on note le code HTTP.
CANDIDATES = [
    "/tracks/",
    "/track/",
    "/subtitles/",
    "/subtitle/",
    "/captions/",
    "/caption/",
    "/track_subtitles/",
    "/video_subtitles/",
    "/completion/",
    "/completions/",
    "/enrichment/",
    "/enrichments/",
    "/transcripts/",
    "/transcript/",
    "/files/",            # Pod stocke parfois les .vtt comme CustomFileModel
    "/customfile/",
]

# Mots-cles reperant un endpoint lie aux sous-titres dans l'index /rest/
HINTS = ("track", "subtitle", "caption", "complet", "enrich", "transcri", "vtt", "file")


def get(url, headers, params=None):
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        try:
            return r.status_code, (r.json() if r.text else None)
        except ValueError:
            return r.status_code, r.text[:200]
    except Exception as e:
        return None, {"_error": str(e)}


def describe_options(url, headers):
    """OPTIONS -> (Allow, champs POST). Dit si l'endpoint est inscriptible."""
    try:
        r = requests.options(url, headers=headers, timeout=15)
        allow = r.headers.get("Allow", "(non fourni)")
        fields = {}
        try:
            actions = (r.json() or {}).get("actions", {})
            post = actions.get("POST", {})
            for name, meta in post.items():
                fields[name] = {
                    "type": meta.get("type"),
                    "required": meta.get("required"),
                    "read_only": meta.get("read_only"),
                }
        except Exception:
            pass
        return allow, fields
    except Exception as e:
        return f"(erreur: {e})", {}


def main():
    print("=" * 70)
    print("  Sonde : sous-titres (WebVTT/SRT) dans l'API Esup-Pod")
    print("=" * 70)

    url = input(f"\nURL de l'instance [{DEFAULT_URL}] : ").strip() or DEFAULT_URL
    url = url.rstrip("/")
    token = input("Token SUPERUTILISATEUR : ").strip()
    if not token:
        print("[X] Pas de token. Abandon.")
        return

    rest = f"{url}/rest"
    headers = {"Authorization": f"Token {token}", "Accept": "application/json"}

    # 0) Token
    print("\n> 0. Connexion ...")
    status, data = get(f"{rest}/videos/", headers, {"limit": 1})
    if status != 200:
        print(f"   [X] HTTP {status}. Verifiez URL et token.")
        return
    print(f"   [OK] Connecte.")

    # 1) Index racine : reperer les endpoints evoquant les sous-titres
    print("\n> 1. Endpoints de l'index /rest/ evoquant des sous-titres ...")
    status, root = get(f"{rest}/", headers)
    rooted = []
    if isinstance(root, dict):
        for name, link in root.items():
            if any(h in name.lower() for h in HINTS):
                rooted.append(name)
                print(f"   [*] {name:22} -> {link}")
    if not rooted:
        print("   (aucun nom evident dans l'index ; on teste les candidats ci-dessous)")

    # 2) Test des endpoints candidats
    print("\n> 2. Test des endpoints candidats ...")
    found = []
    for ep in CANDIDATES:
        status, data = get(f"{rest}{ep}", headers, {"limit": 1})
        tag = {200: "[OK] existe", 401: "[401] auth", 403: "[403] interdit",
               404: "[--] absent", None: "[err]"}.get(status, f"[{status}]")
        print(f"   {ep:20} -> {tag}")
        if status == 200:
            found.append(ep)

    # 3) Pour chaque endpoint trouve : schema OPTIONS (inscriptible ? champs ?)
    writable = []
    if found:
        print("\n> 3. Schema des endpoints trouves (peut-on DEPOSER ?) ...")
        for ep in found:
            allow, fields = describe_options(f"{rest}{ep}", headers)
            can_post = "POST" in allow
            print(f"\n   {ep}")
            print(f"     Allow : {allow}")
            if can_post:
                writable.append(ep)
                print("     Champs attendus au POST :")
                for name, meta in fields.items():
                    flag = "requis" if meta.get("required") else "option."
                    ro = " (lecture seule)" if meta.get("read_only") else ""
                    print(f"       - {name:18} {meta.get('type'):12} [{flag}]{ro}")
            else:
                print("     -> pas de POST : LECTURE SEULE (depot impossible par API)")
            # Exemple d'enregistrement pour voir les noms de champs reels
            status, data = get(f"{rest}{ep}", headers, {"limit": 1})
            ex = None
            if isinstance(data, dict):
                res = data.get("results", [])
                ex = res[0] if res else None
            if ex:
                print(f"     Champs d'un enregistrement : {list(ex.keys())}")

    # VERDICT
    print("\n" + "=" * 70)
    print("  VERDICT")
    print("=" * 70)
    if writable:
        print(f"  Sous-titres GERABLES par API (depot possible) : {', '.join(writable)}")
        print("  => Module Sous-titres envisageable : deposer un .vtt apres l'upload,")
        print("     lister / remplacer / supprimer par video.")
    elif found:
        print(f"  Endpoint(s) trouve(s) mais en LECTURE SEULE : {', '.join(found)}")
        print("  => On pourrait LISTER les sous-titres, mais pas les deposer par API.")
        print("     Le depot resterait a faire dans l'interface web de Pod.")
    else:
        print("  Aucun endpoint de sous-titres trouve dans l'API REST.")
        print("  => Gestion des sous-titres uniquement via l'interface web de Pod.")
        print("     Pas de module PodAdmin possible pour cette fonction.")
    print("=" * 70)
    print("  Recolle ce resultat (etapes 2, 3 et verdict) dans la conversation.")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    input("\nAppuyez sur Entree pour fermer...")
