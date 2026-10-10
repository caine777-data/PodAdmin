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


# Sous Windows, lire un fichier à l'instant où un autre fil le REMPLACE, ou
# remplacer un fichier qu'un autre fil LIT, échoue (« Accès refusé »).
# L'éditeur, l'onglet et le suivi d'Aristote touchent les mêmes projets ; un
# antivirus peut aussi tenir le fichier. Une seconde de tentatives ne
# suffisait pas sous charge (audit O7, reproduit avec six fils) : 5 s, avec
# des pauses croissantes.
DELAI_ACCES_REFUSE = 5.0

# Python ouvre les fichiers sans autoriser leur remplacement : sous Windows,
# os.replace échoue tant qu'un AUTRE fil tient le projet ouvert en lecture.
# Avec plusieurs lecteurs, le fichier était presque toujours ouvert quelque
# part et l'écriture pouvait attendre indéfiniment. Ce verrou empêche, dans
# PodAdmin, qu'une lecture chevauche un remplacement ; les tentatives
# ci-dessus ne servent plus que pour un programme extérieur (antivirus).
import threading as _threading
_VERROU_FICHIERS = _threading.Lock()


def _insister(operation):
    import time
    limite = time.monotonic() + DELAI_ACCES_REFUSE
    pause = 0.02
    while True:
        try:
            return operation()
        except PermissionError:
            if time.monotonic() > limite:
                raise
            time.sleep(pause)
            pause = min(pause * 1.5, 0.25)


def charger(pid: str) -> dict:
    def lire():
        with _VERROU_FICHIERS, open(chemin_projet(pid), encoding="utf-8") as f:
            texte = f.read()
        return json.loads(texte)                # analyse hors du verrou
    return _insister(lire)


def enregistrer(p: dict) -> None:
    os.makedirs(DOSSIER_PROJETS, exist_ok=True)
    p["modifie"] = datetime.now().isoformat(timespec="seconds")
    # Fichier temporaire PROPRE à chaque écriture : avec un nom commun, deux
    # fils qui enregistraient le même projet (suivi Aristote, éditeur,
    # onglet) écrasaient ou déplaçaient le fichier l'un de l'autre.
    import threading
    tmp = f"{chemin_projet(p['id'])}.{os.getpid()}-{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False)
    try:
        def remplacer():
            with _VERROU_FICHIERS:
                os.replace(tmp, chemin_projet(p["id"]))
        _insister(remplacer)
    except PermissionError:
        # Abandon : ne pas laisser le fichier temporaire derrière soi.
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


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
#
# Depuis la 1.11.0, chaque PARTIE (traduction par langue, métadonnées, quiz)
# a sa propre demande Aristote. La sonde verifier_aristote_demandes.py
# (2026-10-08) l'a validé : une demande séparée ne renvoie que ce qu'on lui
# demande, et deux demandes simultanées ne se gênent pas. Une demande est
# ponctuelle : refaire un quiz, c'est une NOUVELLE demande.
#
# Clés : « meta », « quiz », « trad:<langue> » (une langue par demande :
# Aristote n'accepte qu'un translateTo à la fois). La partie « sous_titres »
# n'a pas de demande : elle vient de la transcription (p["etat"]).

def _maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


def enrichissement(p: dict) -> dict:
    """Bloc « enrichissement » du projet, créé vide au besoin, et converti
    s'il date d'avant la 1.11.0 (une seule demande groupée)."""
    e = p.setdefault("enrichissement", {
        "metadonnees": {},
        "quiz": [],
        "traductions": {},     # {"en": [{start, end, text}]}
    })
    for cle, defaut in (("metadonnees", {}), ("quiz", []), ("traductions", {}),
                        ("demandes", None), ("sources", {}), ("faits", {}), ("versions", {})):
        if cle not in e:
            e[cle] = _migrer_demandes(e) if cle == "demandes" else defaut
    for q in e["quiz"]:
        _completer_question(q)
    for d in e["demandes"].values():          # projets d'avant l'audit O5
        if d.get("etat") == "termine" and d.get("groupes"):
            d["groupes"] = []
    return e


def _migrer_demandes(e: dict) -> dict:
    """Ancienne demande groupée (SousTitreur, PodAdmin 1.10.0) : une seule
    demande « groupe » qui couvre les parties qu'elle a pu produire. Si elle
    est encore chez Aristote, son suivi reprend tel quel."""
    if not e.get("eid"):
        return {}
    parties = ["meta", "quiz"] + ([f"trad:{e['traduire_vers']}"] if e.get("traduire_vers") else [])
    etat = {"en_cours": "en_cours", "erreur": "erreur"}.get(e.get("etat"), "termine")
    return {"groupe": {"cle": "groupe", "eid": e["eid"], "parties": parties, "etat": etat,
                       "detail": e.get("detail", ""), "erreur": e.get("erreur", ""),
                       "demande_le": "", "empreinte": "", "groupes": e.get("groupes") or []}}


def empreinte(p: dict) -> str:
    """Empreinte des sous-titres (texte ET minutage) : sert à savoir si une
    traduction, des métadonnées ou un quiz ont été faits sur un texte qui a
    changé depuis."""
    donnees = [(round(float(s["start"]), 2), round(float(s["end"]), 2), s["text"])
               for s in p.get("sous_titres") or []]
    return hashlib.sha1(json.dumps(donnees, ensure_ascii=False).encode()).hexdigest()[:12]


def marquer_relu(p: dict) -> None:
    """« Relecture terminée » : distinct de l'état « corrige », qui veut dire
    « exporté au moins une fois » depuis SousTitreur."""
    p["relu"] = {"le": _maintenant(), "empreinte": empreinte(p)}


def marquer_fait(p: dict, partie: str) -> None:
    """Partie publiée sur Pod (sous-titres, traduction, métadonnées) ou
    exportée (quiz)."""
    if partie == "sous_titres":
        p.setdefault("faits", {})["sous_titres"] = _maintenant()
    else:
        enrichissement(p)["faits"][partie] = _maintenant()


def nouvelle_demande(p: dict, cle: str, eid: str, parties: list[str],
                     groupes: list[dict] | None = None) -> dict:
    """Enregistre une demande partie à Aristote. `groupes` : les phrases
    envoyées, nécessaires pour caler la traduction sur leur minutage."""
    d = {"cle": cle, "eid": eid, "parties": list(parties), "etat": "en_cours",
         "detail": "Envoyé à Aristote", "erreur": "", "demande_le": _maintenant(),
         "empreinte": empreinte(p), "groupes": groupes or []}
    enrichissement(p)["demandes"][cle] = d
    return d


def demandes_en_cours(p: dict) -> list[dict]:
    """Demandes encore chez Aristote : à reprendre au redémarrage."""
    return [d for d in enrichissement(p)["demandes"].values()
            if d.get("etat") == "en_cours" and d.get("eid")]


def echec_demande(p: dict, cle: str, message: str) -> None:
    d = enrichissement(p)["demandes"].get(cle)
    if d:
        d.update(etat="erreur", detail="", erreur=message)


def _metadonnees(version: dict) -> dict:
    m = version.get("enrichmentVersionMetadata") or {}
    if not m:
        return {}
    return {
        "titre": m.get("title") or "",
        "description": m.get("description") or "",
        "mots_cles": list(m.get("topics") or []),
        "discipline": m.get("discipline") or "",
        "type": m.get("mediaType") or "",
    }


def _questions(version: dict) -> list[dict]:
    return [{
        "question": q.get("question") or "",
        "explication": q.get("explanation") or "",
        "choix": [{"texte": c.get("optionText") or "", "correct": bool(c.get("correctAnswer"))}
                  for c in q.get("choices") or []],
    } for q in version.get("multipleChoiceQuestions") or []]


def _traduction(version: dict, groupes: list[dict], params: st.Parametres) -> list[dict]:
    """Aristote traduit élément par élément : une phrase envoyée donne une
    phrase traduite, dans le même ordre. On les redécoupe aux normes sur la
    durée de la phrase d'origine."""
    traduites = (version.get("transcript") or {}).get("translatedSentences") or []
    if not traduites:
        return []
    g = [st.SousTitre.depuis_dict(x) for x in groupes or []]
    if len(g) != len(traduites):
        g = [st.SousTitre(float(t.get("start", 0)), float(t.get("end", 0)), "") for t in traduites]
    return [s.en_dict() for s in st.decouper_traduction(g, [t.get("text") for t in traduites], params)]


def appliquer_demande(p: dict, cle: str, version: dict, params: st.Parametres) -> None:
    """Range dans le projet ce qu'une demande a produit, sans toucher aux
    autres parties. Le quiz s'AJOUTE : les questions déjà là, et surtout
    celles rédigées par l'enseignant, ne sont jamais effacées."""
    e = enrichissement(p)
    d = e["demandes"][cle]
    recu = []
    for partie in d["parties"]:
        if partie == "meta":
            m = _metadonnees(version)
            if m:
                e["metadonnees"] = m
                recu.append(partie)
        elif partie == "quiz":
            if ajouter_questions(e, _questions(version)):
                recu.append(partie)
        elif partie.startswith("trad:"):
            t = _traduction(version, d.get("groupes"), params)
            if t:
                e["traductions"][partie[5:]] = t
                recu.append(partie)
    for partie in recu:
        e["sources"][partie] = d.get("empreinte", "")
        e["faits"].pop(partie, None)      # nouveau contenu : pas encore publié
        e["versions"][partie] = e["versions"].get(partie, 0) + 1
    # Les phrases envoyées ne servaient qu'à caler la traduction : une fois le
    # résultat rangé, on les oublie (23 % du fichier pour une heure de vidéo,
    # recopiées dans chaque demande ; audit O5).
    d.update(etat="termine", detail="", erreur="", termine_le=_maintenant(),
             vide=not recu, groupes=[])


# ── Quiz : origine, questions retenues, doublons ───────────────────────────

# Deux quiz demandés sur le même texte ont donné la même question reformulée
# (« se déplacer » / « circuler », sonde du 2026-10-08) : au-delà de ce taux de
# ressemblance, la nouvelle question arrive décochée.
SEUIL_RESSEMBLANCE = 0.75


def _completer_question(q: dict) -> dict:
    """Champs apparus en 1.11.0 ; une question plus ancienne vient d'Aristote."""
    if not q.get("id"):                   # repère stable, pour fusionner avec la page
        import secrets
        q["id"] = secrets.token_hex(4)
    q.setdefault("origine", "ia")         # ia | redigee
    q.setdefault("retenue", True)         # exportée vers Moodle
    q.setdefault("nouvelle", False)       # arrivée par « Demander d'autres questions »
    q.setdefault("ressemble_a", 0)        # numéro de la question ressemblante, 0 sinon
    return q


def fusionner_page(e: dict, d: dict) -> list[str]:
    """Enregistre ce que la page de l'éditeur envoie, SANS écraser ce
    qu'Aristote a livré entre-temps. Renvoie les parties ignorées.

    - Métadonnées, traductions : la page dit sur quelle version elle a
      travaillé (`versions`) ; si une demande en a livré une plus récente, la
      saisie est ignorée et la page recharge la partie.
    - Quiz : la page envoie sa liste ET les identifiants qu'elle connaît
      (`quiz_vus`). Une question absente de sa liste mais connue d'elle a été
      supprimée ; une question qu'elle n'a jamais vue vient d'arriver : elle
      est conservée.
    """
    ignorees = []
    versions = d.get("versions") or {}
    if "metadonnees" in d:
        if versions.get("meta", 0) == e["versions"].get("meta", 0):
            e["metadonnees"] = d["metadonnees"]
        else:
            ignorees.append("meta")
    for lg, t in (d.get("traductions") or {}).items():
        cle = f"trad:{lg}"
        if versions.get(cle, 0) == e["versions"].get(cle, 0):
            e["traductions"][lg] = t
        else:
            ignorees.append(cle)
    if "quiz" in d:
        page = [_completer_question(dict(q)) for q in d["quiz"]]
        connus = set(d.get("quiz_vus") or []) | {q["id"] for q in page}
        e["quiz"] = page + [q for q in e["quiz"] if q["id"] not in connus]
    return ignorees


def question_redigee() -> dict:
    """Question écrite par l'enseignant : une bonne réponse, une mauvaise."""
    return _completer_question({"question": "", "explication": "", "origine": "redigee",
                                "choix": [{"texte": "", "correct": True},
                                          {"texte": "", "correct": False}]})


def _normaliser(texte: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", texte.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.findall(r"\w+", t))


def ajouter_questions(e: dict, nouvelles: list[dict]) -> int:
    """Ajoute des questions d'Aristote au quiz. Sur un quiz déjà commencé,
    elles portent la marque « nouvelle » ; celles qui ressemblent trop à une
    question existante arrivent décochées, avec le numéro de celle-ci.
    Renvoie le nombre de questions ajoutées."""
    import difflib
    quiz = e["quiz"]
    deja = bool(quiz)
    n = 0
    for q in nouvelles:
        if not q.get("question") or not q.get("choix"):
            continue
        q = _completer_question({**q, "origine": "ia", "nouvelle": deja})
        cible = _normaliser(q["question"])
        for i, autre in enumerate(quiz, 1):
            if difflib.SequenceMatcher(None, cible, _normaliser(autre.get("question", ""))
                                       ).ratio() >= SEUIL_RESSEMBLANCE:
                q["ressemble_a"], q["retenue"] = i, False
                break
        quiz.append(q)
        n += 1
    return n


# ── État de chaque partie, pour les cartes de l'onglet et la page ─────────

def _derniere_demande(e: dict, partie: str) -> dict | None:
    ds = [d for d in e["demandes"].values() if partie in d.get("parties", [])]
    return max(ds, key=lambda d: d.get("demande_le") or "", default=None)


def _contenu(e: dict, partie: str) -> bool:
    if partie == "meta":
        return bool((e["metadonnees"] or {}).get("titre"))
    if partie == "quiz":
        return bool(e["quiz"])
    return bool(e["traductions"].get(partie[5:]))


def etat_partie(p: dict, partie: str) -> dict:
    """État d'une partie : {etat, detail, perime}.

    etat : vide | en_cours | erreur | a_relire | relu (sous-titres) |
           pret | fait (publié sur Pod, ou exporté pour le quiz).
    perime : le contenu a été produit sur des sous-titres modifiés depuis.
    """
    if partie == "sous_titres":
        if p.get("etat") in ("envoi", "attente"):
            return {"etat": "en_cours", "detail": "", "perime": False}
        if p.get("etat") == "erreur":
            return {"etat": "erreur", "detail": p.get("erreur", ""), "perime": False}
        if not p.get("sous_titres"):
            return {"etat": "vide", "detail": "", "perime": False}
        relu = p.get("relu") or {}
        detail = ("modifiés depuis la relecture"
                  if relu and relu.get("empreinte") != empreinte(p) else "")
        etat = ("fait" if (p.get("faits") or {}).get("sous_titres")
                else "relu" if relu else "a_relire")
        return {"etat": etat, "detail": detail, "perime": False}

    e = enrichissement(p)
    d = _derniere_demande(e, partie)
    if d and d.get("etat") == "en_cours":
        return {"etat": "en_cours", "detail": d.get("detail", ""), "perime": False,
                "demande_le": d.get("demande_le", "")}
    source = e["sources"].get(partie)
    perime = bool(source) and source != empreinte(p)
    if not _contenu(e, partie):
        if d and d.get("etat") == "erreur":
            return {"etat": "erreur", "detail": d.get("erreur", ""), "perime": False}
        detail = "Aristote n'a rien proposé" if d and d.get("vide") else ""
        return {"etat": "vide", "detail": detail, "perime": False}
    detail = ""
    if partie == "quiz":
        retenues = sum(1 for q in e["quiz"] if q.get("retenue", True))
        detail = f"{len(e['quiz'])} question{'s' if len(e['quiz']) > 1 else ''}, {retenues} retenue{'s' if retenues > 1 else ''}"
    if d and d.get("etat") == "erreur":
        detail = f"dernière demande échouée : {d.get('erreur', '')}"
    etat = "fait" if e["faits"].get(partie) else "pret"
    return {"etat": etat, "detail": detail, "perime": perime}


# ── Export GIFT ────────────────────────────────────────────────────────────

def _gift(texte: str) -> str:
    """Échappe les caractères spéciaux du format GIFT de Moodle."""
    return re.sub(r"([~=#{}:\\])", r"\\\1", texte.replace("\n", " ").strip())


def _extrait(texte: str, n: int) -> str:
    """Début d'un texte, coupé sur un mot."""
    texte = " ".join(texte.split())
    if len(texte) <= n:
        return texte
    return texte[:n].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def quiz_vers_gift(quiz: list[dict], titre: str = "") -> str:
    """Quiz au format GIFT, importable dans la banque de questions Moodle.

    Seules les questions RETENUES partent. Chaque question est nommée
    d'après la vidéo et son propre début : la banque de Moodle n'affiche que
    le NOM, et « Q1, Q2 » pour chaque vidéo y devenait illisible (essai
    d'import du 2026-10-08)."""
    blocs = []
    if titre:
        blocs.append(f"$CATEGORY: $course$/{titre.replace('/', '-')}\n")
    prefixe = _extrait(titre, 40) if titre else "Question"
    n = 0
    for q in quiz:
        if not q.get("question") or not q.get("choix") or not q.get("retenue", True):
            continue
        n += 1
        nom = f"{prefixe} {n:02d}, {_extrait(q['question'], 50)}"
        lignes = [f"::{_gift(nom)}:: {_gift(q['question'])} {{"]
        for c in q["choix"]:
            if not (c.get("texte") or "").strip():
                continue            # réponse laissée vide : Moodle refuserait l'import
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
        # Titre de la VIDÉO, et non celui proposé par Aristote : la catégorie
        # Moodle et le nom des questions restent les mêmes d'un export à l'autre.
        titre = (p.get("pod") or {}).get("titre") or base
        ecrire(f"{base}.quiz-moodle.gift.txt", quiz_vers_gift(e["quiz"], titre))
        if any(q.get("retenue", True) for q in e["quiz"]):
            marquer_fait(p, "quiz")
    p["exports"] = sorted(deja | set(ecrits))
    return ecrits
