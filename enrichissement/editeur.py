#!/usr/bin/env python3
"""
editeur.py — Serveur local de l'éditeur de sous-titres.

L'éditeur est une page web (assets/editeur.html) ouverte dans le navigateur :
c'est le seul moyen simple et fiable de lire la vidéo à côté du texte. Cette
page parle à un petit serveur HTTP qui tourne DANS l'application, sur
127.0.0.1 uniquement (inaccessible depuis le réseau).

Sécurité : chaque lancement tire un jeton aléatoire. Toute requête doit le
porter, sans quoi une page web quelconque ouverte dans le navigateur pourrait
lire ou modifier les projets via localhost.

Points d'accès (tous suffixés de ?t=<jeton>) :
  GET  /p/<id>              page de l'éditeur
  GET  /api/<id>            projet (sous-titres, réglages, nom)
  POST /api/<id>            enregistre les sous-titres corrigés
  POST /api/<id>/exporter   écrit les fichiers VTT / SRT
  POST /api/<id>/redecouper refait le découpage automatique
  GET  /media/<id>          la vidéo (avec prise en charge du « Range »)
  GET  /audio/<id>          l'audio extrait (lecture de secours)
"""

from __future__ import annotations

__author__ = "Cédric MONNA"
from __version__ import __version__   # noqa: E402

import json
import mimetypes
import os
import secrets
import shutil
from datetime import datetime
import socketserver
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import projet as pj
from . import sous_titres as st


def _ressource(rel: str) -> str:
    """Chemin d'une ressource de `assets/`, celui de la RACINE de PodAdmin :
    ce module vit dans le sous-dossier `enrichissement/`. Une fois compilé,
    PyInstaller place `assets/` sous `_MEIPASS`."""
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(getattr(sys, "_MEIPASS", racine), rel)


def _navigateurs_app() -> list[str]:
    """Navigateurs capables d'ouvrir une page en fenêtre d'application."""
    candidats = []
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", ""),
                     os.environ.get("LOCALAPPDATA", "")):
            candidats += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                          os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    elif sys.platform == "darwin":
        candidats += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                      "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    else:
        candidats += [shutil.which(n) or "" for n in
                      ("google-chrome", "chromium", "chromium-browser", "microsoft-edge")]
    return [c for c in candidats if c and os.path.exists(c)]


class _Serveur(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):
        # HTTPServer.server_bind() appelle socket.getfqdn(), une résolution DNS
        # inverse qui peut bloquer de longues secondes sous Windows. Inutile
        # pour un serveur qui n'écoute que sur 127.0.0.1.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


# Libellés des lignes écrites dans le Journal de PodAdmin.
_PISTE = {"subtitles": "sous-titres", "captions": "légendes"}
_CHAMP = {"titre": "titre", "description": "description", "mots_cles": "mots-clés",
          "ajout_discipline": "discipline ajoutée", "type": "type"}


class ServeurEditeur:
    def __init__(self, formats_defaut: callable = lambda: ["vtt"],
                 sur_enregistrement: callable | None = None,
                 client: callable = lambda: None,
                 reglages: callable = lambda: {},
                 pod: callable = lambda: None,
                 message_erreur: callable = str,
                 journal_hote: callable | None = None,
                 sur_video_modifiee: callable | None = None):
        """`client()` renvoie un AristoteAPI prêt à l'emploi (ou None) ;
        `reglages()` renvoie la configuration (disciplines, types de média) ;
        `pod()` renvoie un PodAPI (ou None).

        Raccordements fournis par PodAdmin (facultatifs) :
          • `message_erreur(e)` : phrase LISIBLE affichée dans la page à la
            place de l'exception brute ;
          • `journal_hote(texte)` : une ligne dans le Journal de PodAdmin pour
            chaque écriture sur Pod, en plus de journal_pod.jsonl. Appelé depuis
            les fils du serveur : à l'hôte de repasser par son fil principal ;
          • `sur_video_modifiee(video)` : la vidéo relue après un changement de
            métadonnées, pour que les listes de PodAdmin ne restent pas périmées."""
        self.jeton = secrets.token_urlsafe(24)
        self.formats_defaut = formats_defaut
        self.sur_enregistrement = sur_enregistrement
        self.client = client
        self.reglages = reglages
        self.pod = pod
        self.message_erreur = message_erreur
        self.journal_hote = journal_hote
        self.sur_video_modifiee = sur_video_modifiee
        self.verrou = threading.Lock()
        self._langues: list[dict] | None = None
        serveur = self

        class Gestionnaire(_Gestionnaire):
            srv = serveur

        self.httpd = _Serveur(("127.0.0.1", 0), Gestionnaire)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, pid: str) -> str:
        return f"http://127.0.0.1:{self.port}/p/{pid}?t={self.jeton}"

    def ouvrir(self, pid: str) -> None:
        """Ouvre l'éditeur dans une fenêtre à part, sans barre d'adresse.

        Edge (toujours présent sous Windows) ou Chrome, en mode « application ».
        À défaut, le navigateur par défaut, dans un onglet.
        """
        url = self.url(pid)
        for exe in _navigateurs_app():
            try:
                subprocess.Popen([exe, f"--app={url}", "--window-size=1440,900",
                                  "--new-window"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 **({"creationflags": 0x08000000} if sys.platform == "win32" else {}))
                return
            except OSError:
                continue
        webbrowser.open(url)

    def arreter(self) -> None:
        self.httpd.shutdown()

    # ── Enrichissement (traduction, métadonnées, quiz) ──────────────────
    def langues_traduction(self, source: str) -> list[dict]:
        """Langues cibles proposées par Aristote, sans la langue source."""
        if self._langues is None:
            try:
                c = self.client()
                self._langues = c.langues() if c else []
            except Exception:                                   # noqa: BLE001
                self._langues = []
            self._langues = self._langues or [{"code": "en", "name": "Anglais"}]
        return [l for l in self._langues if l.get("code") != source]

    def _maj_enrichissement(self, pid: str, **champs) -> dict:
        """Relit le projet sur disque, modifie SEULEMENT l'enrichissement,
        puis enregistre : les corrections faites entre-temps sont préservées."""
        with self.verrou:
            p = pj.charger(pid)
            pj.enrichissement(p).update(champs)
            pj.enregistrer(p)
            return p

    def lancer_enrichissement(self, pid: str, traduire_vers: str,
                              metadonnees: bool, quiz: bool) -> None:
        client = self.client()
        if client is None:
            raise ValueError("Identifiants Aristote manquants (voir Réglages).")
        p = pj.charger(pid)
        # Phrases entières : la traduction a besoin du contexte complet.
        groupes = st.regrouper_phrases([st.SousTitre.depuis_dict(d) for d in p["sous_titres"]])
        r = self.reglages()
        eid = client.enrichir_sous_titres(
            st.vers_vtt(groupes), p["nom"], p.get("langue") or "fr",
            traduire_vers or None, metadonnees, quiz,
            # Vidéo Pod : listes réelles de l'instance ; sinon, celles des réglages.
            (p.get("pod") or {}).get("disciplines") or r.get("disciplines"),
            (p.get("pod") or {}).get("types") or r.get("types_media"))
        self._maj_enrichissement(pid, etat="en_cours", eid=eid, erreur="",
                                 detail="Envoyé à Aristote",
                                 traduire_vers=traduire_vers or "",
                                 groupes=[g.en_dict() for g in groupes])
        threading.Thread(target=self._suivre, args=(pid, client, eid, traduire_vers),
                         daemon=True).start()

    # ── Publication sur Pod (étape 2) ───────────────────────────────────
    def _journal(self, texte: str) -> None:
        """Une ligne dans le Journal de l'hôte ; jamais bloquant."""
        if self.journal_hote:
            try:
                self.journal_hote(texte)
            except Exception:                                   # noqa: BLE001
                pass

    def _pod_et_video(self, p: dict):
        if not p.get("pod"):
            raise ValueError("Ce projet n'est pas rattaché à une vidéo Pod.")
        api = self.pod()
        if api is None:
            raise ValueError("PodAdmin n'est pas connecté à Pod : connectez-vous dans "
                             "l'onglet Configuration, puis réessayez.")
        return api, api.video(p["pod"]["id"])

    def pistes_pod(self, pid: str) -> dict:
        api, video = self._pod_et_video(pj.charger(pid))
        return {"pistes": [{k: t.get(k) for k in ("url", "lang", "kind", "src")}
                           for t in api.pistes(video)],
                "encodee": bool(video.get("encoded")), "brouillon": bool(video.get("is_draft"))}

    def publier_pod(self, pid: str, demandes: list[dict]) -> list[dict]:
        """Publie chaque piste demandée ; une erreur n'arrête pas les suivantes.

        demande = {source: "original" | code de langue traduite, lang, kind,
                   remplacer: url de la piste à remplacer, ou absent}
        """
        from . import journal
        p = pj.charger(pid)
        api, video = self._pod_et_video(p)
        actuelles = {t["url"]: t for t in api.pistes(video)}
        e = p.get("enrichissement") or {}
        resultats = []
        for d in demandes:
            # Rangement imposé (décision de Cédric, 2026-10-04) : l'original
            # corrigé va TOUJOURS dans « fr », une traduction dans SA langue.
            # La langue envoyée par la page est ignorée.
            source = str(d.get("source") or "")
            lang = "fr" if source == "original" else source
            kind = str(d.get("kind") or "subtitles")
            try:
                if not lang or (source != "original" and lang == "fr"):
                    raise ValueError("langue de rangement invalide")
                cues = p["sous_titres"] if d.get("source") == "original" \
                    else (e.get("traductions") or {}).get(d.get("source"))
                if not cues:
                    raise ValueError("aucun sous-titre à publier")
                remplacer = actuelles.get(d["remplacer"]) if d.get("remplacer") else None
                if d.get("remplacer") and not remplacer:
                    raise ValueError("la piste à remplacer n'existe plus sur Pod")
                vtt = st.vers_vtt([st.SousTitre.depuis_dict(c) for c in cues])
                r = api.publier_piste(video, lang, kind, vtt, remplacer,
                                      os.path.join(p.get("dossier") or pj.DOSSIER_PROJETS,
                                                   "sauvegardes_pod"))
                journal.noter("piste_remplacee" if remplacer else "piste_ajoutee", video,
                              lang=lang, kind=kind, nb_sous_titres=len(cues),
                              nouveau_fichier=r["fichier"].get("file"),
                              nouvelle_piste=(r["piste"] or {}).get("url"),
                              ancienne_piste=r["remplacee"],
                              ancien_fichier=(remplacer or {}).get("src", ""),
                              ancien_fichier_supprime=r["fichier_supprime"],
                              sauvegarde=r["sauvegarde"], avertissement=r["avertissement"])
                resultats.append({"lang": lang, "kind": kind, "ok": True,
                                  "remplacee": bool(remplacer), "sauvegarde": r["sauvegarde"],
                                  "avertissement": r["avertissement"]})
                self._journal(
                    f"✏ Vidéo n° {video.get('id')} : {_PISTE.get(kind, kind)} « {lang} » "
                    f"{'remplacés' if remplacer else 'ajoutés'} sur Pod"
                    + (f" (ancienne piste sauvegardée : {r['sauvegarde']})" if r["sauvegarde"] else "")
                    + (f". ⚠️ {r['avertissement']}" if r["avertissement"] else "."))
            except Exception as ex:                             # noqa: BLE001
                journal.noter("echec_publication", video, lang=lang, kind=kind, erreur=str(ex))
                resultats.append({"lang": lang, "kind": kind, "ok": False,
                                  "erreur": self.message_erreur(ex)})
                self._journal(f"❌ Vidéo n° {video.get('id')} : publication des "
                              f"{_PISTE.get(kind, kind)} « {lang} » refusée. "
                              f"Détail : {type(ex).__name__} : {ex}")
        with self.verrou:
            p = pj.charger(pid)
            p.setdefault("publications", []).append(
                {"date": datetime.now().isoformat(timespec="seconds"), "resultats": resultats})
            pj.enregistrer(p)
        return resultats

    # ── Métadonnées sur Pod (étape 3) ───────────────────────────────────
    def metadonnees_pod(self, pid: str) -> dict:
        """Écran avant/après : ce qu'il y a sur Pod, ce que l'on propose."""
        from pod_api import tags_vers_pod
        p = pj.charger(pid)
        api, video = self._pod_et_video(p)
        m = (p.get("enrichissement") or {}).get("metadonnees") or {}
        chaine, ecartes = tags_vers_pod(m.get("mots_cles") or [])
        return {"pod": api.metadonnees(video),
                "propose": {"titre": m.get("titre", ""), "description": m.get("description", ""),
                            "mots_cles": m.get("mots_cles") or [], "discipline": m.get("discipline", ""),
                            "type": m.get("type", "")},
                "mots_cles_pod": chaine, "mots_cles_ecartes": ecartes}

    def publier_metadonnees(self, pid: str, avant: dict, nouveau: dict) -> dict:
        from . import journal
        p = pj.charger(pid)
        api, video = self._pod_et_video(p)
        champs = ", ".join(_CHAMP.get(k, k) for k in nouveau)
        try:
            r = api.maj_metadonnees(video["id"], avant, nouveau)
        except Exception as ex:
            journal.noter("echec_metadonnees", video, champs=list(nouveau), erreur=str(ex))
            self._journal(f"❌ Vidéo n° {video.get('id')} : métadonnées non modifiées "
                          f"({champs}). Détail : {type(ex).__name__} : {ex}")
            raise
        journal.noter("metadonnees_modifiees", video, champs=list(nouveau),
                      avant={k: r["avant"].get("disciplines" if k == "ajout_discipline" else k) for k in nouveau},
                      apres={k: r["apres"].get("disciplines" if k == "ajout_discipline" else k) for k in nouveau})
        self._journal(f"✏ Vidéo n° {video.get('id')} : métadonnées modifiées sur Pod ({champs}).")
        # La vidéo a changé sur Pod : on prévient l'hôte, pour que ses listes
        # (onglet Vidéos de PodAdmin) ne gardent pas l'ancien titre.
        if self.sur_video_modifiee:
            try:
                self.sur_video_modifiee(api.video(video["id"]))
            except Exception as ex:                             # noqa: BLE001
                self._journal(f"Vidéo n° {video.get('id')} : liste non rafraîchie ({ex}).")
        return r

    def reprendre(self, pid: str) -> None:
        """Relance le suivi d'un enrichissement resté en cours (redémarrage)."""
        e = (pj.charger(pid).get("enrichissement") or {})
        client = self.client()
        if e.get("etat") == "en_cours" and e.get("eid") and client:
            threading.Thread(target=self._suivre,
                             args=(pid, client, e["eid"], e.get("traduire_vers", "")),
                             daemon=True).start()

    def _suivre(self, pid: str, client, eid: str, traduire_vers: str) -> None:
        from .aristote_api import ETATS
        try:
            client.attendre(eid, intervalle=5, jusqu_au_bout=True,
                            rappel=lambda s, _d: self._maj_enrichissement(
                                pid, detail=ETATS.get(s, s)))
            version = client.version_finale(eid)
            with self.verrou:
                p = pj.charger(pid)
                params = st.Parametres.depuis_dict(p.get("parametres"))
                pj.appliquer_enrichissement(p, version, traduire_vers, params)
                pj.enregistrer(p)
        except Exception as e:                                  # noqa: BLE001
            self._maj_enrichissement(pid, etat="erreur", detail="", erreur=str(e))
        if self.sur_enregistrement:
            self.sur_enregistrement(pid)


class _Gestionnaire(BaseHTTPRequestHandler):
    srv: ServeurEditeur

    def log_message(self, *args):          # silence dans la console
        pass

    # ── Outils ──────────────────────────────────────────────────────────
    def _chemin(self) -> tuple[list[str], dict]:
        u = urllib.parse.urlparse(self.path)
        return [x for x in u.path.split("/") if x], urllib.parse.parse_qs(u.query)

    def _autorise(self, q: dict) -> bool:
        jeton = (q.get("t") or [""])[0] or self.headers.get("X-Jeton", "")
        return secrets.compare_digest(jeton, self.srv.jeton)

    def _json(self, code: int, d) -> None:
        corps = json.dumps(d, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)

    def _lire_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _projet(self, pid: str) -> dict | None:
        if not pid.isalnum() or not pj.existe(pid):
            return None
        return pj.charger(pid)

    # ── GET ─────────────────────────────────────────────────────────────
    def do_GET(self):
        parts, q = self._chemin()
        if not self._autorise(q):
            return self._json(403, {"erreur": "jeton invalide"})
        if len(parts) == 2 and parts[0] == "p":
            with open(_ressource("assets/editeur.html"), "rb") as f:
                page = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(page)
            return
        if len(parts) == 2 and parts[0] == "api":
            p = self._projet(parts[1])
            if p is None:
                return self._json(404, {"erreur": "projet introuvable"})
            return self._json(200, {
                "id": p["id"], "nom": p["nom"], "langue": p.get("langue"),
                "etat": p.get("etat"), "sous_titres": p["sous_titres"],
                "parametres": st.Parametres.depuis_dict(p.get("parametres")).en_dict(),
                "video": bool(p.get("media")) and os.path.exists(p["media"]),
                # Vidéo Pod : lue directement en ligne par le navigateur.
                "video_distante": p.get("video_distante") or "",
                "pod": p.get("pod"),
                # Même thème que l'application (bascule clair / sombre de la barre latérale).
                # Sans choix enregistré, l'application démarre en sombre (comme PodAdmin).
                "theme": self.srv.reglages().get("theme") or "dark",
                # Choix possibles pour les listes déroulantes de l'onglet
                # Métadonnées : ceux de Pod pour une vidéo Pod, sinon ceux des réglages.
                "listes": {
                    "disciplines": (p.get("pod") or {}).get("disciplines")
                                   or self.srv.reglages().get("disciplines") or [],
                    "types": (p.get("pod") or {}).get("types")
                             or self.srv.reglages().get("types_media") or [],
                },
                "audio": bool(p.get("audio")) and os.path.exists(p["audio"]),
                "formats": self.srv.formats_defaut(),
                "version": __version__,
                "enrichissement": pj.enrichissement(p),
                "langues_traduction": self.srv.langues_traduction(p.get("langue") or "fr"),
            })
        # État des pistes sur Pod, lu juste avant d'ouvrir la fenêtre de publication.
        if len(parts) == 4 and parts[0] == "api" and parts[2:] == ["pod", "pistes"]:
            if self._projet(parts[1]) is None:
                return self._json(404, {"erreur": "projet introuvable"})
            try:
                return self._json(200, self.srv.pistes_pod(parts[1]))
            except Exception as e:                              # noqa: BLE001
                return self._json(400, {"erreur": self.srv.message_erreur(e)})
        if len(parts) == 4 and parts[0] == "api" and parts[2:] == ["pod", "metadonnees"]:
            if self._projet(parts[1]) is None:
                return self._json(404, {"erreur": "projet introuvable"})
            try:
                return self._json(200, self.srv.metadonnees_pod(parts[1]))
            except Exception as e:                              # noqa: BLE001
                return self._json(400, {"erreur": self.srv.message_erreur(e)})
        # Interrogé toutes les 5 s par la page pendant un enrichissement.
        if len(parts) == 3 and parts[0] == "api" and parts[2] == "enrichissement":
            p = self._projet(parts[1])
            if p is None:
                return self._json(404, {"erreur": "projet introuvable"})
            return self._json(200, pj.enrichissement(p))
        if parts == ["ressources", "logo_ut.png"]:      # logo de l'en-tête de l'éditeur
            return self._envoyer_fichier(_ressource("assets/logo_ut.png"))
        if len(parts) == 2 and parts[0] in ("media", "audio"):
            p = self._projet(parts[1])
            fichier = p and (p["media"] if parts[0] == "media" else p.get("audio"))
            if not fichier or not os.path.exists(fichier):
                return self._json(404, {"erreur": "fichier introuvable"})
            return self._envoyer_fichier(fichier)
        self._json(404, {"erreur": "inconnu"})

    def _envoyer_fichier(self, chemin: str) -> None:
        """Sert un fichier avec prise en charge de Range (déplacement dans la vidéo)."""
        taille = os.path.getsize(chemin)
        mime = mimetypes.guess_type(chemin)[0] or "application/octet-stream"
        debut, fin = 0, taille - 1
        plage = self.headers.get("Range")
        if plage and plage.startswith("bytes="):
            a, _, b = plage[6:].split(",")[0].partition("-")
            if a:
                debut = int(a)
                fin = int(b) if b else taille - 1
            else:
                debut = max(taille - int(b), 0)
            fin = min(fin, taille - 1)
            if debut > fin:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{taille}")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {debut}-{fin}/{taille}")
        else:
            self.send_response(200)
        longueur = fin - debut + 1
        self.send_header("Content-Type", mime)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(longueur))
        self.end_headers()
        try:
            with open(chemin, "rb") as f:
                f.seek(debut)
                reste = longueur
                while reste > 0:
                    bloc = f.read(min(1024 * 1024, reste))
                    if not bloc:
                        break
                    self.wfile.write(bloc)
                    reste -= len(bloc)
        except (ConnectionError, BrokenPipeError):
            pass                         # le navigateur a interrompu (normal)

    # ── POST ────────────────────────────────────────────────────────────
    def do_POST(self):
        parts, q = self._chemin()
        if not self._autorise(q):
            return self._json(403, {"erreur": "jeton invalide"})
        if len(parts) < 2 or parts[0] != "api":
            return self._json(404, {"erreur": "inconnu"})
        # Publication sur Pod : hors du verrou (appels réseau, verrou pris au besoin).
        if len(parts) == 4 and parts[2:] == ["pod", "publier"]:
            if self._projet(parts[1]) is None:
                return self._json(404, {"erreur": "projet introuvable"})
            d = self._lire_json()
            try:
                resultats = self.srv.publier_pod(parts[1], list(d.get("pistes") or []))
            except Exception as e:                              # noqa: BLE001
                return self._json(400, {"erreur": self.srv.message_erreur(e)})
            return self._json(200, {"resultats": resultats})
        if len(parts) == 4 and parts[2:] == ["pod", "metadonnees"]:
            if self._projet(parts[1]) is None:
                return self._json(404, {"erreur": "projet introuvable"})
            d = self._lire_json()
            try:
                return self._json(200, self.srv.publier_metadonnees(
                    parts[1], dict(d.get("avant") or {}), dict(d.get("nouveau") or {})))
            except Exception as e:                              # noqa: BLE001
                return self._json(400, {"erreur": self.srv.message_erreur(e)})
        # Hors du verrou : lancer_enrichissement() le prend lui-même.
        if len(parts) == 3 and parts[2] == "enrichir":
            if self._projet(parts[1]) is None:
                return self._json(404, {"erreur": "projet introuvable"})
            d = self._lire_json()
            try:
                self.srv.lancer_enrichissement(
                    parts[1], str(d.get("traduire_vers") or ""),
                    bool(d.get("metadonnees")), bool(d.get("quiz")))
            except Exception as e:                              # noqa: BLE001
                return self._json(400, {"erreur": self.srv.message_erreur(e)})
            return self._json(200, pj.enrichissement(pj.charger(parts[1])))
        with self.srv.verrou:
            p = self._projet(parts[1])
            if p is None:
                return self._json(404, {"erreur": "projet introuvable"})
            d = self._lire_json()
            action = parts[2] if len(parts) > 2 else ""
            try:
                if action == "":
                    p["sous_titres"] = [
                        {"start": float(s["start"]), "end": float(s["end"]),
                         "text": str(s["text"])} for s in d["sous_titres"]]
                    if p.get("etat") != "corrige":
                        p["etat"] = "a_corriger"
                    pj.enregistrer(p)
                    reponse = {"ok": True}
                elif action == "exporter":
                    formats = [f for f in d.get("formats", ["vtt"]) if f in ("vtt", "srt")]
                    if "sous_titres" in d:
                        p["sous_titres"] = d["sous_titres"]
                    ecrits = pj.exporter(p, formats or ["vtt"],
                                         langues=d.get("langues") or [],
                                         metadonnees=bool(d.get("metadonnees")),
                                         quiz=bool(d.get("quiz")))
                    p["etat"] = "corrige"
                    pj.enregistrer(p)
                    reponse = {"ok": True, "fichiers": ecrits}
                elif action == "redecouper":
                    params = st.Parametres.depuis_dict(
                        {**(p.get("parametres") or {}), **d.get("parametres", {})})
                    pj.redecouper(p, params)
                    pj.enregistrer(p)
                    reponse = {"ok": True, "sous_titres": p["sous_titres"],
                               "parametres": params.en_dict()}
                elif action == "enrichissement":
                    # Corrections faites dans les onglets Traduction,
                    # Métadonnées et Quiz.
                    e = pj.enrichissement(p)
                    for cle in ("metadonnees", "quiz", "traductions"):
                        if cle in d:
                            e[cle] = d[cle]
                    pj.enregistrer(p)
                    reponse = {"ok": True}
                else:
                    return self._json(404, {"erreur": "action inconnue"})
            except (KeyError, ValueError, TypeError, OSError) as e:
                return self._json(400, {"erreur": str(e)})
        if self.srv.sur_enregistrement:
            self.srv.sur_enregistrement(p["id"])
        self._json(200, reponse)
