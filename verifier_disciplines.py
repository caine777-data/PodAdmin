#!/usr/bin/env python3
"""
verifier_disciplines.py — Sonde : peut-on créer disciplines et catégories ?
===========================================================================
Objectif : décider si PodAdmin peut gérer les DISCIPLINES et les CATÉGORIES
depuis l'application, plutôt que de renvoyer vers l'administration Django.

POURQUOI CETTE SONDE
--------------------
Les deux tables sont vides sur l'instance. Avant d'ouvrir la plateforme aux
enseignants, il faut décider de la nomenclature — et rattacher des centaines de
vidéos après coup coûterait bien plus cher que de le faire au dépôt.

Mais AVANT de coder quoi que ce soit, trois questions doivent être tranchées.
Elles ne sont pas de détail : selon les réponses, le développement est évident,
inutile, ou impossible.

  1. QUI POSSÈDE UNE CATÉGORIE ?
     On a supposé que discipline et catégorie étaient toutes deux des
     classements d'ÉTABLISSEMENT. C'est peut-être faux pour les catégories :
     dans Pod, elles pourraient être PERSONNELLES (un champ « owner »), comme
     les listes de lecture. Si c'est le cas, les créer depuis PodAdmin n'aurait
     aucun sens : elles appartiendraient au compte administrateur et resteraient
     invisibles pour tout le monde.
     >>> Le champ « owner » sur la ressource est le juge de paix. <<<

  2. LA RESSOURCE ACCEPTE-T-ELLE UNE CRÉATION ?
     Une ressource peut être lisible sans être modifiable. La méthode OPTIONS
     répond : si « actions.POST » existe, on peut créer, et on connaît du même
     coup les champs obligatoires.

  3. LE CHAMP REMONTE-T-IL SUR LA VIDÉO, EN ÉCRITURE ?
     Créer une nomenclature qu'on ne peut rattacher à aucune vidéo ne servirait
     à rien. On vérifie donc que « discipline » (et/ou « categories ») figure
     dans les champs modifiables de /rest/videos/.

La sonde teste plusieurs noms de ressource (singulier, pluriel, français,
anglais) : le nom exact varie selon les versions de Pod, et deviner serait
exactement l'erreur que cette méthode cherche à éviter.

MODE : LECTURE SEULE. Aucune création, aucune modification, aucune suppression.
       Les méthodes employées sont GET et OPTIONS uniquement.

AUTONOME : ce fichier se suffit à lui-même, aucun autre fichier du projet n'est
nécessaire. Seule dépendance : la bibliothèque « requests ».

    python verifier_disciplines.py
"""

__author__ = "Cédric MONNA"
__version__ = "1.0.0"

import json

# ---------------------------------------------------------------------------
# Noms de ressource à tester.
# On ratisse large volontairement : une ressource absente répond 404, ce qui
# ne coûte qu'une requête, alors qu'un nom manqué ferait conclure à tort
# « fonctionnalité indisponible ».
# ---------------------------------------------------------------------------
CANDIDATS = [
    ("discipline",   "Discipline (singulier — nom vu dans les sondes précédentes)"),
    ("disciplines",  "Discipline (pluriel — convention DRF habituelle)"),
    ("categories",   "Catégorie (pluriel)"),
    ("category",     "Catégorie (singulier)"),
    ("categorie",    "Catégorie (orthographe française, au cas où)"),
]

# Champs dont la présence trahit un classement PERSONNEL et non
# d'établissement. C'est le point le plus important de toute la sonde.
CHAMPS_APPARTENANCE = ("owner", "user", "author", "created_by")


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


def examiner(sess, rest, nom, libelle):
    """Examine une ressource candidate : existence, contenu, appartenance,
    et possibilité de création. Renvoie un bilan exploitable par la synthèse."""
    bilan = {
        "nom": nom, "libelle": libelle, "existe": False, "nombre": None,
        "creable": False, "champs_post": [], "requis": [],
        "personnel": False, "indice_personnel": None, "exemple": None,
    }

    # --- 1. La ressource existe-t-elle, et que contient-elle ? --------------
    try:
        r = sess.get(f"{rest}/{nom}/", params={"limit": 5}, timeout=30)
    except Exception as e:
        print(f"\n  {nom:14} ❌ requête impossible : {e}")
        return bilan

    if r.status_code == 404:
        # Cas le plus fréquent et le moins intéressant : on n'encombre pas
        # l'affichage, une ligne suffit.
        print(f"\n  {nom:14} —  n'existe pas sur cette instance (404)")
        return bilan
    if r.status_code != 200:
        print(f"\n  {nom:14} ❌ HTTP {r.status_code} — inaccessible avec ce jeton")
        return bilan

    bilan["existe"] = True
    print(f"\n{'─' * 70}")
    print(f"  {nom.upper()}  —  {libelle}")
    print("─" * 70)

    try:
        data = r.json()
    except Exception:
        print("   ❌ Réponse illisible (pas du JSON).")
        return bilan

    if isinstance(data, dict):
        bilan["nombre"] = data.get("count")
        echantillon = data.get("results") or []
    else:
        echantillon = data or []
        bilan["nombre"] = len(echantillon)

    n = bilan["nombre"]
    if n == 0:
        print("   ⚠  Table VIDE — c'est bien la situation attendue.")
    else:
        print(f"   ✅ {n} élément(s) déjà présent(s) :")
        for e in echantillon[:5]:
            if isinstance(e, dict):
                # On affiche ce qui ressemble à un libellé, sans présumer du nom
                # exact du champ selon les versions.
                titre = (e.get("title") or e.get("name")
                         or e.get("libelle") or e.get("slug") or "?")
                print(f"      • {titre}")

    if echantillon and isinstance(echantillon[0], dict):
        ex = echantillon[0]
        bilan["exemple"] = ex
        print(f"\n   Champs lus ({len(ex)}) : " + ", ".join(sorted(ex.keys())))

    # --- 2. Personnel ou d'établissement ? ---------------------------------
    # Question décisive. On la pose sur les champs LUS (si la table contient
    # quelque chose) ET sur les champs d'ÉCRITURE (renvoyés par OPTIONS), car
    # une table vide ne révèle rien par elle-même.
    for champ in CHAMPS_APPARTENANCE:
        if bilan["exemple"] and champ in bilan["exemple"]:
            bilan["personnel"] = True
            bilan["indice_personnel"] = f"champ « {champ} » présent en lecture"
            break

    # --- 3. Peut-on créer ? -------------------------------------------------
    try:
        ro = sess.options(f"{rest}/{nom}/", timeout=20)
        if ro.status_code == 200:
            actions = (ro.json().get("actions") or {})
            post = actions.get("POST")
            if post:
                bilan["creable"] = True
                bilan["champs_post"] = sorted(post.keys())
                bilan["requis"] = sorted(
                    k for k, v in post.items()
                    if v.get("required") and not v.get("read_only")
                )
                print(f"\n   ✏  CRÉATION POSSIBLE — {len(post)} champ(s) en écriture.")
                print(f"      Champs modifiables  : {', '.join(bilan['champs_post'])}")
                print(f"      Champs OBLIGATOIRES : "
                      f"{', '.join(bilan['requis']) if bilan['requis'] else '(aucun)'}")

                # Second contrôle d'appartenance, sur les champs d'écriture.
                for champ in CHAMPS_APPARTENANCE:
                    if champ in post and not bilan["personnel"]:
                        bilan["personnel"] = True
                        bilan["indice_personnel"] = (
                            f"champ « {champ} » attendu à la création")
                        break
            else:
                print("\n   👁  LECTURE SEULE — création impossible par l'API.")
                print("      (Il resterait l'administration Django, à la main.)")
        else:
            print(f"\n   ?  OPTIONS → HTTP {ro.status_code} : "
                  f"impossible de savoir si la création est permise.")
    except Exception as e:
        print(f"\n   ?  OPTIONS impossible : {e}")

    if bilan["personnel"]:
        print(f"\n   🔴 CLASSEMENT PERSONNEL — {bilan['indice_personnel']}.")
        print("      Cette ressource appartient à un COMPTE, pas à l'établissement.")
        print("      La créer depuis PodAdmin la rattacherait au compte "
              "administrateur\n      et elle resterait invisible pour les enseignants.")
    elif bilan["existe"]:
        print("\n   🟢 Aucun champ d'appartenance : classement d'ÉTABLISSEMENT, "
              "a priori partagé.")

    return bilan


def examiner_champ_video(sess, rest):
    """Vérifie si discipline / catégorie sont modifiables SUR LA VIDÉO.

    Sans cela, créer une nomenclature ne servirait à rien : on ne pourrait la
    rattacher à aucun contenu."""
    print(f"\n{'=' * 70}")
    print("  LE CHAMP REMONTE-T-IL SUR LA VIDÉO ?")
    print("=" * 70)

    trouves = {}
    try:
        r = sess.options(f"{rest}/videos/", timeout=25)
        if r.status_code != 200:
            print(f"   ❌ OPTIONS /videos/ → HTTP {r.status_code}.")
            return trouves
        post = ((r.json().get("actions") or {}).get("POST")) or {}
        if not post:
            print("   ❌ Aucun schéma d'écriture renvoyé pour /videos/.")
            return trouves

        for champ, spec in post.items():
            if "disciplin" in champ.lower() or "categor" in champ.lower():
                trouves[champ] = spec
                lecture_seule = spec.get("read_only", False)
                requis = spec.get("required", False)
                etat = "LECTURE SEULE" if lecture_seule else "modifiable"
                print(f"\n   ✅ Champ « {champ} » présent — {etat}"
                      f"{', obligatoire' if requis else ''}.")
                print(f"      type    : {spec.get('type')}")
                if spec.get("label"):
                    print(f"      libellé : {spec.get('label')}")
                # Le type « field » ou « choice » indique une relation : dans
                # l'API Pod, elle s'exprime par une URL complète, jamais un ID.
                if spec.get("choices"):
                    print(f"      valeurs : {len(spec['choices'])} choix proposés")

        if not trouves:
            print("\n   ❌ NI discipline NI catégorie dans les champs de la vidéo.")
            print("      Créer la nomenclature serait sans effet : rien à rattacher.")
    except Exception as e:
        print(f"   ❌ Vérification impossible : {e}")

    return trouves


def synthese(bilans, champs_video):
    """Traduit les constats en décision — c'est la seule partie qui compte."""
    print(f"\n{'=' * 70}")
    print("  SYNTHÈSE — que peut-on développer ?")
    print("=" * 70 + "\n")

    presentes = [b for b in bilans if b["existe"]]
    if not presentes:
        print("   Aucune des ressources testées n'existe sur cette instance.")
        print("   → Disciplines et catégories ne sont pas exposées par l'API.")
        print("     Le classement resterait à faire dans l'administration "
              "Django.\n")
        return

    for b in presentes:
        etiquette = "PERSONNEL ⛔" if b["personnel"] else "établissement ✅"
        creation = "création possible" if b["creable"] else "lecture seule"
        print(f"   • {b['nom']:14} {str(b['nombre']):>4} élément(s)   "
              f"[{etiquette}]  [{creation}]")

    creables_partagees = [b for b in presentes if b["creable"] and not b["personnel"]]
    rattachable = any(not s.get("read_only") for s in champs_video.values())

    print("\n   DÉCISION :\n")
    if creables_partagees and rattachable:
        noms = ", ".join(b["nom"] for b in creables_partagees)
        print(f"   ✅ FEU VERT sur : {noms}")
        print("      Création possible par l'API ET rattachement possible sur la")
        print("      vidéo. Un onglet de gestion est justifié, ainsi qu'un filtre")
        print("      et une action groupée dans l'onglet Vidéos.")
    elif creables_partagees and not rattachable:
        print("   🟠 Création possible, mais RIEN À RATTACHER : le champ n'est pas")
        print("      modifiable sur la vidéo. Développer serait prématuré.")
    elif any(b["personnel"] for b in presentes):
        print("   ⛔ Au moins une ressource est un classement PERSONNEL.")
        print("      La gérer depuis PodAdmin serait un contresens : les entrées")
        print("      appartiendraient au compte administrateur.")
    else:
        print("   👁  Ressources en LECTURE SEULE : PodAdmin pourrait les AFFICHER")
        print("      et filtrer, mais la création resterait dans l'administration.")

    print("""
   COMMENT LIRE CE BILAN
   • « PERSONNEL » = la ressource porte un propriétaire. C'est rédhibitoire
     pour une gestion centralisée, quelle que soit la suite.
   • « création possible » ne suffit pas : encore faut-il que le champ soit
     modifiable sur la vidéo, sinon la nomenclature reste orpheline.
   • Une table vide n'est pas un obstacle — c'est le point de départ.

   Transmettez cette sortie complète.
""")


def run():
    requests = charger_requests()
    if requests is None:
        return

    base = (input("URL de l'instance [https://videos.utoulouse.fr] : ").strip()
            or "https://videos.utoulouse.fr").rstrip("/")
    token = input("Jeton (compte superutilisateur de préférence) : ").strip()
    if not token:
        print("[X] Jeton vide.")
        return

    rest = f"{base}/rest"
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Token {token}",
                         "Accept": "application/json"})

    print(f"\n{'=' * 70}")
    print("  DISCIPLINES & CATÉGORIES — création possible depuis PodAdmin ?")
    print(f"  Instance : {base}")
    print("  Mode : LECTURE SEULE (GET et OPTIONS uniquement)")
    print("=" * 70)

    bilans = [examiner(sess, rest, nom, libelle) for nom, libelle in CANDIDATS]
    champs_video = examiner_champ_video(sess, rest)
    synthese(bilans, champs_video)


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
