#!/usr/bin/env python3
"""
verifier_tracks.py - Detail du endpoint /rest/tracks/ (sous-titres)
===================================================================
La sonde precedente a confirme que /rest/tracks/ accepte le POST avec les
champs video / kind / lang / src. Il reste 3 inconnues a lever avant de coder
le module Sous-titres :

  1. Les valeurs autorisees de `kind`  (subtitles ? captions ? chapters ?).
  2. Les valeurs autorisees de `lang`  (fr ? en ? ...).
  3. La nature de `src` : attend-il l'URL d'un fichier deja televerse
     (-> workflow en 2 temps via /rest/files/), ou un upload direct ?

LECTURE SEULE (OPTIONS + GET). Ne cree, ne modifie, ne supprime rien.

Lancer avec un token SUPERUTILISATEUR :  python verifier_tracks.py
"""

__author__      = "Cédric MONNA"
__contact__     = "cedricmonna@gmail.com"
__institution__ = "Université de Toulouse — MFCA"
__version__     = "0.1.0"
__date__        = "2026"

import json
import requests

DEFAULT_URL = "https://videos.utoulouse.fr"


def main():
    print("=" * 70)
    print("  Sonde detaillee : /rest/tracks/ (sous-titres)")
    print("=" * 70)

    url = input(f"\nURL de l'instance [{DEFAULT_URL}] : ").strip() or DEFAULT_URL
    url = url.rstrip("/")
    token = input("Token SUPERUTILISATEUR : ").strip()
    if not token:
        print("[X] Pas de token. Abandon.")
        return

    rest = f"{url}/rest"
    headers = {"Authorization": f"Token {token}", "Accept": "application/json"}
    tracks_url = f"{rest}/tracks/"

    # ------------------------------------------------------------------ #
    # 1) OPTIONS detaille : choices de kind / lang + meta de src
    # ------------------------------------------------------------------ #
    print("\n> 1. OPTIONS detaille de /tracks/ ...")
    try:
        r = requests.options(tracks_url, headers=headers, timeout=20)
        actions = (r.json() or {}).get("actions", {})
        post = actions.get("POST", {})
    except Exception as e:
        print(f"   [X] Echec OPTIONS : {e}")
        return

    for field in ("video", "kind", "lang", "src"):
        meta = post.get(field)
        if not meta:
            print(f"\n   [{field}] : (absent du schema POST)")
            continue
        print(f"\n   [{field}]")
        print(f"     type     : {meta.get('type')}")
        print(f"     requis   : {meta.get('required')}")
        print(f"     read_only: {meta.get('read_only')}")
        if meta.get("label"):
            print(f"     label    : {meta.get('label')}")
        if meta.get("help_text"):
            print(f"     aide     : {meta.get('help_text')}")
        # Les 'choice' exposent leurs valeurs dans 'choices'
        choices = meta.get("choices")
        if choices:
            print("     VALEURS AUTORISEES :")
            for c in choices:
                print(f"        - {c.get('value')!r:20} ({c.get('display_name')})")

    # ------------------------------------------------------------------ #
    # 2) Exemples reels : a quoi ressemble 'src' et 'video' sur des tracks
    #    deja existants (URL de fichier ? chemin ? upload ?)
    # ------------------------------------------------------------------ #
    print("\n> 2. Tracks existants (pour voir le format reel de 'src') ...")
    try:
        r = requests.get(tracks_url, headers=headers, params={"limit": 5}, timeout=20)
        data = r.json()
        results = data.get("results", []) if isinstance(data, dict) else (data or [])
    except Exception as e:
        results = []
        print(f"   [!] {e}")

    if not results:
        print("   (aucun track existant sur l'instance — on se basera sur le schema)")
    else:
        for t in results:
            print(f"   - id={t.get('id')}  kind={t.get('kind')!r}  lang={t.get('lang')!r}")
            print(f"       video = {t.get('video')}")
            print(f"       src   = {t.get('src')!r}")

    # ------------------------------------------------------------------ #
    # 3) Indice sur la nature de 'src'
    # ------------------------------------------------------------------ #
    print("\n> 3. Interpretation de 'src' ...")
    src_meta = post.get("src", {})
    src_type = (src_meta.get("type") or "").lower()
    sample_src = results[0].get("src") if results else None
    verdict_src = "INCONNU"
    if "file" in src_type or "upload" in src_type:
        verdict_src = "UPLOAD DIRECT (envoyer le .vtt en multipart sur /tracks/)"
    elif sample_src and isinstance(sample_src, str) and sample_src.startswith("http"):
        verdict_src = "URL d'un fichier deja televerse (workflow en 2 temps via /files/)"
    elif src_type in ("field", "string", "url"):
        verdict_src = ("probablement une URL/reference de fichier "
                       "(workflow en 2 temps via /files/) — a confirmer")
    print(f"   -> {verdict_src}")

    # ------------------------------------------------------------------ #
    print("\n" + "=" * 70)
    print("  A RECOLLER dans la conversation :")
    print("   - les VALEURS AUTORISEES de kind et lang (etape 1)")
    print("   - un exemple de 'src' (etape 2)")
    print("   - l'interpretation de src (etape 3)")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    input("\nAppuyez sur Entree pour fermer...")
