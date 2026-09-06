#!/usr/bin/env python3
"""
verifier_encodages.py — Sonde : y a-t-il vraiment des encodages incomplets ?
============================================================================
L'onglet Encodage de PodAdmin classe les vidéos d'après leurs DRAPEAUX
(`encoded`, `encoding_in_progress`). Autrement dit, il croit Pod sur parole.

Cette sonde vérifie ce qui a RÉELLEMENT été produit, en croisant les vidéos avec
les fichiers d'encodage effectivement présents (`/rest/encodings_video/` et
`/rest/encodings_audio/`). Elle répond à une seule question :

    « Développer un diagnostic d'encodage en vaut-il la peine ? »

Si le nombre d'anomalies est nul, la réponse est non — inutile d'écrire une
interface pour un problème qui n'existe pas. S'il y en a plusieurs dizaines, le
développement se justifie.

Anomalies recherchées :
  1. FAUX SUCCÈS      — marquée « encodée » mais AUCUN fichier d'encodage ;
  2. QUALITÉ UNIQUE   — une seule résolution alors que plusieurs sont configurées ;
  3. SANS AUDIO       — aucune piste audio produite ;
  4. ÉCHEC SILENCIEUX — des fichiers existent alors que la vidéo est dite non encodée.

MODE : LECTURE SEULE. Rien n'est créé ni modifié.

AUTONOME : aucun autre fichier du projet n'est nécessaire.
Seule dépendance : la bibliothèque « requests ».

    python verifier_encodages.py
"""

__author__ = "Cédric MONNA"
__version__ = "1.0.0"

from collections import defaultdict


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


def tout_lire(sess, url, libelle, max_pages=60):
    """Récupère une ressource complète en suivant la pagination."""
    elements, page = [], 0
    params = {"limit": 100}
    print(f"   Lecture de {libelle}…", end="", flush=True)
    while url and page < max_pages:
        try:
            r = sess.get(url, params=(params if page == 0 else None), timeout=40)
        except Exception as e:
            print(f"  [X] {e}")
            return elements
        if r.status_code != 200:
            print(f"  [X] HTTP {r.status_code}")
            return elements
        data = r.json()
        if isinstance(data, dict):
            elements.extend(data.get("results", []))
            url = data.get("next")
        else:
            elements.extend(data or [])
            url = None
        page += 1
        print(".", end="", flush=True)
    print(f"  {len(elements)} élément(s)")
    return elements


def cle_video(valeur):
    """Extrait l'identifiant d'une vidéo depuis une URL de relation."""
    if isinstance(valeur, dict):
        valeur = valeur.get("url", "")
    return str(valeur or "").rstrip("/").rsplit("/", 1)[-1]


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

    print(f"\n{'=' * 68}\n  COLLECTE DES DONNÉES\n{'=' * 68}")
    videos = tout_lire(sess, f"{rest}/videos/", "vidéos")
    enc_video = tout_lire(sess, f"{rest}/encodings_video/", "encodages vidéo")
    enc_audio = tout_lire(sess, f"{rest}/encodings_audio/", "encodages audio")
    renditions = tout_lire(sess, f"{rest}/renditions/", "qualités configurées", max_pages=3)

    if not videos:
        print("\n[X] Aucune vidéo lue : diagnostic impossible.")
        return

    # Qualités attendues, d'après la configuration de l'instance.
    resolutions = sorted({str(r.get("resolution", "")) for r in renditions if r.get("resolution")})
    print(f"\n   Qualités configurées sur l'instance : "
          f"{', '.join(resolutions) if resolutions else '(inconnues)'}")

    # Regroupement des fichiers produits, par vidéo.
    par_video_v = defaultdict(set)
    for e in enc_video:
        par_video_v[cle_video(e.get("video"))].add(str(e.get("name", "?")))
    par_video_a = defaultdict(set)
    for e in enc_audio:
        par_video_a[cle_video(e.get("video"))].add(str(e.get("name", "?")))

    faux_succes, qualite_unique, sans_audio, echec_silencieux = [], [], [], []
    encodees = 0

    for v in videos:
        vid = cle_video(v.get("url") or v.get("id"))
        titre = (v.get("title") or "(sans titre)")[:52]
        marquee_ok = bool(v.get("encoded"))
        en_cours = bool(v.get("encoding_in_progress"))
        qualites = par_video_v.get(vid, set())
        audio = par_video_a.get(vid, set())

        if marquee_ok:
            encodees += 1
            if not qualites:
                faux_succes.append((titre, vid))
            elif len(qualites) == 1:
                qualite_unique.append((titre, vid, next(iter(qualites))))
            if not audio:
                sans_audio.append((titre, vid))
        else:
            if qualites and not en_cours:
                echec_silencieux.append((titre, vid, len(qualites)))

    def bloc(titre, liste, explication, montrer=8):
        """Affiche une catégorie d'anomalie."""
        print(f"\n{'─' * 68}\n  {titre} : {len(liste)}\n{'─' * 68}")
        print(f"   {explication}")
        if not liste:
            print("   ✅ Aucun cas.")
            return
        for item in liste[:montrer]:
            details = "  ".join(str(x) for x in item[1:])
            print(f"      • {item[0]:54} [{details}]")
        if len(liste) > montrer:
            print(f"      … et {len(liste) - montrer} autre(s)")

    print(f"\n{'=' * 68}\n  RÉSULTATS\n{'=' * 68}")
    print(f"\n   {len(videos)} vidéo(s) au total, dont {encodees} marquée(s) « encodée ».")
    print(f"   {len(enc_video)} fichier(s) vidéo et {len(enc_audio)} fichier(s) audio produits.")

    bloc("FAUX SUCCÈS", faux_succes,
         "Marquées « encodées » mais AUCUN fichier produit : elles ne sont pas "
         "lisibles, et rien ne le signale aujourd'hui.")
    bloc("QUALITÉ UNIQUE", qualite_unique,
         "Une seule résolution disponible : lecture dégradée sur mauvaise "
         "connexion, ou encodage interrompu en cours de route.")
    bloc("SANS PISTE AUDIO", sans_audio,
         "Aucun fichier audio produit. Normal pour une vidéo muette, "
         "anormal sinon.")
    bloc("ÉCHEC SILENCIEUX", echec_silencieux,
         "Des fichiers existent alors que la vidéo est dite NON encodée : "
         "le drapeau est faux, la vidéo est peut-être utilisable.")

    total = len(faux_succes) + len(qualite_unique) + len(echec_silencieux)
    print(f"\n{'=' * 68}\n  FAUT-IL DÉVELOPPER CE DIAGNOSTIC ?\n{'=' * 68}\n")
    if total == 0:
        print("   ➜  NON. Aucune anomalie : les encodages aboutissent correctement.")
        print("      L'onglet Encodage actuel suffit ; inutile d'ajouter un module")
        print("      pour un problème qui ne se pose pas.")
    elif total < 5:
        print(f"   ➜  PROBABLEMENT PAS. Seulement {total} anomalie(s) : les traiter")
        print("      à la main est plus économique qu'écrire une interface.")
    else:
        print(f"   ➜  OUI. {total} anomalie(s) que rien ne signale aujourd'hui.")
        print("      Un enrichissement de l'onglet Encodage se justifie :")
        print("      un état « ⚠ encodage incomplet » et le détail des qualités")
        print("      disponibles dans le panneau de la vidéo.")
    print("\n   (Les vidéos « sans piste audio » ne sont pas comptées : une vidéo")
    print("    muette est un cas légitime, non une anomalie.)\n")
    print("   Transmettez cette sortie complète.\n")


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
