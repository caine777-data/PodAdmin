#!/usr/bin/env python3
"""
verifier_encodage.py - Sondage de l'API Esup-Pod cote ENCODAGE (lecture seule)
==============================================================================
Objectif : determiner ce que l'API expose pour superviser l'encodage, afin de
decider quoi mettre dans un futur onglet "Encodage" de PodAdmin.

Questions auxquelles ce script repond :
  1. Quels champs d'etat d'encodage porte une video ? (encoded,
     encoding_in_progress, get_encoding_step, get_encoding_step_label...)
  2. Existe-t-il un endpoint dedie listant une FILE d'encodage / des JOBS
     (avec progression en %) ? On teste plusieurs URLs candidates.
  3. Peut-on filtrer les videos par etat d'encodage cote serveur
     (parametres ?encoding_in_progress=, ?encoded=) ou faut-il tout scanner ?
  4. Combien de videos sont actuellement encodees / en cours / a problemes,
     d'apres les champs disponibles.

LECTURE SEULE : uniquement des requetes GET et OPTIONS. Ne modifie rien,
ne relance aucun encodage. Sans danger pour la production.

Lancer avec un token SUPERUTILISATEUR :  python verifier_encodage.py
"""

__author__      = "Cédric MONNA"
__contact__     = "cedricmonna@gmail.com"
__institution__ = "Université de Toulouse — MFCA"
__version__     = "0.1.0"
__date__        = "2026"
__license__     = "Usage interne — Université de Toulouse"

import json
import requests

DEFAULT_URL = "https://videos.utoulouse.fr"

# Endpoints candidats pour une eventuelle file/jobs d'encodage.
# On ne sait pas s'ils existent : on teste, on note le code HTTP.
CANDIDATE_ENCODE_ENDPOINTS = [
    "/encoding/",
    "/encodings/",
    "/encoding_videos/",
    "/encode/",
    "/encode_videos/",
    "/encoding_steps/",
    "/encoding_jobs/",
    "/jobs/",
    "/encoding_video/",
    "/launch_encode_view/",   # connu (lance un encodage) - on regarde juste son OPTIONS
]

# Mots-cles reperant un champ lie a l'encodage dans une video
ENCODE_HINTS = ("encod", "transcod", "step", "process", "job", "progress",
                "is_video", "is_audio", "duration")


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def get(url, headers, params=None):
    """GET simple -> (status, data|texte|None)."""
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        try:
            return r.status_code, r.json() if r.text else None
        except ValueError:
            return r.status_code, r.text[:200]
    except Exception as e:
        return None, {"_error": str(e)}


def options_allow(url, headers):
    """OPTIONS -> en-tete Allow (methodes autorisees) ou message d'erreur."""
    try:
        r = requests.options(url, headers=headers, timeout=15)
        return r.status_code, r.headers.get("Allow", "(non fourni)")
    except Exception as e:
        return None, str(e)


def first_result(data):
    """1er element d'une reponse paginee {results:[...]} ou d'une liste."""
    if isinstance(data, dict):
        res = data.get("results", [])
        return res[0] if res else None
    if isinstance(data, list) and data:
        return data[0]
    return None


# --------------------------------------------------------------------------- #
#  Main
# --------------------------------------------------------------------------- #
def main():
    print("=" * 70)
    print("  PodAdmin - Sondage ENCODAGE (lecture seule)")
    print("=" * 70)

    url = input(f"\nURL de l'instance [{DEFAULT_URL}] : ").strip() or DEFAULT_URL
    url = url.rstrip("/")
    print("\nCollez le token d'un compte SUPERUTILISATEUR :")
    token = input("Token : ").strip()
    if not token:
        print("\n[X] Aucun token saisi. Abandon.")
        return

    rest = f"{url}/rest"
    headers = {"Authorization": f"Token {token}", "Accept": "application/json"}

    # ----------------------------------------------------------------- #
    # 0) Validite du token
    # ----------------------------------------------------------------- #
    print("\n> 0. Connexion (GET /rest/videos/) ...")
    status, data = get(f"{rest}/videos/", headers, {"limit": 1})
    if status != 200:
        print(f"   [X] Echec HTTP {status}. Verifiez URL et token.")
        return
    total = data.get("count") if isinstance(data, dict) else "?"
    print(f"   [OK] Connecte - {total} video(s) au total.")

    # ----------------------------------------------------------------- #
    # 1) Champs d'etat d'encodage sur une video
    # ----------------------------------------------------------------- #
    print("\n> 1. Champs d'encodage exposes par une video ...")
    sample = first_result(data)
    if sample:
        enc_fields = [k for k in sample
                      if any(h in k.lower() for h in ENCODE_HINTS)]
        print(f"   Champs reperes : {enc_fields or '(aucun)'}")
        for k in enc_fields:
            print(f"     - {k} = {sample.get(k)!r}")
    else:
        print("   (pas de video temoin disponible)")

    # ----------------------------------------------------------------- #
    # 2) Existe-t-il une file / des jobs d'encodage ?
    # ----------------------------------------------------------------- #
    print("\n> 2. Recherche d'un endpoint de file/jobs d'encodage ...")
    found = []
    for ep in CANDIDATE_ENCODE_ENDPOINTS:
        status, data = get(f"{rest}{ep}", headers, {"limit": 1})
        tag = {200: "[OK] existe", 401: "[401] auth", 403: "[403] interdit",
               404: "[--] absent", None: "[err]"}.get(status, f"[{status}]")
        print(f"   {ep:22} -> {tag}")
        if status == 200:
            found.append(ep)
            ex = first_result(data)
            if ex:
                print(f"      champs : {list(ex.keys())}")
            scode, allow = options_allow(f"{rest}{ep}", headers)
            print(f"      OPTIONS Allow : {allow}")

    # ----------------------------------------------------------------- #
    # 3) Filtrage cote serveur par etat d'encodage ?
    # ----------------------------------------------------------------- #
    print("\n> 3. Peut-on filtrer les videos par etat (cote serveur) ?")
    for label, params in [
        ("?encoding_in_progress=true", {"encoding_in_progress": "true", "limit": 1}),
        ("?encoded=false",            {"encoded": "false", "limit": 1}),
        ("?is_draft=false",           {"is_draft": "false", "limit": 1}),
    ]:
        status, data = get(f"{rest}/videos/", headers, params)
        cnt = data.get("count") if isinstance(data, dict) else "?"
        # Note : si le filtre est ignore, le count = total (signe qu'il ne filtre pas)
        print(f"   {label:30} -> HTTP {status}, count={cnt}")
    print("   (si count == total a chaque fois, le filtre est ignore : "
          "il faudra scanner et trier cote client)")

    # ----------------------------------------------------------------- #
    # 4) Comptage par etat (sur un echantillon pagine raisonnable)
    # ----------------------------------------------------------------- #
    print("\n> 4. Comptage par etat d'encodage (echantillon, max ~500) ...")
    encoded = in_progress = failed = drafts = 0
    seen = 0
    url_page = f"{rest}/videos/"
    params = {"limit": 100}
    pages = 0
    while url_page and pages < 5:
        try:
            r = requests.get(url_page, params=(params if pages == 0 else None),
                             headers=headers, timeout=30)
            d = r.json()
        except Exception as e:
            print(f"   [!] arret pagination : {e}")
            break
        results = d.get("results", []) if isinstance(d, dict) else (d or [])
        for v in results:
            seen += 1
            enc = bool(v.get("encoded"))
            prog = bool(v.get("encoding_in_progress"))
            draft = bool(v.get("is_draft"))
            if enc:
                encoded += 1
            elif prog:
                in_progress += 1
            elif draft:
                drafts += 1
            else:
                failed += 1   # ni encodee, ni en cours, ni brouillon = suspecte
        url_page = d.get("next") if isinstance(d, dict) else None
        pages += 1

    print(f"   Analysees : {seen}")
    print(f"     [OK]  encodees ............. {encoded}")
    print(f"     [..]  en cours d'encodage .. {in_progress}")
    print(f"     [!!]  echec probable ....... {failed}  "
          f"(ni encodee, ni en cours, ni brouillon)")
    print(f"     [DR]  brouillons non lances  {drafts}")

    # ----------------------------------------------------------------- #
    # VERDICT
    # ----------------------------------------------------------------- #
    print("\n" + "=" * 70)
    print("  VERDICT")
    print("=" * 70)
    if found:
        print(f"  File/jobs d'encodage dediee : OUI -> {', '.join(found)}")
        print("  => l'onglet Encodage pourra afficher une vraie file serveur.")
    else:
        print("  File/jobs d'encodage dediee : NON trouvee.")
        print("  => l'onglet Encodage se basera sur les champs par video")
        print("     (encoded / encoding_in_progress / get_encoding_step),")
        print("     en scannant puis triant cote client. Suffisant pour voir")
        print("     les encodages en cours / echoues et les relancer.")
    print("=" * 70)
    print("  Recolle ce resultat dans la conversation pour qu'on cale l'onglet.")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    input("\nAppuyez sur Entree pour fermer...")
