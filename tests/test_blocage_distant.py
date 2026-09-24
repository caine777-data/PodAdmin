"""Blocage à distance — interrupteur manuel, INDÉPENDANT de la mise à jour.

Modèle repris tel quel d'EnqueteGen (voir BLOCAGE.md) : invisible tant que rien
n'est bloqué, seule une réponse RÉSEAU RÉELLE change l'état, et ce qui est
confirmé une fois est mémorisé localement pour résister à une coupure réseau
volontaire — voir test_mise_a_jour.py::TestVerrouLocalDuBlocage pour le même
principe appliqué à la mise à jour obligatoire.
"""
import os
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)


def _boutons(widget):
    """Tous les CTkButton descendants de `widget`, quelle que soit la profondeur."""
    import customtkinter as ctk
    trouves = []
    for enfant in widget.winfo_children():
        if isinstance(enfant, ctk.CTkButton):
            trouves.append(enfant)
        trouves.extend(_boutons(enfant))
    return trouves


@pytest.fixture(scope="module")
def app():
    """Instance partagée, réseau neutralisé : ni connexion automatique, ni
    vérification de mise à jour ou de blocage réelle (voir test_mise_a_jour.py)."""
    import tempfile
    os.environ.setdefault("HOME", tempfile.mkdtemp())
    try:
        import app as module_app
    except Exception as e:
        pytest.skip(f"interface indisponible : {e}")
    for nom in ("_auto_connect", "_verifier_maj", "_surveiller_blocage"):
        setattr(module_app.App, nom, lambda s, *a, **k: None)
    a = module_app.App()
    a.update()
    yield a
    try:
        a.destroy()
    except Exception:
        pass


class TestLectureEtatDistant:
    """`maj.etat_blocage` : jamais bloquant, jamais ambigu.

    `_telecharger_json` (réseau réel : requests puis urllib) est mocké — ce
    n'est pas sa responsabilité ici, elle est déjà couverte pour
    `recuperer_info` par TestVerification::test_un_reseau_absent_ne_bloque_rien
    dans test_mise_a_jour.py. Ce qui compte ici est la conversion du contenu
    JSON en True/False/None."""

    @staticmethod
    def _simuler(monkeypatch, donnees):
        import maj
        monkeypatch.setattr(maj, "_telecharger_json", lambda *a, **k: donnees)
        return maj.etat_blocage("https://x.invalid/etat.json")

    def test_bloque_et_debloque(self, monkeypatch):
        assert self._simuler(monkeypatch, {"bloque": True}) is True
        assert self._simuler(monkeypatch, {"bloque": False}) is False

    def test_aucune_reponse_exploitable_ne_bloque_ni_ne_debloque(self, monkeypatch):
        """⚠️ Un None doit rester un None : jamais interprété comme un
        déblocage implicite (voir la mise en garde dans maj.etat_blocage)."""
        assert self._simuler(monkeypatch, None) is None                # réseau coupé
        assert self._simuler(monkeypatch, {}) is None                  # champ absent
        assert self._simuler(monkeypatch, {"bloque": "oui"}) is None   # pas un booléen
        assert self._simuler(monkeypatch, {"bloque": 1}) is None       # pas un booléen

    def test_reseau_reellement_indisponible(self):
        """Bout-en-bout, sans mock : une adresse injoignable ne doit jamais
        lever d'exception ni renvoyer autre chose que None."""
        import maj
        assert maj.etat_blocage("https://exemple.invalid/etat.json", timeout=1) is None
        assert maj.etat_blocage("") is None


class TestVerrouLocalDuBlocageDistant:
    """Même modèle que la mise à jour obligatoire (config.py) : seule une
    réponse réseau réelle change l'état mémorisé, qui tient hors ligne."""

    @staticmethod
    def _config_isolee(tmp_path, monkeypatch):
        """Redirige config.CONFIG_PATH vers un fichier jetable, pour ne
        jamais toucher au vrai fichier de configuration de la machine qui
        exécute ces tests."""
        import config as cfg
        chemin = tmp_path / "config_test.json"
        monkeypatch.setattr(cfg, "CONFIG_PATH", str(chemin))
        return cfg

    def test_rien_au_depart(self, tmp_path, monkeypatch):
        cfg = self._config_isolee(tmp_path, monkeypatch)
        assert cfg.blocage_distant_actif() is False

    def test_enregistrement_puis_lecture(self, tmp_path, monkeypatch):
        cfg = self._config_isolee(tmp_path, monkeypatch)
        cfg.enregistrer_blocage_distant(True)
        assert cfg.blocage_distant_actif() is True
        cfg.enregistrer_blocage_distant(False)
        assert cfg.blocage_distant_actif() is False

    def test_le_verrou_survit_a_un_echec_reseau_simule(self, tmp_path, monkeypatch):
        """C'est tout le sens du mécanisme : le verrou doit continuer de
        s'appliquer même quand `maj.etat_blocage` échoue (réseau coupé)."""
        cfg = self._config_isolee(tmp_path, monkeypatch)
        cfg.enregistrer_blocage_distant(True)
        import maj
        monkeypatch.setattr(maj, "etat_blocage", lambda *a, **k: None)
        assert cfg.blocage_distant_actif() is True


class TestApplicationDuBlocage:
    """Comportement observable dans l'application : voile plein écran, seule
    issue « Quitter », rien tant que le serveur ne répond pas."""

    @staticmethod
    def _config_isolee(tmp_path, monkeypatch):
        import config as cfg
        chemin = tmp_path / "config_test.json"
        monkeypatch.setattr(cfg, "CONFIG_PATH", str(chemin))
        return cfg

    def test_rien_a_l_ecran_par_defaut(self, app):
        assert app._voile_blocage is None

    def test_une_panne_reseau_ne_change_rien(self, app, tmp_path, monkeypatch):
        self._config_isolee(tmp_path, monkeypatch)
        app._appliquer_blocage(None)
        app.update()
        assert app._voile_blocage is None

    def test_blocage_puis_deblocage(self, app, tmp_path, monkeypatch):
        cfg = self._config_isolee(tmp_path, monkeypatch)
        try:
            app._appliquer_blocage(True)
            app.update()
            assert app._voile_blocage is not None
            assert cfg.blocage_distant_actif() is True

            app._appliquer_blocage(None)          # une panne ne débloque pas
            app.update()
            assert app._voile_blocage is not None

            app._appliquer_blocage(False)
            app.update()
            assert app._voile_blocage is None
            assert cfg.blocage_distant_actif() is False
        finally:
            app._appliquer_blocage(False)
            app.update()

    def test_le_bouton_quitter_est_present(self, app, tmp_path, monkeypatch):
        self._config_isolee(tmp_path, monkeypatch)
        try:
            app._appliquer_blocage(True)
            app.update()
            boutons = _boutons(app._voile_blocage)
            assert any(b.cget("text") == "Quitter" for b in boutons), (
                "aucun bouton « Quitter » dans le voile de blocage : la "
                "seule issue toujours garantie serait absente")
        finally:
            app._appliquer_blocage(False)
            app.update()

    def test_les_fenetres_secondaires_sont_fermees(self, app, tmp_path, monkeypatch):
        """Une fenêtre (Réglages, À propos…) restée ouverte par-dessus le
        voile permettrait de continuer à s'en servir malgré le blocage."""
        import customtkinter as ctk
        self._config_isolee(tmp_path, monkeypatch)
        fen = ctk.CTkToplevel(app)
        try:
            app._appliquer_blocage(True)
            app.update()
            assert not fen.winfo_exists(), (
                "une fenêtre secondaire est restée ouverte pendant le blocage")
        finally:
            app._appliquer_blocage(False)
            app.update()
