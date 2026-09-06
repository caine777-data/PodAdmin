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


class TestCorrectionsAudit:
    """Défauts relevés par l'audit du 5 septembre 2026, corrigés en 1.3.1.

    Ces tests existent parce qu'AUCUN test ne couvrait ces cas : la suite
    vérifiait que les onglets s'affichent, jamais leur comportement au fil de la
    vie de l'application."""

    def test_b1_onglet_ouvert_avant_connexion(self, app):
        """Un onglet ouvert pendant la connexion doit se charger ensuite.

        Sans reprise, il restait vide indéfiniment — ce qui ressemble à une
        panne de l'instance alors que tout va bien."""
        app.api = None
        app._auto_loaded.clear()
        app._show_tab("browse")
        assert app.onglet_courant == "browse", (
            "l'onglet courant doit être mémorisé pour pouvoir rejouer le chargement")
        assert "browse" not in app._auto_loaded, (
            "sans connexion, aucun chargement ne doit partir")

    def test_b1_methode_de_reprise_existe(self, app):
        """La reprise doit être appelable depuis les deux points de connexion."""
        assert hasattr(app, "_on_connexion_etablie")

    def test_b5_pas_de_lecture_tk_dans_le_thread(self):
        """`_do_reassign_apply` s'exécute dans un thread : il ne doit PAS y lire
        de variable Tk. Le paramètre `keep` existe précisément pour cela."""
        import inspect

        import app as module_app
        src = inspect.getsource(module_app.App._do_reassign_apply)
        assert "reassign_keep_var.get()" not in src, (
            "lecture d'une variable Tk depuis un thread de travail : "
            "c'est la raison d'être du paramètre `keep`")

    def test_b6_refus_meme_proprietaire(self, app):
        """Réaffecter vers le même compte n'a aucun sens : à refuser avant
        d'émettre des écritures inutiles."""
        app._show_tab("reassign")
        compte = {"url": "https://v/rest/users/6/", "username": "test"}
        app.reassign_source = compte
        app.reassign_target = dict(compte)       # même URL, objet distinct
        app.reassign_videos = []
        app.reassign_rowvars = {}
        app._reassign_confirm()
        app.update()
        assert "même compte" in str(app.reassign_progress.cget("text"))

    def test_b4_pas_de_nom_indefini(self):
        """Contrôle statique : aucun nom indéfini dans le module.

        Le défaut d'origine — un lambda référençant `e` hors de son bloc
        `except` — n'était détectable que par analyse statique."""
        import subprocess
        import sys
        r = subprocess.run([sys.executable, "-m", "pyflakes", "app.py"],
                           capture_output=True, text=True)
        indefinis = [l for l in r.stdout.splitlines() if "undefined name" in l]
        assert not indefinis, "noms indéfinis détectés :\n" + "\n".join(indefinis)


class TestLargeurDesBarres:
    """Vérifie qu'aucune barre de contrôles ne déborde HORIZONTALEMENT.

    Le banc de test ne mesurait que la HAUTEUR des fenêtres. Il a donc laissé
    passer un débordement de 485 px sur la barre de filtres de l'onglet Vidéos :
    huit contrôles réclamaient 1237 px pour 752 px disponibles en fenêtre
    minimale. Le tri et les filtres de détection, placés en fin de ligne,
    étaient présents dans le code mais invisibles à l'écran.

    Ces tests s'exécutent à la taille MINIMALE autorisée (1000 x 660) : c'est le
    pire cas, et celui qu'il faut garantir."""

    @staticmethod
    def _mesurer(app, widget):
        """Renvoie (largeur requise, largeur disponible) du conteneur."""
        app.update_idletasks()
        cadre = widget.master
        return cadre.winfo_reqwidth(), cadre.winfo_width()

    def test_filtres_videos_rangee_1(self, app):
        app.geometry("1000x660")
        app._show_tab("browse")
        app.update()
        requis, dispo = self._mesurer(app, app.browse_text)
        assert requis <= dispo + MARGE, (
            f"la 1re rangée de filtres réclame {requis} px pour {dispo} px "
            f"disponibles : {requis - dispo} px seraient tronqués")

    def test_filtres_videos_rangee_2(self, app):
        app.geometry("1000x660")
        app._show_tab("browse")
        app.update()
        requis, dispo = self._mesurer(app, app.browse_tri)
        assert requis <= dispo + MARGE, (
            f"la 2e rangée de filtres réclame {requis} px pour {dispo} px "
            f"disponibles : {requis - dispo} px seraient tronqués")

    def test_controles_de_tri_et_detection_atteignables(self, app):
        """Les contrôles ajoutés en 1.2.x doivent être réellement visibles.

        Ils existaient déjà, mais hors écran : présents à l'inspection du code,
        inutilisables par l'utilisateur."""
        app.geometry("1000x660")
        app._show_tab("browse")
        app.update()
        app.update_idletasks()
        largeur = app.winfo_width()
        for nom, widget in (("tri", app.browse_tri),
                            ("détection", app.browse_detect),
                            ("seuil en mois", app.browse_months)):
            droite = widget.winfo_rootx() - app.winfo_rootx() + widget.winfo_reqwidth()
            assert droite <= largeur, (
                f"le contrôle « {nom} » se termine à {droite} px, "
                f"hors d'une fenêtre de {largeur} px")


class TestMagasinPartage:
    """Cohérence entre onglets — le manque relevé par l'audit (M3).

    La suite vérifiait que les onglets s'affichent, jamais que leurs données
    restent cohérentes. Trois onglets (Encodage, Inventaire, Réaffectation)
    rechargeaient l'instance de leur côté et gardaient une copie que rien ne
    rafraîchissait : après une suppression, l'Encodage proposait de relancer une
    vidéo disparue et l'Inventaire affichait un total périmé."""

    @staticmethod
    def _faux_api():
        class FauxAPI:
            appels = 0

            def get_all_videos(self, progress_cb=None):
                FauxAPI.appels += 1
                return [{"slug": f"s{i}", "title": f"V{i}", "is_draft": 0,
                         "is_restricted": 0, "owner": "https://v/rest/users/6/",
                         "type": "", "channel": [], "encoded": 1, "duration": 60,
                         "date_added": "2026-08-01"} for i in range(5)]

            def get_channels(self):
                return []

            def get_all_users(self, **kw):
                return [{"url": "https://v/rest/users/6/", "username": "u6"}]

            def get_types(self):
                return []

            def get_view_counts(self, **kw):
                return []

            def get_owners_map(self, **kw):
                return {}
        FauxAPI.appels = 0
        return FauxAPI()

    def test_aucun_onglet_ne_court_circuite_le_magasin(self):
        """Contrôle statique : plus aucun appel direct à `get_all_videos`
        en dehors du magasin lui-même."""
        import inspect
        import re

        import app as module_app
        source = inspect.getsource(module_app)
        fautifs = []
        for methode in ("_do_encode_scan", "_do_reassign_preview", "_do_stats_scan"):
            m = re.search(rf"def {methode}\(.*?(?=\n    def )", source, re.S)
            if m and "self.api.get_all_videos" in m.group(0):
                fautifs.append(methode)
        assert not fautifs, (
            "ces onglets rechargent l'instance au lieu d'utiliser le magasin "
            f"partagé : {', '.join(fautifs)}")

    def test_suppression_propagee_a_tous_les_onglets(self, app):
        """Une vidéo retirée du magasin doit disparaître de PARTOUT."""
        app.api = self._faux_api()
        app.videos[:] = app.api.get_all_videos()
        app.encode_videos = list(app.videos)
        app._stats_contexte = ({"https://v/rest/users/6": "u6"}, {}, {}, [])
        app.stats_data = app._compute_stats(list(app.videos),
                                            {"https://v/rest/users/6": "u6"},
                                            {}, {}, [])
        app._show_tab("encode")
        app.update()

        app.videos.pop(0)                       # suppression (mémoire seule)
        app._refresh_video_views()
        app.update()

        assert len(app.encode_videos) == 4, (
            "l'onglet Encodage garde une vidéo qui n'existe plus")
        assert app.stats_data["total"] == 4, (
            "l'Inventaire affiche un total périmé")


class TestInterruptionDesLots:
    """Un traitement par lot doit pouvoir être arrêté proprement.

    Depuis « Tout sélectionner », un lot peut porter sur plusieurs centaines de
    vidéos. Sans interruption, le seul recours serait de tuer l'application —
    en laissant le traitement à moitié fait, sans savoir où il s'est arrêté."""

    def test_drapeau_present(self, app):
        assert hasattr(app, "lot_interrompu")

    @staticmethod
    def _preparer_selection(app):
        """Place l'application dans un état connu : une vidéo sélectionnée.

        L'instance étant PARTAGÉE entre les tests, on ne peut pas se contenter
        d'un Ctrl+clic : si la vidéo était déjà retenue, le clic la RETIRERAIT,
        le panneau reviendrait au détail et le bouton d'arrêt n'existerait plus.
        Un test dépendant de l'ordre d'exécution est un test qui ment."""
        app._show_tab("browse")
        app.videos[:] = [{"slug": "s1", "title": "V", "is_draft": 0,
                          "is_restricted": 0, "owner": "", "type": "", "channel": []}]
        app._browse_do_filter()
        app._browse_vider_multi()                 # état de départ garanti
        app._browse_toggle_multi(app.browse_filtered[0])
        app.update()

    def test_bouton_desactive_au_repos(self, app):
        self._preparer_selection(app)
        assert str(app.browse_stop_btn.cget("state")) == "disabled", (
            "un bouton d'arrêt toujours cliquable laisserait croire qu'il agit")

    def test_cycle_activation(self, app):
        self._preparer_selection(app)
        app._lot_debut(); app.update()
        assert str(app.browse_stop_btn.cget("state")) == "normal"
        app._lot_fin(); app.update()
        assert str(app.browse_stop_btn.cget("state")) == "disabled"

    def test_demande_d_arret_leve_le_drapeau(self, app):
        self._preparer_selection(app)
        app.lot_interrompu.clear()
        app._lot_interrompre()
        assert app.lot_interrompu.is_set()


class TestErgonomie:
    """Constats d'ergonomie relevés par les audits, corrigés en 1.5.1."""

    def test_icones_de_navigation_toutes_distinctes(self):
        """Sur une barre de douze entrées parcourue du regard, l'icône est le
        repère principal : deux entrées identiques l'annulent.

        « ⚙️ » désignait à la fois Encodage et Configuration."""
        import collections
        import re

        import app as module_app
        source = open(module_app.__file__.replace(".pyc", ".py"),
                      encoding="utf-8").read()
        entrees = re.findall(r'\("(\S+)\s+([A-ZÀ-Ü][^"]*)",\s*"([a-z]+)"\)', source)
        icones = [i for i, lib, cle in entrees
                  if cle in ("upload", "encode", "comptes", "browse", "reassign",
                             "stats", "ct", "groups", "config", "help", "log", "about")]
        doublons = [i for i, n in collections.Counter(icones).items() if n > 1]
        assert not doublons, f"icônes en double dans la navigation : {doublons}"

    def test_raccourcis_clavier_sur_les_modales(self, app):
        """Échap et Entrée doivent être liés sur toute fenêtre secondaire.

        Les cinq modales passent par `_focus_toplevel` : les raccourcis y sont
        posés une seule fois, ce qui évite d'en oublier une."""
        import app as module_app
        m = module_app.ProgressModal(app, title="T", subtitle="s", intro="i")
        app.update()
        try:
            assert bool(m.bind("<Escape>")), "Échap non lié"
            assert bool(m.bind("<Return>")), "Entrée non liée"
        finally:
            try:
                m.destroy()
            except Exception:
                pass

    def test_theme_bascule_et_se_memorise(self, app):
        """Le mode clair/sombre doit basculer et retenir le choix."""
        import customtkinter as ctk
        depart = ctk.get_appearance_mode().lower()
        app._basculer_theme()
        app.update()
        assert ctk.get_appearance_mode().lower() != depart
        assert app.config_data.get("theme") in ("dark", "light")
        app._basculer_theme()                    # remettre l'état initial
        app.update()

    def test_palette_sans_couleur_en_dur(self):
        """Les couleurs doivent passer par les constantes sémantiques.

        24 teintes étaient écrites en hexadécimal dans les appels de widgets,
        dont une répétée 75 fois : changer la nuance d'avertissement demandait
        75 modifications, et le mode clair était impossible."""
        import re

        import app as module_app
        source = open(module_app.__file__.replace(".pyc", ".py"),
                      encoding="utf-8").read()
        # On ignore le bloc de définition de la palette lui-même.
        corps = source[source.index("# Page Moodle où les enseignants"):]
        restantes = re.findall(r'(?:fg_color|hover_color|text_color)="#[0-9a-fA-F]{6}"',
                               corps)
        assert len(restantes) <= 12, (
            f"{len(restantes)} couleurs encore en dur : {set(restantes)}")


class TestHierarchieVisuelle:
    """Chantier 1.5.2 : un seul point coloré par écran.

    Les listes déroulantes prenaient le bleu par défaut de CustomTkinter,
    c'est-à-dire exactement la teinte des boutons d'action. Sur l'onglet
    Vidéos, cinq filtres et deux boutons criaient donc aussi fort. Ces tests
    empêchent la réintroduction d'un contrôle au bleu implicite : c'est un
    oubli invisible à la relecture, puisqu'il ne s'écrit nulle part."""

    @staticmethod
    def _appels(source: str, widget: str):
        """Découpe les appels `widget(...)` en équilibrant les parenthèses.

        Une expression régulière ne suffirait pas : les appels contiennent des
        lambdas et des tuples, donc des parenthèses imbriquées."""
        appels, i = [], 0
        motif = widget + "("
        while True:
            j = source.find(motif, i)
            if j < 0:
                return appels
            k, profondeur = j + len(motif), 1
            while profondeur > 0 and k < len(source):
                if source[k] == "(":
                    profondeur += 1
                elif source[k] == ")":
                    profondeur -= 1
                k += 1
            appels.append((source[:j].count("\n") + 1, source[j:k]))
            i = k

    @staticmethod
    def _source() -> str:
        import app as module_app
        return open(module_app.__file__.replace(".pyc", ".py"),
                    encoding="utf-8").read()

    def test_aucune_liste_deroulante_au_bleu_par_defaut(self):
        """Tout CTkOptionMenu doit recevoir STYLE_CHAMP."""
        source = self._source()
        fautifs = [ligne for ligne, appel in self._appels(source, "CTkOptionMenu")
                   if "STYLE_CHAMP" not in appel]
        assert not fautifs, (
            f"listes déroulantes sans STYLE_CHAMP, lignes {fautifs} : elles "
            "reprendraient le bleu des boutons d'action.")

    def test_aucun_bouton_sans_couleur_explicite(self):
        """Un CTkButton sans `fg_color` hérite du bleu du thème.

        C'est ainsi que quatorze boutons secondaires — « Ajouter un dossier »,
        « Parcourir… », « Fermer » — se retrouvaient aussi accentués que
        l'action principale de leur écran."""
        source = self._source()
        fautifs = [ligne for ligne, appel in self._appels(source, "CTkButton")
                   if "fg_color" not in appel]
        assert not fautifs, (
            f"boutons sans fg_color, lignes {fautifs} : ils prendraient le "
            "bleu d'action par défaut.")

    def test_boutons_secondaires_lisibles(self):
        """Un bouton gris garde le texte BLANC par défaut : en mode clair, il
        paraît DÉSACTIVÉ.

        Constaté sur « Rafraîchir » et « Tout sélectionner » dès le passage des
        filtres en neutre — le remède au premier défaut en avait créé un
        second, moins visible mais plus gênant."""
        source = self._source()
        fautifs = [ligne for ligne, appel in self._appels(source, "CTkButton")
                   if "fg_color=C_NEUTRE" in appel and "text_color" not in appel]
        assert not fautifs, (
            f"boutons gris sans text_color, lignes {fautifs} : ils "
            "paraîtraient désactivés en mode clair.")

    def test_navigation_groupee_couvre_tous_les_onglets(self):
        """Le regroupement en blocs ne doit avoir égaré aucune entrée."""
        import app as module_app
        attendus = {"upload", "encode", "browse", "reassign", "ct", "nomen",
                    "stats", "comptes", "groups", "config", "log", "help",
                    "about"}
        source = self._source()
        assert "NAVIGATION = [" in source, "navigation par blocs absente"
        # Les onglets construits et les boutons de navigation doivent coïncider.
        for cle in attendus:
            assert f'"{cle}"' in source, f"entrée de navigation manquante : {cle}"

    # ⚠️ TEST FAUX JUSQU'EN 1.5.3, ET C'EST INSTRUCTIF.
    #
    # Il forçait la fenêtre en 1280×800 et concluait « tout tient ». Or
    # l'application s'ouvre en 1180×760 : à la taille réelle, « À propos »
    # était hors champ dès le démarrage, pour tout le monde. Le test validait
    # une situation qui ne se produit chez personne.
    #
    # Règle qui en découle : ne JAMAIS forcer une géométrie confortable dans un
    # test de place disponible. On mesure à la taille par défaut, celle que
    # l'utilisateur voit.

    @staticmethod
    def _limite_zone_defilante(app):
        """Bord haut de la rangée épinglée = fin de la zone défilante."""
        return app.nav_btns["help"].winfo_rooty()

    def test_navigation_tient_sans_defilement(self, app):
        """À la taille PAR DÉFAUT, le dernier onglet du flux doit être visible."""
        # Le fixture `app` est partagé par tout le module : un test qui
        # redimensionne la fenêtre fausserait celui-ci. On repose donc
        # explicitement la taille PAR DÉFAUT — celle que l'utilisateur voit —
        # et surtout pas une taille confortable choisie pour faire passer.
        app.geometry("1180x760")
        app.update()
        app.update_idletasks()
        dernier = app.nav_btns["log"]      # dernier du flux défilant
        bas = dernier.winfo_rooty() + dernier.winfo_height()
        limite = self._limite_zone_defilante(app)
        assert bas <= limite, (
            f"« Journal » finit à {bas} px pour une zone s'arrêtant à {limite} : "
            "la navigation déborde et défile dès l'ouverture.")

    def test_aide_et_a_propos_toujours_atteignables(self, app):
        """Épinglés en pied, ils ne doivent JAMAIS sortir de l'écran."""
        app.update()
        app.update_idletasks()
        for cle in ("help", "about"):
            bouton = app.nav_btns[cle]
            bas = bouton.winfo_rooty() + bouton.winfo_height()
            assert bas <= app.winfo_height() + app.winfo_rooty(), (
                f"« {cle} » sort de la fenêtre")
            # `grid` depuis la 1.5.3 : `pack` laissait « Aide » à 140 px et
            # « À propos » à 68 — deux colonnes visiblement inégales, chaque
            # bouton gardant sa largeur naturelle.
            assert bouton.winfo_manager() == "grid"


class TestProgressionMasquee:
    """Chantier 1.5.2 : les barres de progression ne s'affichent qu'en usage."""

    # NOTE — on interroge `winfo_manager()` et non `winfo_ismapped()`.
    # `winfo_ismapped()` répond « visible à l'écran », ce qui est TOUJOURS faux
    # ici : l'onglet Téléversement n'est pas l'onglet affiché pendant les tests.
    # `winfo_manager()` répond « placé par un gestionnaire » — "pack" si le
    # widget est posé, "" après pack_forget. C'est bien ce qu'on veut vérifier.

    def test_masquees_au_repos(self, app):
        """Au démarrage, aucun envoi n'est en cours : rien à montrer."""
        assert app.progression_visible is False
        assert app.file_progress.winfo_manager() == ""
        assert app.batch_progress.winfo_manager() == ""

    def test_cycle_affichage_masquage(self, app):
        """Afficher puis masquer doit revenir exactement à l'état initial."""
        app._afficher_progression()
        app.update()
        assert app.progression_visible is True
        assert app.file_progress.winfo_manager() == "pack"
        assert app.batch_progress.winfo_manager() == "pack"
        app._masquer_progression()
        app.update()
        assert app.progression_visible is False
        assert app.file_progress.winfo_manager() == ""

    def test_appels_repetes_sans_effet(self, app):
        """Appelée deux fois, la méthode ne doit pas placer les barres en double
        (ni le masquage échouer sur des widgets déjà retirés)."""
        app._afficher_progression()
        app._afficher_progression()
        app.update()
        assert app.progression_visible is True
        app._masquer_progression()
        app._masquer_progression()
        app.update()
        assert app.progression_visible is False

    def test_lancement_du_lot_affiche_la_progression(self):
        """Symétrique du test suivant, et découvert par lui.

        En éprouvant les tests par mutation, la suppression de l'appel dans
        `_start_upload` n'était détectée par AUCUN test : seule la relance des
        échecs était couverte. Un défaut passé au travers d'une vérification
        est un défaut que la vérification doit désormais voir."""
        import inspect

        import app as module_app
        source = inspect.getsource(module_app.App._start_upload)
        assert "_afficher_progression" in source, (
            "le lancement d'un lot n'affiche pas les barres de progression.")

    def test_fin_de_lot_masque_la_progression(self):
        """Sans masquage, les barres resteraient à l'écran après l'envoi —
        c'est-à-dire l'état d'origine qu'on cherchait à corriger."""
        import inspect

        import app as module_app
        source = inspect.getsource(module_app.App._on_batch_done)
        assert "_masquer_progression" in source, (
            "la fin du lot ne masque pas les barres de progression.")

    def test_relance_des_echecs_affiche_la_progression(self):
        """`_retry_failed` n'emprunte PAS `_start_upload` : sans appel propre,
        les barres resteraient masquées pendant tout le renvoi.

        Le défaut avait été introduit puis rattrapé à la relecture du code —
        d'où ce test, qui vérifie la présence de l'appel dans la méthode."""
        import inspect

        import app as module_app
        source = inspect.getsource(module_app.App._retry_failed)
        assert "_afficher_progression" in source, (
            "la relance des échecs n'affiche pas les barres de progression.")


class TestBandeauMiseAJour:
    """Le bandeau de mise à jour reste correct après le remaniement visuel.

    Rappel du piège : un cadre conteneur transparent de hauteur nulle se
    dessinait en CARRÉ NOIR sur macOS. Le bandeau doit donc être créé de toutes
    pièces au moment de l'affichage, sans conteneur en attente."""

    def test_aucun_conteneur_en_attente(self, app):
        """Tant qu'aucune mise à jour n'est détectée, aucun widget n'existe."""
        assert app.maj_bandeau is None

    def test_affichage_version_ordinaire(self, app):
        app._afficher_bandeau_maj({"version": "9.9.9",
                                   "url": "https://exemple.invalid/releases",
                                   "notes": "Notes de version."})
        app.update()
        assert app.maj_bandeau is not None
        assert app.maj_bandeau.winfo_ismapped()
        assert app.maj_bandeau.winfo_height() > 1, (
            "bandeau de hauteur nulle : c'est la configuration qui produisait "
            "un carré noir sur macOS.")

    def test_affichage_sans_lien(self, app):
        """Branche la plus risquée : elle force `height=0` sur le cadre."""
        app._afficher_bandeau_maj({"version": "9.9.9", "notes": "Sans lien."})
        app.update()
        app.update_idletasks()
        assert app.maj_bandeau.winfo_height() > 1

    def test_un_seul_bandeau_a_la_fois(self, app):
        """Deux détections successives ne doivent pas empiler deux bandeaux."""
        app._afficher_bandeau_maj({"version": "9.9.8", "url": "https://x.invalid"})
        app.update()
        premier = app.maj_bandeau
        app._afficher_bandeau_maj({"version": "9.9.9", "url": "https://x.invalid"})
        app.update()
        assert app.maj_bandeau is not premier
        assert not premier.winfo_exists(), "le bandeau précédent n'a pas été détruit"


class TestEchelleDeSurfaces:
    """Chantier 1.5.2 : quatre niveaux de surface, pas douze gris."""

    @staticmethod
    def _corps() -> str:
        """Source de `app.py`, hors bloc de définition de la palette."""
        import app as module_app
        source = open(module_app.__file__.replace(".pyc", ".py"),
                      encoding="utf-8").read()
        return source[source.index("# Page Moodle où les enseignants"):]

    def test_aucun_gris_hors_echelle(self):
        """Douze gris différents désignaient quatre choses.

        « gray85 » et « gray86 » servaient au même usage sans qu'on puisse dire
        lequel faisait référence, et un même panneau changeait de teinte d'un
        onglet à l'autre."""
        import re
        fautifs = re.findall(r'fg_color=\("gray\d+", "gray\d+"\)', self._corps())
        assert not fautifs, (
            f"{len(fautifs)} surfaces hors échelle : {set(fautifs)}. "
            "Utiliser S_CARTE, S_LIGNE, S_SELECTION, S_PUCE ou S_FILET.")

    def test_aucune_couleur_unique_pour_les_deux_modes(self):
        """Une couleur écrite seule s'applique TELLE QUELLE aux deux thèmes.

        C'est ainsi qu'une ligne sur deux du tableau de téléversement
        s'affichait presque NOIRE en mode clair (`"gray14"`), et que les filets
        de séparation barraient les panneaux clairs d'un trait sombre
        (`"gray30"`). Le défaut est resté invisible tant que le mode sombre
        était le seul disponible."""
        import re
        corps = self._corps()
        # Une teinte est LÉGITIME quand elle est un membre de couple : le
        # caractère significatif qui la précède est alors « ( » ou « , ».
        # Partout ailleurs — après « = » ou après « else » — elle s'applique
        # telle quelle aux deux modes, ce qui est le défaut recherché.
        #
        # Une simple regex sur `fg_color="grayNN"` ne suffisait pas : elle
        # laissait passer la forme ternaire
        #     fg_color=S_LIGNE if i % 2 else "gray14"
        # qui est précisément celle qui noircissait une ligne sur deux.
        import app as module_app
        entier = open(module_app.__file__.replace(".pyc", ".py"),
                      encoding="utf-8").read()
        decalage = entier[:entier.index("# Page Moodle où les enseignants")].count("\n")
        fautifs = []
        for m in re.finditer(r'"gray\d+"', corps):
            avant = corps[:m.start()].rstrip()
            if avant and avant[-1] not in "(,":
                # Le décalage ramène au numéro de ligne du FICHIER : sans lui,
                # le message renvoyait vers des lignes sans rapport, ce qui a
                # coûté une recherche inutile.
                ligne = corps[:m.start()].count("\n") + 1 + decalage
                fautifs.append((ligne, m.group(0)))
        assert not fautifs, (
            f"teintes appliquées aux deux modes : {fautifs}. "
            "Un couple (clair, sombre) est nécessaire.")


class TestBarreLateraleCompacte:
    """Le libellé « Dépôt au nom de » ne doit pas occuper la place qu'il
    n'utilise pas : ses 34 px étaient pris sur la navigation."""

    def test_absent_au_repos(self, app):
        assert app.agent_visible is False
        assert app.agent_lbl.winfo_manager() == ""

    def test_apparait_et_se_place_avant_le_separateur(self, app):
        """Sans l'argument `before`, `pack` le placerait en FIN de barre
        latérale, sous la navigation, et non à sa place logique."""
        app._definir_agent("Dépôt au nom de :\nun.utilisateur")
        app.update()
        app.update_idletasks()
        assert app.agent_visible is True
        assert app.agent_lbl.winfo_manager() == "pack"
        assert app.agent_lbl.winfo_rooty() < app.sidebar_separateur.winfo_rooty(), (
            "le libellé s'est placé après le séparateur, donc sous la navigation")

    def test_disparait_quand_il_redevient_vide(self, app):
        app._definir_agent("Dépôt au nom de :\nun.utilisateur")
        app.update()
        app._definir_agent("")
        app.update()
        assert app.agent_visible is False
        assert app.agent_lbl.winfo_manager() == ""


class TestElevation:
    """Le fond de fenêtre, la barre latérale et les panneaux doivent se
    distinguer.

    Mesuré sur capture avant correction : fond de fenêtre et barre latérale
    valaient tous deux (219, 219, 219), et `S_LIGNE` tombait exactement dessus.
    D'où l'impression de gris uniforme où rien ne se détachait."""

    @staticmethod
    def _niveau(teinte: str) -> int:
        """Convertit « gray88 » en 88."""
        return int(teinte.replace("gray", ""))

    def test_trois_niveaux_distincts_en_mode_clair(self):
        import app as module_app
        fond = self._niveau(module_app.S_FOND[0])
        barre = self._niveau(module_app.S_BARRE[0])
        carte = self._niveau(module_app.S_CARTE[0])
        assert fond < barre < carte, (
            f"élévation incohérente en clair : fond={fond}, barre={barre}, "
            f"carte={carte}. Une surface posée doit être plus claire que son "
            "support.")

    def test_trois_niveaux_distincts_en_mode_sombre(self):
        import app as module_app
        fond = self._niveau(module_app.S_FOND[1])
        barre = self._niveau(module_app.S_BARRE[1])
        carte = self._niveau(module_app.S_CARTE[1])
        assert fond < barre < carte, (
            f"élévation incohérente en sombre : fond={fond}, barre={barre}, "
            f"carte={carte}.")

    def test_le_fond_est_applique_a_la_fenetre(self, app):
        """Sans cet appel, CustomTkinter donne au fond la teinte par défaut
        d'un cadre — exactement celle de la barre latérale."""
        import app as module_app
        assert tuple(app.cget("fg_color")) == module_app.S_FOND

    def test_aucun_panneau_defilant_au_defaut(self):
        """Un CTkScrollableFrame sans `fg_color` retombe sur « gray86 »,
        c'est-à-dire l'ancien fond de fenêtre : le panneau devenait invisible.

        Dix-neuf panneaux étaient dans ce cas, ce qui expliquait pourquoi
        éclaircir le fond ne suffisait pas à les faire ressortir."""
        source = TestEchelleDeSurfaces._corps()
        appels, i, fautifs = [], 0, []
        while True:
            j = source.find("CTkScrollableFrame(", i)
            if j < 0:
                break
            k, profondeur = j + len("CTkScrollableFrame("), 1
            while profondeur > 0 and k < len(source):
                if source[k] == "(":
                    profondeur += 1
                elif source[k] == ")":
                    profondeur -= 1
                k += 1
            if "fg_color" not in source[j:k]:
                fautifs.append(source[:j].count("\n") + 1)
            i = k
        assert not fautifs, (
            f"panneaux défilants sans fg_color, lignes {fautifs} (relatives au "
            "corps) : ils prendraient la teinte par défaut, hors échelle.")


class TestSuppressionsEnListe:
    """Une suppression répétée sur chaque ligne ne doit pas saturer l'écran.

    Cinq boutons rouges « Supprimer » apparaissaient sur trois chaînes
    seulement : sur vingt, l'action la plus dangereuse serait devenue la plus
    visible, et l'œil s'y serait habitué. Elles passent en icône neutre, rouge
    AU SURVOL, le libellé revenant par une infobulle."""

    @staticmethod
    def _corps() -> str:
        return TestEchelleDeSurfaces._corps()

    def test_plus_de_libelle_rouge_repete(self):
        """Aucun bouton « 🗑 Supprimer » ne doit subsister dans une liste."""
        assert '"🗑 Supprimer"' not in self._corps(), (
            "un bouton de suppression avec libellé subsiste dans une liste.")

    def test_suppressions_uniques_conservent_leur_libelle(self):
        """L'argument d'origine — « une icône seule n'annonce pas la gravité »
        — reste valable pour une suppression NON répétée.

        Les boutons du panneau de détail d'une vidéo gardent donc leur texte :
        c'est la répétition qui posait problème, pas la couleur en soi."""
        corps = self._corps()
        assert "🗑  Supprimer cette vidéo" in corps
        assert "🗑  Supprimer définitivement ces" in corps

    def test_icones_neutres_avec_survol_destructif(self):
        """Le rouge ne doit apparaître qu'au survol."""
        # Extraction par ÉQUILIBRAGE de parenthèses, pas par regex : une
        # expression non gourmande s'arrêtait à la première « ) » rencontrée,
        # c'est-à-dire celle de `CTkFont(...)`, et signalait comme fautifs des
        # boutons parfaitement conformes.
        corps = self._corps()
        boutons = [appel for _l, appel
                   in TestHierarchieVisuelle._appels(corps, "CTkButton")
                   if 'text="🗑"' in appel]
        assert boutons, "aucun bouton poubelle trouvé"
        for b in boutons:
            assert "fg_color=C_NEUTRE" in b, f"poubelle non neutre : {b[:90]}"
            assert "hover_color=C_DESTRUCTIF" in b, (
                f"poubelle sans survol destructif : {b[:90]}")


class TestInfobulle:
    """L'infobulle rend le mot perdu avec le libellé.

    ⚠️ Ces tests pilotent une VRAIE souris (`xdotool`). `event_generate` ne
    convient pas : vérification faite, il ne déclenche pas les liaisons
    <Enter>/<Leave>, y compris sans infobulle installée — un test fondé
    dessus aurait conclu à tort que rien ne fonctionne."""

    @staticmethod
    def _souris_disponible() -> bool:
        import shutil
        return shutil.which("xdotool") is not None

    @staticmethod
    def _survoler(app, widget, duree=1.2):
        import os
        import time
        x = widget.winfo_rootx() + widget.winfo_width() // 2
        y = widget.winfo_rooty() + widget.winfo_height() // 2
        os.system(f"xdotool mousemove {x} {y}")
        debut = time.time()
        while time.time() - debut < duree:
            app.update()
            time.sleep(0.05)

    @staticmethod
    def _bulles(widget):
        return [w for w in widget.winfo_children()
                if w.winfo_class() == "Toplevel"]

    def test_apparait_puis_disparait(self, app):
        import os
        import time

        import pytest
        if not self._souris_disponible():
            pytest.skip("xdotool absent")
        import app as module_app
        bouton = module_app.ctk.CTkButton(app, text="🗑", width=34)
        bouton.pack()
        module_app.ajouter_infobulle(bouton, "Supprimer ceci")
        app.update()
        app.update_idletasks()

        self._survoler(app, bouton)
        assert self._bulles(bouton), "aucune infobulle au survol"

        os.system("xdotool mousemove 5 5")
        debut = time.time()
        while time.time() - debut < 0.5:
            app.update()
            time.sleep(0.05)
        assert not self._bulles(bouton), (
            "l'infobulle survit à la sortie du curseur")
        bouton.destroy()

    def test_reste_dans_l_ecran(self, app):
        """Ces boutons sont en BOUT DE RANGÉE, donc collés au bord droit.

        Alignée naïvement sur le bord gauche du bouton, l'infobulle sortait de
        l'écran et se lisait « Supprimer ce… »."""
        import pytest
        if not self._souris_disponible():
            pytest.skip("xdotool absent")
        import app as module_app
        # La fenêtre doit occuper TOUTE la largeur de l'écran, sans quoi le
        # bouton n'atteint jamais le bord et le débordement ne peut pas se
        # produire : le test passait alors même en réintroduisant le défaut.
        app.geometry(f"{app.winfo_screenwidth()}x800+0+0")
        app.update()
        app.update_idletasks()
        # Le fixture est partagé : la géométrie est restaurée en fin de test,
        # sinon les suivants mesurent dans une fenêtre qu'ils n'ont pas voulue.
        # `pack(side="right")` ne suffisait pas : le cadre ne s'étendait pas
        # jusqu'au bord et le bouton se retrouvait à 220 px, très loin de la
        # marge. Mesure faite, le test passait alors même en réintroduisant le
        # défaut. `place` garantit la position voulue.
        bouton = module_app.ctk.CTkButton(app, text="🗑", width=34)
        bouton.place(relx=1.0, y=100, anchor="ne")   # collé au bord droit
        module_app.ajouter_infobulle(bouton, "Supprimer cette chaîne")
        app.update()
        app.update_idletasks()

        self._survoler(app, bouton)
        bulles = self._bulles(bouton)
        assert bulles, "aucune infobulle au survol"
        bulle = bulles[0]
        bulle.update_idletasks()
        droite = bulle.winfo_rootx() + bulle.winfo_reqwidth()
        assert droite <= app.winfo_screenwidth(), (
            f"infobulle coupée : bord droit à {droite} pour un écran de "
            f"{app.winfo_screenwidth()}")
        assert bulle.winfo_rootx() >= 0
        bouton.destroy()
        app.geometry("1180x760")
        app.update()


class TestCoherenceDesIcones:
    """Une même icône désigne un onglet, et un seul.

    Constaté en 1.5.2 : « Encodage » affichait 🎬 dans la navigation et ⚙️ dans
    son titre — c'est-à-dire l'icône de « Configuration ». Deux onglets
    partageaient donc le même symbole, et un troisième changeait d'identité
    selon l'endroit où on le regardait. Même chose pour « Chaînes » (📺 contre
    🗂)."""

    @staticmethod
    def _navigation(source: str):
        """Renvoie [(icône, libellé, clé)] tel que déclaré dans NAVIGATION."""
        import re
        bloc = source[source.index("NAVIGATION = ["):
                      source.index("self.nav_btns = {}")]
        entrees = re.findall(r'\("([^"\s]+)",\s*"([^"]+)",\s*"(\w+)"\)', bloc)
        # GARDE-FOU. Ces tests lisent la source à l'expression régulière : si
        # le format de NAVIGATION change, la recherche ne renvoie plus rien et
        # les tests passent À VIDE, sans rien vérifier. C'est arrivé en
        # séparant l'icône du libellé — les douze entrées étaient devenues
        # invisibles au test, qui restait vert.
        # Le bloc lu va de NAVIGATION à `self.nav_btns`, ce qui englobe aussi
        # EPINGLES : les 12 entrées sont donc bien toutes couvertes, 10 dans le
        # flux défilant et 2 épinglées en pied.
        assert len(entrees) == 13, (
            f"{len(entrees)} entrées de navigation trouvées au lieu de 13 : "
            "le format de NAVIGATION ou d'EPINGLES a changé, ces tests ne "
            "vérifient plus rien.")
        return entrees

    @staticmethod
    def _titres(source: str):
        """Renvoie {icône: titre} pour les en-têtes d'onglet."""
        import re
        lignes = source.split("\n")
        trouves = {}
        for i, ligne in enumerate(lignes):
            if 'size=20, weight="bold"' in ligne:
                m = re.search(r'text="([^"]+)"', lignes[i - 1])
                if m:
                    trouves[m.group(1).split("  ")[0]] = m.group(1)
        return trouves

    def test_aucune_icone_partagee_entre_onglets(self):
        source = TestEchelleDeSurfaces._corps()
        icones = [ic for ic, _lib, _cle in self._navigation(source)]
        doublons = {i for i in icones if icones.count(i) > 1}
        assert not doublons, f"icônes utilisées par plusieurs onglets : {doublons}"

    def test_le_titre_reprend_l_icone_de_la_navigation(self):
        """Sans quoi l'onglet change d'identité selon l'endroit regardé."""
        source = TestEchelleDeSurfaces._corps()
        titres = self._titres(source)
        ecarts = []
        for icone, libelle, _cle in self._navigation(source):
            # Tous les onglets n'ont pas d'en-tête à cette taille ; on ne
            # vérifie que ceux qui en ont un.
            attendu = [t for t in titres.values() if libelle.split()[0] in t]
            if attendu and not any(t.startswith(icone) for t in attendu):
                ecarts.append((libelle, icone, attendu))
        assert not ecarts, f"icône du titre différente de la navigation : {ecarts}"


class TestAlignementNavigation:
    """Les libellés de navigation doivent tomber sur une colonne fixe.

    Les glyphes d'icônes n'ont pas la même largeur : un espacement en dur les
    décalait jusqu'à 11 px. Et comme cette largeur dépend de la police du
    système, les entrées fautives changeaient d'un poste à l'autre — un
    diagnostic fait sur une machine ne valait pas pour une autre."""

    TOLERANCE = 3   # px

    @staticmethod
    def _positions_reelles(app):
        """Position du texte dans CHAQUE BOUTON RÉELLEMENT CONSTRUIT.

        Mesurer `_prefixe_aligne` directement ne suffisait pas : en
        réintroduisant l'espacement figé dans la construction des boutons, le
        test restait vert puisqu'il interrogeait une fonction que le code
        n'appelait plus. On lit donc le texte affiché."""
        # Le découpage se fait sur le LIBELLÉ DÉCLARÉ, pas sur une heuristique
        # « premier caractère alphabétique » : « ℹ » (U+2139) est considéré
        # comme une lettre par Python, si bien que le préfixe d'« À propos »
        # était mesuré vide et faussait tout l'écart.
        libelles = {cle: lib for _ic, lib, cle
                    in TestCoherenceDesIcones._navigation(
                        TestEchelleDeSurfaces._corps())}
        # « Aide » et « À propos » sont ÉPINGLÉS en pied, côte à côte sur une
        # seule ligne : ils ne sont pas dans la colonne et n'ont donc pas à s'y
        # aligner. Les inclure ferait échouer le test pour une bonne raison
        # qui n'en est pas une.
        positions = []
        for cle, bouton in app.nav_btns.items():
            if cle in ("help", "about"):
                continue
            texte = bouton.cget("text")
            libelle = libelles[cle]
            assert libelle in texte, f"libellé « {libelle} » absent du bouton"
            positions.append(
                (cle, bouton.cget("font").measure(texte[:texte.index(libelle)])))
        return positions

    def test_ecart_residuel_faible(self, app):
        """Mesure la position réelle du texte dans les boutons construits."""
        positions = self._positions_reelles(app)
        assert positions, "aucun bouton de navigation"
        valeurs = [p for _c, p in positions]
        ecart = max(valeurs) - min(valeurs)
        assert ecart <= self.TOLERANCE, (
            f"libellés décalés de {ecart} px : {positions}")

    def test_le_calcul_est_meilleur_que_l_espacement_fige(self, app):
        """Vérifie que la correction apporte bien quelque chose.

        Sans cette comparaison, le test précédent pourrait rester vert avec un
        alignement qui n'aurait jamais été un problème sur cette police."""
        import app as module_app
        police = module_app.ctk.CTkFont(size=13)
        entrees = TestCoherenceDesIcones._navigation(
            TestEchelleDeSurfaces._corps())
        fige = [police.measure(icone + "   ") for icone, _l, _c in entrees]
        calcule = [police.measure(module_app._prefixe_aligne(police, icone, 34))
                   for icone, _l, _c in entrees]
        assert (max(calcule) - min(calcule)) <= (max(fige) - min(fige))

    def test_survit_a_une_police_sans_espace_fin(self, app):
        """Certaines polices ne possèdent pas U+2009 et renvoient 0, ce qui
        provoquerait une division par zéro au moment de construire la barre."""
        import app as module_app

        class PoliceSansEspaceFin:
            def measure(self, texte):
                return 0 if texte == "\u2009" else 4 * len(texte)

        prefixe = module_app._prefixe_aligne(PoliceSansEspaceFin(), "📂", 34)
        assert prefixe.startswith("📂")
        assert len(prefixe) > 1, "aucun espacement produit"


class TestBoutonDeMasse:
    """La cardinalité doit figurer DANS le bouton d'action de masse.

    « Appliquer » nu, à côté d'un libellé disant « aux vidéos affichées » sans
    jamais dire combien, était le seul élément saturé de l'écran Vidéos — et
    l'action la plus lourde de conséquences. Porter le nombre dans le bouton
    est la meilleure protection contre le clic de masse par inadvertance."""

    def test_compte_affiche_et_suit_le_filtre(self, app):
        app._show_tab("browse")
        app.update()
        app.browse_filtered = [{"slug": f"v{i}"} for i in range(74)]
        app._maj_bouton_masse()
        app.update()
        assert "74" in app.browse_mass_btn.cget("text")
        # Le compte doit SUIVRE le filtre : figé, il devient un mensonge, ce
        # qui est pire qu'une absence de compte.
        app.browse_filtered = [{"slug": "v1"} for _ in range(3)]
        app._maj_bouton_masse()
        app.update()
        assert "3" in app.browse_mass_btn.cget("text")
        assert "74" not in app.browse_mass_btn.cget("text")

    def test_singulier(self, app):
        app.browse_filtered = [{"slug": "v1"}]
        app._maj_bouton_masse()
        app.update()
        texte = app.browse_mass_btn.cget("text")
        assert "1 vidéo" in texte and "vidéos" not in texte

    def test_desactive_quand_rien_a_appliquer(self, app):
        """Un bouton actif qui ne fait rien laisse croire à un échec."""
        app.browse_filtered = []
        app._maj_bouton_masse()
        app.update()
        assert app.browse_mass_btn.cget("state") == "disabled"

    def test_teinte_d_alerte_et_non_d_action(self):
        """Ce n'est pas l'opération courante de l'écran mais une opération de
        masse irréversible."""
        corps = TestEchelleDeSurfaces._corps()
        appels = [a for _l, a in TestHierarchieVisuelle._appels(corps, "CTkButton")
                  if "browse_mass_btn" in corps[max(0, corps.index(a) - 120):
                                                corps.index(a) + len(a)]]
        assert appels, "bouton de masse introuvable"
        assert "fg_color=C_ALERTE" in appels[0], (
            "le bouton de masse doit être en teinte d'alerte")


class TestSeparationBarreContenu:
    """Un filet marque la limite barre latérale / contenu.

    L'élévation seule ne suffit pas en mode clair : l'écart mesuré est de 11
    niveaux de gris, soit 26 % en sombre mais 4,7 % en clair. À forte
    luminance, l'œil exige un écart bien plus grand pour percevoir la même
    différence."""

    def test_filet_present(self):
        corps = TestEchelleDeSurfaces._corps()
        assert 'ctk.CTkFrame(self, width=1, corner_radius=0,\n                     fg_color=S_FILET)' in corps, (
            "filet de séparation absent entre la barre latérale et le contenu")


class TestEntetesDePanneaux:
    """Les en-têtes de panneaux ne doivent pas ressembler à des boutons grisés.

    Rendus par CustomTkinter en barre pleine largeur, texte centré, dans un
    gris proche de celui des boutons voisins : trois éléments de même teinte,
    dont deux cliquables et un pas."""

    def test_tous_alignes_a_gauche_et_en_gras(self):
        corps = TestEchelleDeSurfaces._corps()
        fautifs = []
        i = 0
        while True:
            j = corps.find("CTkScrollableFrame(", i)
            if j < 0:
                break
            k, profondeur = j + len("CTkScrollableFrame("), 1
            while profondeur > 0 and k < len(corps):
                if corps[k] == "(":
                    profondeur += 1
                elif corps[k] == ")":
                    profondeur -= 1
                k += 1
            appel = corps[j:k]
            if "label_text=" in appel and (
                    'label_anchor="w"' not in appel or "label_font" not in appel):
                fautifs.append(corps[:j].count("\n") + 1)
            i = k
        assert not fautifs, (
            f"en-têtes centrés ou non gras, lignes {fautifs} (relatives au corps)")


class TestEpinglesEnPied:
    """« Aide » et « À propos » forment DEUX COLONNES ÉGALES, alignées à gauche.

    Posés au `pack` avec `expand=True`, chaque bouton conservait sa largeur
    naturelle — 140 px pour l'un, 68 pour l'autre — et leur texte restait
    centré alors que les dix autres entrées sont alignées à gauche. L'œil
    voyait un décalage."""

    def test_largeurs_egales(self, app):
        app.geometry("1180x760")
        app.update()
        app.update_idletasks()
        aide = app.nav_btns["help"].winfo_width()
        propos = app.nav_btns["about"].winfo_width()
        assert abs(aide - propos) <= 2, (
            f"colonnes inégales : Aide {aide} px, À propos {propos} px")

    def test_textes_alignes_a_gauche(self, app):
        for cle in ("help", "about"):
            assert app.nav_btns[cle].cget("anchor") == "w", (
                f"« {cle} » est centré alors que le reste est aligné à gauche")

    def test_cote_a_cote_sur_une_seule_ligne(self, app):
        """Les épingler sans les compacter n'aurait rien rapporté : ils
        occuperaient la même hauteur ailleurs."""
        app.update()
        app.update_idletasks()
        aide, propos = app.nav_btns["help"], app.nav_btns["about"]
        assert abs(aide.winfo_rooty() - propos.winfo_rooty()) <= 2, (
            "les deux épinglés ne sont pas sur la même ligne")
        assert propos.winfo_rootx() > aide.winfo_rootx()


class TestLibellesDeFiltres:
    """Chaque filtre annonce en permanence CE QU'IL FILTRE.

    Les quatre premiers portaient leur intitulé dans leur valeur par défaut
    (« Tous statuts », « Toutes chaînes »). Dès qu'on filtrait, ces mots
    disparaissaient : l'écran affichait « Public », « MFCA », « Cours » sans
    plus rien dire de ce que chaque valeur filtrait — l'information se perdait
    exactement au moment où le filtre devenait actif.

    Le libellé est AU-DESSUS et non à gauche : mesuré, à gauche il coûterait
    139 px sur une rangée qui n'a que 3 px de marge en fenêtre minimale."""

    FILTRES = ("browse_statut", "browse_encode", "browse_chan",
               "browse_type", "browse_tri", "browse_detect")

    def test_chaque_filtre_a_un_libelle_au_dessus(self, app):
        app._show_tab("browse")
        app.update()
        app.update_idletasks()
        for nom in self.FILTRES:
            menu = getattr(app, nom)
            parent = menu.master
            libelles = [w for w in parent.winfo_children()
                        if isinstance(w, module_ctk().CTkLabel)]
            assert libelles, f"{nom} n'a pas de libellé au-dessus"
            assert libelles[0].winfo_rooty() < menu.winfo_rooty(), (
                f"le libellé de {nom} n'est pas au-dessus du menu")

    def test_la_valeur_ne_reprend_plus_l_intitule(self, app):
        """« Tous statuts » dans la valeur, c'était l'intitulé caché dedans."""
        interdits = ("Tous statuts", "Tout encodage", "Toutes chaînes",
                     "Tous types", "Aucune détection")
        corps = TestEchelleDeSurfaces._corps()
        presents = [m for m in interdits if f'"{m}"' in corps]
        assert not presents, (
            f"intitulés encore enfermés dans les valeurs : {presents}")

    def test_le_filtrage_fonctionne_toujours(self, app):
        """⚠️ Renommer les valeurs casse le filtrage si une comparaison reste
        sur l'ancienne chaîne — le filtre devient alors silencieusement
        inopérant, sans la moindre erreur."""
        app._show_tab("browse")
        base = "https://exemple.invalid/rest"
        app.videos = [
            {"slug": "a", "title": "Anatomie", "is_draft": False, "encoded": True,
             "channel": [f"{base}/channels/1/"], "type": f"{base}/types/1/", "owner": "x"},
            {"slug": "b", "title": "Brouillon", "is_draft": True, "encoded": False,
             "channel": [], "type": f"{base}/types/2/", "owner": "y"},
        ]
        # Clés NORMALISÉES (sans barre finale), comme le fait le chargement réel.
        app.browse_chan_by_url = {f"{base}/channels/1": "MFCA"}
        app.type_map = {"Cours": f"{base}/types/1/"}
        app.browse_chan.configure(values=["Toutes", "MFCA"])
        app.browse_type.configure(values=["Tous", "Cours"])

        def filtrer(**kw):
            app.browse_statut.set(kw.get("st", "Tous"))
            app.browse_encode.set(kw.get("enc", "Tout"))
            app.browse_chan.set(kw.get("ch", "Toutes"))
            app.browse_type.set(kw.get("ty", "Tous"))
            app.browse_detect.set("Aucune")
            app.browse_text.delete(0, "end")
            # Appel DIRECT : `_browse_apply_filter` est temporisé, un test qui
            # ne l'attend pas mesure une liste vide et conclut à tort au bug.
            app._browse_do_filter()
            app.update()
            return len(app.browse_filtered)

        assert filtrer() == 2, "le filtre « tout afficher » ne montre plus rien"
        assert filtrer(st="Brouillon") == 1
        assert filtrer(st="Public") == 1
        assert filtrer(enc="Encodées") == 1
        assert filtrer(ch="MFCA") == 1
        assert filtrer(ty="Cours") == 1

    def test_tient_en_fenetre_minimale(self, app):
        """Les filtres sont sur deux rangées parce qu'ils débordaient déjà :
        sur une seule ligne, huit contrôles réclamaient 1237 px pour 752
        disponibles."""
        app.geometry("1000x660")
        app.update()
        app.update_idletasks()
        try:
            droite = max(getattr(app, n).winfo_rootx() + getattr(app, n).winfo_width()
                         for n in ("browse_statut", "browse_encode",
                                   "browse_chan", "browse_type"))
            assert droite <= app.winfo_width(), (
                f"filtres tronqués : le dernier finit à {droite} px pour une "
                f"fenêtre de {app.winfo_width()}")
            assert app.browse_text.winfo_width() > 60, (
                "le champ de recherche est écrasé par les filtres")
        finally:
            app.geometry("1180x760")
            app.update()


def module_ctk():
    import app as module_app
    return module_app.ctk


class TestPoidsDeLInterface:
    """La bascule clair/sombre parcourt TOUS les widgets de l'application.

    Mesuré : 871 widgets → 85 ms, 1 771 widgets → 175 ms. Sur Windows, comptez
    deux à trois fois plus. Le nombre de widgets n'est donc pas un détail
    d'implémentation : c'est directement la lenteur ressentie à chaque
    bascule."""

    # Relevé de 800 à 860 à l'ajout de l'onglet « Types & disciplines »
    # (+56 widgets, mesuré à 807). Un plafond qu'on relève à chaque ajout ne
    # sert plus à rien : il est là pour signaler une DÉRIVE, pas pour interdire
    # un onglet. Si un ajout coûtait 300 widgets, c'est la construction qu'il
    # faudrait revoir, pas ce chiffre.
    PLAFOND_TOTAL = 860      # application neuve : constaté à 807
    PLAFOND_AIDE = 40        # constaté à 14 ; était à 134

    @staticmethod
    def _compter(widget):
        total = 1
        for enfant in widget.winfo_children():
            total += TestPoidsDeLInterface._compter(enfant)
        return total

    def test_aide_reste_legere(self, app):
        """Dix-sept sections de texte STATIQUE coûtaient 134 widgets — le plus
        lourd des douze onglets, pour la page la moins consultée."""
        poids = self._compter(app.tabs["help"])
        assert poids <= self.PLAFOND_AIDE, (
            f"l'onglet Aide pèse {poids} widgets (plafond {self.PLAFOND_AIDE}) : "
            "il a probablement été reconstruit à coups d'étiquettes.")

    def test_poids_total_maitrise(self):
        """Garde-fou global : un onglet ajouté sans précaution se verrait ici
        plutôt que dans une lenteur inexpliquée.

        ⚠️ Ce test instancie une application NEUVE au lieu d'employer le
        fixture partagé. Deux tentatives ont échoué avant d'en arriver là :
        compter la fenêtre entière incluait les boutons témoins créés par
        d'autres tests, et compter les onglets incluait les listes qu'ils
        avaient remplies (733 widgets au lieu de 659). Un seuil ne veut rien
        dire s'il dépend de l'ordre d'exécution."""
        import app as module_app
        neuve = module_app.App()
        try:
            neuve.update()
            poids = self._compter(neuve)
        finally:
            try:
                neuve.destroy()
            except Exception:
                pass
        assert poids <= self.PLAFOND_TOTAL, (
            f"{poids} widgets dans les onglets (plafond {self.PLAFOND_TOTAL}) : "
            "la bascule de thème ralentit d'autant.")

    def test_titres_de_l_aide_lisibles_dans_les_deux_modes(self, app):
        """Les balises d'une zone de texte n'acceptent qu'une couleur SIMPLE,
        là où le reste emploie des couples résolus par CustomTkinter. Sans
        adaptation explicite, le bleu foncé des titres devient illisible sur
        fond sombre."""
        import app as module_app
        depart = module_app.ctk.get_appearance_mode()
        try:
            couleurs = {}
            for _ in range(2):
                app._basculer_theme()
                app.update()
                mode = module_app.ctk.get_appearance_mode().lower()
                couleurs[mode] = str(app.help_box.tag_cget("titre", "foreground"))
            assert len(set(couleurs.values())) == 2, (
                f"même couleur de titre dans les deux modes : {couleurs}")
        finally:
            if module_app.ctk.get_appearance_mode() != depart:
                app._basculer_theme()
                app.update()


class TestCompilation:
    """Le mode de compilation décide du temps de démarrage.

    En `--onefile`, l'exécutable est une archive auto-extractible : tout
    l'interpréteur Python est décompressé dans un dossier temporaire à CHAQUE
    lancement, avant que quoi que ce soit ne s'affiche. Mesuré côté
    application, il y a déjà 1,3 s d'import et 1,3 s de construction — la
    décompression s'y ajoute intégralement."""

    @staticmethod
    def _workflow() -> str:
        import os
        import app as module_app
        racine = os.path.dirname(os.path.abspath(module_app.__file__))
        chemin = os.path.join(racine, ".github", "workflows", "build.yml")
        return open(chemin, encoding="utf-8").read()

    def test_compilation_en_onedir(self):
        import re
        texte = self._workflow()
        # On ne regarde que les LIGNES DE COMMANDE, les commentaires citant
        # « --onefile » pour l'expliquer étant légitimes.
        # `strip().startswith` et non `in` : sinon « pip install pyinstaller »
        # est pris pour une commande de compilation et fait échouer le test
        # pour une raison qui n'en est pas une.
        commandes = [l for l in texte.split("\n")
                     if l.strip().startswith("pyinstaller ")]
        assert commandes, "aucune commande pyinstaller trouvée"
        fautives = [l for l in commandes if "--onefile" in l]
        assert not fautives, (
            f"compilation encore en --onefile : {fautives}")
        assert all("--onedir" in l for l in commandes), (
            f"commandes sans --onedir : {commandes}")

    def test_installeur_embarque_tout_le_dossier(self):
        """En `--onedir`, ne copier que l'exe donnerait une application qui
        s'installe sans erreur mais refuse de démarrer."""
        texte = self._workflow()
        assert "recursesubdirs" in texte, (
            "l'installeur ne copie pas les sous-dossiers : PodAdmin.exe seul "
            "ne démarre pas en --onedir")
        assert 'Source: "dist\\PodAdmin\\*"' in texte


class TestVerrouillageSuppressionType:
    """⚠️ SUPPRESSION EN CASCADE, ÉTABLIE PAR SONDE SUR L'INSTANCE RÉELLE.

    Supprimer un type y supprime AUSSI ses vidéos. Le serveur ne proteste
    pas : il répond HTTP 204 et la vidéo n'existe plus. Une vidéo de test y
    est réellement passée.

    Un avertissement ne suffit pas — une confirmation se clique, et
    celle-ci se cliquerait au milieu d'une session de rangement. Un seul clic
    détruirait 57 vidéos. La suppression d'un type non vide doit donc être
    IMPOSSIBLE, pas déconseillée."""

    def test_type_non_vide_jamais_supprime(self, app, monkeypatch):
        """Le cœur du garde-fou : l'appel de suppression ne doit pas partir."""
        appels = []
        monkeypatch.setattr(app, "_run",
                            lambda fn, *a: appels.append((fn.__name__, a)))
        fenetres = []
        monkeypatch.setattr(app, "_nomen_refuser_suppression",
                            lambda t, n: fenetres.append((t, n)))

        app._nomen_supprimer({"title": "vidéo", "url": "u"}, "type", 57)

        assert not appels, (
            "une suppression a été lancée sur un type portant 57 vidéos")
        assert fenetres == [("vidéo", 57)], "le refus n'a pas été présenté"

    def test_type_vide_reste_supprimable(self, app, monkeypatch):
        """Le verrou ne doit pas bloquer le cas légitime."""
        ouvertes = []
        monkeypatch.setattr(ctk_module().CTkToplevel, "__init__",
                            lambda self, *a, **k: ouvertes.append(1))
        try:
            app._nomen_supprimer({"title": "Tutoriel", "url": "u"}, "type", 0)
        except Exception:
            pass    # la fenêtre neutralisée lève, seul compte qu'on soit arrivé là
        assert ouvertes, "aucune confirmation proposée pour un type vide"

    def test_discipline_non_concernee(self, app, monkeypatch):
        """Les disciplines ne portent pas de vidéos par ce champ : le verrou
        des types ne doit pas déborder sur elles."""
        refus = []
        monkeypatch.setattr(app, "_nomen_refuser_suppression",
                            lambda t, n: refus.append(t))
        ouvertes = []
        monkeypatch.setattr(ctk_module().CTkToplevel, "__init__",
                            lambda self, *a, **k: ouvertes.append(1))
        try:
            app._nomen_supprimer({"title": "Odontologie", "url": "u"},
                                 "discipline", None)
        except Exception:
            pass
        assert not refus, "le verrou des types s'applique à tort aux disciplines"

    def test_avertissement_visible_dans_l_onglet(self):
        """La cascade doit être annoncée à l'écran, pas seulement dans le code."""
        corps = TestEchelleDeSurfaces._corps()
        assert "les types non " in corps and "verrouillés" in corps, (
            "l'onglet n'annonce pas que les types non vides sont verrouillés")


def ctk_module():
    import app as module_app
    return module_app.ctk
