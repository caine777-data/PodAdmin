#!/usr/bin/env python3
"""
pod_api.py — Client de l'API REST Esup-Pod v4
Application « Pod Admin » (Université de Toulouse — MFCA)
Forké de « Pod Téléverseur » : tout le client d'upload est conservé, une
section ADMINISTRATION est ajoutée en dessous.

Particularités Esup-Pod gérées ici :
  • Auth par en-tête  Authorization: Token <token>
  • Les relations (owner, type, additional_owners, channel, theme…) sont des
    URLs, pas des IDs
  • Upload multipart en STREAMING (gros fichiers, sans charger en RAM)
  • L'upload ne lance PAS l'encodage → appel séparé launch_encode_view

⚠️ Cette appli vise un compte SUPERUTILISATEUR (lister les comptes, agir sur
   des vidéos qui ne vous appartiennent pas, créer des chaînes…).
"""

from __future__ import annotations

__author__      = "Cédric MONNA"
__contact__     = "cedricmonna@gmail.com"
__institution__ = "Université de Toulouse — MFCA"
__version__     = "0.1.0"
__date__        = "2026"
__license__     = "Usage interne — Université de Toulouse"


import os
import re
import requests
from typing import Callable, Optional

try:
    # Permet un upload streamé avec callback de progression
    from requests_toolbelt.multipart.encoder import (
        MultipartEncoder, MultipartEncoderMonitor
    )
    HAS_TOOLBELT = True
except ImportError:
    HAS_TOOLBELT = False


class PodAPIError(Exception):
    """Erreur renvoyée par l'API Pod (avec code HTTP et corps de réponse)."""
    def __init__(self, message: str, status: int = 0, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class PodAPI:
    def __init__(self, base_url: str, token: str, verify_ssl: bool = True):
        self.base_url = base_url.rstrip("/")
        self.rest = f"{self.base_url}/rest"
        self.token = token
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Token {token}"})

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  HELPERS                                                          ║
    # ╚══════════════════════════════════════════════════════════════════╝

    def _abs(self, endpoint_or_url: str) -> str:
        """Accepte un endpoint relatif (/videos/) OU une URL absolue de l'API."""
        s = str(endpoint_or_url)
        return s if s.startswith("http") else f"{self.rest}{s}"

    def _json(self, resp: requests.Response):
        if resp.status_code >= 400:
            raise PodAPIError(
                f"HTTP {resp.status_code} sur {resp.url}",
                status=resp.status_code,
                body=resp.text[:1000],
            )
        if resp.text:
            try:
                return resp.json()
            except ValueError:
                return resp.text
        return None

    def _get(self, endpoint: str, params: dict | None = None):
        r = self.session.get(self._abs(endpoint), params=params,
                             headers={"Accept": "application/json"},
                             timeout=30, verify=self.verify_ssl)
        return self._json(r)

    def _post(self, endpoint: str, json=None, data=None):
        r = self.session.post(self._abs(endpoint), json=json, data=data,
                             headers={"Accept": "application/json"},
                             timeout=30, verify=self.verify_ssl)
        return self._json(r)

    def _patch(self, endpoint: str, json=None, data=None):
        r = self.session.patch(self._abs(endpoint), json=json, data=data,
                             headers={"Accept": "application/json"},
                             timeout=30, verify=self.verify_ssl)
        return self._json(r)

    def _delete(self, endpoint: str):
        r = self.session.delete(self._abs(endpoint),
                             headers={"Accept": "application/json"},
                             timeout=30, verify=self.verify_ssl)
        if r.status_code >= 400:
            raise PodAPIError(f"HTTP {r.status_code} sur {r.url}",
                              status=r.status_code, body=r.text[:1000])
        return True  # 204 No Content attendu en cas de succès

    def _options(self, endpoint: str) -> dict:
        r = self.session.options(self._abs(endpoint),
                             headers={"Accept": "application/json"},
                             timeout=20, verify=self.verify_ssl)
        return self._json(r) or {}

    def _paginate(self, endpoint: str, params: dict | None = None,
                  max_pages: int = 300,
                  progress_cb: Optional[Callable[[int], None]] = None) -> list[dict]:
        """Suit le champ 'next' jusqu'au bout. progress_cb(nb_cumulé) optionnel."""
        items: list[dict] = []
        url = self._abs(endpoint)
        p = dict(params or {})
        p.setdefault("limit", 100)
        pages = 0
        while url and pages < max_pages:
            r = self.session.get(url, params=(p if pages == 0 else None),
                                 headers={"Accept": "application/json"},
                                 timeout=30, verify=self.verify_ssl)
            data = self._json(r)
            if isinstance(data, dict):
                items.extend(data.get("results", []))
                url = data.get("next")     # URL absolue de la page suivante
            else:
                items.extend(data or [])
                url = None
            pages += 1
            if progress_cb:
                progress_cb(len(items))
        return items

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TÉLÉVERSEUR (conservé tel quel)                                  ║
    # ╚══════════════════════════════════════════════════════════════════╝

    # ── 0. Connexion ──────────────────────────────────────────────────────

    def test_connection(self) -> int:
        """Renvoie le nombre de vidéos accessibles (valide le token)."""
        data = self._get("/videos/", {"limit": 1})
        return data.get("count", 0) if isinstance(data, dict) else 0

    # ── 1. Utilisateurs (résolution owner) ────────────────────────────────

    def search_users(self, query: str) -> list[dict]:
        """Recherche des utilisateurs → liste de dicts {username, url, ...}."""
        data = self._get("/users/", {"search": query, "limit": 25})
        return data.get("results", []) if isinstance(data, dict) else (data or [])

    def get_all_users(self, max_pages: int = 80) -> list[dict]:
        """Récupère TOUS les utilisateurs en suivant la pagination de l'API."""
        return self._paginate("/users/", {"limit": 100}, max_pages=max_pages)

    # ── 2. Types / chaînes / sites ────────────────────────────────────────

    def get_types(self) -> list[dict]:
        data = self._get("/types/", {"limit": 100})
        return data.get("results", []) if isinstance(data, dict) else (data or [])

    def get_channels(self) -> list[dict]:
        return self._paginate("/channels/", {"limit": 200})

    def get_sites(self) -> list[dict]:
        """Sites de l'instance (requis pour l'upload multi-établissements)."""
        data = self._get("/sites/", {"limit": 100})
        return data.get("results", []) if isinstance(data, dict) else (data or [])

    # ── 3. Upload d'une vidéo (streaming + progression) ───────────────────

    def upload_video(
        self,
        file_path: str,
        title: str,
        owner_url: str,
        type_url: str,
        *,
        main_lang: str = "fr",
        cursus: str = "0",
        is_draft: bool = True,
        description: str = "",
        additional_owner_urls: Optional[list[str]] = None,
        site_urls: Optional[list[str]] = None,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> dict:
        """
        Téléverse une vidéo. Renvoie le dict de la vidéo créée (avec 'slug', 'url').
        progress_cb(bytes_envoyés, bytes_total) est appelé pendant l'envoi.
        N'amorce PAS l'encodage (voir launch_encoding).
        """
        if not os.path.isfile(file_path):
            raise PodAPIError(f"Fichier introuvable : {file_path}")

        fields = [
            ("owner", owner_url),
            ("type", type_url),
            ("title", title[:250]),
            ("main_lang", main_lang),
            ("cursus", str(cursus)),
            ("is_draft", "true" if is_draft else "false"),
        ]
        if description:
            fields.append(("description", description))
        for url in (additional_owner_urls or []):
            fields.append(("additional_owners", url))
        for url in (site_urls or []):
            fields.append(("sites", url))

        filename = os.path.basename(file_path)
        f = open(file_path, "rb")
        try:
            fields.append(("video", (filename, f, "application/octet-stream")))

            if HAS_TOOLBELT:
                encoder = MultipartEncoder(fields=fields)
                total = encoder.len

                def _cb(monitor):
                    if progress_cb:
                        progress_cb(monitor.bytes_read, total)

                monitor = MultipartEncoderMonitor(encoder, _cb)
                headers = {"Content-Type": monitor.content_type}
                r = self.session.post(f"{self.rest}/videos/", data=monitor,
                                     headers=headers, timeout=None,
                                     verify=self.verify_ssl)
            else:
                # Repli sans streaming (charge en mémoire) si toolbelt absent
                files = {"video": (filename, f, "application/octet-stream")}
                data = {k: v for k, v in fields if k != "video"}
                r = self.session.post(f"{self.rest}/videos/", data=data,
                                     files=files, timeout=None,
                                     verify=self.verify_ssl)
            return self._json(r)
        finally:
            f.close()

    # ── 4. Lancer l'encodage ──────────────────────────────────────────────

    def launch_encoding(self, slug: str):
        return self._get("/launch_encode_view/", {"slug": slug})

    # ── 5. Propriétaires additionnels (PATCH) ─────────────────────────────

    def set_additional_owners(self, video, owner_urls: list[str]) -> dict:
        """Remplace la liste des propriétaires additionnels d'une vidéo
        (réf = dict vidéo, URL, id ou slug)."""
        return self._patch(self._video_endpoint(video),
                           json={"additional_owners": list(owner_urls)})

    # ── 6. Contributeurs (crédits) ────────────────────────────────────────

    def add_contributor(self, video_url: str, name: str, email: str = "",
                       role: str = "author", weblink: str = "") -> dict:
        data = {
            "video": video_url,
            "name": name,
            "email_address": email,
            "role": role,
            "weblink": weblink,
        }
        r = self.session.post(f"{self.rest}/contributors/", data=data,
                            timeout=30, verify=self.verify_ssl)
        return self._json(r)

    def get_contributors(self, video_id: int) -> list[dict]:
        data = self._get("/contributors/", {"video": video_id})
        return data.get("results", []) if isinstance(data, dict) else (data or [])

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  ADMINISTRATION (nouveau)                                         ║
    # ╚══════════════════════════════════════════════════════════════════╝

    # ── A. Comptes — statut « équipe » (is_staff) ─────────────────────────
    # Diagnostic : PATCH autorisé sur /rest/users/<id>/, is_staff modifiable.

    def get_user(self, user_url: str) -> dict:
        """Détail d'un compte à partir de son URL (champ 'url' du compte)."""
        return self._get(user_url)

    def set_user_staff(self, user_url: str, is_staff: bool) -> dict:
        """Donne (True) ou retire (False) le statut « équipe » à un compte."""
        return self._patch(user_url, json={"is_staff": bool(is_staff)})

    def set_user_groups(self, user_url: str, group_names: list[str]) -> dict:
        """Remplace les groupes d'accès d'un compte (champ 'groups')."""
        return self._patch(user_url, json={"groups": list(group_names)})

    # ── B. Vidéos en masse — inventaire, réaffectation, nettoyage ─────────
    # Diagnostic : PATCH + DELETE autorisés, owner / is_draft modifiables.
    # Champs de statut utiles : encoded, encoding_in_progress,
    #                           get_encoding_step, is_draft, duration.

    def get_all_videos(self, max_pages: int = 300,
                       progress_cb: Optional[Callable[[int], None]] = None,
                       extra_params: dict | None = None) -> list[dict]:
        """Scan complet de l'instance (paginé). progress_cb(nb_cumulé) optionnel."""
        return self._paginate("/videos/", extra_params, max_pages, progress_cb)

    def search_videos(self, params: dict) -> list[dict]:
        """GET filtré sur /videos/ (ex. {'owner': <url>} ou {'search': 'mot'})."""
        data = self._get("/videos/", params)
        return data.get("results", []) if isinstance(data, dict) else (data or [])

    # ── Résolution de l'endpoint d'une vidéo ──────────────────────────────
    # IMPORTANT : l'API indexe les vidéos par ID NUMÉRIQUE (/rest/videos/108/),
    # PAS par slug. On accepte donc une « référence » souple :
    #   • un dict vidéo  -> on prend son champ 'url' (absolu, fourni par l'API)
    #   • une URL (http) -> utilisée telle quelle
    #   • un id numérique-> /videos/<id>/
    #   • à défaut, un slug (peu fiable : peut donner 404 sur le détail)
    def _video_endpoint(self, ref) -> str:
        """Construit l'URL de détail d'une vidéo à partir d'une référence souple."""
        if isinstance(ref, dict):
            if ref.get("url"):
                return ref["url"]                 # URL absolue donnée par l'API
            ref = ref.get("id")                   # repli sur l'id numérique
        s = str(ref)
        if s.startswith("http"):
            return s                              # déjà une URL absolue
        return f"/videos/{s}/"                     # id numérique (ou slug en dernier recours)

    def get_video(self, video) -> dict:
        """Détail d'une vidéo (réf = dict vidéo, URL, id ou slug)."""
        return self._get(self._video_endpoint(video))

    def patch_video(self, video, payload: dict) -> dict:
        """PATCH générique d'une vidéo (réf = dict vidéo, URL, id ou slug).
        Les relations (owner, channel…) sont des URLs ou des listes d'URLs."""
        return self._patch(self._video_endpoint(video), json=payload)

    def set_video_owner(self, video, owner_url: str,
                        additional_owner_urls: Optional[list[str]] = None) -> dict:
        """Réaffecte le propriétaire (et, en option, les co-propriétaires)."""
        payload: dict = {"owner": owner_url}
        if additional_owner_urls is not None:
            payload["additional_owners"] = list(additional_owner_urls)
        return self.patch_video(video, payload)

    def set_video_draft(self, video, value: bool) -> dict:
        return self.patch_video(video, {"is_draft": bool(value)})

    def set_video_restricted(self, video, value: bool) -> dict:
        return self.patch_video(video, {"is_restricted": bool(value)})

    def get_access_groups(self, max_id: int = 60) -> list[dict]:
        """Récupère les groupes d'accès AVEC leur URL adressable.

        Particularité de l'API Pod : la liste /accessgroups/ n'expose ni `id`
        ni `url` (seulement code_name/display_name). Or le champ
        `restrict_access_to_groups` d'une vidéo attend une URL par id
        (/rest/accessgroups/<id>/). On reconstruit donc la correspondance en
        sondant les routes de détail numériques /accessgroups/<n>/ : chacune qui
        répond donne {code_name, url}. On renvoie une liste de dicts
        {code_name, display_name, url} triée par nom.
        """
        groups = []
        for n in range(1, max_id + 1):
            url = f"{self.rest}/accessgroups/{n}/"
            try:
                r = self.session.get(url, headers={"Accept": "application/json"},
                                     timeout=15, verify=self.verify_ssl)
            except Exception:
                continue
            if r.status_code != 200:
                continue
            try:
                g = r.json()
            except ValueError:
                continue
            if isinstance(g, dict) and g.get("code_name"):
                groups.append({
                    "code_name": g.get("code_name"),
                    "display_name": g.get("display_name") or g.get("code_name"),
                    "url": url,
                })
        groups.sort(key=lambda x: (x.get("code_name") or "").lower())
        return groups

    def set_video_groups(self, video, group_urls: list[str]) -> dict:
        """Restreint une vidéo à une liste de groupes d'accès (URLs
        /accessgroups/<id>/). Couple le statut : `is_restricted` passe à True
        s'il y a au moins un groupe, à False si la liste est vide."""
        urls = list(group_urls)
        return self.patch_video(video, {
            "restrict_access_to_groups": urls,
            "is_restricted": bool(urls),
        })

    # — Gestion complète des groupes d'accès (création / membres / suppression) —

    def get_owners_map(self, max_pages: int = 80) -> dict:
        """Table de correspondance URL de compte (/users/<id>/) → URL d'owner
        (/owners/<id>/). Les groupes d'accès référencent leurs membres par des
        URLs /owners/, alors que partout ailleurs on manipule des /users/.
        Cette table permet de convertir un compte choisi par l'utilisateur en
        l'URL /owners/ attendue par le champ `users` d'un groupe."""
        mapping, url, params, pages = {}, f"{self.rest}/owners/", {"limit": 100}, 0
        while url and pages < max_pages:
            r = self.session.get(url, params=(params if pages == 0 else None),
                                 headers={"Accept": "application/json"},
                                 timeout=30, verify=self.verify_ssl)
            d = self._json(r)
            items = d.get("results", []) if isinstance(d, dict) else (d or [])
            for o in items:
                user_url = o.get("user")
                if user_url:
                    mapping[str(user_url).rstrip("/")] = o.get("url")
            url = d.get("next") if isinstance(d, dict) else None
            pages += 1
        return mapping

    def get_access_group(self, code_name: str, max_id: int = 80) -> Optional[dict]:
        """Récupère un groupe d'accès complet (avec son URL adressable) par son
        code_name, en sondant les routes de détail /accessgroups/<id>/."""
        for n in range(1, max_id + 1):
            url = f"{self.rest}/accessgroups/{n}/"
            try:
                r = self.session.get(url, headers={"Accept": "application/json"},
                                     timeout=15, verify=self.verify_ssl)
            except Exception:
                continue
            if r.status_code != 200:
                continue
            try:
                g = r.json()
            except ValueError:
                continue
            if isinstance(g, dict) and g.get("code_name") == code_name:
                g["url"] = url
                return g
        return None

    def create_access_group(self, code_name: str, site_urls: list[str],
                            display_name: str = "",
                            owner_urls: Optional[list[str]] = None) -> dict:
        """Crée un groupe d'accès (POST). `code_name` et `sites` sont requis ;
        `users` (au format /owners/) peuvent être fournis dès la création."""
        body = {
            "code_name": code_name,
            "display_name": display_name or code_name,
            "sites": list(site_urls),
        }
        if owner_urls:
            body["users"] = list(owner_urls)
        r = self.session.post(f"{self.rest}/accessgroups/", json=body,
                              headers={"Accept": "application/json"},
                              timeout=30, verify=self.verify_ssl)
        return self._json(r)

    def set_access_group_members(self, group_url: str, owner_urls: list[str]) -> dict:
        """Remplace la liste des membres d'un groupe (PATCH du champ `users`,
        au format /owners/<id>/)."""
        r = self.session.patch(group_url, json={"users": list(owner_urls)},
                               headers={"Accept": "application/json"},
                               timeout=30, verify=self.verify_ssl)
        return self._json(r)

    def delete_access_group(self, group_url: str) -> bool:
        """⚠️ Supprime définitivement un groupe d'accès (DELETE)."""
        return self._delete(group_url)

    def assign_video_to_channels(self, video, channel_urls: list[str],
                                 theme_urls: Optional[list[str]] = None) -> dict:
        """Place une vidéo dans une/des chaîne(s) (et thème(s)) — champs M2M."""
        payload: dict = {"channel": list(channel_urls)}
        if theme_urls is not None:
            payload["theme"] = list(theme_urls)
        return self.patch_video(video, payload)

    def delete_video(self, video) -> bool:
        """⚠️ Suppression définitive d'une vidéo (DELETE)."""
        return self._delete(self._video_endpoint(video))

    # Aides au module Nettoyage (logique pure, testable sans réseau) ───────

    @staticmethod
    def is_unencoded(video: dict) -> bool:
        """Vidéo jamais encodée et pas en cours d'encodage."""
        return (not video.get("encoded", False)
                and not video.get("encoding_in_progress", False))

    @staticmethod
    def is_stale_draft(video: dict, before_iso: str) -> bool:
        """Brouillon dont la date d'ajout est antérieure à before_iso (AAAA-MM-JJ)."""
        return bool(video.get("is_draft")) and \
            str(video.get("date_added", ""))[:10] < before_iso

    # ── C. Chaînes & thèmes ───────────────────────────────────────────────
    # Diagnostic : POST autorisé. Chaîne requiert title + themes ;
    #              thème requiert title + channel (URL) ; thèmes hiérarchiques
    #              via parentId.

    def get_themes(self) -> list[dict]:
        return self._paginate("/themes/", {"limit": 300})

    def create_channel(self, title: str, theme_urls: Optional[list[str]] = None, *,
                       description: str = "", visible: bool = True,
                       site_url: Optional[str] = None,
                       owner_urls: Optional[list[str]] = None, **extra) -> dict:
        """Crée une chaîne. 'themes' est requis par l'API (liste, vide si aucune)."""
        payload: dict = {"title": title, "themes": list(theme_urls or [])}
        if description:
            payload["description"] = description
        payload["visible"] = bool(visible)
        if site_url:
            payload["site"] = site_url
        if owner_urls is not None:
            payload["owners"] = list(owner_urls)
        payload.update(extra)
        return self._post("/channels/", json=payload)

    def patch_channel(self, channel: str, payload: dict) -> dict:
        ep = channel if str(channel).startswith("http") else f"/channels/{channel}/"
        return self._patch(ep, json=payload)

    def create_theme(self, title: str, channel_url: str, *,
                     parent_url: Optional[str] = None,
                     description: str = "", **extra) -> dict:
        """Crée un thème rattaché à une chaîne (channel_url). parent_url = sous-thème."""
        payload: dict = {"title": title, "channel": channel_url}
        if parent_url:
            payload["parentId"] = parent_url
        if description:
            payload["description"] = description
        payload.update(extra)
        return self._post("/themes/", json=payload)

    def patch_theme(self, theme: str, payload: dict) -> dict:
        ep = theme if str(theme).startswith("http") else f"/themes/{theme}/"
        return self._patch(ep, json=payload)

    def delete_channel(self, channel: str) -> bool:
        """⚠️ Supprime une chaîne (et ses thèmes côté serveur). DELETE."""
        ep = channel if str(channel).startswith("http") else f"/channels/{channel}/"
        return self._delete(ep)

    def delete_theme(self, theme: str) -> bool:
        """⚠️ Supprime un thème. DELETE."""
        ep = theme if str(theme).startswith("http") else f"/themes/{theme}/"
        return self._delete(ep)

    # ── C-bis. Sous-titres (tracks + files + folders) ─────────────────────
    # Diagnostic (sondes) : l'API expose /rest/tracks/ (POST autorisé) dont le
    # champ `src` pointe vers un fichier /rest/files/<id>/. Déposer un sous-titre
    # se fait donc en 3 temps :
    #   1) trouver (ou créer) le DOSSIER de la vidéo  -> /rest/folders/ (name = slug)
    #   2) TÉLÉVERSER le .vtt dans ce dossier         -> /rest/files/ (multipart)
    #   3) créer la PISTE qui pointe vers ce fichier  -> /rest/tracks/
    # Valeurs confirmées : kind ∈ {subtitles, captions} ; lang = code ISO 2 lettres.
    # Le fichier déposé doit être du WebVTT ; un .srt est converti à la volée.

    def get_tracks(self, video) -> list[dict]:
        """Liste les pistes de sous-titres/légendes d'une vidéo.
        `video` = dict vidéo (ou URL/id). On filtre sur l'URL de la vidéo."""
        vurl = str(self._video_endpoint(video)).rstrip("/")
        out = []
        # /tracks/ ne propose pas forcément de filtre serveur : on parcourt et on trie.
        for t in self._paginate("/tracks/"):
            if str(t.get("video")).rstrip("/") == vurl:
                out.append(t)
        return out

    def find_or_create_folder(self, name: str, owner_url: str) -> str:
        """Renvoie l'URL du dossier `name` (= slug de la vidéo) appartenant à
        `owner_url`. Le crée s'il n'existe pas. Les fichiers d'une vidéo sont
        rangés dans un dossier portant son slug, propriété de son propriétaire."""
        owner_n = str(owner_url).rstrip("/")
        # Recherche : on parcourt les dossiers et on compare nom + propriétaire.
        for f in self._paginate("/folders/"):
            if f.get("name") == name and str(f.get("owner")).rstrip("/") == owner_n:
                return f.get("url")
        # Absent -> création (POST /folders/ : name + owner suffisent)
        created = self._post("/folders/", json={"name": name, "owner": owner_url})
        return created.get("url")

    def upload_subtitle_file(self, folder_url: str, name: str, vtt_bytes: bytes,
                             filename: str, created_by_url: str) -> dict:
        """Téléverse un fichier .vtt (en mémoire) dans un dossier, via POST
        multipart sur /rest/files/. Renvoie le fichier créé (avec son `url`)."""
        # multipart : le binaire dans `files`, les champs relationnels dans `data`
        files = {"file": (filename, vtt_bytes, "text/vtt")}
        data = {"folder": folder_url, "name": name, "created_by": created_by_url}
        r = self.session.post(self._abs("/files/"), data=data, files=files,
                              headers={"Accept": "application/json"},
                              timeout=120, verify=self.verify_ssl)
        return self._json(r)

    def add_track(self, video, lang: str, kind: str = "subtitles",
                  file_url: Optional[str] = None) -> dict:
        """Crée une piste sur /rest/tracks/ liant une vidéo à un fichier de
        sous-titres. kind ∈ {subtitles, captions} ; lang = code ISO (fr, en…)."""
        payload: dict = {
            "video": self._video_endpoint(video),   # URL absolue de la vidéo
            "lang": lang,
            "kind": kind,
        }
        if file_url:
            payload["src"] = file_url                # URL du fichier /files/<id>/
        return self._post("/tracks/", json=payload)

    def delete_track(self, track) -> bool:
        """⚠️ Supprime une piste de sous-titres (DELETE /rest/tracks/<id>/).
        `track` = id, URL ou dict track."""
        if isinstance(track, dict):
            track = track.get("url") or track.get("id")
        ep = track if str(track).startswith("http") else f"/tracks/{track}/"
        return self._delete(ep)

    def add_subtitle(self, video: dict, lang: str, kind: str, file_path: str) -> dict:
        """Orchestration complète : ajoute un sous-titre à une vidéo à partir
        d'un fichier .vtt OU .srt (converti automatiquement).
        Enchaîne : lecture/conversion -> dossier -> upload -> création de piste.
        Renvoie la piste (track) créée. `video` doit contenir 'slug' et 'owner'."""
        # 1) Lecture du fichier. 'utf-8-sig' retire un éventuel BOM en tête.
        with open(file_path, "rb") as fh:
            raw = fh.read()
        text = raw.decode("utf-8-sig", errors="replace")

        # Conversion / validation selon l'extension
        if file_path.lower().endswith(".srt"):
            text = srt_to_vtt(text)                       # SRT -> WebVTT
        elif not text.lstrip().startswith("WEBVTT"):
            # Garde-fou : un .vtt valide commence par l'en-tête WEBVTT
            raise PodAPIError("Fichier .vtt invalide : il doit commencer par "
                              "l'en-tête « WEBVTT ».")
        vtt_bytes = text.encode("utf-8")

        # 2) Dossier de la vidéo (= son slug), appartenant à SON propriétaire
        slug = video.get("slug") or "video"
        owner_url = video.get("owner")
        if not owner_url:
            raise PodAPIError("Propriétaire de la vidéo introuvable (champ 'owner').")
        folder_url = self.find_or_create_folder(slug, owner_url)

        # 3) Téléversement du .vtt (nom à la convention Pod : subtitle_<lang>_<horodatage>)
        from datetime import datetime
        name = f"subtitle_{lang}_{datetime.now():%Y%m%d-%H%M%S}"
        f = self.upload_subtitle_file(folder_url, name, vtt_bytes,
                                      name + ".vtt", owner_url)

        # 4) Création de la piste qui référence le fichier téléversé
        return self.add_track(video, lang, kind, f.get("url"))

    # ── D. Découverte de schéma (OPTIONS) ─────────────────────────────────
    # Pour s'adapter à l'instance plutôt que supposer (réflexe « diagnostic »).

    def options_schema(self, endpoint: str, verb: str = "POST") -> dict:
        """Schéma des champs pour un verbe (POST création / PUT modification)."""
        return self._options(endpoint).get("actions", {}).get(verb, {})

    def required_fields(self, endpoint: str, verb: str = "POST") -> list[str]:
        """Liste des champs marqués 'required' par l'instance pour ce verbe."""
        schema = self.options_schema(endpoint, verb)
        return [name for name, meta in schema.items() if meta.get("required")]

    def allowed_methods(self, endpoint: str) -> str:
        """En-tête Allow (méthodes HTTP autorisées) d'un endpoint."""
        r = self.session.options(self._abs(endpoint),
                             headers={"Accept": "application/json"},
                             timeout=20, verify=self.verify_ssl)
        return r.headers.get("Allow", "")


# Rôles de contributeur usuels dans Esup-Pod
CONTRIBUTOR_ROLES = [
    "author", "actor", "designer", "consultant",
    "editor", "speaker", "soundman", "writer", "publisher",
]


# ── Sous-titres : conversion SRT -> WebVTT ────────────────────────────────
def srt_to_vtt(text: str) -> str:
    """Convertit un sous-titrage SRT en WebVTT.
    Deux seules différences en pratique :
      1) on ajoute l'en-tête « WEBVTT » en première ligne ;
      2) les millisecondes SRT utilisent une virgule (00:00:01,000) là où le
         VTT utilise un point (00:00:01.000)."""
    # Normalise les fins de ligne (Windows/Mac -> Unix)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Virgule -> point dans les codes temps (hh:mm:ss,mmm -> hh:mm:ss.mmm)
    text = re.sub(r"(\d\d:\d\d:\d\d),(\d{3})", r"\1.\2", text)
    # Ajoute l'en-tête WEBVTT s'il manque
    if not text.lstrip().startswith("WEBVTT"):
        text = "WEBVTT\n\n" + text.lstrip("\n")
    return text


# ── Sous-titres : langues acceptées par l'API (code ISO -> libellé) ───────
# Sous-ensemble usuel (l'API en accepte beaucoup plus ; voir verifier_tracks.py).
SUBTITLE_LANGS = [
    ("fr", "Français"), ("en", "Anglais"), ("es", "Espagnol"),
    ("de", "Allemand"), ("it", "Italien"), ("pt", "Portugais"),
    ("ar", "Arabe"), ("zh", "Chinois"), ("ru", "Russe"),
    ("ja", "Japonais"), ("nl", "Hollandais"), ("ca", "Catalan"),
    ("oc", "Occitan"),
]

# Types de piste acceptés par l'API (champ `kind`)
SUBTITLE_KINDS = [("subtitles", "Sous-titres"), ("captions", "Légendes")]
