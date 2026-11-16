"""
Recherches sur l'API REST d'Esup-Pod : seulement par des filtres qui existent.

Esup-Pod 3.8.4 n'a ni `search` ni `slug` sur /users/ et /videos/ : un
paramètre inconnu est ignoré en silence et l'API renvoie la première page de
tout. Ces tests simulent exactement ce comportement (le faux serveur ignore
les paramètres inconnus) pour vérifier que PodAdmin ne s'y fie plus.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from pod_api import PodAPI, PodAPIError, id_depuis_url  # noqa: E402

BASE = "https://videos.exemple.fr/rest"

COMPTES = [
    {"username": "dupont", "email": "jean.dupont@exemple.fr", "url": f"{BASE}/users/1/"},
    {"username": "vehicule", "email": "pod-depot@exemple.fr", "url": f"{BASE}/users/18/"},
    {"username": "martin", "email": "m.martin@exemple.fr", "url": f"{BASE}/users/7/"},
]

# Filtres réellement appliqués par Pod 3.8.4 (rest_views.py, filterset_fields).
FILTRES_USERS = {"username", "email", "id"}


def _faux_get_users(endpoint, params=None):
    """Imite /users/ : applique username/email/id, ignore tout le reste."""
    resultats = list(COMPTES)
    for champ, valeur in (params or {}).items():
        if champ in FILTRES_USERS:
            resultats = [u for u in resultats if str(u.get(champ)) == str(valeur)]
    return {"count": len(resultats), "results": resultats}


@pytest.fixture
def api(monkeypatch):
    a = PodAPI("https://videos.exemple.fr", "jeton")
    monkeypatch.setattr(a, "_get", _faux_get_users)
    return a


class TestIdDepuisUrl:
    @pytest.mark.parametrize(
        "entree, attendu",
        [
            (f"{BASE}/users/177/", 177),
            (f"{BASE}/users/177", 177),
            ({"url": f"{BASE}/users/18/"}, 18),
            ("", None),
            (None, None),
            (f"{BASE}/users/", None),
        ],
    )
    def test_extraction(self, entree, attendu):
        assert id_depuis_url(entree) == attendu


class TestRechercheDeComptes:
    def test_identifiant_exact(self, api):
        assert [u["username"] for u in api.search_users("vehicule")] == ["vehicule"]

    def test_adresse_electronique_en_second(self, api):
        assert [u["username"] for u in api.search_users("m.martin@exemple.fr")] == ["martin"]

    def test_inconnu_ne_renvoie_pas_les_derniers_comptes(self, api):
        """Régression : `?search=` ignoré renvoyait la première page de tous
        les comptes ; un appelant peu prudent aurait pris le premier."""
        assert api.search_users("inconnu") == []

    def test_vide(self, api):
        assert api.search_users("  ") == []

    def test_filtre_ignore_par_le_serveur_revérifie(self, monkeypatch):
        """Si un jour `username` était ignoré lui aussi, la revérification
        côté client empêche de renvoyer un autre compte."""
        a = PodAPI("https://videos.exemple.fr", "jeton")
        monkeypatch.setattr(a, "_get", lambda e, p=None: {"count": 3, "results": list(COMPTES)})
        assert [u["username"] for u in a.search_users("martin")] == ["martin"]
        assert a.search_users("absent") == []


class TestVideoParSlug:
    def _api(self, monkeypatch, repondre):
        """API dont la lecture du détail passe par `repondre(endpoint)`."""
        a = PodAPI("https://videos.exemple.fr", "jeton")
        lus = []

        def faux_get(endpoint, params=None):
            lus.append(endpoint)
            return repondre(endpoint)

        monkeypatch.setattr(a, "_get", faux_get)
        return a, lus

    def test_lit_le_detail_par_l_id_en_tete_du_slug(self, monkeypatch):
        a, lus = self._api(monkeypatch, lambda e: {"slug": "1234-cours", "url": "u"})
        assert a.get_video_by_slug("1234-cours")["url"] == "u"
        assert lus == ["/videos/1234/"], "la vidéo doit être lue par son ID, pas filtrée"

    def test_slug_different_refuse(self, monkeypatch):
        """L'ID existe mais porte une autre vidéo : on ne la prend pas."""
        a, _ = self._api(monkeypatch, lambda e: {"slug": "1234-autre", "url": "u"})
        assert a.get_video_by_slug("1234-cours") is None

    def test_slug_sans_id_aucune_requete(self, monkeypatch):
        a, lus = self._api(monkeypatch, lambda e: {"slug": "cours"})
        assert a.get_video_by_slug("cours") is None
        assert a.get_video_by_slug("") is None
        assert lus == []

    @pytest.mark.parametrize(
        "erreur", [PodAPIError("HTTP 404", status=404), requests.ConnectionError("coupure")]
    )
    def test_erreur_de_lecture_donne_none(self, monkeypatch, erreur):
        def repondre(e):
            raise erreur

        a, _ = self._api(monkeypatch, repondre)
        assert a.get_video_by_slug("1234-cours") is None


class TestVideosDuProprietaire:
    def test_filtre_owner_revérifie_et_troncature_a_part(self, monkeypatch):
        """Même si le serveur ignorait `owner`, seules les vidéos du compte
        reviennent ; et la lecture filtrée n'écrase pas l'alerte de
        troncature du scan complet de /videos/."""
        a = PodAPI("https://videos.exemple.fr", "jeton")
        a.troncatures["/videos/"] = True  # scan complet précédent incomplet
        vus = {}

        def faux_paginate(endpoint, params=None, **kw):
            vus.update(endpoint=endpoint, params=params, **kw)
            a.troncatures[kw.get("cle_troncature") or endpoint] = False
            return [
                {"slug": "a", "owner": f"{BASE}/users/18/"},
                {"slug": "b", "owner": f"{BASE}/users/1/"},
                {"slug": "c", "owner": f"{BASE}/users/180/"},
            ]

        monkeypatch.setattr(a, "_paginate", faux_paginate)
        assert [v["slug"] for v in a.get_videos_of_owner(18)] == ["a"]
        assert vus["params"] == {"owner": 18}
        assert a.est_tronque("/videos/"), "l'alerte du scan complet a été effacée"
