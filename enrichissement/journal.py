#!/usr/bin/env python3
"""
journal.py — Journal de toutes les écritures faites dans Pod.

Une ligne JSON par écriture, dans ~/.soustitreur/journal_pod.jsonl : date,
vidéo, action, ancienne et nouvelle valeur, fichier de sauvegarde. Il permet
de savoir qui a changé quoi, et de revenir en arrière à la main si besoin.
Le fichier n'est jamais réécrit : on ne fait qu'y ajouter des lignes.
"""

from __future__ import annotations

__author__ = "Cédric MONNA"
import getpass
import json
import os
from datetime import datetime

from __version__ import __version__  # noqa: E402

from . import reglages as cfg

CHEMIN = os.path.join(cfg.DOSSIER, "journal_pod.jsonl")


def noter(action: str, video: dict, **details) -> None:
    os.makedirs(cfg.DOSSIER, exist_ok=True)
    ligne = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "poste": getpass.getuser(),
        "version": __version__,
        "action": action,
        "video_id": video.get("id"),
        "video_titre": video.get("title") or video.get("titre"),
        **details,
    }
    with open(CHEMIN, "a", encoding="utf-8") as f:
        f.write(json.dumps(ligne, ensure_ascii=False) + "\n")


def lire(video_id: int | None = None, derniers: int = 50) -> list[dict]:
    try:
        with open(CHEMIN, encoding="utf-8") as f:
            lignes = [json.loads(l) for l in f if l.strip()]
    except (OSError, ValueError):
        return []
    if video_id is not None:
        lignes = [l for l in lignes if l.get("video_id") == video_id]
    return lignes[-derniers:]
