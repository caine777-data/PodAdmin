#!/usr/bin/env python3
"""
verifier_nomenclature_ecriture.py — les deux inconnues restantes
=================================================================
L'onglet « Types & disciplines » est construit, mais deux comportements n'ont
pas pu être vérifiés en lecture seule et sont pour l'instant traités
défensivement. Cette sonde les tranche.

  ESSAI A — PEUT-ON RENOMMER UNE DISCIPLINE ?
    La création et la suppression ont été confirmées. Le PATCH, non : `OPTIONS`
    annonce des méthodes, mais annoncer n'est pas accepter — une ressource peut
    déclarer PATCH et le refuser sur un champ précis. PodAdmin propose
    aujourd'hui un bouton « Renommer » sans savoir s'il aboutira.

  ESSAI B — QUE DEVIENNENT LES VIDÉOS D'UN TYPE SUPPRIMÉ ?
    C'est la question qui décide du garde-fou. Trois comportements possibles :
      • le serveur REFUSE la suppression tant qu'une vidéo y est rattachée
        (protection Django `PROTECT`) — le plus rassurant ;
      • il supprime le type et VIDE le champ des vidéos (`SET_NULL`) ;
      • il supprime le type ET les vidéos (`CASCADE`) — le pire, et il vaut
        mieux le savoir sur une vidéo jetable que sur cinquante-sept.

    ⚠️ Cet essai est le plus intrusif de tout le projet. Il rattache une
    VRAIE vidéo à un type jetable, supprime ce type, observe, puis rend à la
    vidéo son type d'origine. La sonde choisit de préférence une vidéo en
    BROUILLON, donc non publique, pour limiter l'exposition pendant les
    quelques secondes de l'essai.

    Si le troisième comportement se produisait, la vidéo serait perdue. C'est
    pourquoi la sonde AFFICHE la vidéo retenue et demande une confirmation
    explicite avant d'y toucher : lancez-la de préférence sur l'instance de
    TEST, ou choisissez une vidéo dont la perte serait sans conséquence.

Chaque essai a sa propre confirmation. Répondre « non » à l'un n'empêche pas
l'autre. Tous les objets créés sont supprimés, y compris en cas d'erreur.

    python verifier_nomenclature_ecriture.py
"""

__author__ = "Cédric MONNA"
__version__ = "1.0.0"

import json
from datetime import datetime

PREFIXE = "ZZ_SONDE_PODADMIN_"


def charger_requests():
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


def confirmer(question: str) -> bool:
    return input(f"\n   {question} (o/N) : ").strip().lower() in ("o", "oui", "y")


def lire_site(sess, rest):
    try:
        data = sess.get(f"{rest}/sites/", timeout=25).json()
        sites = data.get("results", []) if isinstance(data, dict) else (data or [])
        for s in sites:
            if isinstance(s, dict) and s.get("url"):
                return s["url"]
    except Exception as e:
        print(f"   ❌ Lecture des sites impossible : {e}")
    return ""


# ═══════════════════════════════════════════════════════════════════════════
#  ESSAI A — renommer une discipline
# ═══════════════════════════════════════════════════════════════════════════

def essai_renommage(sess, rest, site_url):
    print(f"\n{'=' * 70}")
    print("  ESSAI A — peut-on RENOMMER une discipline ?")
    print("=" * 70)
    print("\n   Une discipline jetable est créée, renommée, relue, puis supprimée.")
    print("   Aucune donnée existante n'est touchée.")
    if not confirmer("Procéder à l'essai A ?"):
        print("   Ignoré.")
        return

    titre = PREFIXE + datetime.now().strftime("%H%M%S")
    url = None
    try:
        # `site` au SINGULIER et sous forme de CHAÎNE (établi par sonde).
        r = sess.post(f"{rest}/discipline/",
                      json={"title": titre, "site": site_url}, timeout=30)
        if r.status_code not in (200, 201):
            print(f"\n   ❌ Création impossible (HTTP {r.status_code}) : "
                  f"{(r.text or '')[:200]}")
            return
        url = (r.json() or {}).get("url")
        print(f"\n   Discipline jetable créée : {url}")

        nouveau = titre + "_RENOMMEE"
        r = sess.patch(url, json={"title": nouveau}, timeout=30)
        print(f"   PATCH → HTTP {r.status_code}")
        if r.status_code not in (200, 202):
            print(f"\n   ⛔ RENOMMAGE REFUSÉ : {(r.text or '')[:250]}")
            print("      → Le bouton « Renommer » doit être retiré de PodAdmin,")
            print("        ou clairement annoncé comme indisponible.")
            return

        # Le serveur peut répondre 200 sans avoir rien changé : on RELIT.
        relu = sess.get(url, timeout=25).json()
        effectif = relu.get("title")
        print(f"   Titre relu : {effectif}")
        if effectif == nouveau:
            print("\n   ✅ RENOMMAGE CONFIRMÉ — le bouton de PodAdmin est justifié.")
        else:
            print("\n   ⚠  Le serveur a répondu favorablement mais n'a RIEN changé.")
            print("      Un 200 ne prouve pas la modification : d'où la relecture.")
    except Exception as e:
        print(f"\n   ❌ Essai impossible : {e}")
    finally:
        if url:
            try:
                r = sess.delete(url, timeout=25)
                print(f"\n   Nettoyage : discipline jetable supprimée "
                      f"(HTTP {r.status_code}).")
            except Exception as e:
                print(f"\n   ⚠️  NETTOYAGE ÉCHOUÉ : {e}")
                print(f"      Supprimez « {titre} » manuellement.")


# ═══════════════════════════════════════════════════════════════════════════
#  ESSAI B — sort des vidéos d'un type supprimé
# ═══════════════════════════════════════════════════════════════════════════

def choisir_video(sess, rest):
    """Retient de préférence une vidéo en BROUILLON, donc non publique."""
    try:
        data = sess.get(f"{rest}/videos/", params={"limit": 50}, timeout=30).json()
        videos = data.get("results", []) if isinstance(data, dict) else (data or [])
    except Exception as e:
        print(f"   ❌ Lecture des vidéos impossible : {e}")
        return None
    brouillons = [v for v in videos if isinstance(v, dict) and v.get("is_draft")]
    if brouillons:
        return brouillons[0]
    return videos[0] if videos else None


def essai_suppression_type(sess, rest, site_url):
    print(f"\n{'=' * 70}")
    print("  ESSAI B — que deviennent les vidéos d'un type supprimé ?")
    print("=" * 70)

    video = choisir_video(sess, rest)
    if not video:
        print("\n   ❌ Aucune vidéo lisible : essai impossible.")
        return

    type_origine = video.get("type")
    type_origine = (type_origine.get("url") if isinstance(type_origine, dict)
                    else type_origine)
    print(f"""
   Vidéo retenue : {video.get('slug')}
   Brouillon     : {'OUI (non publique)' if video.get('is_draft') else 'NON — vidéo PUBLIÉE'}
   Type actuel   : {type_origine}

   Déroulement : un type jetable est créé, cette vidéo lui est rattachée, le
   type est supprimé, on observe ce qu'est devenue la vidéo, puis son type
   d'origine lui est rendu.

   ⚠️  Si le serveur supprimait les vidéos en cascade, CETTE VIDÉO SERAIT
       PERDUE. C'est justement ce que l'essai cherche à savoir.""")
    if not video.get("is_draft"):
        print("\n   ⚠️  Aucun brouillon disponible : la vidéo retenue est PUBLIÉE.")
    if not confirmer("Procéder à l'essai B ?"):
        print("   Ignoré.")
        return

    titre = PREFIXE + datetime.now().strftime("%H%M%S")
    url_type = None
    url_video = video.get("url")
    rattache = False
    try:
        # `sites` au PLURIEL et sous forme de LISTE, et il est obligatoire.
        r = sess.post(f"{rest}/types/",
                      json={"title": titre, "sites": [site_url]}, timeout=30)
        if r.status_code not in (200, 201):
            print(f"\n   ❌ Création du type impossible (HTTP {r.status_code}) : "
                  f"{(r.text or '')[:200]}")
            return
        url_type = (r.json() or {}).get("url")
        print(f"\n   Type jetable créé : {url_type}")

        r = sess.patch(url_video, json={"type": url_type}, timeout=30)
        if r.status_code not in (200, 202):
            print(f"   ❌ Rattachement refusé (HTTP {r.status_code}) : "
                  f"{(r.text or '')[:200]}")
            return
        rattache = True
        print("   Vidéo rattachée au type jetable.")

        print("\n   Suppression du type, vidéo rattachée…")
        r = sess.delete(url_type, timeout=30)
        print(f"   DELETE → HTTP {r.status_code}")

        if r.status_code in (400, 409, 403):
            print(f"\n   🛡  SUPPRESSION REFUSÉE : {(r.text or '')[:250]}")
            print("      → Le serveur PROTÈGE les types utilisés. C'est le")
            print("        comportement le plus sûr : PodAdmin n'a qu'à relayer")
            print("        le refus, ce qu'il fait déjà.")
            return                       # le type existe encore, nettoyé plus bas

        if r.status_code not in (200, 202, 204):
            print(f"\n   ⚠  Réponse inattendue : {(r.text or '')[:250]}")
            return

        url_type = None                  # supprimé : plus rien à nettoyer
        # Que devient la vidéo ?
        r = sess.get(url_video, timeout=25)
        if r.status_code == 404:
            print("\n   🔴 LA VIDÉO A DISPARU — suppression en CASCADE.")
            print("      C'est le comportement le plus dangereux. PodAdmin doit")
            print("      REFUSER de supprimer un type portant des vidéos, sans")
            print("      se contenter d'un avertissement.")
            rattache = False
            return
        apres = r.json()
        type_apres = apres.get("type")
        type_apres = (type_apres.get("url") if isinstance(type_apres, dict)
                      else type_apres)
        print(f"\n   Vidéo toujours présente. Son type vaut : {type_apres!r}")
        if not type_apres:
            print("\n   🟠 TYPE VIDÉ — la vidéo survit mais perd son classement.")
            print("      → L'avertissement actuel de PodAdmin est justifié, et")
            print("        doit préciser que les vidéos se retrouveront SANS type.")
        else:
            print("\n   🟢 La vidéo a conservé un type (valeur de repli du serveur).")
    except Exception as e:
        print(f"\n   ❌ Essai impossible : {e}")
    finally:
        # Remise en état, quoi qu'il arrive.
        if rattache and type_origine:
            try:
                sess.patch(url_video, json={"type": type_origine}, timeout=30)
                verif = sess.get(url_video, timeout=25).json().get("type")
                verif = verif.get("url") if isinstance(verif, dict) else verif
                if str(verif).rstrip("/") == str(type_origine).rstrip("/"):
                    print("   Vidéo restaurée dans son type d'origine.")
                else:
                    print(f"   ⚠️  ÉTAT ACTUEL DE LA VIDÉO : type = {verif!r}")
                    print(f"      Attendu : {type_origine}")
            except Exception as e:
                print(f"   ⚠️  RESTAURATION ÉCHOUÉE : {e}")
                print(f"      Remettez le type de {video.get('slug')} à la main.")
        if url_type:
            try:
                sess.delete(url_type, timeout=25)
                print("   Nettoyage : type jetable supprimé.")
            except Exception as e:
                print(f"   ⚠️  NETTOYAGE ÉCHOUÉ : {e}")
                print(f"      Supprimez « {titre} » manuellement.")


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
    print("  NOMENCLATURES — les deux comportements non confirmés")
    print(f"  Instance : {base}")
    print("  ⚠️  CETTE SONDE ÉCRIT, ET L'ESSAI B TOUCHE UNE VRAIE VIDÉO")
    print("=" * 70)

    site_url = lire_site(sess, rest)
    print(f"\n   Site déclaré : {site_url or '(aucun)'}")
    if not site_url:
        print("   ⚠  Sans site, la création d'un type échouera (champ requis).")

    essai_renommage(sess, rest, site_url)
    essai_suppression_type(sess, rest, site_url)

    print(f"\n{'=' * 70}")
    print("  Transmettez cette sortie complète (le jeton n'y figure pas).")
    print("=" * 70 + "\n")


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
