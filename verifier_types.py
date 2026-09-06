#!/usr/bin/env python3
"""
verifier_types.py — Sonde : gérer les TYPES de vidéo depuis PodAdmin ?
======================================================================
PodAdmin LIT déjà les types partout — menu au Téléversement, filtre et action
de masse dans Vidéos. Ce qu'il ne sait pas faire, c'est les CRÉER, les
renommer et les supprimer, comme il le fait pour les chaînes.

Cette sonde répond aux quatre questions qui décident du module.

  1. QUE CONTIENT DÉJÀ LA TABLE ?
     Contrairement aux disciplines, les types sont DÉJÀ PEUPLÉS et
     DÉJÀ UTILISÉS par des vidéos en production. On ne part donc pas d'une
     page blanche : renommer ou supprimer un type touche des contenus
     existants. La sonde liste ce qui existe et compte les vidéos rattachées.

  2. LA CRÉATION EST-ELLE PERMISE ?
     `OPTIONS` sur la collection : si `actions.POST` existe, on peut créer, et
     on connaît les champs obligatoires.

  3. LE RENOMMAGE ET LA SUPPRESSION SONT-ILS PERMIS ?
     `OPTIONS` sur un élément précis, et non sur la collection : une ressource
     peut accepter la création sans accepter la modification. C'est
     précisément ce qui distingue un module « créer seulement » d'un module
     complet.

  4. QUE DEVIENDRAIENT LES VIDÉOS D'UN TYPE SUPPRIMÉ ?
     Cette question ne se sonde PAS sans détruire quelque chose. La sonde se
     borne à compter les vidéos concernées par chaque type, pour que la
     décision soit prise en connaissance de cause. Supprimer un type utilisé
     par 300 vidéos n'est pas la même chose que supprimer un type vide.

CE QUI EST DÉJÀ ÉTABLI
----------------------
Le champ `site` d'un type s'écrit sous forme de LISTE :

    types  →  site = ["https://videos.utoulouse.fr/rest/sites/1/"]

Constaté en lecture sur des types réels lors d'une sonde précédente. Cela évite
d'avoir à tâtonner comme pour les disciplines, dont la table vide ne permettait
aucune lecture.

MODE : LECTURE SEULE. GET et OPTIONS uniquement. Rien n'est créé ni modifié.

    python verifier_types.py
"""

__author__ = "Cédric MONNA"
__version__ = "1.0.0"

import json


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


def lister_types(sess, rest):
    """Liste les types existants. Renvoie [(titre, url, dict)]."""
    print(f"\n{'=' * 70}")
    print("  QUESTION 1 — que contient déjà la table ?")
    print("=" * 70)
    types = []
    url = f"{rest}/types/"
    pages = 0
    # Pagination en suivant `next`, comme partout ailleurs dans le projet.
    while url and pages < 20:
        try:
            r = sess.get(url, params={"limit": 100} if pages == 0 else None, timeout=30)
        except Exception as e:
            print(f"   ❌ Requête impossible : {e}")
            return types
        if r.status_code != 200:
            print(f"   ❌ HTTP {r.status_code} sur /types/")
            return types
        data = r.json()
        if isinstance(data, dict):
            types.extend(data.get("results", []))
            url = data.get("next")
        else:
            types.extend(data or [])
            url = None
        pages += 1

    print(f"\n   {len(types)} type(s) déclaré(s) :\n")
    for t in types:
        if isinstance(t, dict):
            site = t.get("site")
            forme = ("liste" if isinstance(site, list)
                     else "chaîne" if isinstance(site, str) else "absent")
            print(f"      • {str(t.get('title', '?'))[:38]:40} "
                  f"slug={str(t.get('slug', '?'))[:18]:20} site: {forme}")

    if types and isinstance(types[0], dict):
        print(f"\n   Champs lus : {', '.join(sorted(types[0].keys()))}")
    return [(t.get("title", "?"), t.get("url", ""), t) for t in types
            if isinstance(t, dict)]


def compter_videos(sess, rest, liste_types):
    """Compte les vidéos rattachées à chaque type.

    C'est le chiffre qui compte pour la décision : supprimer un type vide et
    supprimer un type porté par 300 vidéos ne sont pas la même opération."""
    print(f"\n{'=' * 70}")
    print("  QUESTION 4 — combien de vidéos chaque type porte-t-il ?")
    print("=" * 70)
    print("\n   (lecture de tout le fonds, un instant…)\n")

    videos = []
    url = f"{rest}/videos/"
    pages = 0
    while url and pages < 80:
        try:
            r = sess.get(url, params={"limit": 100} if pages == 0 else None, timeout=45)
            if r.status_code != 200:
                print(f"   ⚠  Lecture interrompue (HTTP {r.status_code}) après "
                      f"{len(videos)} vidéos : les comptes ci-dessous sont partiels.")
                break
            data = r.json()
            if isinstance(data, dict):
                videos.extend(data.get("results", []))
                url = data.get("next")
            else:
                videos.extend(data or [])
                url = None
            pages += 1
        except Exception as e:
            print(f"   ⚠  Lecture interrompue : {e}")
            break

    comptes = {}
    sans_type = 0
    for v in videos:
        if not isinstance(v, dict):
            continue
        vt = v.get("type")
        vt = vt.get("url") if isinstance(vt, dict) else vt
        if not vt:
            sans_type += 1
            continue
        comptes[str(vt).rstrip("/")] = comptes.get(str(vt).rstrip("/"), 0) + 1

    print(f"   {len(videos)} vidéo(s) lues.\n")
    for titre, url_type, _t in liste_types:
        n = comptes.get(str(url_type).rstrip("/"), 0)
        marque = "  ⚠ supprimer ce type toucherait ces vidéos" if n else "  (vide)"
        print(f"      {titre[:38]:40} {n:5} vidéo(s){marque}")
    if sans_type:
        print(f"\n      {'(sans type)':40} {sans_type:5} vidéo(s)")
    return comptes


def droits_ecriture(sess, rest, liste_types):
    """Création, renommage, suppression : que permet réellement l'API ?"""
    print(f"\n{'=' * 70}")
    print("  QUESTIONS 2 et 3 — création, renommage, suppression")
    print("=" * 70)

    resultat = {"creer": False, "modifier": False, "supprimer": False,
                "requis": [], "champs": []}

    # — Création : OPTIONS sur la COLLECTION —
    try:
        r = sess.options(f"{rest}/types/", timeout=25)
        if r.status_code == 200:
            actions = (r.json().get("actions") or {})
            post = actions.get("POST")
            if post:
                resultat["creer"] = True
                resultat["champs"] = sorted(post.keys())
                resultat["requis"] = sorted(
                    k for k, v in post.items()
                    if v.get("required") and not v.get("read_only"))
                print(f"\n   ✏  CRÉATION POSSIBLE — {len(post)} champ(s) en écriture.")
                print(f"      Champs modifiables  : {', '.join(resultat['champs'])}")
                print(f"      Champs OBLIGATOIRES : "
                      f"{', '.join(resultat['requis']) or '(aucun)'}")
                if "site" in post:
                    print("\n      Champ « site » :")
                    print("      " + json.dumps(post["site"], ensure_ascii=False,
                                                indent=3)[:300])
            else:
                print("\n   👁  Création IMPOSSIBLE par l'API (pas d'action POST).")
        else:
            print(f"\n   ?  OPTIONS /types/ → HTTP {r.status_code}.")
    except Exception as e:
        print(f"\n   ❌ OPTIONS /types/ impossible : {e}")

    # — Renommage et suppression : OPTIONS sur UN ÉLÉMENT —
    # Distinction importante : une ressource peut accepter la création sans
    # accepter la modification. Interroger la collection ne le dirait pas.
    if not liste_types:
        print("\n   ⚠  Aucun type existant : renommage et suppression non testables.")
        return resultat

    url_test = liste_types[0][1]
    print(f"\n   Élément témoin : {liste_types[0][0]}")
    try:
        r = sess.options(url_test, timeout=25)
        if r.status_code == 200:
            actions = (r.json().get("actions") or {})
            if actions.get("PUT") or actions.get("PATCH"):
                resultat["modifier"] = True
                print("   ✏  RENOMMAGE POSSIBLE (PATCH ou PUT accepté).")
            else:
                print("   👁  Renommage impossible : aucune action PUT/PATCH.")
            # DRF n'annonce pas DELETE dans `actions` ; l'en-tête Allow le dit.
            autorises = (r.headers.get("Allow") or "").upper()
            print(f"   Méthodes annoncées : {autorises or '(non précisé)'}")
            if "DELETE" in autorises:
                resultat["supprimer"] = True
                print("   🗑  SUPPRESSION annoncée comme possible.")
            else:
                print("   🔒 Suppression non annoncée.")
        else:
            print(f"   ?  OPTIONS sur l'élément → HTTP {r.status_code}.")
    except Exception as e:
        print(f"   ❌ OPTIONS sur l'élément impossible : {e}")

    return resultat


def synthese(droits, liste_types, comptes):
    print(f"\n{'=' * 70}")
    print("  SYNTHÈSE — quel module peut-on construire ?")
    print("=" * 70 + "\n")

    lignes = [("Créer un type", droits["creer"]),
              ("Renommer un type", droits["modifier"]),
              ("Supprimer un type", droits["supprimer"])]
    for libelle, ok in lignes:
        print(f"   {'✅' if ok else '⛔'}  {libelle}")

    peuples = sum(1 for t in liste_types
                  if comptes.get(str(t[1]).rstrip("/"), 0) > 0)
    print(f"\n   {len(liste_types)} type(s) existant(s), dont {peuples} "
          f"déjà utilisé(s) par des vidéos.")

    print("\n   DÉCISION :\n")
    if droits["creer"] and droits["modifier"] and droits["supprimer"]:
        print("   ✅ Module COMPLET possible, sur le modèle de l'onglet Chaînes :")
        print("      liste, création, renommage, suppression.")
    elif droits["creer"]:
        print("   🟠 Création possible, mais pas tout le reste : le module se")
        print("      limiterait à lister et créer. Renommer ou supprimer")
        print("      resterait dans l'administration Django.")
    else:
        print("   ⛔ L'API ne permet pas de créer de type. PodAdmin continuerait")
        print("      à les LIRE seulement, comme aujourd'hui.")

    if peuples:
        print(f"""
   ⚠️  ATTENTION — {peuples} type(s) portent déjà des vidéos.
      Contrairement aux disciplines (table vide, page blanche), toute
      suppression ici touche des contenus en production. Si le module inclut
      la suppression, il devra afficher le nombre de vidéos concernées AVANT
      de confirmer — et il reste à déterminer ce que le serveur fait de ces
      vidéos : type vidé, ou refus de suppression. Cela ne se sonde pas sans
      détruire quelque chose.""")

    print("\n   Transmettez cette sortie complète (le jeton n'y figure pas).\n")


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
    print("  TYPES DE VIDÉO — gérables depuis PodAdmin ?")
    print(f"  Instance : {base}")
    print("  Mode : LECTURE SEULE (GET et OPTIONS uniquement)")
    print("=" * 70)

    liste = lister_types(sess, rest)
    droits = droits_ecriture(sess, rest, liste)
    comptes = compter_videos(sess, rest, liste)
    synthese(droits, liste, comptes)


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
