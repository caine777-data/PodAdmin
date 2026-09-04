"""
Vérification des dimensions de fenêtres
=======================================
Ces tests ouvrent réellement les fenêtres de l'application et comparent la
hauteur RÉCLAMÉE par leur contenu à la hauteur DÉCLARÉE dans `geometry()`.

POURQUOI CE FICHIER
-------------------
Trois défauts du même type sont survenus, chacun signalé par l'utilisateur et
non par les tests :

  • la fenêtre « À propos » du Téléverseur coupait la mention de licence ;
  • la fenêtre « Remplacer & ré-encoder » laissait le bouton Fermer hors cadre ;
  • l'onglet Configuration masquait ses derniers boutons en fenêtre réduite.

Les tests existants vérifiaient que les fenêtres S'OUVRENT, jamais que leur
contenu TIENT DEDANS. Or ces fenêtres ne sont pas redimensionnables : ce qui
dépasse est simplement invisible, sans barre de défilement ni indice.

Ces vérifications ne remplacent pas un coup d'œil humain — une fenêtre peut
« tenir » tout en étant laide — mais elles attrapent le cas franc : un bouton
inaccessible.

Ils nécessitent un affichage : sous Linux sans écran, lancer avec `xvfb-run`.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Marge tolérée : quelques pixels d'écart ne gênent personne.
MARGE = 8


@pytest.fixture(scope="module")
def app():
    """Instancie l'application une seule fois pour tout le module."""
    import tempfile
    os.environ.setdefault("HOME", tempfile.mkdtemp())
    try:
        import app as module_app
    except Exception as e:                       # pas d'affichage disponible
        pytest.skip(f"interface indisponible : {e}")
    a = module_app.App()
    a.update()
    yield a
    try:
        a.destroy()
    except Exception:
        pass


def _mesurer(fenetre, hauteur_declaree):
    """Compare la hauteur réclamée par le contenu à celle déclarée."""
    fenetre.update_idletasks()
    requise = fenetre.winfo_reqheight()
    return requise, hauteur_declaree, requise <= hauteur_declaree + MARGE


class TestDimensionsFenetres:
    """Chaque fenêtre doit pouvoir afficher l'intégralité de son contenu."""

    def test_fenetre_progression_remplacement(self, app):
        """Cas long : message de finalisation interrompue (le plus verbeux)."""
        import app as module_app
        m = module_app.ProgressModal(
            app,
            title="Remplacer le fichier & ré-encoder",
            subtitle="« Cours magistral — séance 3 »\n"
                     "cours_seance3_v2.mp4 (740 Mo) — méthode par MORCEAUX.",
            intro="Étape 1/3 — Envoi du fichier par morceaux…")
        app.update()
        try:
            requise, declaree, ok = _mesurer(m, 320)
            assert ok, (f"contenu de {requise} px pour une fenêtre de {declaree} px : "
                        "une partie serait invisible")

            # Message de fin long : la fenêtre doit s'ajuster d'elle-même.
            m.finish(False,
                     "Le fichier est envoyé, mais le serveur termine encore son "
                     "assemblage (cela peut prendre ~10 min). Vérifiez la vidéo sur "
                     "le site, puis relancez le ré-encodage si besoin.")
            app.update()
            m.update_idletasks()
            import re
            hauteur = int(re.search(r"x(\d+)", m.geometry()).group(1))
            assert m.winfo_reqheight() <= hauteur + MARGE, (
                "après un message de fin long, le contenu dépasse encore")
        finally:
            try:
                m.destroy()
            except Exception:
                pass

    def test_bouton_fermer_reste_dans_la_fenetre(self, app):
        """Le bouton Fermer doit être ATTEIGNABLE, pas seulement exister.

        C'est le défaut constaté : le bouton existait, mais tombait sous le bord
        inférieur d'une fenêtre non redimensionnable.

        IMPORTANT : on remplit la fenêtre avec un contenu RÉALISTE. Une première
        version de ce test employait un sous-titre d'un caractère : la fenêtre
        tenait alors dans n'importe quelle taille, et le test passait même après
        réintroduction volontaire du bug. Un test doit reproduire le cas réel,
        pas le cas commode."""
        import app as module_app
        m = module_app.ProgressModal(
            app,
            title="Remplacer le fichier & ré-encoder",
            subtitle="« Cours magistral — séance 3 »\n"
                     "cours_seance3_v2.mp4 (740 Mo) — méthode par MORCEAUX "
                     "(compte véhicule).",
            intro="Étape 1/3 — Envoi du fichier par morceaux…")
        app.update()
        try:
            m.update_idletasks()
            import re
            hauteur = int(re.search(r"x(\d+)", m.geometry()).group(1))
            bas_du_bouton = m.close_btn.winfo_y() + m.close_btn.winfo_reqheight()
            assert bas_du_bouton <= hauteur, (
                f"le bouton Fermer se termine à {bas_du_bouton} px, "
                f"hors d'une fenêtre de {hauteur} px")
        finally:
            try:
                m.destroy()
            except Exception:
                pass

    def test_onglet_configuration_defilable(self, app):
        """L'onglet Configuration est long : il DOIT être défilable.

        Sans cela, ses dernières sections (réglages de l'instance) sont
        inaccessibles en fenêtre réduite."""
        import customtkinter as ctk
        app._show_tab("config")
        app.update()
        assert isinstance(app.tabs["config"], ctk.CTkScrollableFrame), (
            "l'onglet Configuration doit rester défilable : son contenu dépasse "
            "la hauteur disponible en fenêtre réduite")

    def test_tous_les_onglets_s_affichent(self, app):
        """Garde-fou : aucun onglet ne doit lever d'erreur à l'affichage."""
        for cle in list(app.tabs):
            app._show_tab(cle)
            app.update()
