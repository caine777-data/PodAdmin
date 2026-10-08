#!/usr/bin/env python3
"""
verifier_aristote_demandes.py — Sonde : Aristote accepte-t-il des demandes SÉPARÉES ?
====================================================================================
Refonte de l'onglet « Enrichissement IA » (1.11.0) : trois parties distinctes
(sous-titres et traduction, métadonnées, quiz), et UNE demande Aristote par
partie au lieu d'une demande groupée. Avant de développer, il faut savoir :

  A. si une demande de TRADUCTION SEULE (ni métadonnées ni quiz) aboutit ;
  B. si une demande de QUIZ SEUL aboutit ;
  C. si une demande de MÉTADONNÉES SEULES aboutit ;
  D. si deux demandes envoyées EN MÊME TEMPS (A et B) se gênent ;
  E. ce que chaque réponse contient : rien de plus que ce qui a été demandé ?

SÉRIE 2 (option --serie2), décidée après la première :

  D. NOTES DE COURS seules (generateNotes, jamais utilisé jusqu'ici) :
     quelle forme, quelle longueur ?
  E. un DEUXIÈME QUIZ sur le même texte : des questions nouvelles, ou la
     même question reformulée ? (bouton « Demander d'autres questions »)

    python verifier_aristote_demandes.py --serie2

La sonde envoie trois fois le même petit texte français (un VTT de dix
sous-titres : Aristote saute alors la transcription), suit les trois demandes
jusqu'au bout, puis résume. Les réponses brutes sont enregistrées dans
`sonde_aristote_demandes.json` (aucun secret dedans), pour analyse.

CE QUE LA SONDE CRÉE : trois enrichissements chez Aristote, à partir d'un
texte de quelques lignes. Elle propose de les supprimer à la fin.

À lancer depuis le dossier de PodAdmin (elle reprend ses identifiants
Aristote : ceux du coffre-fort s'il y en a, sinon ceux fournis) :

    python verifier_aristote_demandes.py
"""

__author__ = "Cédric MONNA"
__version__ = "1.1.0"

import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as cfg                                            # noqa: E402
from enrichissement import reglages                            # noqa: E402
from enrichissement.aristote_api import AristoteAPI, AristoteErreur  # noqa: E402

PHRASES = [
    "Bonjour à tous et bienvenue dans cette conférence.",
    "Nous allons parler des premières villes du Néolithique.",
    "Vers 7000 avant notre ère, des villages deviennent de véritables agglomérations.",
    "Çatal Höyük, en Anatolie, compte alors plusieurs milliers d'habitants.",
    "Les maisons sont accolées et l'on circule par les toits.",
    "L'agriculture et l'élevage permettent de nourrir une population plus dense.",
    "Les archéologues y ont trouvé des peintures murales et des figurines.",
    "Ces découvertes renseignent sur les croyances et la vie quotidienne.",
    "La question reste ouverte : peut-on déjà parler de ville ?",
    "Merci de votre attention, nous verrons la suite la semaine prochaine.",
]


def _horodatage(s: float) -> str:
    return f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:06.3f}"


def vtt() -> str:
    lignes = ["WEBVTT", ""]
    for i, p in enumerate(PHRASES):
        lignes += [f"{_horodatage(i * 6.0)} --> {_horodatage(i * 6.0 + 5.5)}", p, ""]
    return "\n".join(lignes)


RIEN = {"generateMetadata": False, "generateQuiz": False, "generateNotes": False}
SERIE_1 = {
    "A_traduction_seule": {**RIEN, "translateTo": "en"},
    "B_quiz_seul":        {**RIEN, "generateQuiz": True},
    "C_metadonnees":      {**RIEN, "generateMetadata": True,
                           "disciplines": ["Histoire", "Archéologie", "Autres"],
                           "mediaTypes": ["Cours", "Conférence"]},
}
SERIE_2 = {
    "D_notes_seules": {**RIEN, "generateNotes": True},
    "E_quiz_bis":     {**RIEN, "generateQuiz": True},
}
SERIE2 = "--serie2" in sys.argv
DEMANDES = SERIE_2 if SERIE2 else SERIE_1
FICHIER = "sonde_aristote_demandes_2.json" if SERIE2 else "sonde_aristote_demandes.json"


def envoyer_vtt(client: AristoteAPI, texte: str, nom: str, parametres: dict) -> str:
    """Même envoi qu'enrichir_sous_titres, mais avec des paramètres libres
    (generateNotes n'y est pas prévu)."""
    fd, chemin = tempfile.mkstemp(suffix=".vtt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(texte)
        return client.envoyer_fichier(chemin, "fr", nom_original=f"sonde_{nom}.vtt",
                                      parametres_sup=parametres)
    finally:
        try:
            os.remove(chemin)
        except OSError:
            pass


def main() -> int:
    cid, secret, origine = cfg.load_aristote_credentials()
    if not (cid and secret):
        print("Identifiants Aristote introuvables.")
        return 1
    client = AristoteAPI(cid, secret, reglages.url_aristote())
    print(f"Aristote : {reglages.url_aristote()} (identifiants {origine})")
    try:
        print("Connexion :", client.tester())
        print("Langues proposées :", [(l.get("code"), l.get("name")) for l in client.langues()])
    except AristoteErreur as e:
        print("✖", e)
        return 1

    print(f"\n{len(DEMANDES)} demandes vont être créées chez Aristote (texte de 10 sous-titres) :",
          ", ".join(DEMANDES))
    if input("Continuer ? (oui / non) : ").strip().lower() != "oui":
        return 0

    texte = vtt()
    ids, erreurs, resultats = {}, {}, {}

    def envoyer(nom):
        try:
            ids[nom] = envoyer_vtt(client, texte, nom, DEMANDES[nom])
        except Exception as e:                                  # noqa: BLE001
            erreurs[nom] = f"{type(e).__name__} : {e}"

    fils = [threading.Thread(target=envoyer, args=(n,)) for n in DEMANDES]
    for f in fils:
        f.start()
    for f in fils:
        f.join()
    for nom in DEMANDES:
        print(f"  {nom} : {'ID ' + ids[nom] if nom in ids else '✖ refusée : ' + erreurs[nom]}")

    debut = time.time()

    def suivre(nom):
        try:
            client.attendre(ids[nom], intervalle=10, delai_max=45 * 60, jusqu_au_bout=True,
                            rappel=lambda s, _d: print(f"  [{int(time.time() - debut):4d} s] {nom} : {s}"))
            resultats[nom] = {"duree_s": round(time.time() - debut),
                              "version": client.version_finale(ids[nom])}
        except Exception as e:                                  # noqa: BLE001
            erreurs[nom] = f"{type(e).__name__} : {e}"

    print("\nSuivi (peut prendre plusieurs minutes, Ctrl+C pour abandonner) :")
    fils = [threading.Thread(target=suivre, args=(n,)) for n in ids]
    for f in fils:
        f.start()
    for f in fils:
        f.join()

    print("\n══════ RÉSUMÉ ══════")
    for nom in DEMANDES:
        if nom not in resultats:
            print(f"{nom} : ✖ {erreurs.get(nom, 'pas de résultat')}")
            continue
        v = resultats[nom]["version"]
        tr = v.get("transcript") or {}
        meta = v.get("enrichmentVersionMetadata") or {}
        print(f"{nom} : terminé en {resultats[nom]['duree_s']} s")
        print(f"    traduction : {len(tr.get('translatedSentences') or [])} phrase(s) "
              f"pour {len(PHRASES)} envoyées")
        print(f"    quiz       : {len(v.get('multipleChoiceQuestions') or [])} question(s)")
        print(f"    métadonnées: titre « {meta.get('title') or ''} », discipline "
              f"« {meta.get('discipline') or ''} », type « {meta.get('mediaType') or ''} »")
        print(f"    clés de la réponse : {sorted(v)}")
        notes = v.get("notes")
        if notes:
            texte_notes = notes if isinstance(notes, str) else json.dumps(notes, ensure_ascii=False)
            print(f"    notes      : {type(notes).__name__}, {len(texte_notes)} caractères")
            print("    ┌" + "─" * 60)
            for ligne in texte_notes[:1500].splitlines():
                print("    │ " + ligne)
            print("    └" + "─" * 60)
        for q in v.get("multipleChoiceQuestions") or []:
            print(f"    question   : {q.get('question')}")

    # E : la question du deuxième quiz est-elle nouvelle ?
    precedent = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sonde_aristote_demandes.json")
    if SERIE2 and "E_quiz_bis" in resultats and os.path.exists(precedent):
        with open(precedent, encoding="utf-8") as f:
            b = json.load(f).get("resultats", {}).get("B_quiz_seul", {}).get("version", {})
        print("\nQuiz de la série 1 (B), pour comparaison :")
        for q in b.get("multipleChoiceQuestions") or []:
            print(f"    question   : {q.get('question')}")

    chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), FICHIER)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump({"ids": ids, "erreurs": erreurs, "resultats": resultats}, f,
                  ensure_ascii=False, indent=2)
    print(f"\nRéponses brutes : {chemin}")

    if ids and input("\nSupprimer les enrichissements créés chez Aristote ? (oui / non) : ").strip().lower() == "oui":
        for nom, eid in ids.items():
            try:
                client.supprimer(eid)
                print(f"  {nom} : supprimé")
            except Exception as e:                              # noqa: BLE001
                print(f"  {nom} : suppression impossible ({e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
