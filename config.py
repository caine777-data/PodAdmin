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
__contact__     = "cedricmonna@gmail.com"
__institution__ = "Université de Toulouse — MFCA"
__version__     = "0.1.0"
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
CHUNK_THRESHOLD_BYTES = 500 * 1024 * 1024      # 500 Mo
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
