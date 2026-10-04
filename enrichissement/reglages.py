"""
reglages.py — Dossier de données et préférences de l'onglet « Enrichissement IA ».

Le dossier reste ~/.soustitreur, celui de SousTitreur : projets en cours,
sauvegardes des pistes remplacées, journal des écritures sur Pod et
préférences (config.json) s'y retrouvent sans migration.

Le `config.py` de PodAdmin n'est pas utilisé pour ces préférences : `projet`
et `journal` attendaient celui de SousTitreur (constante DOSSIER). Les
IDENTIFIANTS Aristote, eux, sont dans `config.py` de PodAdmin, à côté du
compte DEPOT : tous les secrets embarqués au même endroit.
"""

from __future__ import annotations

import json
import os

DOSSIER = os.path.join(os.path.expanduser("~"), ".soustitreur")
CONFIG_PATH = os.path.join(DOSSIER, "config.json")
URL_ARISTOTE_DEFAUT = "https://stt.ilaas.fr/api"     # instance ILaaS

# Taille maximale d'un fichier du POSTE envoyé à Aristote. ffmpeg n'étant pas
# embarqué, une vidéo part ENTIÈRE (et non son seul son). Mesuré par la sonde
# verifier_ilaas_taille.py (2026-10-04) : la passerelle d'ILaaS accepte
# environ 795 Mo et refuse à partir de 811 Mo. 780 Mo garde une marge pour
# l'enveloppe multipart. Une vidéo déjà sur Pod n'est PAS concernée : Aristote
# télécharge alors son MP3 lui-même, sans passer par cette porte.
LIMITE_ENVOI_OCTETS = 780 * 1024 * 1024

# Repris de SousTitreur, SAUF « langue » (les vidéos sont en français, sans
# choix) et « extraire_audio » (ffmpeg n'est pas embarqué dans PodAdmin).
DEFAUTS = {
    "url_aristote": URL_ARISTOTE_DEFAUT,
    "formats": ["vtt"],
    "decoupage": {},            # surcharges de sous_titres.Parametres
    # Listes dans lesquelles Aristote choisit la discipline et le type d'une
    # vidéo du POSTE (pour une vidéo Pod, ce sont les listes réelles de Pod).
    "disciplines": ["Arts", "Droit", "Économie et gestion", "Éducation", "Informatique",
                    "Langues", "Lettres", "Mathématiques", "Santé", "Sciences de l'ingénieur",
                    "Sciences de la vie", "Sciences humaines et sociales", "Sciences physiques",
                    "Sport", "Autres"],
    "types_media": ["Cours", "Conférence", "Tutoriel", "Témoignage", "Présentation",
                    "Webinaire", "Autre"],
}


def charger() -> dict:
    """Préférences, complétées par les valeurs par défaut."""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    return {**DEFAUTS, **(d if isinstance(d, dict) else {})}


def enregistrer(cfg: dict) -> None:
    """Écriture atomique : un arrêt brutal ne laisse jamais un fichier tronqué."""
    os.makedirs(DOSSIER, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)


def url_aristote() -> str:
    """Adresse de l'API Aristote : celle des préférences, sinon ILaaS."""
    return (charger().get("url_aristote") or URL_ARISTOTE_DEFAUT).rstrip("/")
