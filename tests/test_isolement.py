"""Les tests ne doivent jamais toucher au profil réel de l'utilisateur
(voir conftest.py) : ni ses réglages, ni son Journal, ni ses projets, ni son
coffre-fort, ni sa connexion à l'instance."""
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from conftest import DOSSIER_PERSONNEL_REEL, DOSSIER_PERSONNEL_TESTS  # noqa: E402


def test_dossier_personnel_temporaire():
    assert os.path.expanduser("~") == DOSSIER_PERSONNEL_TESTS != DOSSIER_PERSONNEL_REEL


def test_chemins_de_l_application_hors_du_profil_reel():
    import config as cfg
    from enrichissement import journal, projet, reglages
    for chemin in (cfg.CONFIG_PATH, reglages.DOSSIER, projet.DOSSIER_PROJETS, journal.CHEMIN):
        assert chemin.startswith(DOSSIER_PERSONNEL_TESTS), chemin


def test_coffre_fort_vide_donc_aucune_connexion():
    """Sans jeton, `App.__init__` ne lance pas la connexion automatique."""
    import keyring

    import config as cfg
    assert type(keyring.get_keyring()).__module__ == "keyring.backends.null"
    assert cfg.load_token() == ""
