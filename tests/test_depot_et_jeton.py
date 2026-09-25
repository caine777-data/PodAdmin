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

        def verifier(marqueur, vehicule, annuler=None, delai_s=None):
            vus["recherche"] = (marqueur, vehicule)
            vus["annuler"] = annuler
            return {"slug": "retrouvee", "url": "u"}

        faux = SimpleNamespace(
            _nouveau_marqueur=A.App._nouveau_marqueur,
            _verify_chunked_creation=verifier, vehicle_owner_url=VEHICULE,
            _ui=lambda *a, **k: None, _log=lambda *a: None,
            _set_item_status=lambda *a: None, api=None)
        it = SimpleNamespace(path="v.mp4", title="Cours")
        arret = threading.Event().is_set
        slug, video = A.App._deposer_par_morceaux(faux, _Morceaux(), it, None, None, arret)
        assert slug == "retrouvee"
        assert vus["recherche"] == (vus["envoi"], VEHICULE)
        assert vus["annuler"] is arret, "l'attente après 504 ne reçoit pas l'arrêt"

    @pytest.mark.parametrize("code, delai", [(504, "CHUNK_VERIFY_TIMEOUT_S"),
                                             (502, "CHUNK_VERIFY_TIMEOUT_502_S"),
                                             (503, "CHUNK_VERIFY_TIMEOUT_502_S")])
    def test_attente_longue_seulement_pour_un_504(self, code, delai):
        """Un 502 est tombé 44 s après le début d'un envoi et la vidéo n'est
        jamais apparue : 30 min d'attente pour rien, tout le lot bloqué.
        Seul le 504 (Pod continue de son côté) justifie l'attente longue."""
        import app as A
        from pod_chunked import PodChunkedError
        vus = {}

        class _Morceaux:
            def upload_video_chunked(self, path, **kw):
                raise PodChunkedError("passerelle", status=code)

        def verifier(marqueur, vehicule, annuler=None, delai_s=None):
            vus["delai"] = delai_s
            return {"slug": "s", "url": "u"}

        faux = SimpleNamespace(
            _nouveau_marqueur=A.App._nouveau_marqueur, _verify_chunked_creation=verifier,
            vehicle_owner_url=VEHICULE, _ui=lambda *a, **k: None, _log=lambda *a: None,
            _set_item_status=lambda *a: None, api=None)
        A.App._deposer_par_morceaux(faux, _Morceaux(), SimpleNamespace(path="v", title="T"),
                                    None, None)
        assert vus["delai"] == getattr(A.cfg, delai)
        assert A.cfg.CHUNK_VERIFY_TIMEOUT_502_S < A.cfg.CHUNK_VERIFY_TIMEOUT_S

    def test_tous_les_appels_de_verification_ont_le_bon_nombre_d_arguments(self):
        """Garde-fou statique : le défaut d'origine était un appel à deux
        arguments d'une fonction qui en attend trois (self compris)."""
        arbre = ast.parse(_lire("app.py"))
        definition = next(n for n in ast.walk(arbre) if isinstance(n, ast.FunctionDef)
                          and n.name == "_verify_chunked_creation")
        maximum = len(definition.args.args) - 1              # sans self
        minimum = maximum - len(definition.args.defaults)    # sans les facultatifs
        appels = [n for n in ast.walk(arbre) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "_verify_chunked_creation"]
        assert appels
        for n in appels:
            assert minimum <= len(n.args) + len(n.keywords) <= maximum, f"ligne {n.lineno}"


# ══════════════════════════════════════════════════════════════════════════
#  4 bis. Interruption du téléversement, y compris en cours de fichier
# ══════════════════════════════════════════════════════════════════════════

class TestInterruption:
    def test_envoi_direct_arrete_en_cours_de_fichier(self, tmp_path):
        """Sur un VRAI serveur local : l'arrêt doit couper la requête au bloc
        suivant, et non attendre la fin du fichier. On vérifie aussi que
        `requests` laisse remonter l'exception telle quelle (une enveloppe
        en ConnectionError déclencherait les nouvelles tentatives)."""
        import time
        from http.server import BaseHTTPRequestHandler, HTTPServer

        from pod_api import EnvoiAnnule

        class _Recepteur(BaseHTTPRequestHandler):
            def do_POST(self):
                reste = int(self.headers.get("Content-Length", 0))
                while reste > 0:
                    bloc = self.rfile.read(min(65536, reste))
                    if not bloc:
                        break
                    reste -= len(bloc)
                self.send_response(201)
                self.end_headers()

            def log_message(self, *a):
                pass

        class _Serveur(HTTPServer):
            def handle_error(self, *a):      # connexion coupée par le client : attendu
                pass

        serveur = _Serveur(("127.0.0.1", 0), _Recepteur)
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        try:
            fichier = tmp_path / "gros.mp4"
            fichier.write_bytes(os.urandom(20 * 1024 * 1024))
            api = _api(None)
            import requests
            api.session = requests.Session()
            api.rest = f"http://127.0.0.1:{serveur.server_address[1]}/rest"
            envoyes = []
            debut = time.time()
            with pytest.raises(EnvoiAnnule):
                api.upload_video(str(fichier), "t", "o", "ty",
                                 progress_cb=lambda s, t: envoyes.append(s),
                                 annuler=lambda: bool(envoyes) and envoyes[-1] > 2 * 1024 * 1024)
            assert envoyes[-1] < 5 * 1024 * 1024, "l'envoi a continué après l'arrêt"
            assert time.time() - debut < 10
        finally:
            serveur.shutdown()

    def test_envoi_par_morceaux_arrete_avant_la_finalisation(self, tmp_path, monkeypatch):
        """Arrêt entre deux morceaux : la finalisation, qui crée la vidéo,
        ne doit pas avoir lieu."""
        from pod_chunked import EnvoiAnnule
        f = tmp_path / "v.mp4"
        f.write_bytes(b"abcdef")
        s, envoyes = _session_chunk(monkeypatch, [
            {"upload_id": "u", "offset": 2}, {"offset": 4}, {"offset": 6}])
        finalise = []
        monkeypatch.setattr(s, "_complete", lambda *a, **k: finalise.append(1))
        with pytest.raises(EnvoiAnnule):
            s.upload_video_chunked(str(f), chunk_size=2,
                                   annuler=lambda: len(envoyes) >= 1)
        assert len(envoyes) == 1 and not finalise

    def test_attente_apres_504_interrompue_en_moins_d_une_seconde(self, monkeypatch):
        """Pause de sondage de 15 s : l'arrêt ne doit pas l'attendre. Et la
        vidéo existant peut-être, l'annulation le signale (`a_verifier`)."""
        import time

        import app as A
        from pod_api import EnvoiAnnule
        monkeypatch.setattr(A.cfg, "CHUNK_VERIFY_TIMEOUT_S", 60)
        monkeypatch.setattr(A.cfg, "CHUNK_VERIFY_INTERVAL_S", 15)
        top = time.time() + 0.3
        debut = time.time()
        with pytest.raises(EnvoiAnnule) as info:
            A.App._verify_chunked_creation(_faux_app([]), "pa0123456789ab", VEHICULE,
                                           lambda: time.time() > top)
        assert time.time() - debut < 1.5
        assert info.value.a_verifier is True
        assert "pa0123456789ab" in str(info.value), "le Journal doit dire quoi chercher"


def _lot(items, upload):
    """Faux App pour `_do_batch_upload` : widgets simulés, API factice."""
    from unittest.mock import MagicMock

    import app as A
    faux = MagicMock()
    faux.items = items
    faux.api = SimpleNamespace(upload_video=upload, set_disciplines=lambda *a: None,
                               launch_encoding=lambda *a: None)
    faux.depot_interrompu = threading.Event()
    faux.config_data = {"url": "https://videos.exemple.fr"}
    faux.additional_owner_urls = []
    faux.site_urls = []
    faux._file_size = A.App._file_size
    faux._est_coupure_reseau = A.App._est_coupure_reseau
    faux._cle_fichier = A.App._cle_fichier
    faux.deposes_session = {}
    faux.appels_ui = []
    faux._ui = lambda fn, *a, **k: faux.appels_ui.append((fn, a))
    return faux


def _bilan(faux):
    """Arguments passés à `_on_batch_done` (dernier appel via _ui)."""
    return next(a for fn, a in reversed(faux.appels_ui) if fn is faux._on_batch_done)


class TestInterruptionDuLot:
    def _items(self, n):
        import app as A
        return [A.UploadItem(f"video{i}.mp4") for i in range(n)]

    def test_arret_demande_avant_une_video_rien_n_est_envoye(self):
        import app as A
        envois = []
        faux = _lot(self._items(2), lambda *a, **k: envois.append(a) or {"slug": "s"})
        faux.depot_interrompu.set()
        A.App._do_batch_upload(faux, "owner", "type", True, False)
        assert not envois
        assert _bilan(faux) == (0, 2, True)

    def test_arret_pendant_un_envoi_n_est_ni_un_echec_ni_suivi_du_suivant(self):
        import app as A
        from pod_api import EnvoiAnnule
        envois = []

        def envoi(*a, **k):
            envois.append(k["annuler"])
            raise EnvoiAnnule()
        items = self._items(2)
        faux = _lot(items, envoi)
        A.App._do_batch_upload(faux, "owner", "type", True, False)
        assert len(envois) == 1, "la vidéo suivante est partie après l'arrêt"
        assert envois[0] == faux.depot_interrompu.is_set, "l'arrêt n'est pas transmis à l'envoi"
        assert not items[0].done and not items[0].a_verifier
        statuts = [a[1] for fn, a in faux.appels_ui if fn is faux._set_item_status]
        assert "⏹ interrompu" in statuts and "❌ échec" not in statuts
        assert _bilan(faux) == (0, 2, True)

    def test_video_a_verifier_jamais_renvoyee(self):
        """Arrêt pendant l'attente d'un 504 : la vidéo existe peut-être. La
        relance du lot ne doit pas la renvoyer (doublon)."""
        import app as A
        from pod_api import EnvoiAnnule
        items = self._items(1)
        faux = _lot(items, lambda *a, **k: (_ for _ in ()).throw(
            EnvoiAnnule("peut-être créée", a_verifier=True)))
        A.App._do_batch_upload(faux, "owner", "type", True, False)
        assert items[0].a_verifier is True

        envois = []
        faux2 = _lot(items, lambda *a, **k: envois.append(1) or {"slug": "s"})
        A.App._do_batch_upload(faux2, "owner", "type", True, False)
        assert not envois


# ══════════════════════════════════════════════════════════════════════════
#  4 ter. Liste de téléversement modifiée pendant ou après un lot
# ══════════════════════════════════════════════════════════════════════════

class TestListePendantEtApresUnLot:
    def test_fichier_ajoute_pendant_le_lot_part_a_la_suite(self):
        """La boucle suit la liste vivante : ajouté pendant l'envoi du
        premier, le second part dans le même lot, et le total suit."""
        import app as A
        items = [A.UploadItem("premier.mp4")]
        envoyes = []

        def envoi(path, *a, **k):
            envoyes.append(os.path.basename(path))
            if len(envoyes) == 1:
                items.append(A.UploadItem("ajoute_en_cours.mp4"))
            return {"slug": f"s{len(envoyes)}", "url": "u"}
        faux = _lot(items, envoi)
        A.App._do_batch_upload(faux, "owner", "type", True, False)
        assert envoyes == ["premier.mp4", "ajoute_en_cours.mp4"]
        assert _bilan(faux) == (2, 2, False)

    def test_envoi_reussi_memorise_pour_la_session(self):
        import app as A
        items = [A.UploadItem("cours.mp4")]
        faux = _lot(items, lambda *a, **k: {"slug": "cours-mp4", "url": "u"})
        A.App._do_batch_upload(faux, "owner", "type", True, False)
        heure, slug = faux.deposes_session[A.App._cle_fichier("cours.mp4")]
        assert slug == "cours-mp4" and re.match(r"\d\d:\d\d$", heure)

    @pytest.mark.parametrize("methode", ["_remove_item", "_clear_items", "_retirer_terminees"])
    def test_aucun_retrait_pendant_un_lot(self, methode):
        """Retirer une ligne pendant l'envoi décalait les index : la vidéo
        suivante était sautée sans un mot."""
        import app as A
        item = A.UploadItem("a.mp4")
        item.done = True
        faux = SimpleNamespace(items=[item], depot_en_cours=True,
                               _refresh_list=lambda: pytest.fail("liste modifiée"))
        args = (item,) if methode == "_remove_item" else ()
        getattr(A.App, methode)(faux, *args)
        assert faux.items == [item]


def _ajout(items=(), deposes=None, en_cours=False):
    from unittest.mock import MagicMock

    import app as A
    faux = MagicMock()
    faux.items = list(items)
    faux.deposes_session = dict(deposes or {})
    faux.depot_en_cours = en_cours
    faux._cle_fichier = A.App._cle_fichier
    return faux


def _message(faux):
    return faux.global_msg.configure.call_args.kwargs["text"]


class TestAjoutDeFichiers:
    def test_meme_fichier_ecrit_autrement_n_entre_pas_deux_fois(self):
        """Sélecteur et glisser-déposer n'écrivent pas le chemin pareil."""
        import app as A
        faux = _ajout([A.UploadItem(os.path.join(RACINE, "Cours.mp4"))])
        autre_ecriture = os.path.join(RACINE, "Cours.mp4").replace(os.sep, "/")
        if os.name == "nt":
            autre_ecriture = autre_ecriture.upper()
        assert A.App._add_paths(faux, [autre_ecriture]) == 0
        assert len(faux.items) == 1
        assert "1 déjà dans la liste" in _message(faux)

    def test_selecteur_annule_ne_dit_rien(self):
        import app as A
        faux = _ajout()
        assert A.App._add_paths(faux, ()) == 0
        faux.global_msg.configure.assert_not_called()

    def test_fichier_deja_envoye_demande_confirmation(self, monkeypatch):
        """Envoyé, retiré de la liste, puis réajouté : doublon sur Pod si l'on
        ne prévient pas."""
        import app as A
        chemin = os.path.join(RACINE, "deja.mp4")
        questions = []
        monkeypatch.setattr(A.messagebox, "askyesno",
                            lambda titre, texte: questions.append(texte) or False)
        faux = _ajout(deposes={A.App._cle_fichier(chemin): ("21:46", "0195-deja")})
        assert A.App._add_paths(faux, [chemin]) == 0
        assert questions and "0195-deja" in questions[0]
        assert "1 déjà envoyée(s) non ajoutée(s)" in _message(faux)

        monkeypatch.setattr(A.messagebox, "askyesno", lambda *a: True)
        assert A.App._add_paths(faux, [chemin]) == 1

    def test_ajout_pendant_un_lot_annonce_qu_il_part_a_la_suite(self):
        import app as A
        faux = _ajout(en_cours=True)
        A.App._add_paths(faux, [os.path.join(RACINE, "nouveau.mp4")])
        assert "à la suite du lot en cours" in _message(faux)


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
