#!/usr/bin/env python3
"""
verifier_ilaas_taille.py — Sonde : quelle taille de fichier ILaaS accepte-t-il ?
================================================================================
PodAdmin va intégrer SousTitreur (onglet « Enrichissement IA »). Décision prise :
pas de ffmpeg, donc une vidéo du POSTE part ENTIÈRE chez Aristote (instance
ILaaS), et non plus son seul son. Une heure de cours peut peser plus d'un
gigaoctet. Avant de développer, il faut savoir jusqu'où ILaaS accepte.

DEUX PHASES

  1. Limite d'entrée de la passerelle — GRATUITE, rien n'est créé.
     La sonde annonce une taille de fichier (en-tête « Content-Length ») et
     demande la permission d'envoyer (« Expect: 100-continue »), SANS envoyer
     le fichier. La passerelle répond aussitôt « 413, trop gros » ou « 100,
     allez-y ». Plusieurs tailles sont essayées pour encadrer la limite.
     Aucun fichier ne part, aucun enrichissement n'est créé, aucun quota n'est
     consommé.

  2. Envoi réel d'une vidéo — FACULTATIF, il faut taper OUI.
     La phase 1 ne voit que la passerelle. L'application Aristote, derrière,
     peut avoir ses propres limites (taille, durée), visibles seulement après
     un vrai envoi. La sonde envoie la vidéo que vous choisissez, puis suit
     son état deux minutes : refus, « en file d'attente » (accepté), ou échec.
     Cet envoi CRÉE un enrichissement chez Aristote : la sonde propose de le
     supprimer à la fin, pour ne pas consommer de transcription inutile.

AUTONOME : ce fichier se suffit à lui-même. Dépendances : « requests », et
« requests-toolbelt » pour la phase 2 (déjà installés avec PodAdmin).

    python verifier_ilaas_taille.py

Identifiants Aristote : demandés au lancement. Si SousTitreur est présent dans
le dossier Téléchargements, la sonde propose de reprendre les siens.
"""

__author__ = "Cédric MONNA"
__version__ = "1.0.0"

import json
import os
import socket
import ssl
import sys
import time
from urllib.parse import urlsplit

URL_DEFAUT = "https://stt.ilaas.fr/api"
MO = 1024 * 1024
# Tailles annoncées en phase 1, de la plus petite à la plus grande.
PALIERS_MO = [50, 100, 250, 500, 1024, 2048, 4096, 8192]
DELAI_REPONSE_S = 10  # attente d'un 413 ou d'un 100 après l'en-tête


def charger_requests():
    """Importe `requests`, en proposant de l'installer si nécessaire."""
    try:
        import requests

        return requests
    except ImportError:
        pass
    print("La bibliothèque « requests » est nécessaire et n'est pas installée.")
    if input("L'installer maintenant ? (o/N) : ").strip().lower() not in ("o", "oui", "y"):
        print("\nInstallation manuelle :   python -m pip install requests")
        return None
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

    return requests


def identifiants() -> tuple[str, str]:
    """Identifiants Aristote : ceux de SousTitreur s'il est là, sinon saisis."""
    dossier = os.path.join(os.path.expanduser("~"), "Downloads", "SousTitreur")
    if os.path.isfile(os.path.join(dossier, "config.py")):
        rep = input(f"Reprendre les identifiants de SousTitreur ({dossier}) ? (O/n) : ")
        if rep.strip().lower() not in ("n", "non"):
            sys.path.insert(0, dossier)
            try:
                import config as cfg_soustitreur

                cid, secret = cfg_soustitreur.lire_identifiants()
                if cid and secret:
                    return cid, secret
            except Exception as e:  # noqa: BLE001
                print(f"   Lecture impossible ({e}) : saisie manuelle.")
            finally:
                sys.path.remove(dossier)
    cid = input("Identifiant client Aristote : ").strip()
    secret = input("Secret client Aristote : ").strip()
    return cid, secret


def jeton_aristote(requests, url: str, cid: str, secret: str) -> str:
    r = requests.post(
        f"{url}/token",
        timeout=30,
        headers={"Accept": "application/json"},
        json={"grant_type": "client_credentials", "client_id": cid, "client_secret": secret},
    )
    if r.status_code != 200:
        raise SystemExit(
            f"\n❌ Connexion refusée par Aristote ({r.status_code}). "
            "Vérifiez l'identifiant et le secret."
        )
    return r.json()["access_token"]


# ══════════════════════════ Phase 1 : passerelle ══════════════════════════


def annoncer(url: str, jeton: str, taille: int) -> tuple[str, str]:
    """Annonce `taille` octets SANS les envoyer. Renvoie (verdict, détail).

    verdict : « accepte » (100 Continue), « refuse » (413), « muet » (aucune
    réponse dans le délai : rien ne s'y oppose à l'entrée), ou « autre »."""
    p = urlsplit(url)
    hote, port = p.hostname, p.port or 443
    chemin = f"{p.path.rstrip('/')}/v1/enrichments/upload"
    requete = (
        f"POST {chemin} HTTP/1.1\r\n"
        f"Host: {hote}\r\n"
        f"Authorization: Bearer {jeton}\r\n"
        "Accept: application/json\r\n"
        "Content-Type: multipart/form-data; boundary=sonde-podadmin\r\n"
        f"Content-Length: {taille}\r\n"
        "Expect: 100-continue\r\n"
        "User-Agent: PodAdmin-sonde-taille\r\n"
        "Connection: close\r\n\r\n"
    )
    contexte = ssl.create_default_context()
    try:
        import certifi  # macOS : certificats fiables

        contexte.load_verify_locations(certifi.where())
    except Exception:  # noqa: BLE001
        pass
    with socket.create_connection((hote, port), timeout=15) as brut:
        with contexte.wrap_socket(brut, server_hostname=hote) as s:
            s.sendall(requete.encode("ascii"))
            s.settimeout(DELAI_REPONSE_S)
            try:
                reponse = s.recv(4096).decode("latin-1", "replace")
            except TimeoutError:
                return "muet", f"aucune réponse en {DELAI_REPONSE_S} s"
    ligne = reponse.split("\r\n", 1)[0]
    morceaux = ligne.split(" ", 2)
    code = morceaux[1] if len(morceaux) > 1 else "?"
    if code == "100":
        return "accepte", ligne
    if code == "413":
        return "refuse", ligne
    return "autre", ligne or "(réponse vide)"


def phase_1(url: str, jeton: str) -> tuple[int | None, int | None]:
    """Encadre la limite. Renvoie (plus grande taille acceptée, plus petite
    refusée), en octets ; None si non observé."""
    print("\n── Phase 1 : limite d'entrée de la passerelle (rien n'est envoyé) ──")
    acceptee, refusee = None, None
    for mo in PALIERS_MO:
        verdict, detail = annoncer(url, jeton, mo * MO)
        signe = {"accepte": "✅", "muet": "✅", "refuse": "⛔"}.get(verdict, "❔")
        print(f"   {signe} {mo:>5} Mo annoncés : {verdict:8} ({detail})")
        if verdict in ("accepte", "muet"):
            acceptee = mo * MO
        elif verdict == "refuse":
            refusee = mo * MO
            break
        else:
            print("   Réponse inattendue : l'encadrement s'arrête ici.")
            return acceptee, refusee
    # Affinage entre le dernier palier accepté et le premier refusé.
    if acceptee and refusee:
        bas, haut = acceptee, refusee
        while haut - bas > 25 * MO:
            milieu = (bas + haut) // 2
            verdict, _ = annoncer(url, jeton, milieu)
            if verdict in ("accepte", "muet"):
                bas = milieu
            else:
                haut = milieu
        acceptee, refusee = bas, haut
    return acceptee, refusee


# ══════════════════════════ Phase 2 : envoi réel ══════════════════════════


def phase_2(requests, url: str, jeton: str) -> dict | None:
    print("\n── Phase 2 (facultative) : envoi réel d'une vidéo ──")
    print("   Elle part chez Aristote et CRÉE un enrichissement (suppression proposée à la fin).")
    if input("   Tapez OUI pour lancer cet envoi : ").strip().lower() != "oui":
        print("   Phase 2 ignorée.")
        return None
    try:
        from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor
    except ImportError:
        print("   « requests-toolbelt » manque : python -m pip install requests-toolbelt")
        return None
    # Le glisser-déposer ajoute des guillemets ou des apostrophes selon le terminal.
    chemin = input("   Chemin de la vidéo (vous pouvez la glisser ici) : ").strip().strip("\"'")
    if not os.path.isfile(chemin):
        print("   Fichier introuvable.")
        return None
    taille = os.path.getsize(chemin)
    nom = os.path.basename(chemin)
    print(f"   {nom} : {taille / MO:.0f} Mo")

    champs = {
        "enrichmentParameters": json.dumps(
            {
                "generateMetadata": False,
                "generateQuiz": False,
                "generateNotes": False,
                "language": "fr",
            }
        ),
        "originalFileName": nom,
        "notificationWebhookUrl": f"{url}/v1/webhook",
        "endUserIdentifier": "podadmin-sonde-taille",
    }
    debut = time.time()
    with open(chemin, "rb") as fh:
        import mimetypes

        mime = mimetypes.guess_type(nom)[0] or "application/octet-stream"
        enc = MultipartEncoder(fields={**champs, "file": (nom, fh, mime)})
        dernier = [0.0]

        def progression(m):
            if time.time() - dernier[0] > 2:
                dernier[0] = time.time()
                print(f"\r   Envoi : {m.bytes_read / MO:.0f} / {enc.len / MO:.0f} Mo  ", end="")

        mon = MultipartEncoderMonitor(enc, progression)
        try:
            r = requests.post(
                f"{url}/v1/enrichments/upload",
                data=mon,
                timeout=(30, 3600),
                headers={
                    "Authorization": f"Bearer {jeton}",
                    "Accept": "application/json",
                    "Content-Type": mon.content_type,
                },
            )
        except requests.exceptions.RequestException as e:
            print(f"\n   ⛔ Envoi interrompu au bout de {time.time() - debut:.0f} s : {e}")
            return {"taille": taille, "ok": False, "detail": f"coupure : {e}"}
    duree = time.time() - debut
    print(f"\n   Réponse HTTP {r.status_code} après {duree:.0f} s : {r.text[:300]}")
    if r.status_code != 200:
        return {"taille": taille, "ok": False, "detail": f"HTTP {r.status_code}"}
    eid = (r.json() or {}).get("id")
    resultat = {"taille": taille, "ok": True, "duree": duree, "id": eid, "etat": "?"}

    # Suivi : l'application accepte-t-elle réellement le fichier ?
    print("   Suivi de l'état pendant 2 minutes…")
    fin = time.time() + 120
    while eid and time.time() < fin:
        e = requests.get(
            f"{url}/v1/enrichments/{eid}",
            timeout=30,
            headers={"Authorization": f"Bearer {jeton}", "Accept": "application/json"},
        ).json()
        resultat["etat"] = e.get("status", "?")
        print(f"   État : {resultat['etat']} {e.get('failureCause') or ''}")
        if resultat["etat"] in (
            "FAILURE",
            "SUCCESS",
            "WAITING_MEDIA_TRANSCRIPTION",
            "TRANSCRIBING_MEDIA",
        ):
            break
        time.sleep(15)

    if eid and input(
        "   Supprimer cet enrichissement chez Aristote ? (O/n) : "
    ).strip().lower() not in ("n", "non"):
        r = requests.delete(
            f"{url}/v1/enrichments/{eid}", timeout=30, headers={"Authorization": f"Bearer {jeton}"}
        )
        print(f"   Suppression : HTTP {r.status_code}")
    return resultat


# ══════════════════════════════ Synthèse ══════════════════════════════════


def synthese(acceptee, refusee, envoi) -> None:
    print("\n══ SYNTHÈSE (à transmettre) ══")
    if refusee:
        print(
            f"• Passerelle : accepte jusqu'à {acceptee / MO:.0f} Mo, "
            f"refuse à partir de {refusee / MO:.0f} Mo environ."
        )
    elif acceptee:
        print(f"• Passerelle : aucun refus jusqu'à {acceptee / MO:.0f} Mo annoncés.")
    else:
        print("• Passerelle : limite non déterminée (voir les réponses ci-dessus).")
    if envoi is None:
        print("• Envoi réel : non effectué.")
    elif envoi["ok"]:
        print(
            f"• Envoi réel de {envoi['taille'] / MO:.0f} Mo : ACCEPTÉ en {envoi['duree']:.0f} s, "
            f"état ensuite : {envoi['etat']}."
        )
    else:
        print(f"• Envoi réel de {envoi['taille'] / MO:.0f} Mo : REFUSÉ ({envoi['detail']}).")


if __name__ == "__main__":
    print(__doc__.split("DEUX PHASES")[0])
    requests = charger_requests()
    if requests:
        url = (input(f"Adresse de l'API Aristote [{URL_DEFAUT}] : ").strip() or URL_DEFAUT).rstrip(
            "/"
        )
        cid, secret = identifiants()
        jeton = jeton_aristote(requests, url, cid, secret)
        print("✅ Connexion à Aristote réussie.")
        acceptee, refusee = phase_1(url, jeton)
        envoi = phase_2(requests, url, jeton)
        synthese(acceptee, refusee, envoi)
    input("\nAppuyez sur Entrée pour fermer…")
