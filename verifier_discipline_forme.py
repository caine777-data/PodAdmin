#!/usr/bin/env python3
"""
verifier_discipline_forme.py — Sonde : comment ÉCRIRE une discipline ?
======================================================================
Complément de `verifier_disciplines.py`, qui a déjà donné le feu vert :
la ressource « discipline » existe, elle est vide, elle accepte la création,
et le champ remonte sur la vidéo en écriture.

Restent DEUX questions de forme. Elles paraissent secondaires ; en réalité,
se tromper sur l'une ou l'autre fait échouer chaque enregistrement.

  1. UNE VIDÉO PORTE-T-ELLE UNE DISCIPLINE, OU PLUSIEURS ?
     Le champ s'appelle « discipline » au singulier, mais son libellé affiché
     est « Disciplines » au pluriel. C'est la signature d'une relation
     MULTIPLE — le même écart existe sur `additional_owners`.
       • relation simple   → on envoie UNE url   : "https://…/discipline/3/"
       • relation multiple → on envoie une LISTE : ["https://…/discipline/3/"]
     Envoyer l'une pour l'autre produit un HTTP 400, et rien dans le message
     d'erreur ne le dit clairement.

  2. FAUT-IL RENSEIGNER LE SITE ?
     La ressource expose un champ « site », déclaré NON obligatoire. Mais
     l'instance est multi-établissements : le piège est connu, une ressource
     créée sans site peut n'apparaître nulle part. On regarde comment les
     ressources COMPARABLES et déjà peuplées (types, chaînes) le renseignent —
     l'usage réel est plus fiable que la déclaration.

MODE : LECTURE SEULE. Uniquement GET et OPTIONS. Aucune discipline n'est créée.

AUTONOME : seule dépendance, la bibliothèque « requests ».

    python verifier_discipline_forme.py
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


def forme_du_champ(sess, rest):
    """Détermine si « discipline » est une relation simple ou multiple.

    Trois indices sont croisés, du plus fiable au moins :
      A. le schéma OPTIONS de /videos/ (présence d'un sous-schéma « child »,
         signature d'une liste dans Django REST Framework) ;
      B. la valeur réellement lue sur des vidéos existantes ([] ou null) ;
      C. le libellé affiché (pluriel), simple présomption.
    """
    print(f"\n{'=' * 70}")
    print("  QUESTION 1 — une seule discipline par vidéo, ou plusieurs ?")
    print("=" * 70)

    verdict = None

    # --- Indice A : le schéma d'écriture -----------------------------------
    try:
        r = sess.options(f"{rest}/videos/", timeout=25)
        post = ((r.json().get("actions") or {}).get("POST")) or {}
        spec = post.get("discipline")
        if spec:
            print("\n   Schéma déclaré pour le champ « discipline » :")
            print("   " + json.dumps(spec, ensure_ascii=False, indent=3)[:900])
            # Dans DRF, un ManyRelatedField expose un sous-schéma « child ».
            if "child" in spec:
                verdict = "multiple"
                print("\n   → Sous-schéma « child » PRÉSENT : relation MULTIPLE.")
            elif spec.get("type") == "field":
                print("\n   → Type « field » sans sous-schéma : indice non concluant,")
                print("     on passe aux vidéos réelles.")
    except Exception as e:
        print(f"   ❌ OPTIONS /videos/ impossible : {e}")

    # --- Indice B : ce que renvoient les vidéos existantes ------------------
    # C'est l'indice DÉCISIF : une liste vide « [] » ne peut pas être confondue
    # avec une absence de valeur « null ».
    print("\n   Valeur du champ sur des vidéos réelles :")
    try:
        r = sess.get(f"{rest}/videos/", params={"limit": 5}, timeout=30)
        data = r.json()
        videos = data.get("results", []) if isinstance(data, dict) else (data or [])
        if not videos:
            print("      (aucune vidéo lisible — indice indisponible)")
        for v in videos[:5]:
            if not isinstance(v, dict):
                continue
            if "discipline" not in v:
                print(f"      • {str(v.get('slug'))[:38]:40} champ ABSENT en lecture")
                continue
            val = v.get("discipline")
            apercu = json.dumps(val, ensure_ascii=False)
            print(f"      • {str(v.get('slug'))[:38]:40} discipline = {apercu[:40]}")
            if isinstance(val, list) and verdict is None:
                verdict = "multiple"
            elif val is None or isinstance(val, str):
                if verdict is None and not isinstance(val, list):
                    verdict = "simple ou indéterminé (valeur nulle)"
    except Exception as e:
        print(f"      ❌ Lecture impossible : {e}")

    print("\n   CONCLUSION :")
    if verdict == "multiple":
        print("   ✅ Relation MULTIPLE — envoyer une LISTE d'URLs, même pour une")
        print("      seule discipline :  {\"discipline\": [\"https://…/discipline/3/\"]}")
        print("      Dans l'interface : cases à cocher, pas une liste déroulante.")
    elif verdict:
        print(f"   🟠 {verdict}.")
        print("      Les vidéos n'ayant AUCUNE discipline (table vide), la lecture")
        print("      ne tranche pas. Se fier au schéma ci-dessus ; en cas de doute,")
        print("      coder l'envoi en LISTE : DRF accepte souvent les deux formes")
        print("      en lecture, mais jamais l'inverse.")
    else:
        print("   ❓ Indéterminé — reporter la sortie complète pour arbitrage.")


def question_du_site(sess, rest):
    """Le champ « site » doit-il être renseigné à la création ?

    On observe l'usage réel sur des ressources comparables et peuplées plutôt
    que de se fier au caractère « non obligatoire » déclaré : sur une instance
    multi-établissements, l'omission est le piège classique."""
    print(f"\n{'=' * 70}")
    print("  QUESTION 2 — faut-il renseigner le site ?")
    print("=" * 70)

    # Les sites déclarés sur l'instance.
    sites = []
    try:
        r = sess.get(f"{rest}/sites/", timeout=25)
        data = r.json()
        sites = data.get("results", []) if isinstance(data, dict) else (data or [])
        print(f"\n   Sites déclarés : {len(sites)}")
        for s in sites:
            if isinstance(s, dict):
                print(f"      • {s.get('name', '?')}   →  {s.get('url', '?')}")
    except Exception as e:
        print(f"   ❌ /sites/ illisible : {e}")

    # Le schéma exact du champ « site » sur discipline.
    try:
        r = sess.options(f"{rest}/discipline/", timeout=20)
        spec = (((r.json().get("actions") or {}).get("POST")) or {}).get("site")
        if spec:
            print("\n   Champ « site » de la ressource discipline :")
            print("   " + json.dumps(spec, ensure_ascii=False, indent=3)[:500])
    except Exception as e:
        print(f"   ❌ OPTIONS /discipline/ impossible : {e}")

    # Comment les ressources DÉJÀ peuplées le renseignent-elles ?
    print("\n   Usage réel sur des ressources comparables :")
    for res in ("types", "channels"):
        try:
            r = sess.get(f"{rest}/{res}/", params={"limit": 3}, timeout=25)
            data = r.json()
            items = data.get("results", []) if isinstance(data, dict) else (data or [])
            for it in items[:3]:
                if isinstance(it, dict):
                    val = it.get("site", it.get("sites", "(champ absent)"))
                    titre = it.get("title") or it.get("name") or "?"
                    print(f"      • {res:9} {str(titre)[:26]:28} "
                          f"site = {json.dumps(val, ensure_ascii=False)[:38]}")
        except Exception as e:
            print(f"      ❌ {res} : {e}")

    print("\n   CONCLUSION :")
    if len(sites) <= 1:
        print("   🟢 Un seul site : l'omission est probablement sans conséquence,")
        print("      mais le renseigner explicitement ne coûte rien et supprime")
        print("      le risque. C'est ce que fera PodAdmin.")
    else:
        print(f"   🔴 {len(sites)} sites : le champ DOIT être renseigné, sinon la")
        print("      discipline risque de n'apparaître sur aucun d'eux.")
    print("      Rappel : la relation s'exprime par une URL complète, jamais un ID.")


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
    print("  DISCIPLINE — forme exacte des données à envoyer")
    print(f"  Instance : {base}")
    print("  Mode : LECTURE SEULE (GET et OPTIONS uniquement)")
    print("=" * 70)

    forme_du_champ(sess, rest)
    question_du_site(sess, rest)

    print("\n   Transmettez cette sortie complète "
          "(le jeton n'y figure pas).\n")


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
