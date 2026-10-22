"""Intégration de SousTitreur, étape 3 : identifiants et adresse d'Aristote.

Décision de Cédric : identifiants EMBARQUÉS (config.py), surcharge possible dans
le coffre-fort, réglage depuis Configuration. Aucun test ne touche au vrai
coffre-fort ni au vrai dossier personnel.
"""

import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)


@pytest.fixture
def coffre(monkeypatch):
    """Faux coffre-fort : remplace les accès aux secrets de config.py."""
    import config as cfg

    stock = {}
    monkeypatch.setattr(cfg, "_load_secret", lambda cle, suffixe: stock.get(cle, ""))

    def ranger(cle, suffixe, valeur):
        stock[cle] = valeur
        return "keyring"

    monkeypatch.setattr(cfg, "_save_secret", ranger)
    monkeypatch.setattr(cfg, "_clear_secret", lambda cle, suffixe: stock.pop(cle, None))
    return stock


class TestIdentifiants:
    def test_embarques_par_defaut(self, coffre):
        import config as cfg

        cid, secret, origine = cfg.load_aristote_credentials()
        assert (cid, secret, origine) == (
            cfg.ARISTOTE_CLIENT_ID_EMBARQUE,
            cfg.ARISTOTE_CLIENT_SECRET_EMBARQUE,
            "embarques",
        )
        assert cid and secret, "les identifiants embarqués sont vides"

    def test_coffre_prioritaire(self, coffre):
        import config as cfg

        assert cfg.save_aristote_credentials(" mon-id ", " mon-secret ") == "keyring"
        assert cfg.load_aristote_credentials() == ("mon-id", "mon-secret", "coffre")

    def test_ressaisir_les_embarques_vide_le_coffre(self, coffre):
        """Une copie des embarqués restée au coffre masquerait, après une
        rotation, le nouveau secret embarqué."""
        import config as cfg

        cfg.save_aristote_credentials("mon-id", "mon-secret")
        assert (
            cfg.save_aristote_credentials(
                cfg.ARISTOTE_CLIENT_ID_EMBARQUE, cfg.ARISTOTE_CLIENT_SECRET_EMBARQUE
            )
            == "embarques"
        )
        assert not coffre
        assert cfg.load_aristote_credentials()[2] == "embarques"

    def test_effacer_revient_aux_embarques(self, coffre):
        import config as cfg

        cfg.save_aristote_credentials("mon-id", "mon-secret")
        cfg.clear_aristote_credentials()
        assert cfg.load_aristote_credentials()[2] == "embarques"

    def test_le_secret_n_existe_que_dans_config(self):
        """Tous les secrets embarqués au même endroit : config.py, à côté de
        DEPOT. Une copie ailleurs échapperait à la prochaine rotation."""
        import config as cfg

        secret = cfg.ARISTOTE_CLIENT_SECRET_EMBARQUE
        fautifs = []
        for dossier, _d, fichiers in os.walk(RACINE):
            if any(p in dossier for p in (".git", "__pycache__", os.sep + "tests")):
                continue
            for f in fichiers:
                if (
                    f.endswith((".py", ".html", ".md", ".txt", ".yml", ".json"))
                    and f != "config.py"
                ):
                    chemin = os.path.join(dossier, f)
                    if secret in open(chemin, encoding="utf-8", errors="ignore").read():
                        fautifs.append(os.path.relpath(chemin, RACINE))
        assert not fautifs, f"secret Aristote recopié dans : {fautifs}"


class TestPreferences:
    @pytest.fixture
    def dossier(self, tmp_path, monkeypatch):
        from enrichissement import reglages

        monkeypatch.setattr(reglages, "DOSSIER", str(tmp_path))
        monkeypatch.setattr(reglages, "CONFIG_PATH", str(tmp_path / "config.json"))
        return reglages

    def test_valeurs_par_defaut_sans_fichier(self, dossier):
        p = dossier.charger()
        assert p["url_aristote"] == "https://stt.ilaas.fr/api"
        assert "langue" not in p and "extraire_audio" not in p, (
            "réglages abandonnés : français imposé, pas de ffmpeg"
        )

    def test_aller_retour_et_preferences_de_soustitreur_conservees(self, dossier, tmp_path):
        """Un config.json écrit par SousTitreur se relit sans perte."""
        (tmp_path / "config.json").write_text(
            json.dumps({"url_aristote": "https://autre.exemple/api/", "theme": "dark"}),
            encoding="utf-8",
        )
        p = dossier.charger()
        assert p["theme"] == "dark" and dossier.url_aristote() == "https://autre.exemple/api"
        p["formats"] = ["vtt", "srt"]
        dossier.enregistrer(p)
        assert dossier.charger()["formats"] == ["vtt", "srt"]
        assert not (tmp_path / "config.json.tmp").exists()

    def test_fichier_illisible_ne_bloque_pas(self, dossier, tmp_path):
        (tmp_path / "config.json").write_text("{pas du json", encoding="utf-8")
        assert dossier.url_aristote() == "https://stt.ilaas.fr/api"


class TestTestDeConnexion:
    def _lancer(self, monkeypatch, comportement):
        import app as A

        monkeypatch.setattr(
            A, "AristoteAPI", lambda cid, secret, url: SimpleNamespace(tester=comportement)
        )
        etiquette = SimpleNamespace(
            winfo_exists=lambda: True, recu={}, configure=lambda **k: etiquette.recu.update(k)
        )
        bouton = SimpleNamespace(
            etat=None, configure=lambda **k: setattr(bouton, "etat", k["state"])
        )
        journal = []
        faux = SimpleNamespace(_ui=lambda fn, *a, **k: fn(*a, **k), _log=journal.append)
        A.App._aristote_tester(faux, "https://x/api", "id", "secret", etiquette, bouton)
        return etiquette.recu, bouton.etat, journal

    def test_succes(self, monkeypatch):
        import app as A

        recu, etat, _j = self._lancer(monkeypatch, lambda: "Connexion réussie.")
        assert recu == {"text": "Connexion réussie.", "text_color": A.T_SUCCES} and etat == "normal"

    def test_refus_d_aristote_affiche_tel_quel(self, monkeypatch):
        import app as A

        def refus():
            raise A.AristoteErreur("Connexion refusée par Aristote (401). Vérifiez…")

        recu, etat, journal = self._lancer(monkeypatch, refus)
        assert recu["text"].startswith("Connexion refusée") and etat == "normal"
        assert not journal

    def test_panne_reseau_traduite_et_journalisee(self, monkeypatch):
        import app as A

        def panne():
            raise ConnectionError("Max retries exceeded with url")

        recu, _e, journal = self._lancer(monkeypatch, panne)
        assert recu["text"] == A.message_utilisateur(ConnectionError("Max retries exceeded"))
        assert journal and "ConnectionError" in journal[0]


SCENARIO_FENETRE = r"""
import json, os, sys, tempfile
sys.path.insert(0, RACINE)
import config as cfg
stock = {}
cfg._load_secret = lambda cle, s: stock.get(cle, "")
cfg._save_secret = lambda cle, s, v: stock.__setitem__(cle, v) or "keyring"
cfg._clear_secret = lambda cle, s: stock.pop(cle, None)
import customtkinter as ctk
import app as A
for nom in ("_auto_connect", "_verifier_maj", "_surveiller_blocage"):
    setattr(A.App, nom, lambda s, *a, **k: None)
from enrichissement import reglages
a = A.App(); a.update()

def ouvrir():
    avant = set(a.winfo_children())
    a._aristote_ouvrir(); a.update()
    fen = [w for w in a.winfo_children() if w not in avant and isinstance(w, ctk.CTkToplevel)][0]
    entrees = [w for w in fen.winfo_children()[0].winfo_children() if isinstance(w, ctk.CTkEntry)]
    boutons = {b.cget("text"): b for b in fen.winfo_children()[2].winfo_children()}
    resultat = fen.winfo_children()[1]
    return fen, entrees, boutons, resultat

fen, (url, ident, secret), b, res = ouvrir()
assert secret.get() == "" and ident.get() == "", "secret embarqué affiché"
assert fen.bouton_defaut is b["Enregistrer"]
url.delete(0, "end"); url.insert(0, "http://stt.ilaas.fr/api")
b["Enregistrer"].invoke(); a.update()
assert "https://" in res.cget("text") and fen.winfo_exists(), "adresse en clair acceptée"
url.delete(0, "end"); url.insert(0, "https://autre.exemple/api")
ident.insert(0, "seul-id")
b["Enregistrer"].invoke(); a.update()
assert "ET le secret" in res.cget("text") and not stock
secret.insert(0, "mon-secret")
b["Enregistrer"].invoke(); a.update()
assert not fen.winfo_exists()
assert stock == {"aristote_client_id": "seul-id", "aristote_client_secret": "mon-secret"}
assert reglages.url_aristote() == "https://autre.exemple/api"
assert "personnalisés" in a.aristote_etat_lbl.cget("text")
fen, (url, ident, secret), b, res = ouvrir()
assert ident.get() == "seul-id" and secret.get() == "", "secret personnalisé réaffiché"
b["Revenir aux réglages fournis"].invoke(); a.update()
assert not stock and reglages.url_aristote() == "https://stt.ilaas.fr/api"
assert "fournis avec l'application" in a.aristote_etat_lbl.cget("text")
print("SCENARIO OK")
a.destroy()
"""


def test_fenetre_aristote_de_bout_en_bout(tmp_path):
    """Vraie fenêtre, dans un processus séparé : une seule instance Tk, un
    dossier personnel temporaire, un faux coffre-fort."""
    script = tmp_path / "scenario.py"
    script.write_text(f"RACINE = {RACINE!r}\n" + SCENARIO_FENETRE, encoding="utf-8")
    env = {**os.environ, "USERPROFILE": str(tmp_path), "HOME": str(tmp_path), "PYTHONUTF8": "1"}
    r = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=RACINE,
    )
    assert r.returncode == 0 and "SCENARIO OK" in r.stdout, r.stdout + r.stderr
