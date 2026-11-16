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

from pod_api import PodAPI, id_depuis_url  # noqa: E402

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
