#!/usr/bin/env python3
"""
verifier_discipline_ecriture.py — Sonde : créer réellement une discipline
=========================================================================
Dernière inconnue avant de coder le module « Disciplines ».

CE QUE LES SONDES PRÉCÉDENTES ONT ÉTABLI
----------------------------------------
  • `verifier_disciplines.py` : la ressource existe, la table est vide, la
    création est permise (seul `title` obligatoire), aucun champ de
    propriétaire — c'est bien un classement d'établissement — et le champ est
    modifiable sur la vidéo.
  • `verifier_discipline_forme.py` : le champ est une relation MULTIPLE. Les
    vidéos renvoient `discipline = []`, une liste vide, ce qui ne se confond
    pas avec une absence de valeur.

CE QUI RESTE INCONNU, ET POURQUOI ON NE PEUT PAS LE DEVINER
-----------------------------------------------------------
Sous quelle forme envoyer le champ `site`. L'instance emploie DEUX formes
différentes pour ce même champ selon la ressource :

    types     →  site = ["https://…/sites/1/"]     (une liste)
    channels  →  site = "https://…/sites/1/"       (une chaîne)

La table `discipline` étant vide, aucune valeur ne peut être lue. Et `OPTIONS`
répond « type: field » sans sous-schéma — exactement ce qu'il répondait pour
`discipline` sur les vidéos, où il s'est pourtant avéré que c'était une liste.
Sur ce serveur, l'absence de sous-schéma ne prouve donc rien.

Se tromper de forme produit un HTTP 400 au premier enregistrement. La seule
façon de savoir est d'essayer.

⚠️ CETTE SONDE ÉCRIT
--------------------
Contrairement aux précédentes, elle CRÉE puis SUPPRIME des objets. Elle
procède ainsi :

  1. elle essaie de créer une discipline jetable, en testant les trois formes
     possibles du champ `site` (liste, chaîne, omis) jusqu'à ce que l'une
     passe ;
  2. elle RELIT ce qui a réellement été enregistré — le serveur peut accepter
     une valeur puis en stocker une autre, ou ignorer le site en silence ;
  3. elle propose, séparément et sur confirmation, de rattacher cette
     discipline à UNE vidéo de test pour vérifier le PATCH, puis remet la
     vidéo dans son état initial ;
  4. elle SUPPRIME la discipline jetable dans tous les cas, y compris en cas
     d'erreur.

Le nom employé est reconnaissable et horodaté, de sorte qu'un reliquat soit
identifiable si le nettoyage échouait.

À lancer de préférence sur l'instance de TEST. Sur la production, l'objet créé
est supprimé dans la foulée et n'est visible de personne entre-temps, mais
autant éviter.

    python verifier_discipline_ecriture.py
"""

__author__ = "Cédric MONNA"
__version__ = "1.0.0"

import json
from datetime import datetime

PREFIXE_JETABLE = "ZZ_SONDE_PODADMIN_"


def charger_requests():
    """Importe « requests », en proposant de l'installer si nécessaire."""
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


def lire_site(sess, rest):
    """Renvoie l'URL du premier site déclaré, ou None."""
    try:
        r = sess.get(f"{rest}/sites/", timeout=25)
        data = r.json()
        sites = data.get("results", []) if isinstance(data, dict) else (data or [])
        for s in sites:
            if isinstance(s, dict) and s.get("url"):
                return s["url"]
    except Exception as e:
        print(f"   ❌ Lecture des sites impossible : {e}")
    return None


def tenter_creation(sess, rest, titre, site_url):
    """Essaie les trois formes du champ `site`, dans l'ordre du plus probable.

    Renvoie (forme_retenue, objet_créé) ou (None, None) si tout échoue.

    L'ordre n'est pas indifférent : on commence par la LISTE parce que c'est la
    forme employée par `types`, la ressource la plus proche de `discipline`
    (toutes deux sont des nomenclatures d'établissement, quand `channels` est
    d'une autre nature)."""
    formes = [
        ("liste",  {"title": titre, "site": [site_url]}),
        ("chaîne", {"title": titre, "site": site_url}),
        ("omis",   {"title": titre}),
    ]
    for nom, charge in formes:
        try:
            r = sess.post(f"{rest}/discipline/", json=charge, timeout=30)
        except Exception as e:
            print(f"      {nom:7} → requête impossible : {e}")
            continue
        if r.status_code in (200, 201):
            print(f"      {nom:7} → ✅ ACCEPTÉ (HTTP {r.status_code})")
            try:
                return nom, r.json()
            except Exception:
                return nom, {}
        # Un 400 sur la forme est exactement l'information recherchée : on
        # affiche le motif, il désigne le champ fautif.
        motif = (r.text or "")[:200].replace("\n", " ")
        print(f"      {nom:7} → refusé (HTTP {r.status_code}) : {motif}")
    return None, None


def relire(sess, rest, url):
    """Relit l'objet créé : le serveur peut stocker autre chose que l'envoyé."""
    try:
        r = sess.get(url, timeout=25)
        if r.status_code == 200:
            return r.json()
        print(f"   ⚠  Relecture impossible (HTTP {r.status_code}).")
    except Exception as e:
        print(f"   ⚠  Relecture impossible : {e}")
    return None


def essai_rattachement(sess, rest, url_discipline):
    """Vérifie qu'une vidéo accepte la discipline, puis REMET son état initial.

    C'est le point qui décide de tout : créer une nomenclature qu'on ne peut
    rattacher à rien ne servirait à rien."""
    print(f"\n{'=' * 70}")
    print("  ESSAI DE RATTACHEMENT SUR UNE VIDÉO")
    print("=" * 70)
    print("\n   Cet essai MODIFIE une vidéo réelle, puis la remet exactement")
    print("   dans son état de départ (la valeur d'origine est relue avant).")
    if input("\n   Procéder ? (o/N) : ").strip().lower() not in ("o", "oui", "y"):
        print("   Ignoré.")
        return

    try:
        r = sess.get(f"{rest}/videos/", params={"limit": 1}, timeout=30)
        data = r.json()
        videos = data.get("results", []) if isinstance(data, dict) else (data or [])
        if not videos:
            print("   ❌ Aucune vidéo lisible.")
            return
        video = videos[0]
        url_video = video.get("url")
        avant = video.get("discipline", [])
        print(f"\n   Vidéo d'essai : {video.get('slug')}")
        print(f"   Valeur AVANT  : {json.dumps(avant, ensure_ascii=False)}")

        # Envoi en LISTE : la sonde précédente a établi que c'est une relation
        # multiple.
        r = sess.patch(url_video, json={"discipline": [url_discipline]}, timeout=30)
        if r.status_code not in (200, 202):
            print(f"   ❌ PATCH refusé (HTTP {r.status_code}) : "
                  f"{(r.text or '')[:200]}")
            return
        apres = (r.json() or {}).get("discipline")
        print(f"   Valeur APRÈS  : {json.dumps(apres, ensure_ascii=False)}")
        if apres and url_discipline.rstrip("/") in [str(x).rstrip("/") for x in apres]:
            print("   ✅ RATTACHEMENT CONFIRMÉ — le PATCH en liste fonctionne.")
        else:
            print("   ⚠  Le serveur a accepté le PATCH mais n'a pas stocké la")
            print("      discipline attendue. À signaler.")
    except Exception as e:
        print(f"   ❌ Essai impossible : {e}")
    finally:
        # Remise en état, quoi qu'il arrive.
        try:
            sess.patch(url_video, json={"discipline": avant}, timeout=30)
            verif = sess.get(url_video, timeout=25).json().get("discipline")
            etat = "restaurée" if verif == avant else f"⚠ ÉTAT ACTUEL : {verif}"
            print(f"   Vidéo {etat}.")
        except Exception as e:
            print(f"   ⚠️  REMISE EN ÉTAT ÉCHOUÉE : {e}")
            print(f"      Vérifiez manuellement la vidéo {video.get('slug')}.")


def run():
    requests = charger_requests()
    if requests is None:
        return

    base = (input("URL de l'instance [https://videos.utoulouse.fr] : ").strip()
            or "https://videos.utoulouse.fr").rstrip("/")
    token = input("Jeton : ").strip()
    if not token:
        print("[X] Jeton vide.")
        return

    rest = f"{base}/rest"
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Token {token}",
                         "Accept": "application/json"})

    print(f"\n{'=' * 70}")
    print("  DISCIPLINE — essai d'écriture réel")
    print(f"  Instance : {base}")
    print("  ⚠️  CETTE SONDE CRÉE PUIS SUPPRIME UN OBJET")
    print("=" * 70)
    print("\n   Un objet jetable sera créé, relu, puis supprimé. Son nom est")
    print(f"   préfixé « {PREFIXE_JETABLE} » afin d'être reconnaissable si le")
    print("   nettoyage échouait.")
    if input("\n   Continuer ? (o/N) : ").strip().lower() not in ("o", "oui", "y"):
        print("   Annulé — aucune écriture effectuée.")
        return

    site_url = lire_site(sess, rest)
    print(f"\n   Site déclaré : {site_url or '(aucun)'}")

    titre = PREFIXE_JETABLE + datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n{'=' * 70}")
    print("  QUESTION — sous quelle forme envoyer le champ « site » ?")
    print("=" * 70)
    print(f"\n   Titre jetable : {titre}\n")

    forme, cree = (None, None)
    url_creee = None
    try:
        forme, cree = tenter_creation(sess, rest, titre, site_url)
        if not forme:
            print("\n   ❌ AUCUNE forme n'a été acceptée. Reportez la sortie")
            print("      complète : les motifs de refus ci-dessus désignent le")
            print("      champ fautif.")
            return

        url_creee = (cree or {}).get("url")
        print(f"\n   ✅ Forme retenue : « {forme} »")
        print(f"   URL créée      : {url_creee}")

        # Relecture : le serveur peut accepter une valeur et en stocker une autre.
        relu = relire(sess, rest, url_creee) if url_creee else None
        if relu:
            print("\n   Objet tel qu'il est RÉELLEMENT enregistré :")
            print("   " + json.dumps(relu, ensure_ascii=False, indent=3)[:700])
            site_stocke = relu.get("site")
            if not site_stocke:
                print("\n   ⚠  Le champ « site » est VIDE après création.")
                print("      La discipline risque de n'apparaître sur aucun site.")
            else:
                print(f"\n   🟢 Site enregistré : "
                      f"{json.dumps(site_stocke, ensure_ascii=False)}")

        if url_creee:
            essai_rattachement(sess, rest, url_creee)

    finally:
        # NETTOYAGE, quoi qu'il arrive.
        if url_creee:
            print(f"\n{'=' * 70}")
            print("  NETTOYAGE")
            print("=" * 70)
            try:
                r = sess.delete(url_creee, timeout=25)
                if r.status_code in (200, 202, 204):
                    print(f"   ✅ Discipline jetable supprimée ({url_creee}).")
                else:
                    print(f"   ⚠️  SUPPRESSION ÉCHOUÉE (HTTP {r.status_code}).")
                    print(f"      Supprimez manuellement « {titre} » dans")
                    print(f"      {base}/admin/video/discipline/")
            except Exception as e:
                print(f"   ⚠️  SUPPRESSION ÉCHOUÉE : {e}")
                print(f"      Supprimez manuellement « {titre} ».")

    print(f"""
{'=' * 70}
  CE QUE PODADMIN FERA
{'=' * 70}

   • Création  : champ « site » envoyé sous la forme « {forme} »
   • Rattachement : PATCH /rest/videos/<slug>/ avec une LISTE d'URLs
   • Interface : cases à cocher, une vidéo pouvant porter plusieurs
     disciplines

   Transmettez cette sortie complète (le jeton n'y figure pas).
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
