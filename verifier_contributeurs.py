#!/usr/bin/env python3
"""
verifier_contributeurs.py — Sonde : l'onglet Co-auteurs sert-il à quelque chose ?
=================================================================================
L'onglet « Co-auteurs » de PodAdmin ajoute des CONTRIBUTEURS : des crédits
libres (nom, rôle, courriel, lien) attachés à une vidéo. La personne créditée
n'a pas besoin d'un compte Pod et n'obtient aucun droit — c'est une mention au
générique, à ne pas confondre avec les co-propriétaires.

Cette sonde répond à une question simple : **est-ce que quelqu'un s'en sert ?**

  • Aucun contributeur      → l'onglet peut être supprimé sans regret.
  • Quelques-uns            → à rapatrier comme section de l'onglet Vidéos.
  • Beaucoup                → l'onglet mérite d'être enrichi (voir, supprimer).

Elle vérifie aussi si l'API permet de SUPPRIMER un contributeur : l'onglet
actuel ne sait qu'en ajouter, ce qui est sa principale faiblesse.

MODE : LECTURE SEULE. Rien n'est créé ni modifié.

AUTONOME : aucun autre fichier du projet n'est nécessaire.

    python verifier_contributeurs.py
"""

__author__ = "Cédric MONNA"
__version__ = "1.0.0"

from collections import Counter


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

    # ── Combien de contributeurs ? ────────────────────────────────────────
    print(f"\n{'=' * 66}\n  CONTRIBUTEURS SUR L'INSTANCE\n{'=' * 66}")
    contributeurs, url, page = [], f"{rest}/contributors/", 0
    params = {"limit": 100}
    try:
        while url and page < 30:
            r = sess.get(url, params=(params if page == 0 else None), timeout=30)
            if r.status_code != 200:
                print(f"   ❌ HTTP {r.status_code} — ressource inaccessible.")
                return
            data = r.json()
            if isinstance(data, dict):
                contributeurs.extend(data.get("results", []))
                url = data.get("next")
            else:
                contributeurs.extend(data or [])
                url = None
            page += 1
    except Exception as e:
        print(f"   ❌ Lecture impossible : {e}")
        return

    total = len(contributeurs)
    print(f"\n   {total} contributeur(s) enregistré(s).")

    if total:
        roles = Counter(str(c.get("role", "?")) for c in contributeurs)
        videos = {str(c.get("video", "")) for c in contributeurs}
        print(f"   Répartis sur {len(videos)} vidéo(s).\n")
        print("   Rôles utilisés :")
        for role, n in roles.most_common():
            print(f"      • {role:16} {n}")
        print("\n   Quelques exemples :")
        for c in contributeurs[:5]:
            print(f"      • {str(c.get('name', '?')):28} "
                  f"{str(c.get('role', '?')):12} {str(c.get('email_address', '') or '—')}")

    # ── L'API permet-elle de supprimer ? ──────────────────────────────────
    print(f"\n{'=' * 66}\n  ACTIONS POSSIBLES\n{'=' * 66}")
    try:
        r = sess.options(f"{rest}/contributors/", timeout=20)
        if r.status_code == 200:
            actions = (r.json().get("actions") or {})
            print(f"   Écriture (POST) : {'oui' if actions.get('POST') else 'non'}")
    except Exception:
        pass
    if contributeurs:
        exemple = contributeurs[0].get("url", "")
        if exemple:
            try:
                r = sess.options(exemple, timeout=20)
                autorises = r.headers.get("Allow", "")
                print(f"   Méthodes sur un contributeur : {autorises or '(non précisé)'}")
                print(f"   Suppression possible : "
                      f"{'oui' if 'DELETE' in autorises else 'à vérifier'}")
            except Exception:
                pass

    # ── Conclusion ────────────────────────────────────────────────────────
    print(f"\n{'=' * 66}\n  QUE FAIRE DE L'ONGLET « CO-AUTEURS » ?\n{'=' * 66}\n")
    if total == 0:
        print("   ➜  AUCUN contributeur : personne n'utilise cette fonction.")
        print("      L'onglet peut être SUPPRIMÉ sans perte — une place de moins")
        print("      dans une barre latérale déjà chargée.")
        print("      (À conserver seulement si vous comptez lancer cet usage.)")
    elif total <= 20:
        print(f"   ➜  USAGE MARGINAL ({total} crédits).")
        print("      Plutôt que de garder un onglet entier, rapatrier la fonction")
        print("      comme section du panneau de détail de l'onglet Vidéos —")
        print("      là où se gèrent déjà les co-propriétaires.")
    else:
        print(f"   ➜  USAGE RÉEL ({total} crédits).")
        print("      L'onglet se justifie, mais mérite d'être complété : aujourd'hui")
        print("      il ne sait qu'AJOUTER, sans permettre de voir ni de supprimer")
        print("      les crédits existants d'une vidéo.")
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
