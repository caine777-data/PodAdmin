"""
maj.py — Vérification de la disponibilité d'une nouvelle version
================================================================
L'application interroge, au démarrage, un petit fichier `version.json` hébergé
sur un dépôt GitHub PUBLIC. Si une version plus récente existe, elle affiche un
bandeau discret avec un lien de téléchargement.

PRINCIPES
---------
• **Jamais bloquant.** Pas de réseau, fichier absent, serveur injoignable,
  contenu illisible : la vérification échoue en silence et l'application démarre
  normalement. Une vérification qui empêche de travailler serait pire que pas de
  vérification du tout.
• **Aucun secret.** Le dépôt interrogé est public et ne contient que le fichier
  de version et les exécutables. Le dépôt de code, lui, reste privé (il contient
  le mot de passe du compte véhicule).
• **Informer, pas contraindre.** Même une version très ancienne n'empêche pas
  d'utiliser l'application : le ton du message se durcit, mais rien n'est jamais
  bloqué. Un utilisateur empêché de travailler à un mauvais moment appellerait
  le support — à juste titre.

FORMAT ATTENDU (version.json)
-----------------------------
```json
{
  "version": "1.1.0",
  "url": "https://github.com/VOTRE-COMPTE/podadmin-releases/releases/latest",
  "notes": "Correction de l'affichage des groupes d'accès.",
  "version_minimale": "1.0.0"
}
```
Seul `version` est obligatoire.
`version_minimale` désigne la version en dessous de laquelle l'application est
considérée comme périmée (par exemple après une rotation du mot de passe du
compte véhicule, qui rend les anciennes versions incapables de téléverser les
gros fichiers). Le message devient alors insistant — sans blocage.
"""

__author__ = "Cédric MONNA"

import json
import urllib.request


def comparer_versions(a: str, b: str) -> int:
    """Compare deux numéros de version. Renvoie -1, 0 ou 1 (a<b, a==b, a>b).

    ATTENTION au piège : comparer des CHAÎNES donnerait "1.10.0" < "1.9.0",
    puisque le caractère « 1 » précède « 9 ». On compare donc les nombres
    composante par composante.

    Les suffixes non numériques (« 1.2.0-beta ») sont ignorés, et les longueurs
    différentes sont complétées par des zéros (« 1.2 » équivaut à « 1.2.0 »).
    """
    def morceaux(v: str) -> list:
        out = []
        for bloc in str(v or "0").strip().split("."):
            chiffres = ""
            for c in bloc:
                if c.isdigit():
                    chiffres += c
                else:
                    break            # on s'arrête au premier caractère non numérique
            out.append(int(chiffres) if chiffres else 0)
        return out

    ma, mb = morceaux(a), morceaux(b)
    taille = max(len(ma), len(mb))
    ma += [0] * (taille - len(ma))       # « 1.2 » == « 1.2.0 »
    mb += [0] * (taille - len(mb))
    for x, y in zip(ma, mb):
        if x != y:
            return -1 if x < y else 1
    return 0


def recuperer_info(url: str, timeout: float = 5.0) -> dict | None:
    """Télécharge et analyse le fichier de version. Renvoie None en cas d'échec.

    Toute erreur est absorbée : réseau coupé, adresse fausse, dépôt supprimé,
    JSON malformé… La vérification est un confort, pas une dépendance.
    """
    if not url:
        return None                      # vérification désactivée
    try:
        requete = urllib.request.Request(
            url, headers={"User-Agent": "PodAdmin-MAJ", "Accept": "application/json"})
        with urllib.request.urlopen(requete, timeout=timeout) as reponse:
            if getattr(reponse, "status", 200) != 200:
                return None
            donnees = json.loads(reponse.read().decode("utf-8", "replace"))
        if not isinstance(donnees, dict) or not donnees.get("version"):
            return None                  # fichier présent mais inexploitable
        return donnees
    except Exception:
        return None                      # jamais bloquant


def etat_mise_a_jour(version_actuelle: str, url: str, timeout: float = 5.0) -> dict | None:
    """Compare la version installée à celle publiée.

    Renvoie None si tout va bien (à jour, ou vérification impossible), sinon un
    dictionnaire :
        {"version": "1.1.0", "url": "...", "notes": "...", "urgent": False}

    `urgent` est vrai lorsque la version installée est antérieure à la
    `version_minimale` annoncée : le bandeau est alors plus visible, mais
    l'application reste utilisable.
    """
    infos = recuperer_info(url, timeout)
    if not infos:
        return None
    derniere = str(infos.get("version", "")).strip()
    if comparer_versions(version_actuelle, derniere) >= 0:
        return None                      # déjà à jour (ou en avance : build local)

    minimale = str(infos.get("version_minimale", "") or "").strip()
    urgent = bool(minimale) and comparer_versions(version_actuelle, minimale) < 0

    return {
        "version": derniere,
        "url": str(infos.get("url", "") or ""),
        "notes": str(infos.get("notes", "") or ""),
        "urgent": urgent,
    }
