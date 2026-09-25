#!/usr/bin/env python3
"""
config.py — Configuration et stockage sécurisé des identifiants (PodAdmin).

• L'URL de l'instance + les préférences → fichier JSON (~/.podadmin.json)
• Le TOKEN de service → coffre-fort natif de l'OS via keyring
  (Windows Credential Manager / macOS Keychain). Jamais en clair sur disque.

⚠️ PodAdmin vise un compte SUPERUTILISATEUR. Son token est stocké sous une clé
   DIFFÉRENTE de celle de « Pod Téléverseur » : les deux applis peuvent
   cohabiter sur un même poste sans se marcher dessus.
"""

from __future__ import annotations

__author__      = "Cédric MONNA"
__contact__     = "support-pod@utoulouse.fr"
__institution__ = "Université de Toulouse — MFCA"
from __version__ import __version__   # source unique (voir __version__.py)
__date__        = "2026"
__license__     = "Usage interne — Université de Toulouse"


import json
import os

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".podadmin.json")
KEYRING_SERVICE = "PodAdmin-UToulouse"          # ≠ "PodTeleverseur-UToulouse"
KEYRING_TOKEN_KEY = "service_token"
# Identifiants du COMPTE VÉHICULE (local) servant à ouvrir la session web pour
# le téléversement chunké des gros fichiers. Stockés chiffrés (keyring), dans
# l'espace de noms de PodAdmin. L'admin les saisit dans l'onglet Configuration.
KEYRING_USER_KEY = "vehicle_username"
KEYRING_PASS_KEY = "vehicle_password"

# ── Compte VÉHICULE embarqué (DEPOT) ──────────────────────────────────────
# Compte LOCAL sans privilège, servant UNIQUEMENT à ouvrir la session web du
# téléversement par morceaux (chunké). Il est embarqué pour que la bascule sur
# les gros fichiers soit TRANSPARENTE : l'administrateur n'a rien à saisir.
#
# Un compte véhicule saisi dans l'onglet Configuration reste PRIORITAIRE :
# ces valeurs ne servent que de repli quand aucun n'a été renseigné.
#
# ⚠️ SÉCURITÉ : ce mot de passe est en clair dans le code, donc extractible d'un
#    exécutable. C'est acceptable UNIQUEMENT parce que le compte est LOCAL et
#    SANS PRIVILÈGE (au pire, déposer une vidéo en son nom).
#    → Le dépôt GitHub de PodAdmin doit rester PRIVÉ.
#    → Ce compte ne doit JAMAIS être superutilisateur ni staff.
#    → Toute rotation du mot de passe impose de recompiler et redistribuer.
VEHICLE_USERNAME = "DEPOT"
VEHICLE_PASSWORD = "V&xehx7WB!iBWLoL%97HDjK&kg"

# ── Bascule vers le téléversement par morceaux (chunked) ──────────────────
# > seuil : session web (véhicule) + chunk, puis PATCH owner vers le propriétaire
# choisi. ≤ seuil : upload classique par token (inchangé).
# Seuil de bascule vers l'envoi par morceaux.
#
# ATTENTION : ce seuil est en OCTETS, mais ce qui fait échouer un envoi direct
# est sa DURÉE. La passerelle (nginx) ferme la connexion au-delà d'environ une
# minute de transfert — erreur « SSLEOFError: EOF occurred in violation of
# protocol ». Sur une liaison montante lente, un fichier bien plus petit que le
# seuil peut donc dépasser cette minute et être coupé.
#
# L'application se replie automatiquement sur l'envoi par morceaux dans ce cas
# (voir App._replier_sur_chunked), mais après avoir perdu du temps en tentatives
# inutiles. Abaisser ce seuil évite ces tentatives : 150 Mo correspond à environ
# une minute d'envoi sur une liaison à 20 Mbit/s.
CHUNK_THRESHOLD_BYTES = 150 * 1024 * 1024      # 150 Mo
CHUNK_SIZE_BYTES      = 2 * 1024 * 1024         # 2 Mo par morceau (validé)

# ── Vérification « lancer puis vérifier » après un 504 de finalisation ────
# Sur un gros fichier, nginx peut couper (504) avant que Pod ait fini d'assembler
# — mais Pod termine en arrière-plan. On sonde l'API jusqu'à voir la vidéo.
# Fenêtre portée à 30 min (des fichiers > 2 Go peuvent dépasser le quart d'heure).
CHUNK_VERIFY_TIMEOUT_S  = 1800   # 30 minutes
CHUNK_VERIFY_INTERVAL_S = 15     # intervalle entre deux sondages (secondes)

try:
    import keyring
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False


DEFAULTS = {
    "url": "https://videos.utoulouse.fr",
    "type_url": "",          # URL du type par défaut (ex : .../rest/types/1/)
    "main_lang": "fr",
    "cursus": "0",
    "is_draft": True,
    "agent_username": "",    # qui dépose (devient owner) — onglet Téléversement
    "agent_owner_url": "",   # URL résolue de l'agent
}


def load_config() -> dict:
    """Charge la configuration (JSON) en complétant par les valeurs par défaut."""
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg: dict) -> None:
    # On ne sauvegarde jamais de secret dans le JSON
    secrets = {"token", "vehicle_username", "vehicle_password", "password"}
    safe = {k: v for k, v in cfg.items() if k not in secrets}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(safe, f, indent=2, ensure_ascii=False)


# ── Token : coffre-fort de l'OS si possible, sinon fichier local ──────────


# ── Mise à jour OBLIGATOIRE : mémorisation locale du blocage confirmé ──────
#
# Principe retenu (« modèle 1 durci », choisi après discussion sur les
# risques d'un blocage qui dépendrait d'une disponibilité réseau
# permanente) :
#
#   1. Tant que le serveur n'a jamais confirmé l'obligation pour CETTE
#      version installée, l'application démarre normalement — un réseau
#      coupé, un dépôt GitHub injoignable ou un token expiré ne doivent
#      JAMAIS empêcher tout le monde de travailler.
#   2. Le jour où le serveur RÉPOND et confirme l'obligation pour la
#      version installée, ce fait est enregistré ICI, localement. Aux
#      lancements suivants, le blocage s'applique MÊME SANS RÉSEAU : on
#      empêche ainsi qu'une personne notifiée une fois contourne le
#      blocage en coupant simplement sa connexion ensuite.
#   3. Le verrou local ne vaut QUE pour la version qui l'a déclenché : dès
#      que l'application est mise à jour vers une version qui n'est plus
#      concernée, elle redémarre normalement sans avoir besoin du réseau
#      pour "prouver" qu'elle est à jour.
#
# Ce mécanisme protège contre un contournement volontaire une fois notifié ;
# il ne transforme jamais une panne réseau générale en arrêt total du
# service pour des postes qui n'ont jamais été notifiés.

def enregistrer_blocage_confirme(version_bloquee: str, version_minimale: str,
                                 url: str = "", notes: str = "") -> None:
    """Mémorise qu'un blocage a été confirmé par le serveur pour cette version.

    `url` et `notes` sont conservées pour que la fenêtre bloquante rejouée
    HORS LIGNE (voir `blocage_local_actif`) garde son lien de téléchargement
    et son message — sans elles, un lancement sans réseau afficherait un
    blocage muet, sans moyen d'agir.

    Appelée uniquement après une réponse RÉSEAU RÉELLE et positive du
    serveur (voir `maj.etat_mise_a_jour`) — jamais de manière spéculative."""
    try:
        cfg = load_config()
        cfg["maj_obligatoire_version"] = str(version_bloquee)
        cfg["maj_obligatoire_minimale"] = str(version_minimale)
        cfg["maj_obligatoire_url"] = str(url or "")
        cfg["maj_obligatoire_notes"] = str(notes or "")
        save_config(cfg)
    except Exception:
        pass          # ne jamais lever depuis un enregistrement de confort


def blocage_local_actif(version_actuelle: str) -> dict | None:
    """Renvoie les infos du blocage mémorisé SI il s'applique encore à la
    version actuellement lancée (dict avec version/url/notes), sinon None.

    Ne s'applique que si `version_actuelle` correspond exactement à la
    version qui avait été bloquée : une mise à jour vers une version plus
    récente lève le verrou local automatiquement, sans avoir besoin du
    réseau pour le constater."""
    try:
        cfg = load_config()
        bloquee = str(cfg.get("maj_obligatoire_version", "") or "")
        if bloquee and bloquee == str(version_actuelle):
            minimale = str(cfg.get("maj_obligatoire_minimale", "") or "")
            if minimale:
                return {
                    "version": minimale,
                    "url": str(cfg.get("maj_obligatoire_url", "") or ""),
                    "notes": str(cfg.get("maj_obligatoire_notes", "") or ""),
                }
    except Exception:
        pass
    return None


def lever_blocage_local() -> None:
    """Efface le verrou local (utilisé quand une version plus récente est
    détectée : le blocage n'a plus lieu d'être, autant nettoyer le fichier)."""
    try:
        cfg = load_config()
        cfg.pop("maj_obligatoire_version", None)
        cfg.pop("maj_obligatoire_minimale", None)
        cfg.pop("maj_obligatoire_url", None)
        cfg.pop("maj_obligatoire_notes", None)
        save_config(cfg)
    except Exception:
        pass


# ── Token : coffre-fort de l'OS si possible, sinon fichier local ──────────


def _token_file() -> str:
    """Chemin du fichier de repli pour le token (si keyring indisponible)."""
    return os.path.join(os.path.expanduser("~"), ".podadmin_token")


def save_token(token: str) -> str:
    """Enregistre le token. Renvoie 'keyring' ou 'file' selon le moyen utilisé."""
    if HAS_KEYRING:
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY, token)
            try:
                p = _token_file()
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
            return "keyring"
        except Exception:
            pass  # backend indisponible → on bascule sur le fichier
    try:
        path = _token_file()
        with open(path, "w", encoding="utf-8") as f:
            f.write(token)
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        return "file"
    except Exception:
        return ""


def load_token() -> str:
    """Lit le token (keyring puis fichier de repli)."""
    if HAS_KEYRING:
        try:
            t = keyring.get_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY)
            if t:
                return t
        except Exception:
            pass
    path = _token_file()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""


def clear_token() -> None:
    """Efface le token du poste (keyring et fichier)."""
    if HAS_KEYRING:
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY)
        except Exception:
            pass
    path = _token_file()
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


# ── Identifiants du COMPTE VÉHICULE (session chunkée) ─────────────────────
# Même principe que le token : keyring si possible, sinon fichier local 0600.
def _secret_file(suffix: str) -> str:
    """Chemin du fichier de repli pour un secret donné."""
    return os.path.join(os.path.expanduser("~"), f".podadmin_{suffix}")


def _save_secret(key: str, suffix: str, value: str) -> str:
    """Enregistre un secret (keyring si possible, sinon fichier 0600)."""
    if HAS_KEYRING:
        try:
            keyring.set_password(KEYRING_SERVICE, key, value)
            try:
                p = _secret_file(suffix)
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
            return "keyring"
        except Exception:
            pass
    try:
        path = _secret_file(suffix)
        with open(path, "w", encoding="utf-8") as f:
            f.write(value)
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        return "file"
    except Exception:
        return ""


def _load_secret(key: str, suffix: str) -> str:
    """Lit un secret (keyring puis fichier de repli)."""
    if HAS_KEYRING:
        try:
            v = keyring.get_password(KEYRING_SERVICE, key)
            if v:
                return v
        except Exception:
            pass
    path = _secret_file(suffix)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""


def _clear_secret(key: str, suffix: str) -> None:
    """Efface un secret du poste (keyring et fichier)."""
    if HAS_KEYRING:
        try:
            keyring.delete_password(KEYRING_SERVICE, key)
        except Exception:
            pass
    path = _secret_file(suffix)
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


def save_vehicle_credentials(username: str, password: str) -> str:
    """Enregistre l'identifiant ET le mot de passe du compte véhicule.
    Renvoie le moyen de stockage du mot de passe ('keyring', 'file' ou '')."""
    _save_secret(KEYRING_USER_KEY, "vehicle_user", username or "")
    return _save_secret(KEYRING_PASS_KEY, "vehicle_pass", password or "")


def load_vehicle_credentials() -> tuple[str, str]:
    """Renvoie (identifiant, mot_de_passe) du compte véhicule — ('','') si absent."""
    return (_load_secret(KEYRING_USER_KEY, "vehicle_user"),
            _load_secret(KEYRING_PASS_KEY, "vehicle_pass"))


def clear_vehicle_credentials() -> None:
    """Efface l'identifiant ET le mot de passe du compte véhicule du poste."""
    _clear_secret(KEYRING_USER_KEY, "vehicle_user")
    _clear_secret(KEYRING_PASS_KEY, "vehicle_pass")


# Extensions vidéo reconnues lors du scan de dossier (onglet Téléversement)
VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v",
    ".wmv", ".flv", ".mpg", ".mpeg", ".ts", ".mts",
}

# ── Vérification des mises à jour ────────────────────────────────────────
# Adresse du fichier décrivant la dernière version publiée. Il est hébergé sur
# un dépôt GitHub PUBLIC distinct du dépôt de code (qui reste privé, puisqu'il
# contient le mot de passe du compte véhicule).
#
# Le dépôt public ne contient QUE ce fichier et les exécutables : aucun secret.
# Voir MISE_A_JOUR.md pour la marche à suivre.
#
# Mettre à "" pour désactiver complètement la vérification.
UPDATE_URL = ("https://raw.githubusercontent.com/"
              "caine777-data/podadmin-releases/main/version.json")

# Page de secours si un `version.json` (ou un verrou local ancien) n'a pas
# d'URL renseignée : une fenêtre de blocage OBLIGATOIRE ne doit jamais se
# retrouver sans AUCUN moyen d'agir.
UPDATE_FALLBACK_URL = "https://github.com/caine777-data/podadmin-releases/releases/latest"

# Délai maximal (secondes) accordé à la vérification. Volontairement court :
# elle ne doit jamais retarder le démarrage.
UPDATE_TIMEOUT_S = 5

# ── Blocage à distance : interrupteur manuel, INDÉPENDANT de la MAJ ──────
# Contrairement à la mise à jour obligatoire ci-dessus (liée à un numéro de
# version), ce mécanisme permet de rendre TOUTES les copies installées
# inutilisables — puis de les débloquer — sur simple décision, sans publier
# de nouvelle version. Contrôlé depuis GitHub Actions (workflow "Build
# installers" → champ "Blocage"), PARAMÉTRÉ PAR DÉFAUT SUR « ne rien
# changer » : il ne se déclenche donc jamais tout seul, seule une action
# manuelle et explicite dans Actions peut l'activer.
#
# Publié dans un fichier SÉPARÉ (etat.json) sur le MÊME dépôt public que la
# mise à jour (podadmin-releases), pour ne jamais interférer avec
# version.json ni exiger une installation supplémentaire.
#
# Mettre à "" pour désactiver complètement la vérification.
BLOCAGE_URL = ("https://raw.githubusercontent.com/"
               "caine777-data/podadmin-releases/main/etat.json")
BLOCAGE_PERIODE_MS = 3600 * 1000     # délai entre deux vérifications (1 heure)
BLOCAGE_TIMEOUT_S = 5                 # jamais bloquant : délai volontairement court


# ── Blocage à distance : mémorisation locale (tient hors ligne) ──────────
#
# Même principe que le verrou de mise à jour obligatoire ci-dessus : seule
# une réponse RÉSEAU RÉELLE du serveur change l'état mémorisé. Un réseau
# coupé, un dépôt injoignable ou une adresse désactivée ne doivent JAMAIS
# déclencher, ni lever, un blocage — sans quoi couper sa connexion
# suffirait à contourner un blocage déjà notifié.

def enregistrer_blocage_distant(bloque: bool) -> None:
    """Mémorise localement l'état de blocage confirmé par le serveur.

    Appelée uniquement après une réponse réseau réelle et exploitable (voir
    `maj.etat_blocage`) — jamais de manière spéculative."""
    try:
        cfg = load_config()
        if bloque:
            cfg["blocage_distant"] = True
        else:
            cfg.pop("blocage_distant", None)
        save_config(cfg)
    except Exception:
        pass          # ne jamais lever depuis un enregistrement de confort


def blocage_distant_actif() -> bool:
    """Renvoie True si un blocage à distance a été mémorisé localement.

    Vérifié EN TOUT PREMIER au démarrage, avant tout accès réseau : un
    blocage déjà confirmé doit s'appliquer sans attendre la vérification
    périodique, sinon l'application resterait utilisable pendant ce délai."""
    try:
        return load_config().get("blocage_distant") is True
    except Exception:
        return False
