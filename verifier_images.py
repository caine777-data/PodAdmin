#!/usr/bin/env python3
"""
verifier_images.py — Sonde : comment déposer une bannière de chaîne ?
=====================================================================
La première sonde a montré que l'habillage des chaînes est pilotable par l'API,
et que la bannière (`headband`) n'est pas un fichier mais une RELATION vers la
ressource `/rest/images/` :

    headband = "https://videos.utoulouse.fr/rest/images/16/"

Poser une bannière suppose donc deux temps :
    1. déposer l'image dans /rest/images/   → on obtient son URL
    2. lier cette URL à la chaîne (PATCH)   → déjà maîtrisé

Cette sonde éclaire le PREMIER temps, qui est l'inconnue :
  • quels champs la ressource /images/ attend-elle ?
  • le dépôt se fait-il en multipart (fichier) ou autrement ?
  • quels champs sont obligatoires (un site ? un propriétaire ?) ?
  • à quoi ressemble une image existante ?

MODE PAR DÉFAUT : LECTURE SEULE. Rien n'est créé ni modifié.

Un test d'écriture RÉEL est proposé en option, à la toute fin, et seulement
après confirmation explicite : il dépose une petite image de test (un carré de
quelques centaines d'octets, généré sur place) pour vérifier que le dépôt
fonctionne vraiment. C'est le seul moyen d'en avoir le cœur net — mais il crée
un élément sur l'instance, que la sonde propose ensuite de supprimer.

AUTONOME : ce fichier se suffit à lui-même, aucun autre fichier du projet n'est
nécessaire. Seule dépendance : la bibliothèque « requests ».

    python verifier_images.py
"""

__author__ = "Cédric MONNA"
__version__ = "1.0.0"

import base64
import json

# Image PNG minimale (carré rouge 8×8), intégrée en dur pour éviter toute
# dépendance : sert uniquement au test d'écriture optionnel.
# Image PNG valide (200 x 60, fond bleu), intégrée en dur pour éviter toute
# dépendance. L'ancienne version faisait 8 x 8 pixels et Pod la rejetait comme
# « corrompue » : le serveur attend une image de dimensions plausibles.
PNG_TEST = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAMgAAAA8CAIAAACsOWLGAAAAuUlEQVR4nO3SQQ3AIADA"
    "QMDIHOEH9zOxhmS5U9BH57PPgK+t2wH8k7FIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4Sx"
    "SBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFI"
    "GIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgY"
    "i4SxSBiLhLFIGIuEsUgYi8QLJU4BXnyztY4AAAAASUVORK5CYII=")


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


def schema_images(sess, rest):
    """Affiche les champs attendus par /rest/images/ (méthode OPTIONS)."""
    print(f"\n{'=' * 68}\n  SCHÉMA DE /rest/images/\n{'=' * 68}")
    try:
        r = sess.options(f"{rest}/images/", timeout=30)
        print(f"   OPTIONS → HTTP {r.status_code}")
        if r.status_code != 200:
            print("   [X] Schéma inaccessible : impossible de savoir quoi envoyer.")
            return None
        actions = (r.json().get("actions") or {})
        schema = actions.get("POST")
        if not schema:
            print("   [X] Aucun schéma POST : la ressource est peut-être en "
                  "LECTURE SEULE (dépôt impossible par l'API).")
            print("       Actions disponibles :", ", ".join(actions.keys()) or "aucune")
            return None
        print(f"\n   {len(schema)} champ(s) acceptés au dépôt :\n")
        obligatoires = []
        for nom, meta in sorted(schema.items()):
            t = meta.get("type", "?")
            req = meta.get("required", False)
            ro = meta.get("read_only", False)
            etat = "LECTURE SEULE" if ro else ("OBLIGATOIRE" if req else "facultatif")
            if req and not ro:
                obligatoires.append(nom)
            print(f"      • {nom:22} type={t:16} {etat}")
            # Un champ de type « file »/« image » impose un envoi multipart.
            if t in ("file upload", "image upload"):
                print(f"        → envoi de FICHIER (multipart) attendu pour « {nom} »")
        print("\n   Champs obligatoires :",
              ", ".join(obligatoires) if obligatoires else "aucun")
        return schema
    except Exception as e:
        print(f"   [X] OPTIONS impossible : {e}")
        return None


def exemple_image(sess, rest):
    """Montre une image existante : quels champs, quelles valeurs."""
    print(f"\n{'=' * 68}\n  EXEMPLE D'IMAGE EXISTANTE\n{'=' * 68}")
    try:
        r = sess.get(f"{rest}/images/", params={"limit": 2}, timeout=30)
        print(f"   GET → HTTP {r.status_code}")
        if r.status_code != 200:
            return
        data = r.json()
        total = data.get("count") if isinstance(data, dict) else None
        res = data.get("results") if isinstance(data, dict) else data
        if total is not None:
            print(f"   {total} image(s) sur l'instance.")
        if not res:
            print("   (aucune image pour l'échantillon)")
            return
        for i, img in enumerate(res, 1):
            print(f"\n   — Image {i} —")
            for k, v in sorted(img.items()):
                print(f"      {k:16} = {json.dumps(v, ensure_ascii=False)[:64]}")
    except Exception as e:
        print(f"   [X] GET impossible : {e}")


def test_ecriture(sess, rest, requests):
    """Dépose RÉELLEMENT une image de test, après confirmation explicite."""
    print(f"\n{'=' * 68}\n  TEST D'ÉCRITURE (optionnel)\n{'=' * 68}")
    print("""
   Ce test dépose une petite image (200 x 60 pixels, 242 octets) sur l'instance,
   pour vérifier que le dépôt fonctionne réellement. C'est le seul moyen d'en
   avoir la certitude — le schéma seul ne dit pas tout.

   Un élément SERA CRÉÉ sur l'instance. La sonde proposera de le supprimer
   juste après.
""")
    if input("   Lancer ce test ? (o/N) : ").strip().lower() not in ("o", "oui", "y"):
        print("   Test ignoré (aucune écriture).")
        return

    # L'API exige quatre champs : file, name, folder et created_by.
    # (Une première version n'envoyait qu'un « site » : le serveur a répondu
    #  « Ce champ est requis » pour les trois autres — d'où cette correction.)
    print("\n   Préparation : récupération du dossier et du compte…")

    dossier = ""
    try:
        r = sess.get(f"{rest}/folders/", params={"limit": 1}, timeout=20)
        d = r.json()
        res = (d.get("results") if isinstance(d, dict) else d) or []
        if res:
            dossier = res[0].get("url", "")
            print(f"      dossier    : {dossier}  ({res[0].get('name', '?')})")
    except Exception as e:
        print(f"      [X] dossiers inaccessibles : {e}")

    # `created_by` doit désigner un utilisateur. On reprend le propriétaire
    # d'une image existante : c'est un compte forcément valide pour ce champ.
    createur = ""
    try:
        r = sess.get(f"{rest}/images/", params={"limit": 1}, timeout=20)
        d = r.json()
        res = (d.get("results") if isinstance(d, dict) else d) or []
        if res:
            createur = res[0].get("created_by", "")
            print(f"      créateur   : {createur}")
    except Exception as e:
        print(f"      [X] impossible de déterminer un créateur : {e}")

    if not dossier or not createur:
        print("\n   [X] Informations insuffisantes pour tenter le dépôt.")
        print("       Il faut au minimum un dossier (/rest/folders/) et un compte.")
        return

    fichier = {"file": ("sonde_test.png", PNG_TEST, "image/png")}
    donnees = {
        "name": "sonde_test_habillage",
        "folder": dossier,
        "created_by": createur,
    }

    print("   Envoi en cours…")
    try:
        r = sess.post(f"{rest}/images/", files=fichier, data=donnees,
                      timeout=60)
        print(f"   POST → HTTP {r.status_code}")
        if r.status_code in (200, 201):
            cree = r.json()
            print("   ✅ DÉPÔT RÉUSSI. L'image créée :")
            for k, v in sorted(cree.items()):
                print(f"      {k:16} = {json.dumps(v, ensure_ascii=False)[:64]}")
            url = cree.get("url", "")
            print("\n   → Une bannière se pose donc en deux temps :")
            print("        1. POST multipart sur /rest/images/  (champ « file »)")
            print("        2. PATCH de la chaîne : headband = <url de l'image>")
            if url and input("\n   Supprimer cette image de test ? (O/n) : "
                             ).strip().lower() in ("", "o", "oui", "y"):
                rd = sess.delete(url, timeout=30)
                print(f"   Suppression → HTTP {rd.status_code}"
                      + ("  (nettoyée)" if rd.status_code in (204, 200) else
                         "  ⚠ à supprimer à la main"))
        else:
            print("   ❌ DÉPÔT REFUSÉ. Réponse du serveur :")
            print("      " + r.text[:500])
            print("\n   → Comparez les champs refusés avec le schéma affiché plus haut :")
            print("      la réponse du serveur indique précisément ce qui manque.")
    except Exception as e:
        print(f"   [X] Envoi impossible : {e}")


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

    schema_images(sess, rest)
    exemple_image(sess, rest)
    test_ecriture(sess, rest, requests)

    print(f"\n{'=' * 68}\n  CE QU'IL FAUT RETENIR\n{'=' * 68}")
    print("""
   • Si le schéma POST existe et qu'un champ de type fichier apparaît, le dépôt
     de bannières est réalisable depuis PodAdmin.
   • Si le test d'écriture a réussi, la marche à suivre est confirmée :
     dépôt de l'image, puis liaison de son URL à la chaîne.
   • Si la ressource est en lecture seule, les bannières devront être déposées
     depuis l'interface web de Pod ; PodAdmin ne pourrait alors que réutiliser
     des images DÉJÀ présentes sur l'instance — ce qui reste utile.

   Transmettez cette sortie complète.
""")


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
