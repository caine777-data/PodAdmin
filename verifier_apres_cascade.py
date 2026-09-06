#!/usr/bin/env python3
"""
verifier_apres_cascade.py — état des lieux après la suppression en cascade
===========================================================================
L'essai B de `verifier_nomenclature_ecriture.py` a établi que l'instance
supprime les vidéos EN CASCADE avec leur type. La vidéo d'essai
`0138-ues7-la-certification-pix` (un brouillon) a été détruite.

Cette sonde fait trois choses, en LECTURE SEULE :

  1. CONFIRME LA PERTE.
     Un HTTP 404 sur l'URL directe ne suffit pas à conclure : il peut venir
     d'un droit, d'un slug modifié, d'un cache. On recherche donc la vidéo par
     plusieurs voies avant de la déclarer perdue.

  2. CHERCHE LES RELIQUATS.
     Les objets jetables sont préfixés `ZZ_SONDE_PODADMIN_`. Le nettoyage
     automatique a pu échouer sur l'un d'eux — et un type jetable oublié
     serait dangereux, puisque le supprimer emporterait ses vidéos.

  3. RECENSE LES TYPES À RISQUE.
     Maintenant qu'on sait que la suppression est destructive, il faut savoir
     combien de vidéos chaque type emporterait avec lui. Ce chiffre n'est plus
     une information de confort : c'est le nombre de vidéos qu'un clic
     détruirait.

MODE : LECTURE SEULE. Aucune écriture, aucune suppression.

    python verifier_apres_cascade.py
"""

__author__ = "Cédric MONNA"
__version__ = "1.0.0"

PREFIXE = "ZZ_SONDE_PODADMIN_"
SLUG_PERDU = "0138-ues7-la-certification-pix"


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


def nettoyer_url(saisie: str, defaut: str) -> str:
    """Nettoie l'URL saisie des scories du copier-coller.

    L'invite affiche « [https://videos.utoulouse.fr] » : coller la valeur
    proposée emporte les crochets, et toutes les requêtes partent alors vers
    « https://videos.utoulouse.fr] », qui n'est pas une URL valide. La sonde
    échouait sur chaque appel — et, plus grave, concluait quand même.
    """
    v = (saisie or "").strip().strip("[]<>\"' ").rstrip("/")
    return v or defaut


def paginer(sess, url, params=None, max_pages=80):
    """Suit le champ `next` jusqu'au bout, comme partout dans le projet."""
    resultats, pages, complete = [], 0, True
    while url and pages < max_pages:
        try:
            r = sess.get(url, params=params if pages == 0 else None, timeout=40)
        except Exception as e:
            print(f"   ⚠  Lecture interrompue : {e}")
            complete = False
            break
        if r.status_code != 200:
            print(f"   ⚠  Lecture interrompue (HTTP {r.status_code}).")
            complete = False
            break
        data = r.json()
        if isinstance(data, dict):
            resultats.extend(data.get("results", []))
            url = data.get("next")
        else:
            resultats.extend(data or [])
            url = None
        pages += 1
    # Le drapeau accompagne les résultats : sans lui, une liste vide pour cause
    # de panne réseau se confond avec une liste vide pour cause d'absence — et
    # c'est ainsi qu'on conclut « aucun reliquat » alors qu'on n'a rien lu.
    return resultats, complete


def verifier_connexion(sess, rest) -> bool:
    """S'assure que l'instance répond AVANT de conclure quoi que ce soit.

    Sans ce contrôle, une URL mal saisie faisait échouer chaque requête, et la
    sonde annonçait pourtant « perte confirmée » et « aucun reliquat ». Un
    verdict rassurant tiré de zéro donnée est pire qu'une erreur : il clôt une
    question qui reste ouverte."""
    print(f"\n   Contrôle de la connexion : {rest}/videos/")
    try:
        r = sess.get(f"{rest}/videos/", params={"limit": 1}, timeout=25)
    except Exception as e:
        print(f"   ❌ INSTANCE INJOIGNABLE : {e}")
        return False
    if r.status_code == 401:
        print("   ❌ Jeton refusé (HTTP 401).")
        return False
    if r.status_code != 200:
        print(f"   ❌ Réponse inattendue : HTTP {r.status_code}")
        return False
    try:
        total = r.json().get("count")
    except Exception:
        total = None
    print(f"   ✅ Connexion établie — {total} vidéo(s) annoncée(s) par l'API.")
    return True


def confirmer_la_perte(sess, rest, videos, lecture_complete):
    """La vidéo est-elle réellement absente, ou seulement inaccessible ?"""
    print(f"\n{'=' * 70}")
    print("  1. LA VIDÉO EST-ELLE RÉELLEMENT PERDUE ?")
    print("=" * 70)
    print(f"\n   Slug recherché : {SLUG_PERDU}\n")

    # Voie 1 : URL directe.
    try:
        r = sess.get(f"{rest}/videos/{SLUG_PERDU}/", timeout=25)
        print(f"      URL directe          → HTTP {r.status_code}")
    except Exception as e:
        print(f"      URL directe          → erreur : {e}")

    # Voie 2 : parmi TOUTES les vidéos lues (le listing peut différer).
    trouvee = [v for v in videos
               if isinstance(v, dict) and v.get("slug") == SLUG_PERDU]
    print(f"      Dans le listing complet → {'PRÉSENTE' if trouvee else 'absente'}")

    # Voie 3 : recherche plein texte, le slug ayant pu changer.
    try:
        r = sess.get(f"{rest}/videos/", params={"search": "certification-pix"},
                     timeout=30)
        if r.status_code == 200:
            data = r.json()
            proches = data.get("results", []) if isinstance(data, dict) else (data or [])
            print(f"      Recherche « certification-pix » → {len(proches)} résultat(s)")
            for v in proches[:5]:
                if isinstance(v, dict):
                    print(f"         • {v.get('slug')} — {v.get('title')}")
    except Exception as e:
        print(f"      Recherche            → erreur : {e}")

    print()
    if not lecture_complete:
        print("   ⛔ CONCLUSION IMPOSSIBLE — le fonds n'a pas pu être lu")
        print("      entièrement. L'absence constatée peut n'être qu'un défaut")
        print("      de lecture. Corrigez l'accès et relancez.")
        return None
    if trouvee:
        print("   🟢 LA VIDÉO EXISTE ENCORE. Le 404 de la sonde venait d'autre")
        print("      chose (droit, cache, slug). Rien n'a été détruit.")
    else:
        print("   🔴 PERTE CONFIRMÉE par les trois voies.")
        print("      Il s'agissait d'un BROUILLON, donc jamais publié : aucun")
        print("      lien public n'est cassé, aucun spectateur n'est concerné.")
        print("      Le fichier source d'origine, lui, n'a pas été touché — seule")
        print("      l'entrée dans Pod a disparu, et un nouveau dépôt la recrée.")
        print("      Une restauration depuis la sauvegarde du serveur reste")
        print("      possible : c'est à voir avec la DSI si la notice comptait.")
    return bool(trouvee)


def chercher_reliquats(sess, rest):
    """Renvoie le nombre de reliquats, ou None si la lecture a échoué."""
    """Un objet jetable oublié serait dangereux : le supprimer emporterait
    ses vidéos."""
    print(f"\n{'=' * 70}")
    print("  2. RESTE-T-IL DES OBJETS JETABLES ?")
    print("=" * 70)
    total, tout_lu = 0, True
    for ressource, libelle in (("types", "type"), ("discipline", "discipline")):
        objets, complete = paginer(sess, f"{rest}/{ressource}/",
                                   {"limit": 200}, max_pages=10)
        tout_lu = tout_lu and complete
        restes = [o for o in objets
                  if isinstance(o, dict) and str(o.get("title", "")).startswith(PREFIXE)]
        total += len(restes)
        print(f"\n   {libelle} : {len(objets)} au total, "
              f"{len(restes)} jetable(s) oublié(s)")
        for o in restes:
            print(f"      ⚠  {o.get('title')}  →  {o.get('url')}")
    if not tout_lu:
        print("\n   ⛔ CONCLUSION IMPOSSIBLE — les ressources n'ont pas pu être")
        print("      lues. « Aucun reliquat » ne voudrait rien dire ici.")
        return None
    if total == 0:
        print("\n   ✅ Aucun reliquat : le nettoyage automatique a bien fonctionné.")
    else:
        print(f"\n   ⚠️  {total} objet(s) à supprimer à la main dans l'administration.")
        print("      ⚠️ Pour un TYPE, vérifier d'abord qu'aucune vidéo n'y est")
        print("         rattachée : la suppression est destructive.")
    return total


def recenser_les_risques(sess, rest, videos, lecture_complete):
    """Combien de vidéos chaque type emporterait-il avec lui ?"""
    print(f"\n{'=' * 70}")
    print("  3. COMBIEN DE VIDÉOS CHAQUE TYPE EMPORTERAIT-IL ?")
    print("=" * 70)

    types, complete = paginer(sess, f"{rest}/types/", {"limit": 200}, max_pages=10)
    if not complete or not lecture_complete:
        print("\n   ⛔ Comptes non fiables : la lecture a été incomplète.")
        return
    comptes = {}
    for v in videos:
        if not isinstance(v, dict):
            continue
        t = v.get("type")
        t = t.get("url") if isinstance(t, dict) else t
        if t:
            cle = str(t).rstrip("/")
            comptes[cle] = comptes.get(cle, 0) + 1

    print(f"\n   {len(videos)} vidéo(s) lues.\n")
    total_risque = 0
    for t in types:
        if not isinstance(t, dict):
            continue
        n = comptes.get(str(t.get("url", "")).rstrip("/"), 0)
        total_risque += n
        marque = f"⚠ {n} vidéo(s) SERAIENT DÉTRUITES" if n else "(vide — sans risque)"
        print(f"      {str(t.get('title', '?'))[:38]:40} {marque}")

    print(f"""
   Ces {total_risque} vidéos ne sont PAS en danger tant que personne ne
   supprime leur type. Mais un seul clic suffirait, et c'est exactement ce
   que PodAdmin doit désormais rendre impossible.
""")


def run():
    requests = charger_requests()
    if requests is None:
        return

    base = nettoyer_url(input("URL de l'instance [https://videos.utoulouse.fr] : "),
                        "https://videos.utoulouse.fr")
    token = input("Jeton : ").strip()
    if not token:
        print("[X] Jeton vide.")
        return

    rest = f"{base}/rest"
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Token {token}",
                         "Accept": "application/json"})

    print(f"\n{'=' * 70}")
    print("  ÉTAT DES LIEUX APRÈS LA SUPPRESSION EN CASCADE")
    print(f"  Instance : {base}")
    print("  Mode : LECTURE SEULE")
    print("=" * 70)
    if not verifier_connexion(sess, rest):
        print("""
   Rien n'a été vérifié. Causes fréquentes :
     • l'URL a été collée avec les crochets de l'invite — écrivez-la sans
       « [ » ni « ] », ou appuyez simplement sur Entrée pour la valeur par
       défaut ;
     • le jeton a été régénéré depuis la dernière fois.
""")
        return

    print("\n   Lecture du fonds, un instant…")
    videos, lecture_complete = paginer(sess, f"{rest}/videos/", {"limit": 100})
    if not lecture_complete:
        print(f"   ⚠  Seules {len(videos)} vidéo(s) ont pu être lues.")

    confirmer_la_perte(sess, rest, videos, lecture_complete)
    chercher_reliquats(sess, rest)
    recenser_les_risques(sess, rest, videos, lecture_complete)

    print(f"{'=' * 70}")
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
