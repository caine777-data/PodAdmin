"""Intégration de SousTitreur dans PodAdmin, étape 1 : modules sans interface.

Ces tests ne touchent ni au réseau ni au disque de l'utilisateur. Ils vérifient
que les modules copiés dans `enrichissement/` vivent bien dans PodAdmin : ils
s'importent, retrouvent leurs ressources, et ne dépendent d'aucun fichier
resté dans le dossier de SousTitreur.
"""

import ast
import importlib
import os
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

MODULES = ["aristote_api", "sous_titres", "projet", "editeur", "journal", "reglages"]
DOSSIER_PAQUET = os.path.join(RACINE, "enrichissement")

# Seuls modules de PodAdmin qu'un module du paquet peut importer en absolu.
# `config`, `charte`, `media` sont ceux de SousTitreur : les importer ici
# chargerait en silence le `config.py` de PodAdmin, sans les mêmes noms.
IMPORTS_POD_ADMIN_PERMIS = {"__version__", "pod_api"}
MODULES_SOUSTITREUR = {
    "config",
    "charte",
    "media",
    "app",
    "projet",
    "sous_titres",
    "editeur",
    "journal",
    "aristote_api",
}


@pytest.mark.parametrize("nom", MODULES)
def test_le_module_s_importe_depuis_podadmin(nom):
    importlib.import_module(f"enrichissement.{nom}")


def test_les_donnees_restent_dans_le_dossier_de_soustitreur():
    """Les projets commencés dans SousTitreur doivent se retrouver tels quels."""
    from enrichissement import journal, projet, reglages

    attendu = os.path.join(os.path.expanduser("~"), ".soustitreur")
    assert attendu == reglages.DOSSIER
    assert os.path.join(attendu, "projets") == projet.DOSSIER_PROJETS
    assert os.path.dirname(journal.CHEMIN) == attendu


@pytest.mark.parametrize("ressource", ["assets/editeur.html", "assets/logo_ut.png"])
def test_l_editeur_trouve_ses_ressources(ressource):
    """L'éditeur vit dans un sous-dossier : il doit chercher `assets/` à la
    racine de PodAdmin, et non à côté de son propre fichier."""
    from enrichissement import editeur

    assert os.path.isfile(editeur._ressource(ressource))


@pytest.mark.parametrize("nom", MODULES)
def test_aucune_dependance_a_un_fichier_reste_dans_soustitreur(nom):
    arbre = ast.parse(open(os.path.join(DOSSIER_PAQUET, f"{nom}.py"), encoding="utf-8").read())
    fautifs = []
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            noms = [a.name.split(".")[0] for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            noms = [n.module.split(".")[0]]
        else:
            continue
        fautifs += [
            m for m in noms if m in MODULES_SOUSTITREUR and m not in IMPORTS_POD_ADMIN_PERMIS
        ]
    assert not fautifs, f"{nom}.py importe en absolu : {fautifs} (utiliser « from . import »)"


class TestEnregistrementSousWindows:
    """Remplacer un projet pendant qu'un autre fil le lit échoue sous Windows
    (« Accès refusé ») : l'écriture réessaie brièvement au lieu d'échouer."""

    def _projet(self, tmp_path, monkeypatch):
        from enrichissement import projet

        monkeypatch.setattr(projet, "DOSSIER_PROJETS", str(tmp_path))
        p = projet.nouveau("cours.mp4", "fr")
        return projet, p

    def test_reussit_apres_des_refus_passagers(self, tmp_path, monkeypatch):
        projet, p = self._projet(tmp_path, monkeypatch)
        vrai_replace, refus = os.replace, [2]

        def replace_capricieux(a, b):
            if refus[0]:
                refus[0] -= 1
                raise PermissionError("Accès refusé")
            vrai_replace(a, b)

        monkeypatch.setattr(projet.os, "replace", replace_capricieux)
        projet.enregistrer(p)
        assert projet.charger(p["id"])["nom"] == "cours.mp4"

    def test_refus_persistant_signale(self, tmp_path, monkeypatch):
        projet, p = self._projet(tmp_path, monkeypatch)

        def toujours_refuse(a, b):
            raise PermissionError("Accès refusé")

        monkeypatch.setattr(projet.os, "replace", toujours_refuse)
        monkeypatch.setattr("time.sleep", lambda s: None)
        with pytest.raises(PermissionError):
            projet.enregistrer(p)


@pytest.mark.parametrize(
    "fichier",
    [f"enrichissement/{m}.py" for m in MODULES]
    + ["enrichissement/__init__.py", "assets/editeur.html"],
)
def test_aucune_adresse_personnelle(fichier):
    """Ces fichiers sont livrés dans l'exécutable, publié sur un dépôt public."""
    assert "gmail" not in open(os.path.join(RACINE, fichier), encoding="utf-8").read().lower()
