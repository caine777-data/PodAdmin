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
import json
import os

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".podadmin.json")
KEYRING_SERVICE = "PodAdmin-UToulouse"          # ≠ "PodTeleverseur-UToulouse"
KEYRING_TOKEN_KEY = "service_token"

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
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg: dict) -> None:
    # On ne sauvegarde jamais le token dans le JSON
    safe = {k: v for k, v in cfg.items() if k != "token"}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(safe, f, indent=2, ensure_ascii=False)


# ── Token : coffre-fort de l'OS si possible, sinon fichier local ──────────

def _token_file() -> str:
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


# Extensions vidéo reconnues lors du scan de dossier (onglet Téléversement)
VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v",
    ".wmv", ".flv", ".mpg", ".mpeg", ".ts", ".mts",
}
