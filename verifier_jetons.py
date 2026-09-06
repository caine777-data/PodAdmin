#!/usr/bin/env python3
"""
verifier_jetons.py — Sonde : peut-on savoir QUI a déjà un jeton ?
==================================================================
Objectif : déterminer si PodAdmin peut connaître, pour chaque compte, s'il
possède déjà un jeton d'authentification.

POURQUOI CETTE QUESTION
-----------------------
L'onglet Comptes propose un bouton « 🔑 Token » qui ouvre la LISTE filtrée des
jetons dans l'administration. Ce compromis vient d'une ignorance : l'application
ne sait pas si la personne en a déjà un, elle laisse donc l'utilisateur regarder.

Si l'information était accessible, le bouton pourrait mener directement au bon
endroit :
  • aucun jeton  → formulaire de CRÉATION, compte pré-sélectionné ;
  • jeton existant → liste filtrée, pour le recopier.

Un clic de moins, et plus de décision à prendre : l'interface aurait tranché.

CE QUE LA SONDE VÉRIFIE
-----------------------
1. Une ressource REST expose-t-elle les jetons ?
   (Les sondes précédentes ont recensé 31 ressources, aucune ne semblait
    correspondre — on vérifie explicitement, y compris des noms non listés.)
2. Le champ existe-t-il sur /rest/users/ ?
3. À défaut, l'administration Django est-elle lisible avec ce jeton ?

MODE : LECTURE SEULE. Rien n'est créé ni modifié.

AUTONOME : aucun autre fichier du projet n'est nécessaire.

    python verifier_jetons.py
"""

__author__ = "Cédric MONNA"
__version__ = "1.0.0"

import json


def charger_requests():
    """Importe `requests`, en proposant de l'installer si nécessaire."""
    try:
        import requests
        return requests
    except ImportError:
        pass
    print("La bibliothèque « requests » est nécessaire et n'est pas installée.")
    if input("L'installer maintenant ? (o/N) : ").strip().lower() not in ("o", "oui", "y"):
        print("\nInstallation manuelle :   pip install requests")
        return None
    import subprocess
    import sys as _sys
    try:
        subprocess.check_call([_sys.executable, "-m", "pip", "install", "requests"])
        import requests
        return requests
    except Exception as e:
        print(f"[X] Installation impossible : {e}")
        return None


def essayer_ressources_rest(sess, rest):
    """Cherche une ressource REST exposant les jetons."""
    print(f"\n{'=' * 66}\n  1. RESSOURCES REST\n{'=' * 66}")
    candidats = ["authtoken", "tokens", "token", "apikeys", "api_tokens",
                 "auth_token", "authtokens"]
    trouve = None
    for nom in candidats:
        try:
            r = sess.get(f"{rest}/{nom}/", params={"limit": 1}, timeout=15)
            etat = r.status_code
        except Exception as e:
            print(f"   /{nom:12} → erreur : {e}")
            continue
        marque = ""
        if etat == 200:
            marque = "  ← ACCESSIBLE"
            trouve = nom
        print(f"   /{nom:12} → HTTP {etat}{marque}")

    if trouve:
        try:
            r = sess.get(f"{rest}/{trouve}/", params={"limit": 2}, timeout=20)
            d = r.json()
            res = d.get("results") if isinstance(d, dict) else d
            print(f"\n   Contenu de /{trouve}/ :")
            for e in (res or [])[:2]:
                print("      " + json.dumps(e, ensure_ascii=False)[:120])
        except Exception:
            pass
    else:
        print("\n   Aucune ressource REST n'expose les jetons.")
    return trouve


def champ_dans_users(sess, rest):
    """Le champ apparaît-il sur les comptes eux-mêmes ?"""
    print(f"\n{'=' * 66}\n  2. CHAMP SUR /rest/users/\n{'=' * 66}")
    try:
        r = sess.get(f"{rest}/users/", params={"limit": 3}, timeout=20)
        if r.status_code != 200:
            print(f"   HTTP {r.status_code} — comptes inaccessibles.")
            return False
        d = r.json()
        res = (d.get("results") if isinstance(d, dict) else d) or []
        if not res:
            print("   Aucun compte dans l'échantillon.")
            return False
        champs = sorted(res[0].keys())
        print(f"   Champs d'un compte ({len(champs)}) :")
        print("      " + ", ".join(champs))
        pertinents = [c for c in champs
                      if any(m in c.lower() for m in ("token", "jeton", "key", "auth"))]
        if pertinents:
            print(f"\n   ← Champ(s) lié(s) au jeton : {', '.join(pertinents)}")
            return True
        print("\n   Aucun champ ne renseigne l'existence d'un jeton.")
        return False
    except Exception as e:
        print(f"   [X] {e}")
        return False


def admin_lisible(sess, base):
    """L'administration Django est-elle lisible avec ce jeton ?

    Un jeton REST n'ouvre normalement PAS de session d'administration : celle-ci
    repose sur les cookies de connexion du navigateur. On vérifie pour écarter
    formellement cette piste."""
    print(f"\n{'=' * 66}\n  3. ADMINISTRATION DJANGO\n{'=' * 66}")
    for chemin in ("/admin/authtoken/tokenproxy/", "/admin/authtoken/token/"):
        try:
            r = sess.get(f"{base}{chemin}", timeout=20, allow_redirects=False)
            etat = r.status_code
            note = ""
            if etat in (301, 302):
                note = "  (redirection vers la page de connexion — non lisible)"
            elif etat == 200:
                note = "  ← page reçue, à analyser"
            print(f"   {chemin:36} → HTTP {etat}{note}")
        except Exception as e:
            print(f"   {chemin:36} → erreur : {e}")
    print("\n   Rappel : un jeton REST n'ouvre pas de session d'administration.")


def run():
    requests = charger_requests()
    if requests is None:
        return

    base = (input("URL de l'instance [https://videos.utoulouse.fr] : ").strip()
            or "https://videos.utoulouse.fr").rstrip("/")
    token = input("Token (compte superutilisateur de préférence) : ").strip()
    if not token:
        print("[X] Token vide.")
        return

    rest = f"{base}/rest"
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Token {token}",
                         "Accept": "application/json"})

    ressource = essayer_ressources_rest(sess, rest)
    champ = champ_dans_users(sess, rest)
    admin_lisible(sess, base)

    print(f"\n{'=' * 66}\n  CONCLUSION\n{'=' * 66}\n")
    if ressource or champ:
        print("   ➜  RÉALISABLE. L'information est accessible par l'API.")
        print("      Le bouton de l'onglet Comptes pourra mener directement")
        print("      au formulaire de création ou à la liste, selon le cas.")
    else:
        print("   ➜  NON RÉALISABLE par l'API. Les jetons ne sont pas exposés.")
        print()
        print("      Deux contournements possibles :")
        print("      • mémoriser localement les jetons délivrés DEPUIS PodAdmin")
        print("        (imparfait : ne couvre pas ceux créés avant, ni par un")
        print("         collègue depuis un autre poste) ;")
        print("      • conserver le comportement actuel — le bouton ouvre la")
        print("        liste filtrée, qui répond à la question en un coup d'œil.")
        print()
        print("      Le second est sans doute le plus honnête : mieux vaut un")
        print("      clic de plus qu'une information à moitié fiable.")
    print("\n   Transmettez cette sortie complète.\n")


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    except Exception:
        import traceback
        print("\n[ERREUR] La sonde a rencontré un problème :\n")
        traceback.print_exc()
    input("\nAppuyez sur Entrée pour fermer…")
