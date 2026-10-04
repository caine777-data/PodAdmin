#!/usr/bin/env python3
"""
projet.py — Un « projet » = une vidéo, sa transcription et ses sous-titres.

Les projets sont rangés dans ~/.soustitreur/projets/<id>.json. L'identifiant
dépend du NOM et de la TAILLE de la vidéo : redéposer la même vidéo rouvre le
projet existant au lieu de renvoyer le fichier à Aristote (gain de temps et de
crédits), même si elle a été déplacée entre-temps.

Contenu d'un projet :
  media            chemin de la vidéo
  audio            chemin de l'audio extrait (lecture de secours dans l'éditeur)
  enrichment_id    identifiant Aristote
  langue           langue de la transcription
  mots             mots horodatés (permettent de refaire le découpage)
  sous_titres      liste [{start, end, text}] : c'est ce que l'on corrige
  etat             envoi | attente | a_corriger | corrige | erreur
"""

from __future__ import annotations

__author__ = "Cédric MONNA"
from __version__ import __version__   # noqa: E402

import hashlib
import json
import os
import re
from datetime import datetime

from . import reglages as cfg
from . import sous_titres as st

DOSSIER_PROJETS = os.path.join(cfg.DOSSIER, "projets")
DOSSIER_AUDIO = os.path.join(cfg.DOSSIER, "audio")


def identifiant(chemin_media: str) -> str:
    nom = os.path.basename(chemin_media).lower()
    taille = os.path.getsize(chemin_media) if os.path.exists(chemin_media) else 0
    return hashlib.sha1(f"{nom}|{taille}".encode()).hexdigest()[:16]


def chemin_projet(pid: str) -> str:
    return os.path.join(DOSSIER_PROJETS, f"{pid}.json")


def existe(pid: str) -> bool:
    return os.path.exists(chemin_projet(pid))


def nouveau(chemin_media: str, langue: str) -> dict:
    return {
        "id": identifiant(chemin_media),
        "media": os.path.abspath(chemin_media),
        "nom": os.path.basename(chemin_media),
        "audio": "",
        "langue": langue,
        "enrichment_id": "",
        "mots": [],
        "sous_titres": [],
        "parametres": {},
        "etat": "envoi",
        "erreur": "",
        "cree": datetime.now().isoformat(timespec="seconds"),
        "modifie": datetime.now().isoformat(timespec="seconds"),
    }


def id_pod(video_id: int) -> str:
    """Un projet par vidéo Pod : la rouvrir retrouve le travail en cours."""
    return f"pod{int(video_id)}"


def nouveau_pod(video: dict, lien: str, mp4: str | None, proprietaire: str,
                disciplines: list[str], types: list[str], langue: str) -> dict:
    """Projet rattaché à une vidéo Pod : rien n'est stocké sur le poste.

    La vidéo est lue en ligne (`video_distante`) ; les fichiers exportés vont
    dans Documents/SousTitreur/<identifiant>-<titre>.
    """
    titre = video.get("title") or f"Vidéo {video['id']}"
    p = nouveau(titre, langue or video.get("main_lang") or "fr")
    p.update({
        "id": id_pod(video["id"]),
        "media": "",
        "nom": titre,
        "video_distante": mp4 or "",
        "dossier": os.path.join(os.path.expanduser("~"), "Documents", "SousTitreur",
                                re.sub(r'[\\/:*?"<>|]+', "-", f"{video['id']:04d}-{titre}")[:80]),
        "pod": {
            "id": video["id"], "url_api": video["url"], "lien": lien,
            "slug": video.get("slug", ""), "titre": titre, "proprietaire": proprietaire,
            "duree": video.get("duration"),
            # Listes réelles de Pod : Aristote choisira la discipline et le type dedans.
            "disciplines": disciplines, "types": types,
        },
    })
    os.makedirs(p["dossier"], exist_ok=True)
    return p


def charger(pid: str) -> dict:
    with open(chemin_projet(pid), encoding="utf-8") as f:
        return json.load(f)


def enregistrer(p: dict) -> None:
    os.makedirs(DOSSIER_PROJETS, exist_ok=True)
    p["modifie"] = datetime.now().isoformat(timespec="seconds")
    tmp = chemin_projet(p["id"]) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False)
    # Sous Windows, remplacer un fichier qu'un autre fil est en train de LIRE
    # échoue (« Accès refusé ») : l'éditeur et l'onglet relisent les projets
    # pendant que les fils de travail les écrivent. La lecture dure quelques
    # millisecondes ; on réessaie donc brièvement avant d'abandonner.
    import time
    for essai in range(20):
        try:
            os.replace(tmp, chemin_projet(p["id"]))
            return
        except PermissionError:
            if essai == 19:
                raise
            time.sleep(0.05)


def lister() -> list[dict]:
    """Projets existants, du plus récent au plus ancien (sans les mots)."""
    sortie = []
    if not os.path.isdir(DOSSIER_PROJETS):
        return sortie
    for nom in os.listdir(DOSSIER_PROJETS):
        if nom.endswith(".json"):
            try:
                p = charger(nom[:-5])
                p.pop("mots", None)
                sortie.append(p)
            except (OSError, ValueError):
                pass
    return sorted(sortie, key=lambda p: p.get("modifie", ""), reverse=True)


def appliquer_transcription(p: dict, transcript: dict,
                            params: st.Parametres) -> None:
    """Remplit le projet à partir de la transcription d'Aristote."""
    mots = st.mots_depuis_aristote(transcript.get("sentences") or [],
                                   params.filtrer_hallucinations)
    p["mots"] = [[m.texte, round(m.debut, 3), round(m.fin, 3)] for m in mots]
    p["langue"] = transcript.get("language") or p.get("langue")
    redecouper(p, params)


def redecouper(p: dict, params: st.Parametres) -> None:
    """Refait le découpage depuis les mots (annule les corrections)."""
    mots = [st.Mot(t, d, f) for t, d, f in p.get("mots") or []]
    p["sous_titres"] = [s.en_dict() for s in st.decouper(mots, params)]
    p["parametres"] = params.en_dict()
    p["etat"] = "a_corriger"


# ───────────────────── Enrichissement : traduction, métadonnées, quiz ─────────

def enrichissement(p: dict) -> dict:
    """Bloc « enrichissement » du projet, créé vide au besoin."""
    return p.setdefault("enrichissement", {
        "etat": "",            # "" | en_cours | termine | erreur
        "detail": "",
        "eid": "",
        "traduire_vers": "",
        "metadonnees": {},
        "quiz": [],
        "traductions": {},     # {"en": [{start, end, text}]}
    })


def appliquer_enrichissement(p: dict, version: dict, traduire_vers: str,
                             params: st.Parametres) -> None:
    """Range dans le projet ce qu'Aristote a produit à partir des sous-titres."""
    e = enrichissement(p)
    m = version.get("enrichmentVersionMetadata") or {}
    if m:
        e["metadonnees"] = {
            "titre": m.get("title") or "",
            "description": m.get("description") or "",
            "mots_cles": list(m.get("topics") or []),
            "discipline": m.get("discipline") or "",
            "type": m.get("mediaType") or "",
        }
    quiz = []
    for q in version.get("multipleChoiceQuestions") or []:
        quiz.append({
            "question": q.get("question") or "",
            "explication": q.get("explanation") or "",
            "choix": [{"texte": c.get("optionText") or "",
                       "correct": bool(c.get("correctAnswer"))}
                      for c in q.get("choices") or []],
        })
    if quiz:
        e["quiz"] = quiz

    traduites = (version.get("transcript") or {}).get("translatedSentences") or []
    if traduire_vers and traduites:
        # Aristote traduit élément par élément : une phrase envoyée donne une
        # phrase traduite, dans le même ordre. On les redécoupe aux normes
        # sur la durée de la phrase d'origine.
        groupes = [st.SousTitre.depuis_dict(g) for g in e.get("groupes") or []]
        if len(groupes) != len(traduites):
            groupes = [st.SousTitre(float(t.get("start", 0)), float(t.get("end", 0)), "")
                       for t in traduites]
        sts = st.decouper_traduction(groupes, [t.get("text") for t in traduites], params)
        e["traductions"][traduire_vers] = [s.en_dict() for s in sts]
    e["etat"], e["detail"] = "termine", ""


def _gift(texte: str) -> str:
    """Échappe les caractères spéciaux du format GIFT de Moodle."""
    return re.sub(r"([~=#{}:\\])", r"\\\1", texte.replace("\n", " ").strip())


def quiz_vers_gift(quiz: list[dict], titre: str = "") -> str:
    """Quiz au format GIFT, importable dans la banque de questions Moodle."""
    blocs = []
    if titre:
        blocs.append(f"$CATEGORY: $course$/{titre.replace('/', '-')}\n")
    for i, q in enumerate(quiz, 1):
        if not q.get("question") or not q.get("choix"):
            continue
        lignes = [f"::Q{i}:: {_gift(q['question'])} {{"]
        for c in q["choix"]:
            lignes.append(f"\t{'=' if c.get('correct') else '~'}{_gift(c.get('texte', ''))}")
        if q.get("explication"):
            lignes.append(f"\t####{_gift(q['explication'])}")
        lignes.append("}\n")
        blocs.append("\n".join(lignes))
    return "\n".join(blocs)


def metadonnees_vers_texte(m: dict) -> str:
    return (f"Titre :\n{m.get('titre', '')}\n\n"
            f"Description :\n{m.get('description', '')}\n\n"
            f"Mots-clés :\n{', '.join(m.get('mots_cles') or [])}\n\n"
            f"Discipline : {m.get('discipline', '')}\n"
            f"Type : {m.get('type', '')}\n")


# ─────────────────────────────── Export ──────────────────────────────────

def exporter(p: dict, formats: list[str], dossier: str | None = None,
             langues: list[str] | None = None, metadonnees: bool = False,
             quiz: bool = False) -> list[str]:
    """Écrit les fichiers à côté de la vidéo (ou dans `dossier`).

    `langues` : traductions à exporter en plus des sous-titres d'origine.
    `metadonnees` : fichier texte (titre, description, mots-clés).
    `quiz` : fichier GIFT pour Moodle.

    Le projet doit être enregistré ensuite : il retient la liste des fichiers
    écrits (`exports`) pour pouvoir les remplacer lors d'un nouvel export.
    """
    base = os.path.splitext(p["nom"])[0]
    # « cours.fr.vtt » importé : on ne rajoute pas une seconde fois « .fr ».
    base = re.sub(r"\.(fr|en|es|de|it|pt)$", "", base)
    dossier = dossier or p.get("dossier") or os.path.dirname(p.get("media") or "")
    if not dossier or not os.access(dossier, os.W_OK):
        dossier = os.path.join(os.path.expanduser("~"), "Documents")
    deja = set(p.get("exports") or [])
    ecrits = []

    def ecrire(nom_fichier: str, contenu: str) -> None:
        chemin = os.path.join(dossier, nom_fichier)
        # Ne jamais écraser un fichier que SousTitreur n'a pas écrit lui-même
        # (le VTT d'origine importé depuis Pod, par exemple).
        if os.path.exists(chemin) and chemin not in deja:
            chemin =os.path.join(dossier, f"{base} (corrigé){nom_fichier[len(base):]}")
        with open(chemin, "w", encoding="utf-8", newline="\n") as f:
            f.write(contenu)
        ecrits.append(chemin)

    pistes = [(p.get("langue") or "fr", p["sous_titres"])]
    e = p.get("enrichissement") or {}
    for lg in langues or []:
        if (e.get("traductions") or {}).get(lg):
            pistes.append((lg, e["traductions"][lg]))
    for lg, cues in pistes:
        sts = [st.SousTitre.depuis_dict(d) for d in cues]
        for fmt in formats:
            ecrire(f"{base}.{lg}.{fmt}", st.vers_vtt(sts) if fmt == "vtt" else st.vers_srt(sts))
    if metadonnees and e.get("metadonnees"):
        ecrire(f"{base}.metadonnees.txt", metadonnees_vers_texte(e["metadonnees"]))
    if quiz and e.get("quiz"):
        titre = (e.get("metadonnees") or {}).get("titre") or base
        ecrire(f"{base}.quiz-moodle.gift.txt", quiz_vers_gift(e["quiz"], titre))
    p["exports"] = sorted(deja | set(ecrits))
    return ecrits
