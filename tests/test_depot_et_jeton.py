"""Correctifs repris du Pod Téléverseur 3.4.2 : dépôt par morceaux et jeton.

Ces défauts ne produisaient aucune erreur visible :
  • un envoi figé attendait pour toujours (délai infini) ;
  • le jeton superutilisateur pouvait partir vers un autre hôte, ou en clair ;
  • une position d'envoi incohérente donnait une vidéo corrompue ;
  • après un 504, la vidéo « retrouvée » par son nom de fichier pouvait être
    celle d'un autre dépôt du compte véhicule — puis réattribuée ;
  • dans le repli automatique, cette récupération plantait (mauvais arguments).

Tout est testé SANS réseau et SANS fenêtre Tk : faux objets et appels des
méthodes non liées de `App`.
"""
import ast
import os
import re
import sys
import threading
from types import SimpleNamespace

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)


def _lire(nom):
    return open(os.path.join(RACINE, nom), encoding="utf-8").read()


class _Rep:
    """Réponse HTTP minimale."""
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data
        self.text = "x" if data is not None else ""
        self.url = ""
        self.headers = {}

    def json(self):
        return self._data


class _SessionEspion:
    """Session qui enregistre chaque requête et renvoie des réponses prévues."""
    def __init__(self, reponses=None):
        self.appels = []
        self.reponses = list(reponses or [])
        self.headers = {}

    def _requete(self, verbe, url, **kw):
        self.appels.append((verbe, url, kw))
        return self.reponses.pop(0) if self.reponses else _Rep(200, {})

    def get(self, url, **kw):
        return self._requete("GET", url, **kw)

    def post(self, url, **kw):
        return self._requete("POST", url, **kw)

    def patch(self, url, **kw):
        return self._requete("PATCH", url, **kw)


def _api(session=None):
    from pod_api import PodAPI
    api = PodAPI("https://videos.exemple.fr", "jeton")
    api.session = session or _SessionEspion()
    return api


# ══════════════════════════════════════════════════════════════════════════
#  1. Délais d'envoi bornés
# ══════════════════════════════════════════════════════════════════════════

class TestDelaisBornes:
    def test_aucun_timeout_none_dans_le_client(self):
        """Recherche dans l'ARBRE du code, pas dans le texte : un commentaire
        qui cite `timeout=None` ne doit pas fausser le résultat."""
        arbre = ast.parse(_lire("pod_api.py"))
        fautifs = [n.lineno for n in ast.walk(arbre)
                   if isinstance(n, ast.keyword) and n.arg == "timeout"
                   and isinstance(n.value, ast.Constant) and n.value.value is None]
        assert not fautifs, f"timeout=None aux lignes {fautifs}"

    def test_depot_et_remplacement_utilisent_upload_timeout(self, tmp_path):
        import pod_api
        fichier = tmp_path / "v.mp4"
        fichier.write_bytes(b"abc")
        espion = _SessionEspion([_Rep(201, {"slug": "s"}), _Rep(200, {"slug": "s"})])
        api = _api(espion)
        api.upload_video(str(fichier), "t", "https://videos.exemple.fr/rest/users/1/",
                         "https://videos.exemple.fr/rest/types/1/")
        api.replace_video_file({"url": "https://videos.exemple.fr/rest/videos/9/"},
                               str(fichier))
        delais = [kw["timeout"] for _, _, kw in espion.appels]
        assert delais == [pod_api.UPLOAD_TIMEOUT] * 2


# ══════════════════════════════════════════════════════════════════════════
#  2. Le jeton ne part que vers l'instance, et en https
# ══════════════════════════════════════════════════════════════════════════

class TestJetonVersLInstanceSeulement:
    def test_adresse_http_refusee_a_la_construction(self):
        from pod_api import PodAPI, PodAPIError
        with pytest.raises(PodAPIError):
            PodAPI("http://videos.exemple.fr", "jeton")

    def test_endpoint_relatif(self):
        assert _api()._abs("/videos/") == "https://videos.exemple.fr/rest/videos/"

    def test_meme_instance_acceptee(self):
        url = "https://videos.exemple.fr/rest/videos/3/"
        assert _api()._abs(url) == url

    def test_meme_instance_en_http_reecrite_en_https(self):
        assert (_api()._abs("http://videos.exemple.fr/rest/videos/3/")
                == "https://videos.exemple.fr/rest/videos/3/")

    @pytest.mark.parametrize("url", [
        "https://autre.exemple.fr/rest/videos/3/",
        "https://videos.exemple.fr.pirate.io/rest/",
        "ftp://videos.exemple.fr/rest/",
        "",
    ])
    def test_autre_hote_ou_adresse_vide_refuses(self, url):
        from pod_api import PodAPIError
        with pytest.raises(PodAPIError):
            _api()._abs(url)

    def test_pagination_ne_suit_pas_un_next_etranger(self):
        from pod_api import PodAPIError
        espion = _SessionEspion([_Rep(200, {
            "results": [{"id": 1}],
            "next": "https://autre.exemple.fr/rest/videos/?page=2"})])
        with pytest.raises(PodAPIError):
            _api(espion).get_all_videos()
        assert len(espion.appels) == 1, "la page étrangère a été demandée"

    def test_pagination_suit_la_meme_instance(self):
        espion = _SessionEspion([
            _Rep(200, {"results": [{"id": 1}],
                       "next": "http://videos.exemple.fr/rest/videos/?page=2"}),
            _Rep(200, {"results": [{"id": 2}], "next": None}),
        ])
        videos = _api(espion).get_all_videos()
        assert [v["id"] for v in videos] == [1, 2]
        assert espion.appels[1][1].startswith("https://"), "page 2 demandée en clair"

    def test_table_des_owners_ne_suit_pas_un_next_etranger(self):
        from pod_api import PodAPIError
        espion = _SessionEspion([_Rep(200, {
            "results": [], "next": "https://autre.exemple.fr/rest/owners/?page=2"})])
        with pytest.raises(PodAPIError):
            _api(espion).get_owners_map()
        assert len(espion.appels) == 1

    def test_remplacement_refuse_une_url_de_video_etrangere(self, tmp_path):
        from pod_api import PodAPIError
        fichier = tmp_path / "v.mp4"
        fichier.write_bytes(b"abc")
        espion = _SessionEspion()
        with pytest.raises(PodAPIError):
            _api(espion).replace_video_file(
                {"url": "https://autre.exemple.fr/rest/videos/9/"}, str(fichier))
        assert not espion.appels

    def test_url_de_compte_vide_refusee_sans_requete(self):
        from pod_api import PodAPIError
        espion = _SessionEspion()
        with pytest.raises(PodAPIError):
            _api(espion).set_user_staff("", True)
        assert not espion.appels

    def test_vignette_telechargee_sans_le_jeton(self, monkeypatch):
        import pod_api
        vus = []
        monkeypatch.setattr(pod_api.requests, "get",
                            lambda url, **kw: vus.append((url, kw)) or _Rep(200))
        espion = _SessionEspion()
        _api(espion).telecharger_media("https://media.ailleurs.fr/img.png")
        assert not espion.appels, "la vignette est passée par la session authentifiée"
        assert vus and "headers" not in vus[0][1]

    def test_methode_morte_retiree(self):
        from pod_api import PodAPI
        assert not hasattr(PodAPI, "set_user_groups")


# ══════════════════════════════════════════════════════════════════════════
#  3. Envoi par morceaux : https et position vérifiée
# ══════════════════════════════════════════════════════════════════════════

def _session_chunk(monkeypatch, reponses, chunk_size=2):
    from pod_chunked import PodChunkedSession
    s = PodChunkedSession("https://videos.exemple.fr", "DEPOT", "mdp")
    s._logged_in = True
    envoyes = []

    def faux_envoi(chunk, start, end, total, filename, upload_id, **kw):
        envoyes.append((start, end, filename))
        return reponses.pop(0)
    monkeypatch.setattr(s, "_send_one_chunk", faux_envoi)
    monkeypatch.setattr(s, "_complete", lambda *a, **k: "slug-final")
    return s, envoyes


class TestEnvoiParMorceaux:
    def test_adresse_http_refusee(self):
        from pod_chunked import PodChunkedError, PodChunkedSession
        with pytest.raises(PodChunkedError):
            PodChunkedSession("http://videos.exemple.fr", "DEPOT", "mdp")

    def test_offset_coherent_accepte(self, tmp_path, monkeypatch):
        f = tmp_path / "v.mp4"
        f.write_bytes(b"abcde")
        s, envoyes = _session_chunk(monkeypatch, [
            {"upload_id": "u", "offset": 2}, {"offset": 4}, {"offset": 5}])
        assert s.upload_video_chunked(str(f), chunk_size=2) == "slug-final"
        assert [(a, b) for a, b, _ in envoyes] == [(0, 1), (2, 3), (4, 4)]

    def test_offset_incoherent_interrompt_l_envoi(self, tmp_path, monkeypatch):
        """Le serveur annonce 1 octet reçu au lieu de 2 : continuer
        enverrait les octets suivants sous un Content-Range faux."""
        from pod_chunked import PodChunkedError
        f = tmp_path / "v.mp4"
        f.write_bytes(b"abcde")
        s, envoyes = _session_chunk(monkeypatch, [{"upload_id": "u", "offset": 1}])
        with pytest.raises(PodChunkedError):
            s.upload_video_chunked(str(f), chunk_size=2)
        assert len(envoyes) == 1, "l'envoi a continué après une position incohérente"

    def test_marqueur_dans_le_nom_transmis(self, tmp_path, monkeypatch):
        f = tmp_path / "cours.mp4"
        f.write_bytes(b"ab")
        s, envoyes = _session_chunk(monkeypatch, [{"upload_id": "u", "offset": 2}])
        s.upload_video_chunked(str(f), chunk_size=2, marqueur="pa0123456789ab")
        assert envoyes[0][2] == "cours pa0123456789ab.mp4"


# ══════════════════════════════════════════════════════════════════════════
#  4. Récupération après un 504 : la BONNE vidéo, ou aucune
# ══════════════════════════════════════════════════════════════════════════

VEHICULE = "https://videos.exemple.fr/rest/users/1/"


def _faux_app(candidats):
    return SimpleNamespace(
        api=SimpleNamespace(search_videos=lambda params: list(candidats)),
        _ui=lambda *a, **k: None, _log=lambda *a: None,
        global_msg=SimpleNamespace(configure=lambda **k: None))


def _video(slug, titre, owner=VEHICULE):
    return {"slug": slug, "title": titre, "owner": owner}


class TestRecuperationApres504:
    MARQUEUR = "pa0123456789ab"

    def _verifier(self, candidats, monkeypatch, vehicule=VEHICULE, delai=5):
        import app as A
        monkeypatch.setattr(A.cfg, "CHUNK_VERIFY_TIMEOUT_S", delai)
        monkeypatch.setattr(A.cfg, "CHUNK_VERIFY_INTERVAL_S", 0.05)
        return A.App._verify_chunked_creation(_faux_app(candidats), self.MARQUEUR, vehicule)

    def test_retrouve_la_video_marquee_parmi_des_homonymes(self, monkeypatch):
        """Même nom de fichier, même compte véhicule, autre dépôt : c'est
        exactement la vidéo que l'ancienne recherche par nom pouvait prendre."""
        v = self._verifier([
            _video("autre", "cours"),
            _video("la-bonne", f"cours {self.MARQUEUR}"),
        ], monkeypatch)
        assert v["slug"] == "la-bonne"

    def test_proprietaire_compare_strictement(self, monkeypatch):
        """`/users/1` n'est pas `/users/18` (l'ancienne inclusion de chaîne
        les confondait)."""
        v = self._verifier(
            [_video("x", f"cours {self.MARQUEUR}", "https://videos.exemple.fr/rest/users/18/")],
            monkeypatch, delai=0.2)
        assert v is None

    def test_plusieurs_videos_marquees_refus_de_choisir(self, monkeypatch):
        from pod_api import PodAPIError
        with pytest.raises(PodAPIError):
            self._verifier([_video("a", f"x {self.MARQUEUR}"),
                            _video("b", f"y {self.MARQUEUR}")], monkeypatch)

    def test_le_depot_transmet_le_meme_marqueur_a_l_envoi_et_a_la_recherche(self):
        """Régression du repli automatique : `_verify_chunked_creation` y était
        appelée avec (it, owner_url) — une TypeError à chaque 504."""
        import app as A
        from pod_chunked import PodChunkedError
        vus = {}

        class _Morceaux:
            def upload_video_chunked(self, path, **kw):
                vus["envoi"] = kw["marqueur"]
                raise PodChunkedError("passerelle", status=504)

        def verifier(marqueur, vehicule):
            vus["recherche"] = (marqueur, vehicule)
            return {"slug": "retrouvee", "url": "u"}

        faux = SimpleNamespace(
            _nouveau_marqueur=A.App._nouveau_marqueur,
            _verify_chunked_creation=verifier, vehicle_owner_url=VEHICULE,
            _ui=lambda *a, **k: None, _log=lambda *a: None,
            _set_item_status=lambda *a: None, api=None)
        it = SimpleNamespace(path="v.mp4", title="Cours")
        slug, video = A.App._deposer_par_morceaux(faux, _Morceaux(), it, None, None)
        assert slug == "retrouvee"
        assert vus["recherche"] == (vus["envoi"], VEHICULE)

    def test_tous_les_appels_de_verification_ont_le_bon_nombre_d_arguments(self):
        """Garde-fou statique : le défaut d'origine était un appel à deux
        arguments d'une fonction qui en attend trois (self compris)."""
        arbre = ast.parse(_lire("app.py"))
        definition = next(n for n in ast.walk(arbre) if isinstance(n, ast.FunctionDef)
                          and n.name == "_verify_chunked_creation")
        attendus = len(definition.args.args) - 1
        appels = [n for n in ast.walk(arbre) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "_verify_chunked_creation"]
        assert appels
        for n in appels:
            assert len(n.args) + len(n.keywords) == attendus, f"ligne {n.lineno}"


# ══════════════════════════════════════════════════════════════════════════
#  5. Liste des vidéos et sélection multiple
# ══════════════════════════════════════════════════════════════════════════

class TestListeDesVideos:
    def test_relecture_forcee_pendant_un_scan_est_enchainee(self):
        """Un dépôt qui se termine pendant un scan ne doit pas se contenter de
        ce scan, lancé avant lui : les nouvelles vidéos y manqueraient."""
        import app as A
        faux = SimpleNamespace(videos=[{"slug": "a"}], videos_loading=True,
                               _videos_rescan=False, _videos_waiters=[],
                               _videos_etat_lock=threading.Lock())
        A.App.ensure_videos(faux, on_ready=lambda: None, force=True)
        assert faux._videos_rescan is True
        assert len(faux._videos_waiters) == 1

        scans = []
        faux.api = SimpleNamespace(get_all_videos=lambda **k: scans.append(1) or [])
        faux._videos_lock = threading.RLock()
        faux._ui = lambda *a, **k: None
        faux._log = lambda *a: None
        faux._flush_videos_waiters = lambda: None
        A.App._do_load_videos(faux)
        assert len(scans) == 2, "la relecture demandée pendant le scan n'a pas eu lieu"
        assert faux.videos_loading is False and faux._videos_rescan is False

    def test_une_seule_definition_de_la_selection_multiple(self):
        """Le type et les disciplines en lot lisaient tout le magasin, le
        reste des actions la liste filtrée : une vidéo cochée puis sortie du
        filtre restait visée sans être comptée."""
        import app as A
        assert not hasattr(A.App, "_browse_multi_videos")
        faux = SimpleNamespace(browse_filtered=[{"slug": "a"}, {"slug": "b"}],
                               browse_multi={"b", "cachee"})
        assert [v["slug"] for v in A.App._browse_videos_multi(faux)] == ["b"]


# ══════════════════════════════════════════════════════════════════════════
#  6. Aide, workflows, métadonnées
# ══════════════════════════════════════════════════════════════════════════

class TestCoherenceDesTextes:
    def test_l_aide_n_ecrit_plus_le_seuil_en_dur(self):
        """Le seuil est passé de 500 à 150 Mo ; l'aide annonçait encore 500."""
        chaines = [n.value for n in ast.walk(ast.parse(_lire("app.py")))
                   if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        assert not [c for c in chaines if re.search(r"\b500 Mo\b", c)]

    @pytest.mark.parametrize("nom", ["build.yml", "qualite.yml"])
    def test_workflows_en_lecture_seule(self, nom):
        w = _lire(f".github/workflows/{nom}")
        assert re.search(r"^permissions:\n  contents: read", w, re.M), (
            "pas de permissions en lecture seule à la racine")
        actif = "\n".join(l for l in w.splitlines() if not l.strip().startswith("#"))
        assert "contents: write" not in actif

    @pytest.mark.parametrize("nom", ["app.py", "config.py", "pod_api.py",
                                     "pod_chunked.py", "version.txt"])
    def test_aucune_adresse_personnelle_dans_les_fichiers_livres(self, nom):
        """version.txt alimente les métadonnées de PodAdmin.exe, publié sur le
        dépôt PUBLIC : l'adresse y était lisible par tous."""
        assert "gmail" not in _lire(nom).lower()
