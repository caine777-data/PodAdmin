#!/usr/bin/env python3
"""
verifier_habillage.py — Sonde : que peut-on piloter par l'API ?
================================================================
Objectif : déterminer, AVANT d'écrire la moindre ligne d'interface, ce que
l'API REST d'Esup-Pod expose réellement en matière de :

  1. HABILLAGE DES CHAÎNES — image de couverture, bannière, couleur, style,
     description enrichie ;
  2. THÈMES — mêmes questions (un thème est une sous-section de chaîne) ;
  3. PAGE D'ACCUEIL — vidéos mises en avant, chaînes affichées, texte de
     présentation.

Pourquoi cette sonde : l'expérience du projet montre que l'API expose beaucoup
moins que l'interface web. Les jetons d'authentification, par exemple, ne sont
pas accessibles en REST et n'ont pu être traités que par un renvoi vers
l'administration Django. Il est probable que la page d'accueil relève de la même
catégorie (réglage global de l'instance, hors API). Autant le savoir tout de
suite plutôt qu'à mi-chemin.

La sonde est en LECTURE SEULE : elle ne modifie rien.

AUTONOME : ce fichier se suffit à lui-même. Il n'a besoin d'aucun autre fichier
du projet et peut être copié sur n'importe quel poste disposant de Python. Sa
seule dépendance est la bibliothèque « requests », qu'il propose d'installer
lui-même si elle manque.

    python verifier_habillage.py

Elle répond à trois questions par ressource :
  • le champ existe-t-il ?
  • est-il modifiable (présent dans le schéma d'écriture) ?
  • quel est son type (texte, image, couleur…) ?
"""

__author__ = "Cédric MONNA"
__version__ = "1.0.0"

import json

# Mots-clés recherchés dans les noms de champs, par thématique.
MOTS_HABILLAGE = ("image", "banner", "headband", "logo", "thumbnail", "poster",
                  "cover", "color", "couleur", "style", "css", "background",
                  "description", "visible", "title")
MOTS_ACCUEIL = ("home", "accueil", "front", "featured", "highlight", "carousel",
                "slider", "block", "bloc", "banner", "welcome")


def afficher_champs(schema: dict, mots: tuple, titre: str):
    """Affiche les champs du schéma dont le nom évoque l'une des thématiques."""
    print(f"\n   {titre}")
    trouves = []
    for nom, meta in (schema or {}).items():
        if any(m in nom.lower() for m in mots):
            t = meta.get("type", "?")
            ro = meta.get("read_only", False)
            req = meta.get("required", False)
            etat = "LECTURE SEULE" if ro else ("modifiable" + (" (requis)" if req else ""))
            trouves.append((nom, t, etat))
    if not trouves:
        print("      (aucun champ correspondant)")
        return
    for nom, t, etat in sorted(trouves):
        print(f"      • {nom:28} type={t:12} {etat}")


def sonder_ressource(sess, rest: str, chemin: str, mots: tuple, libelle: str):
    """Interroge le schéma d'une ressource (OPTIONS) puis un exemple réel."""
    print(f"\n{'=' * 68}\n  {libelle}  ({chemin})\n{'=' * 68}")

    # 1. Schéma d'écriture : ce que l'API accepte de modifier.
    try:
        r = sess.options(f"{rest}{chemin}", timeout=30)
        print(f"   OPTIONS → HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            actions = (data.get("actions") or {})
            schema = actions.get("POST") or actions.get("PUT") or {}
            if schema:
                afficher_champs(schema, mots, "Champs pertinents (schéma d'écriture) :")
                print(f"\n      Total : {len(schema)} champ(s) modifiable(s).")
            else:
                print("      (aucun schéma d'écriture exposé — ressource peut-être "
                      "en lecture seule pour ce compte)")
        else:
            print("      (OPTIONS refusé : impossible de connaître les champs modifiables)")
    except Exception as e:
        print(f"   [X] OPTIONS impossible : {e}")

    # 2. Exemple réel : ce que l'API renvoie effectivement.
    try:
        r = sess.get(f"{rest}{chemin}", params={"limit": 1}, timeout=30)
        if r.status_code != 200:
            print(f"   GET → HTTP {r.status_code} (ressource inaccessible)")
            return
        data = r.json()
        exemples = data.get("results") if isinstance(data, dict) else data
        if not exemples:
            print("   GET → aucun élément pour l'échantillon.")
            return
        ex = exemples[0]
        print(f"\n   Champs RÉELLEMENT renvoyés ({len(ex)}) :")
        print("      " + ", ".join(sorted(ex.keys())))
        pertinents = {k: v for k, v in ex.items() if any(m in k.lower() for m in mots)}
        if pertinents:
            print("\n   Valeurs des champs pertinents :")
            for k, v in sorted(pertinents.items()):
                apercu = json.dumps(v, ensure_ascii=False)[:70]
                print(f"      • {k:28} = {apercu}")
    except Exception as e:
        print(f"   [X] GET impossible : {e}")


def explorer_racine(sess, rest: str):
    """Liste TOUTES les ressources exposées : la page d'accueil a-t-elle la sienne ?"""
    print(f"\n{'=' * 68}\n  RESSOURCES EXPOSÉES PAR L'API  ({rest}/)\n{'=' * 68}")
    try:
        r = sess.get(f"{rest}/", timeout=30)
        if r.status_code != 200:
            print(f"   HTTP {r.status_code} — racine inaccessible.")
            return
        data = r.json()
        if not isinstance(data, dict):
            print("   (format inattendu)")
            return
        noms = sorted(data.keys())
        print(f"   {len(noms)} ressource(s) :")
        for n in noms:
            marque = "  ← à examiner" if any(m in n.lower() for m in MOTS_ACCUEIL) else ""
            print(f"      • {n}{marque}")
        candidats = [n for n in noms if any(m in n.lower() for m in MOTS_ACCUEIL)]
        print("\n   Ressource liée à la page d'accueil :",
              ", ".join(candidats) if candidats else
              "AUCUNE — la page d'accueil n'est probablement pas pilotable par l'API.")
    except Exception as e:
        print(f"   [X] Exploration impossible : {e}")


def charger_requests():
    """Importe `requests`, en proposant de l'installer si nécessaire.

    La sonde est prévue pour être lancée depuis N'IMPORTE QUEL poste, sans avoir
    installé le projet : ce module est sa seule dépendance."""
    try:
        import requests
        return requests
    except ImportError:
        pass
    print("La bibliothèque « requests » est nécessaire et n'est pas installée.")
    rep = input("L'installer maintenant ? (o/N) : ").strip().lower()
    if rep not in ("o", "oui", "y", "yes"):
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
        print("    Essayez à la main :   pip install requests")
        return None


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

    explorer_racine(sess, rest)
    sonder_ressource(sess, rest, "/channels/", MOTS_HABILLAGE, "CHAÎNES — habillage")
    sonder_ressource(sess, rest, "/themes/", MOTS_HABILLAGE, "THÈMES — habillage")

    print(f"\n{'=' * 68}\n  CE QU'IL FAUT RETENIR\n{'=' * 68}")
    print("""
   • Un champ « modifiable » dans le schéma d'écriture peut être piloté depuis
     PodAdmin.
   • Un champ « LECTURE SEULE », ou absent du schéma, ne peut PAS être modifié
     par l'API : il faudrait passer par l'administration Django (comme pour les
     jetons d'authentification).
   • Un champ de type « image » suppose un envoi de FICHIER (multipart), et non
     un simple texte : c'est faisable, mais plus lourd qu'un champ ordinaire.
   • Si aucune ressource « accueil » n'apparaît dans la liste ci-dessus, la page
     d'accueil est un réglage global de l'instance, hors de portée de l'API.

   Transmettez cette sortie complète : elle permet de déterminer précisément ce
   qui est réalisable avant d'écrire la moindre interface.
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
