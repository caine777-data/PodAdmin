"""Intégration de SousTitreur, étape 2 : client Pod fusionné.

Les méthodes de lecture et d'écriture de SousTitreur vivent désormais dans
`pod_api.PodAPI`, avec les protections de la 1.9.1. Tout est testé sur un
faux serveur Pod en mémoire : aucun réseau, aucune écriture réelle.
"""

import json
import os
import sys
from urllib.parse import urlsplit

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

BASE = "https://videos.exemple.fr"
REST = f"{BASE}/rest"
PROPRIO = f"{REST}/users/1/"
VIDEO_URL = f"{REST}/videos/202/"
VTT = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nBonjour à tous.\n"


class _Rep:
    def __init__(self, status=200, data=None, texte=None, url=""):
        self.status_code = status
        self._data = data
        self.text = texte if texte is not None else (json.dumps(data) if data is not None else "")
        self.url = url
        self.headers = {}
        self.encoding = None

    def json(self):
        return self._data


class FauxPod:
    """Session factice : routes de Pod utiles à l'enrichissement, état en
    mémoire, et journal de chaque requête (verbe, URL)."""

    def __init__(self):
        self.headers = {}
        self.appels = []
        self.video = {
            "id": 202,
            "url": VIDEO_URL,
            "slug": "0202-neolithique",
            "owner": PROPRIO,
            "title": "Les métropoles",
            "description": "<p>Ancienne</p>",
            "tags": 'archeologie "age du bronze"',
            "discipline": [f"{REST}/discipline/1/"],
            "type": f"{REST}/types/1/",
        }
        self.pistes = {
            f"{REST}/tracks/9/": {
                "url": f"{REST}/tracks/9/",
                "video": f"{REST}/videos/7/",
                "lang": "fr",
                "kind": "subtitles",
                "src": f"{REST}/files/90/",
            }
        }
        self.fichiers = {
            f"{REST}/files/90/": {"url": f"{REST}/files/90/", "file": f"{BASE}/media/a.vtt"}
        }
        self.medias = {f"{BASE}/media/a.vtt": "WEBVTT\n\nautre vidéo"}
        self.dossiers = [
            {"url": f"{REST}/folders/5/", "name": "0202-neolithique", "owner": PROPRIO}
        ]
        self.echec_piste = 0  # nombre de créations de piste à faire échouer
        self.echec_suppr_fichier = False
        self._n = 100

    def ajouter_piste(self, lang="fr", kind="subtitles", contenu="WEBVTT\n\nancienne"):
        self._n += 1
        f = {"url": f"{REST}/files/{self._n}/", "file": f"{BASE}/media/f{self._n}.vtt"}
        self.fichiers[f["url"]] = f
        self.medias[f["file"]] = contenu
        t = {
            "url": f"{REST}/tracks/{self._n}/",
            "video": VIDEO_URL,
            "lang": lang,
            "kind": kind,
            "src": f["url"],
        }
        self.pistes[t["url"]] = t
        return t

    def _liste(self, elements):
        return _Rep(200, {"count": len(elements), "next": None, "results": list(elements)})

    def _repondre(self, verbe, url, params=None, json_=None, data=None):
        self.appels.append((verbe, url))
        chemin = urlsplit(url).path
        if verbe == "GET":
            if url in self.medias:
                return _Rep(200, texte=self.medias[url])
            if chemin == "/rest/tracks/":
                return self._liste(self.pistes.values())
            if chemin in ("/rest/encodings_audio/", "/rest/encodings_video/"):
                autre = {
                    "video": f"{REST}/videos/7/",
                    "encoding_format": "audio/mp3",
                    "source_file": f"{BASE}/media/autre.mp3",
                    "name": "audio",
                }
                return self._liste(
                    [
                        autre,
                        {
                            "video": VIDEO_URL,
                            "encoding_format": "audio/mp3",
                            "source_file": f"{BASE}/media/202.mp3",
                            "name": "audio",
                        },
                        {
                            "video": VIDEO_URL,
                            "encoding_format": "video/mp4",
                            "source_file": f"{BASE}/media/202_360.mp4",
                            "name": "360p",
                        },
                        {
                            "video": VIDEO_URL,
                            "encoding_format": "video/mp4",
                            "source_file": f"{BASE}/media/202_720.mp4",
                            "name": "720p",
                        },
                    ]
                )
            if url in self.fichiers:
                return _Rep(200, self.fichiers[url])
            if chemin == "/rest/folders/":
                return self._liste(self.dossiers)
            if chemin == "/rest/videos/202/":
                return _Rep(200, dict(self.video))
            if chemin == "/rest/discipline/":
                return self._liste(
                    [
                        {"title": "Histoire", "url": f"{REST}/discipline/1/"},
                        {"title": "Archéologie", "url": f"{REST}/discipline/2/"},
                    ]
                )
            if chemin == "/rest/types/":
                return self._liste(
                    [
                        {"title": "Cours", "url": f"{REST}/types/1/"},
                        {"title": "Conférence", "url": f"{REST}/types/2/"},
                    ]
                )
        if verbe == "POST" and chemin == "/rest/files/":
            self._n += 1
            f = {"url": f"{REST}/files/{self._n}/", "file": f"{BASE}/media/f{self._n}.vtt"}
            self.fichiers[f["url"]] = f
            return _Rep(201, f)
        if verbe == "POST" and chemin == "/rest/tracks/":
            if self.echec_piste:
                self.echec_piste -= 1
                return _Rep(500, {"detail": "erreur"})
            self._n += 1
            t = {"url": f"{REST}/tracks/{self._n}/", **json_}
            self.pistes[t["url"]] = t
            return _Rep(201, t)
        if verbe == "DELETE" and url in self.pistes:
            del self.pistes[url]
            return _Rep(204)
        if verbe == "DELETE" and url in self.fichiers:
            if self.echec_suppr_fichier:
                return _Rep(500, {"detail": "erreur"})
            del self.fichiers[url]
            return _Rep(204)
        if verbe == "PATCH" and chemin == "/rest/videos/202/":
            self.video.update(json_)
            return _Rep(200, dict(self.video))
        return _Rep(404, {"detail": "inconnu"})

    def get(self, url, params=None, **kw):
        return self._repondre("GET", url, params)

    def post(self, url, json=None, data=None, **kw):
        return self._repondre("POST", url, json_=json, data=data)

    def patch(self, url, json=None, **kw):
        return self._repondre("PATCH", url, json_=json)

    def delete(self, url, **kw):
        return self._repondre("DELETE", url)


@pytest.fixture
def pod():
    from pod_api import PodAPI

    api = PodAPI(BASE, "jeton")
    api.session = FauxPod()
    return api


def _ecritures(api):
    return [a for a in api.session.appels if a[0] != "GET"]


# ══════════════════════════════ Lecture ════════════════════════════════════


class TestLecture:
    def test_pistes_de_cette_video_seulement(self, pod):
        """Le serveur renvoie aussi une piste d'une AUTRE vidéo : écartée."""
        mienne = pod.session.ajouter_piste()
        assert [t["url"] for t in pod.pistes(pod.session.video)] == [mienne["url"]]

    def test_mp3_et_mp4_de_cette_video(self, pod):
        v = pod.session.video
        assert pod.mp3(v) == f"{BASE}/media/202.mp3"
        assert pod.mp4(v) == f"{BASE}/media/202_720.mp4", "le 720p doit être préféré"

    def test_piste_lue_avec_le_jeton_sur_l_instance(self, pod, monkeypatch):
        """Vidéo en brouillon : son fichier peut exiger le jeton. Sur l'instance,
        la règle de la 1.9.1 l'autorise."""
        import pod_api

        monkeypatch.setattr(
            pod_api.requests, "get", lambda *a, **k: pytest.fail("lecture anonyme sur l'instance")
        )
        t = pod.session.ajouter_piste(contenu="WEBVTT\n\nmon texte")
        assert pod.lire_piste(t) == "WEBVTT\n\nmon texte"

    def test_piste_sur_un_autre_hote_lue_sans_jeton(self, pod, monkeypatch):
        import pod_api

        anonymes = []
        monkeypatch.setattr(
            pod_api.requests,
            "get",
            lambda url, **k: anonymes.append(url) or _Rep(200, texte="WEBVTT\n\nx"),
        )
        t = pod.session.ajouter_piste()
        pod.session.fichiers[t["src"]]["file"] = "https://media.ailleurs.fr/x.vtt"
        assert pod.lire_piste(t).startswith("WEBVTT")
        assert anonymes == ["https://media.ailleurs.fr/x.vtt"]
        assert ("GET", "https://media.ailleurs.fr/x.vtt") not in pod.session.appels

    def test_src_etranger_refuse_sans_requete(self, pod):
        from pod_api import PodAPIError

        with pytest.raises(PodAPIError):
            pod.lire_piste({"src": "https://pirate.exemple.org/rest/files/1/"})
        assert not any("pirate" in u for _, u in pod.session.appels)

    def test_lien_et_identifiant(self, pod):
        from pod_api import identifiant_depuis_lien

        assert pod.lien_public(pod.session.video) == f"{BASE}/video/0202-neolithique/"
        assert identifiant_depuis_lien(f"{BASE}/video/0019-mon-titre/") == 19
        assert identifiant_depuis_lien("0019-mon-titre") == 19
        assert identifiant_depuis_lien("19") == 19
        assert identifiant_depuis_lien("cours de chimie") is None


# ══════════════════════════ Publication de pistes ══════════════════════════


class TestPublicationDePiste:
    def test_ajout_simple(self, pod):
        r = pod.publier_piste(pod.session.video, "fr", "subtitles", VTT)
        assert r["remplacee"] == "" and r["sauvegarde"] == ""
        verbes = [v for v, _ in _ecritures(pod)]
        assert verbes == ["POST", "POST"], "un fichier puis une piste, rien d'autre"

    def test_piste_existante_bloque_sans_demande_de_remplacement(self, pod):
        from pod_api import PodAPIError

        pod.session.ajouter_piste("fr", "subtitles")
        with pytest.raises(PodAPIError):
            pod.publier_piste(pod.session.video, "fr", "subtitles", VTT)
        assert not _ecritures(pod), "rien ne doit être écrit"

    def test_etat_change_depuis_l_ouverture_refuse(self, pod):
        """L'utilisateur a choisi de remplacer une piste qui n'existe plus."""
        from pod_api import PodAPIError

        disparue = {"url": f"{REST}/tracks/999/", "src": f"{REST}/files/999/"}
        with pytest.raises(PodAPIError):
            pod.publier_piste(pod.session.video, "fr", "subtitles", VTT, remplacer=disparue)
        assert not _ecritures(pod)

    @pytest.mark.parametrize("kind, contenu", [("chapters", VTT), ("subtitles", "pas du vtt")])
    def test_entree_invalide_refusee_avant_toute_requete(self, pod, kind, contenu):
        from pod_api import PodAPIError

        with pytest.raises(PodAPIError):
            pod.publier_piste(pod.session.video, "fr", kind, contenu)
        assert not pod.session.appels

    def test_remplacement_sauvegarde_avant_suppression(self, pod, tmp_path):
        ancienne = pod.session.ajouter_piste(contenu="WEBVTT\n\nancien texte")
        ancien_fichier = ancienne["src"]
        r = pod.publier_piste(
            pod.session.video,
            "fr",
            "subtitles",
            VTT,
            remplacer=ancienne,
            dossier_sauvegarde=str(tmp_path),
        )
        assert open(r["sauvegarde"], encoding="utf-8").read() == "WEBVTT\n\nancien texte"
        ordre = [(v, u) for v, u in _ecritures(pod)]
        assert ordre[0][0] == "POST" and ordre[0][1].endswith("/files/")
        assert ordre[1] == ("DELETE", ancienne["url"])
        assert ordre[2][0] == "POST" and ordre[2][1].endswith("/tracks/")
        assert ordre[3] == ("DELETE", ancien_fichier), "ancien fichier effacé en dernier"
        assert r["fichier_supprime"] == ancien_fichier
        fr = [t for t in pod.pistes(pod.session.video) if t["lang"] == "fr"]
        assert len(fr) == 1 and fr[0]["src"] == r["fichier"]["url"]

    def test_echec_de_creation_remet_l_ancienne_piste(self, pod, tmp_path):
        from pod_api import PodAPIError

        ancienne = pod.session.ajouter_piste()
        pod.session.echec_piste = 1
        with pytest.raises(PodAPIError):
            pod.publier_piste(
                pod.session.video,
                "fr",
                "subtitles",
                VTT,
                remplacer=ancienne,
                dossier_sauvegarde=str(tmp_path),
            )
        fr = [t for t in pod.pistes(pod.session.video) if t["lang"] == "fr"]
        assert len(fr) == 1 and fr[0]["src"] == ancienne["src"], "la vidéo est restée sans piste"

    def test_ancien_fichier_non_supprime_n_annule_rien(self, pod, tmp_path):
        ancienne = pod.session.ajouter_piste()
        pod.session.echec_suppr_fichier = True
        r = pod.publier_piste(
            pod.session.video,
            "fr",
            "subtitles",
            VTT,
            remplacer=ancienne,
            dossier_sauvegarde=str(tmp_path),
        )
        assert r["avertissement"] and r["fichier_supprime"] == ""
        assert r["piste"]["src"] == r["fichier"]["url"]

    def test_fichier_de_piste_etranger_arrete_tout_avant_d_ecrire(self, pod, tmp_path):
        """La sauvegarde lit l'ancienne piste en premier : un `src` hors de
        l'instance est refusé, et rien n'est encore modifié sur Pod."""
        from pod_api import PodAPIError

        ancienne = pod.session.ajouter_piste()
        etranger = dict(ancienne, src="https://pirate.exemple.org/rest/files/1/")
        pod.session.pistes[ancienne["url"]] = etranger
        with pytest.raises(PodAPIError):
            pod.publier_piste(
                pod.session.video,
                "fr",
                "subtitles",
                VTT,
                remplacer=etranger,
                dossier_sauvegarde=str(tmp_path),
            )
        assert not _ecritures(pod)


# ═════════════════════════════ Métadonnées ═════════════════════════════════


class TestMetadonnees:
    def test_lecture_lisible(self, pod):
        m = pod.metadonnees(pod.session.video)
        assert m == {
            "titre": "Les métropoles",
            "description": "Ancienne",
            "mots_cles": ["archeologie", "age du bronze"],
            "disciplines": ["Histoire"],
            "type": "Cours",
        }

    def test_discipline_ajoutee_jamais_retiree(self, pod):
        avant = pod.metadonnees(pod.session.video)
        r = pod.maj_metadonnees(202, avant, {"ajout_discipline": "Archéologie"})
        assert r["apres"]["disciplines"] == ["Histoire", "Archéologie"]

    def test_champs_ecrits_au_format_de_pod(self, pod):
        avant = pod.metadonnees(pod.session.video)
        pod.maj_metadonnees(
            202,
            avant,
            {
                "titre": "  Nouveau titre  ",
                "description": "Un.\n\nDeux & trois",
                "mots_cles": ["néolithique", "ville antique"],
                "type": "Conférence",
            },
        )
        v = pod.session.video
        assert v["title"] == "Nouveau titre"
        assert v["description"] == "<p>Un.</p>\n\n<p>Deux &amp; trois</p>"
        assert v["tags"] == 'néolithique "ville antique"'
        assert v["type"] == f"{REST}/types/2/"

    def test_pod_a_change_depuis_l_ouverture(self, pod):
        from pod_api import PodAPIError

        avant = pod.metadonnees(pod.session.video)
        pod.session.video["title"] = "Modifié entre-temps par quelqu'un"
        with pytest.raises(PodAPIError):
            pod.maj_metadonnees(202, avant, {"titre": "Mon titre"})
        assert not _ecritures(pod)

    @pytest.mark.parametrize(
        "nouveau", [{"titre": "   "}, {"ajout_discipline": "Inconnue"}, {"type": "Inconnu"}, {}]
    )
    def test_valeur_invalide_refusee_sans_ecrire(self, pod, nouveau):
        from pod_api import PodAPIError

        avant = pod.metadonnees(pod.session.video)
        with pytest.raises(PodAPIError):
            pod.maj_metadonnees(202, avant, nouveau)
        assert not _ecritures(pod)


class TestConversions:
    def test_mots_cles_limites_a_255_caracteres(self):
        from pod_api import tags_vers_pod

        chaine, ecartes = tags_vers_pod(["mot"] * 60 + ["de trop"], limite=20)
        assert len(chaine) <= 20 and "de trop" in ecartes

    def test_aller_retour_html(self):
        from pod_api import html_vers_texte, texte_vers_html

        texte = "Premier paragraphe.\n\nSecond, avec <balise> & esperluette."
        assert html_vers_texte(texte_vers_html(texte)) == texte

    def test_l_editeur_trouve_tags_vers_pod(self):
        """L'éditeur importe `tags_vers_pod` depuis `pod_api` : absent avant
        cette étape, l'écran des métadonnées aurait échoué."""
        from enrichissement import editeur  # noqa: F401
        from pod_api import tags_vers_pod  # noqa: F401
