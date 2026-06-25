#!/usr/bin/env python3
"""
app.py — PodAdmin (interface graphique)
Université de Toulouse — MFCA

Console d'administration Esup-Pod. Reprend le téléversement par lot de
« Pod Téléverseur » et y ajoute des modules d'admin :
  • Comptes — statut « équipe » (is_staff)
  • (à venir) Réaffectation de propriétaire, Nettoyage/Modération,
    Inventaire/Stats, Chaînes & thèmes.
Nécessite un token de compte SUPERUTILISATEUR.
"""

from __future__ import annotations

__author__      = "Cédric MONNA"
__contact__     = "cedricmonna@gmail.com"
__institution__ = "Université de Toulouse — MFCA"
__version__     = "0.1.0"
__date__        = "2026"
__license__     = "Usage interne — Université de Toulouse"


import os
import sys
import threading
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox

import config as cfg
from pod_api import (PodAPI, PodAPIError, CONTRIBUTOR_ROLES,
                     SUBTITLE_LANGS, SUBTITLE_KINDS)

# Pillow (fourni avec customtkinter) — pour afficher le logo
try:
    from PIL import Image as PILImage
    HAS_PIL = True
except Exception:
    HAS_PIL = False


def resource_path(rel: str) -> str:
    """Chemin d'une ressource, compatible PyInstaller (--onefile) et exécution directe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)

# Glisser-déposer (optionnel — l'appli fonctionne sans, via les boutons)
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except Exception:
    HAS_DND = False

APP_TITLE = "PodAdmin — Université de Toulouse"
APP_VERSION = "0.1.0"


# ════════════════════════════════════════════════════════════════════════════
#  MODÈLE : une entrée de la file d'attente
# ════════════════════════════════════════════════════════════════════════════

class UploadItem:
    def __init__(self, path: str):
        """Crée une entrée de la file d'upload à partir d'un chemin de fichier."""
        self.path = path
        self.filename = os.path.basename(path)
        # Titre par défaut = nom de fichier sans extension, nettoyé
        base = os.path.splitext(self.filename)[0]
        self.title = base.replace("_", " ").replace("-", " ").strip()
        self.status = "en attente"     # en attente | en cours | terminé | échec
        self.slug = ""
        self.video_url = ""
        self.error = ""
        # widgets (remplis à l'affichage)
        self.row = None
        self.title_var = None
        self.status_lbl = None


# ════════════════════════════════════════════════════════════════════════════
#  APPLICATION
# ════════════════════════════════════════════════════════════════════════════

# Base conditionnelle : mixe le moteur de glisser-déposer si disponible
if HAS_DND:
    class _AppBase(ctk.CTk, TkinterDnD.DnDWrapper):
        pass
else:
    class _AppBase(ctk.CTk):
        pass


class App(_AppBase):
    def __init__(self):
        """Initialise la fenêtre, charge config + token, construit l'UI et tente une connexion auto."""
        super().__init__()
        # Initialiser le moteur glisser-déposer (tkdnd)
        self.dnd_ok = False
        if HAS_DND:
            try:
                self.TkdndVersion = TkinterDnD._require(self)
                self.dnd_ok = True
            except Exception:
                self.dnd_ok = False

        self.title(APP_TITLE)
        self.geometry("1180x760")
        self.minsize(1000, 660)

        self.config_data = cfg.load_config()
        self.token = cfg.load_token()
        self.api: PodAPI | None = None

        self.types: list[dict] = []
        self.type_map: dict[str, str] = {}     # titre → url
        self.site_urls: list[str] = []         # sites (requis à l'upload)
        self.items: list[UploadItem] = []
        self.all_users: list[dict] = []        # liste complète Pod (pour sélection owner)
        self.additional_owner_urls: list[str] = []
        self.additional_owner_map: dict[str, str] = {}   # url → libellé (pour ré-ouverture)
        self.common_contributors: list[dict] = []

        self._build_ui()
        self._show_tab("upload")

        # Connexion auto si token déjà présent
        if self.config_data.get("url") and self.token:
            self._run(self._auto_connect)

    # ── Threading helpers ────────────────────────────────────────────────

    def _run(self, fn, *a):
        """Lance une fonction dans un thread d'arrière-plan (pour ne pas geler l'interface)."""
        threading.Thread(target=fn, args=a, daemon=True).start()

    def _ui(self, fn, *a, **kw):
        """Planifie une mise à jour d'interface dans le thread principal Tk (thread-safe)."""
        self.after(0, lambda: fn(*a, **kw))

    # ── Construction de l'interface ──────────────────────────────────────

    def _build_ui(self):
        """Construit la barre latérale (logo, état, navigation) et la zone de contenu."""
        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # En-tête : logo Université de Toulouse sur bandeau blanc (repli texte si absent)
        logo_loaded = False
        if HAS_PIL:
            try:
                logo_path = resource_path(os.path.join("assets", "logo_ut.png"))
                if os.path.exists(logo_path):
                    pil = PILImage.open(logo_path)
                    W = 178
                    H = round(W * pil.height / pil.width)
                    self.logo_img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(W, H))
                    card = ctk.CTkFrame(self.sidebar, fg_color="white", corner_radius=8)
                    card.pack(padx=12, pady=(18, 6), fill="x")
                    ctk.CTkLabel(card, image=self.logo_img, text="").pack(padx=10, pady=10)
                    logo_loaded = True
            except Exception:
                logo_loaded = False

        if not logo_loaded:
            ctk.CTkLabel(self.sidebar, text="Université de Toulouse",
                         font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(20, 0), padx=14)

        ctk.CTkLabel(self.sidebar, text="🛠️  PodAdmin",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(2, 0), padx=14)

        # État connexion
        box = ctk.CTkFrame(self.sidebar, fg_color="gray20", corner_radius=8)
        box.pack(padx=12, pady=14, fill="x")
        self.status_dot = ctk.CTkLabel(box, text="⚫", font=ctk.CTkFont(size=13))
        self.status_dot.pack(side="left", padx=8, pady=6)
        self.status_lbl = ctk.CTkLabel(box, text="Non connecté",
                                       font=ctk.CTkFont(size=11), text_color="gray")
        self.status_lbl.pack(side="left")

        # Agent identifié
        self.agent_lbl = ctk.CTkLabel(self.sidebar, text="", font=ctk.CTkFont(size=11),
                                      text_color="gray70", wraplength=190, justify="left")
        self.agent_lbl.pack(padx=14, pady=(0, 6), anchor="w")

        ctk.CTkFrame(self.sidebar, height=1, fg_color="gray30").pack(fill="x", padx=12, pady=4)

        self.nav_btns = {}
        for label, key in [
            ("📂   Téléversement", "upload"),
            ("⚙️   Encodage",      "encode"),
            ("👤   Comptes",       "comptes"),
            ("🎞️   Vidéos",        "browse"),
            ("🔄   Réaffectation", "reassign"),
            ("🧹   Nettoyage",     "clean"),
            ("📊   Inventaire",    "stats"),
            ("🗂   Chaînes",       "ct"),
            ("👥   Co-auteurs",    "coauthors"),
            ("⚙️   Configuration", "config"),
            ("📋   Journal",       "log"),
        ]:
            b = ctk.CTkButton(self.sidebar, text=label, anchor="w", height=40,
                              fg_color="transparent", text_color=("gray10", "gray90"),
                              hover_color=("gray75", "gray28"),
                              font=ctk.CTkFont(size=13),
                              command=lambda k=key: self._show_tab(k))
            b.pack(fill="x", padx=6, pady=2)
            self.nav_btns[key] = b

        ctk.CTkLabel(self.sidebar, text=f"v{APP_VERSION}",
                     font=ctk.CTkFont(size=9), text_color="gray40").pack(side="bottom", pady=10)

        # Zone principale
        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content.pack(side="right", fill="both", expand=True, padx=14, pady=14)

        self.tabs = {}
        self._build_tab_upload()
        self._build_tab_encode()
        self._build_tab_comptes()
        self._build_tab_browse()
        self._build_tab_reassign()
        self._build_tab_clean()
        self._build_tab_stats()
        self._build_tab_ct()
        self._build_tab_coauthors()
        self._build_tab_config()
        self._build_tab_log()

    def _show_tab(self, key: str):
        """Affiche l'onglet `key` et met en surbrillance son bouton de navigation."""
        for f in self.tabs.values():
            f.pack_forget()
        self.tabs[key].pack(fill="both", expand=True)
        for k, b in self.nav_btns.items():
            b.configure(fg_color=("gray75", "gray24") if k == key else "transparent")

    # ═════════════════════════════════════════════════════════════════════
    #  ONGLET TÉLÉVERSEMENT
    # ═════════════════════════════════════════════════════════════════════

    def _build_tab_upload(self):
        """Construit l'onglet Téléversement (sélection, réglages communs, liste, lancement)."""
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tabs["upload"] = frame

        ctk.CTkLabel(frame, text="📂  Téléversement par lot",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 10))

        # — Barre de sélection —
        sel = ctk.CTkFrame(frame, fg_color="transparent")
        sel.pack(fill="x", pady=(0, 6))

        ctk.CTkButton(sel, text="➕  Ajouter des fichiers", width=190,
                      command=self._add_files).pack(side="left", padx=(0, 8))
        ctk.CTkButton(sel, text="📁  Ajouter un dossier", width=190,
                      command=self._add_folder).pack(side="left", padx=(0, 8))
        ctk.CTkButton(sel, text="🗑  Vider la liste", width=140,
                      fg_color="gray35", hover_color="gray28",
                      command=self._clear_items).pack(side="left")

        self.count_lbl = ctk.CTkLabel(sel, text="0 vidéo(s)", text_color="gray",
                                      font=ctk.CTkFont(size=11))
        self.count_lbl.pack(side="right")

        # — Réglages communs (appliqués à tout le lot) —
        common = ctk.CTkFrame(frame)
        common.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(common, text="Réglages communs au lot",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=4,
                                                           padx=12, pady=(10, 4), sticky="w")

        ctk.CTkLabel(common, text="Type :").grid(row=1, column=0, padx=(12, 4), pady=8, sticky="e")
        self.type_combo = ctk.CTkComboBox(common, values=["(chargement…)"], width=200)
        self.type_combo.grid(row=1, column=1, padx=4, pady=8, sticky="w")

        ctk.CTkLabel(common, text="Visibilité :").grid(row=1, column=2, padx=(20, 4), pady=8, sticky="e")
        self.visibility_combo = ctk.CTkComboBox(
            common, width=200, values=["Brouillon / Privé", "Public"])
        self.visibility_combo.set("Brouillon / Privé")
        self.visibility_combo.grid(row=1, column=3, padx=4, pady=8, sticky="w")

        self.encode_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(common, text="Lancer l'encodage après le téléversement",
                        variable=self.encode_var).grid(row=2, column=0, columnspan=2,
                                                        padx=12, pady=(0, 6), sticky="w")

        # Propriétaires additionnels communs
        ctk.CTkButton(common, text="👥  Propriétaires additionnels…", width=240,
                      fg_color="gray35", hover_color="gray28",
                      command=self._edit_additional_owners).grid(
            row=2, column=2, columnspan=2, padx=12, pady=(0, 6), sticky="w")
        self.add_owners_lbl = ctk.CTkLabel(common, text="aucun", text_color="gray",
                                           font=ctk.CTkFont(size=11))
        self.add_owners_lbl.grid(row=3, column=2, columnspan=2, padx=12, pady=(0, 8), sticky="w")

        common.columnconfigure(3, weight=1)

        # — Tableau des vidéos (titres éditables) —
        hint = ("Vérifiez / corrigez les titres avant l'envoi  —  "
                "💡 vous pouvez aussi glisser-déposer fichiers et dossiers ci-dessous :"
                if getattr(self, "dnd_ok", False) else
                "Vérifiez / corrigez les titres avant l'envoi :")
        ctk.CTkLabel(frame, text=hint, font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(2, 2))

        self.list_frame = ctk.CTkScrollableFrame(frame, height=240)
        self.list_frame.pack(fill="both", expand=True)

        # Activer le glisser-déposer sur la zone de liste
        if getattr(self, "dnd_ok", False):
            try:
                self.list_frame.drop_target_register(DND_FILES)
                self.list_frame.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

        empty_text = ("Aucune vidéo.\nGlissez-déposez ici des fichiers ou des dossiers,\n"
                      "ou utilisez les boutons ci-dessus."
                      if getattr(self, "dnd_ok", False) else
                      "Aucune vidéo.\nUtilisez « Ajouter des fichiers » ou « Ajouter un dossier ».")
        self._empty_hint = ctk.CTkLabel(self.list_frame, text=empty_text, text_color="gray")
        self._empty_hint.pack(pady=40)

        # — Lancement + progression —
        launch = ctk.CTkFrame(frame, fg_color="transparent")
        launch.pack(fill="x", pady=(8, 0))

        self.launch_btn = ctk.CTkButton(
            launch, text="🚀  Lancer le téléversement", height=40,
            fg_color="#16a34a", hover_color="#15803d",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._start_upload)
        self.launch_btn.pack(side="left")

        self.global_msg = ctk.CTkLabel(launch, text="", text_color="gray",
                                       font=ctk.CTkFont(size=12))
        self.global_msg.pack(side="left", padx=14)

        # Progression fichier courant
        self.file_progress = ctk.CTkProgressBar(frame)
        self.file_progress.pack(fill="x", pady=(8, 0))
        self.file_progress.set(0)
        self.file_progress_lbl = ctk.CTkLabel(frame, text="", text_color="gray",
                                              font=ctk.CTkFont(size=10))
        self.file_progress_lbl.pack(anchor="w")

        # Progression globale du lot
        self.batch_progress = ctk.CTkProgressBar(frame, progress_color="#16a34a")
        self.batch_progress.pack(fill="x", pady=(4, 0))
        self.batch_progress.set(0)

    # ── Ajout de fichiers / dossier ──────────────────────────────────────

    def _add_files(self):
        """Ouvre un sélecteur de fichiers et ajoute les vidéos choisies à la file."""
        paths = filedialog.askopenfilenames(
            title="Choisir des vidéos",
            filetypes=[("Vidéos", "*.mp4 *.mov *.avi *.mkv *.webm *.m4v *.wmv *.flv *.mpg *.mpeg"),
                       ("Tous les fichiers", "*.*")])
        self._add_paths(paths)

    def _add_folder(self):
        """Scanne un dossier (récursivement) et ajoute toutes les vidéos trouvées à la file."""
        folder = filedialog.askdirectory(title="Choisir un dossier de vidéos")
        if not folder:
            return
        found = []
        for root, _dirs, files in os.walk(folder):
            for name in files:
                if os.path.splitext(name)[1].lower() in cfg.VIDEO_EXTENSIONS:
                    found.append(os.path.join(root, name))
        if not found:
            self.global_msg.configure(text="Aucune vidéo trouvée dans ce dossier.",
                                      text_color="#f59e0b")
            return
        self._add_paths(sorted(found))

    def _on_drop(self, event):
        """Glisser-déposer : ajoute les vidéos des fichiers/dossiers déposés."""
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]
        found = []
        for p in paths:
            p = p.strip().strip("{}")
            if not p:
                continue
            if os.path.isdir(p):
                for root, _d, names in os.walk(p):
                    for n in names:
                        if os.path.splitext(n)[1].lower() in cfg.VIDEO_EXTENSIONS:
                            found.append(os.path.join(root, n))
            elif os.path.isfile(p) and os.path.splitext(p)[1].lower() in cfg.VIDEO_EXTENSIONS:
                found.append(p)
        if found:
            self._show_tab("upload")
            self._add_paths(sorted(found))
            self.global_msg.configure(
                text=f"{len(found)} vidéo(s) ajoutée(s) par glisser-déposer.", text_color="#22c55e")
        else:
            self.global_msg.configure(
                text="Aucune vidéo reconnue dans les éléments déposés.", text_color="#f59e0b")

    def _add_paths(self, paths):
        """Ajoute des chemins à la file en évitant les doublons, puis rafraîchit l'affichage."""
        existing = {it.path for it in self.items}
        added = 0
        for p in paths:
            if p not in existing:
                self.items.append(UploadItem(p))
                existing.add(p)          # éviter les doublons dans un même lot
                added += 1
        if added:
            self._refresh_list()
            self._log(f"{added} vidéo(s) ajoutée(s) à la file.")

    def _clear_items(self):
        """Vide la file d'attente et rafraîchit l'affichage."""
        self.items.clear()
        self._refresh_list()

    def _refresh_list(self):
        """Reconstruit le tableau des vidéos en attente (nom, titre éditable, état)."""
        for w in self.list_frame.winfo_children():
            w.destroy()

        if not self.items:
            empty_text = ("Aucune vidéo.\nGlissez-déposez ici des fichiers ou des dossiers,\n"
                          "ou utilisez les boutons ci-dessus."
                          if getattr(self, "dnd_ok", False) else
                          "Aucune vidéo.\nUtilisez « Ajouter des fichiers » ou « Ajouter un dossier ».")
            ctk.CTkLabel(self.list_frame, text=empty_text, text_color="gray").pack(pady=40)
            self.count_lbl.configure(text="0 vidéo(s)")
            return

        # En-tête
        hdr = ctk.CTkFrame(self.list_frame, fg_color="gray22", corner_radius=4)
        hdr.pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(hdr, text="Fichier", width=230, anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=8, pady=4)
        ctk.CTkLabel(hdr, text="Titre (éditable)", anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=8, expand=True, fill="x")
        ctk.CTkLabel(hdr, text="État", width=110,
                     font=ctk.CTkFont(size=11, weight="bold")).pack(side="right", padx=8)

        for i, it in enumerate(self.items):
            row = ctk.CTkFrame(self.list_frame,
                               fg_color="gray17" if i % 2 == 0 else "gray14", corner_radius=4)
            row.pack(fill="x", pady=1)
            it.row = row

            # nom de fichier (tronqué) + taille
            try:
                size_mb = os.path.getsize(it.path) / (1024 * 1024)
                size_txt = f"{size_mb:.0f} Mo"
            except OSError:
                size_txt = "?"
            fname = it.filename if len(it.filename) <= 28 else it.filename[:25] + "…"
            ctk.CTkLabel(row, text=f"{fname}\n{size_txt}", width=230, anchor="w",
                         justify="left", font=ctk.CTkFont(size=11)).pack(side="left", padx=8, pady=4)

            # titre éditable
            it.title_var = ctk.StringVar(value=it.title)
            it.title_var.trace_add("write",
                                    lambda *_x, item=it: setattr(item, "title", item.title_var.get()))
            ctk.CTkEntry(row, textvariable=it.title_var).pack(
                side="left", padx=8, pady=6, expand=True, fill="x")

            # bouton supprimer
            ctk.CTkButton(row, text="✕", width=28, height=26,
                          fg_color="gray30", hover_color="#7f1d1d",
                          command=lambda item=it: self._remove_item(item)).pack(side="right", padx=4)

            # état
            it.status_lbl = ctk.CTkLabel(row, text=it.status, width=100,
                                         text_color="gray60", font=ctk.CTkFont(size=11))
            it.status_lbl.pack(side="right", padx=6)

        self.count_lbl.configure(text=f"{len(self.items)} vidéo(s)")

    def _remove_item(self, item: UploadItem):
        """Retire une vidéo de la file et rafraîchit l'affichage."""
        if item in self.items:
            self.items.remove(item)
            self._refresh_list()

    def _set_item_status(self, item: UploadItem, status: str, color="gray60"):
        """Met à jour le libellé d'état d'une vidéo dans la liste."""
        item.status = status
        if item.status_lbl:
            item.status_lbl.configure(text=status, text_color=color)

    # ── Propriétaires additionnels communs ───────────────────────────────

    def _edit_additional_owners(self):
        """Ouvre OwnerPicker pour choisir les co-propriétaires communs au lot."""
        if not self.api:
            self.global_msg.configure(text="Connectez-vous d'abord (onglet Configuration).",
                                      text_color="#f59e0b")
            return
        OwnerPicker(self, on_done=self._on_owners_picked,
                    preselected=dict(self.additional_owner_map))

    def _on_owners_picked(self, urls: list[str], labels: list[str]):
        """Callback d'OwnerPicker : mémorise les co-propriétaires choisis et met à jour le libellé."""
        self.additional_owner_urls = urls
        self.additional_owner_map = dict(zip(urls, labels))
        if urls:
            self.add_owners_lbl.configure(text=", ".join(labels)[:60], text_color="#22c55e")
        else:
            self.add_owners_lbl.configure(text="aucun", text_color="gray")

    # ── Lancement du téléversement ───────────────────────────────────────

    def _start_upload(self):
        """Vérifie les prérequis (connexion, agent, type) puis lance le lot en arrière-plan."""
        if not self.api:
            self.global_msg.configure(text="Non connecté. Voir l'onglet Configuration.",
                                      text_color="#ef4444")
            return
        if not self.items:
            self.global_msg.configure(text="Aucune vidéo à téléverser.", text_color="#f59e0b")
            return
        owner_url = self.config_data.get("agent_owner_url", "")
        if not owner_url:
            self.global_msg.configure(
                text="Identifiez l'agent déposant (onglet Configuration).", text_color="#f59e0b")
            self._show_tab("config")
            return
        type_title = self.type_combo.get()
        type_url = self.type_map.get(type_title, "")
        if not type_url:
            self.global_msg.configure(text="Sélectionnez un type valide.", text_color="#f59e0b")
            return

        self.launch_btn.configure(state="disabled")
        self.batch_progress.set(0)
        self._run(self._do_batch_upload, owner_url, type_url)

    def _do_batch_upload(self, owner_url: str, type_url: str):
        """(Thread) Téléverse chaque vidéo, ajoute les crédits, lance l'encodage, suit la progression."""
        is_draft = self.visibility_combo.get().startswith("Brouillon")
        do_encode = self.encode_var.get()
        total = len(self.items)
        ok = 0

        for idx, it in enumerate(self.items, 1):
            if it.status == "terminé":
                ok += 1
                self._ui(self.batch_progress.set, idx / total)
                continue

            self._ui(self._set_item_status, it, "en cours", "#3b82f6")
            self._ui(self.file_progress.set, 0)
            self._ui(self.global_msg.configure,
                     text=f"Téléversement {idx}/{total} : {it.title}", text_color="gray")

            def progress(sent, tot, item=it):
                frac = sent / tot if tot else 0
                self._ui(self.file_progress.set, frac)
                self._ui(self.file_progress_lbl.configure,
                         text=f"{item.filename} — {sent/1024/1024:.0f} / {tot/1024/1024:.0f} Mo")

            try:
                video = self.api.upload_video(
                    it.path, it.title or it.filename, owner_url, type_url,
                    main_lang=self.config_data.get("main_lang", "fr"),
                    cursus=self.config_data.get("cursus", "0"),
                    is_draft=is_draft,
                    additional_owner_urls=self.additional_owner_urls,
                    site_urls=self.site_urls,
                    progress_cb=progress,
                )
                it.slug = video.get("slug", "") if isinstance(video, dict) else ""
                it.video_url = video.get("url", "") if isinstance(video, dict) else ""

                # Contributeurs communs
                for c in self.common_contributors:
                    try:
                        self.api.add_contributor(it.video_url, c["name"], c.get("email", ""),
                                                 c.get("role", "author"), c.get("weblink", ""))
                    except Exception as e:
                        self._ui(self._log, f"Contributeur non ajouté ({it.title}) : {e}")

                # Encodage
                if do_encode and it.slug:
                    try:
                        self.api.launch_encoding(it.slug)
                    except Exception as e:
                        self._ui(self._log, f"Encodage non lancé ({it.title}) : {e}")

                ok += 1
                self._ui(self._set_item_status, it, "✅ terminé", "#22c55e")
                self._ui(self._log, f"Téléversé : {it.title}  (slug={it.slug})")

            except PodAPIError as e:
                it.error = f"{e} — {e.body}"
                self._ui(self._set_item_status, it, "❌ échec", "#ef4444")
                self._ui(self._log, f"ÉCHEC {it.title} : {e} | {e.body[:200]}")
            except Exception as e:
                it.error = str(e)
                self._ui(self._set_item_status, it, "❌ échec", "#ef4444")
                self._ui(self._log, f"ÉCHEC {it.title} : {e}")

            self._ui(self.batch_progress.set, idx / total)

        self._ui(self._on_batch_done, ok, total)

    def _on_batch_done(self, ok: int, total: int):
        """Réactive l'interface et affiche le bilan une fois le lot terminé."""
        self.launch_btn.configure(state="normal")
        self.file_progress.set(0)
        self.file_progress_lbl.configure(text="")
        color = "#22c55e" if ok == total else "#f59e0b"
        self.global_msg.configure(text=f"Terminé : {ok}/{total} vidéo(s) téléversée(s).", text_color=color)
        self._log(f"Lot terminé : {ok}/{total} réussis.")

    # ═════════════════════════════════════════════════════════════════════
    #  ONGLET CO-AUTEURS (sur vidéos existantes)
    # ═════════════════════════════════════════════════════════════════════

    def _build_tab_coauthors(self):
        """Construit l'onglet Co-auteurs (recherche de vidéo + ajout de contributeurs)."""
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tabs["coauthors"] = frame

        ctk.CTkLabel(frame, text="👥  Co-auteurs sur une vidéo existante",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 6))

        ctk.CTkLabel(frame, text="Recherchez une vidéo par titre, puis ajoutez des "
                                 "propriétaires additionnels (comptes Pod) ou des "
                                 "contributeurs (crédits libres).",
                     text_color="gray70", wraplength=820, justify="left").pack(anchor="w", pady=(0, 10))

        search = ctk.CTkFrame(frame, fg_color="transparent")
        search.pack(fill="x")
        self.ca_search = ctk.CTkEntry(search, placeholder_text="🔍 titre de la vidéo…", width=360)
        self.ca_search.pack(side="left", padx=(0, 8))
        self.ca_search.bind("<Return>", lambda e: self._run(self._ca_search_videos))
        ctk.CTkButton(search, text="Rechercher", width=120,
                      command=lambda: self._run(self._ca_search_videos)).pack(side="left")

        self.ca_results = ctk.CTkScrollableFrame(frame, height=160)
        self.ca_results.pack(fill="x", pady=8)
        ctk.CTkLabel(self.ca_results, text="Lancez une recherche.", text_color="gray").pack(pady=14)

        self.ca_selected_lbl = ctk.CTkLabel(frame, text="Aucune vidéo sélectionnée.",
                                            text_color="gray", font=ctk.CTkFont(size=12, weight="bold"))
        self.ca_selected_lbl.pack(anchor="w", pady=(4, 4))

        # Formulaire contributeur
        form = ctk.CTkFrame(frame)
        form.pack(fill="x", pady=4)
        ctk.CTkLabel(form, text="Ajouter un contributeur (crédit)",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=4,
                                                           padx=12, pady=(10, 4), sticky="w")
        ctk.CTkLabel(form, text="Nom :").grid(row=1, column=0, padx=(12, 4), pady=6, sticky="e")
        self.ca_name = ctk.CTkEntry(form, width=200, placeholder_text="Prénom NOM")
        self.ca_name.grid(row=1, column=1, padx=4, pady=6)
        ctk.CTkLabel(form, text="Email :").grid(row=1, column=2, padx=(16, 4), pady=6, sticky="e")
        self.ca_email = ctk.CTkEntry(form, width=220, placeholder_text="prenom.nom@univ-tlse.fr")
        self.ca_email.grid(row=1, column=3, padx=4, pady=6)
        ctk.CTkLabel(form, text="Rôle :").grid(row=2, column=0, padx=(12, 4), pady=6, sticky="e")
        self.ca_role = ctk.CTkComboBox(form, width=200, values=CONTRIBUTOR_ROLES)
        self.ca_role.set("author")
        self.ca_role.grid(row=2, column=1, padx=4, pady=6)
        ctk.CTkButton(form, text="📋  Choisir dans la liste Pod", width=200,
                      fg_color="gray35", hover_color="gray28",
                      command=self._ca_pick_user).grid(row=2, column=2, padx=4, pady=6)
        ctk.CTkButton(form, text="➕  Ajouter le contributeur", fg_color="#16a34a",
                      hover_color="#15803d", command=self._ca_add_contributor).grid(
            row=2, column=3, padx=4, pady=6, sticky="e")
        form.columnconfigure(3, weight=1)

        self.ca_msg = ctk.CTkLabel(frame, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self.ca_msg.pack(anchor="w", pady=4)

        self._ca_selected_video = None

    def _ca_search_videos(self):
        """(Thread) Recherche des vidéos par titre via l'API et affiche les résultats."""
        if not self.api:
            self._ui(self.ca_msg.configure, text="Non connecté.", text_color="#ef4444")
            return
        q = self.ca_search.get().strip()
        try:
            data = self.api._get("/videos/", {"search": q, "limit": 30})
            videos = data.get("results", []) if isinstance(data, dict) else []
            self._ui(self._ca_show_results, videos)
        except Exception as e:
            self._ui(self.ca_msg.configure, text=f"Erreur : {e}", text_color="#ef4444")

    def _ca_show_results(self, videos: list):
        """Affiche la liste cliquable des vidéos trouvées."""
        for w in self.ca_results.winfo_children():
            w.destroy()
        if not videos:
            ctk.CTkLabel(self.ca_results, text="Aucun résultat.", text_color="gray").pack(pady=14)
            return
        for v in videos:
            title = v.get("title", "Sans titre")
            ctk.CTkButton(self.ca_results, text=f"  {title[:60]}", anchor="w",
                          fg_color="transparent", text_color=("gray10", "gray90"),
                          hover_color=("gray75", "gray28"), height=30,
                          command=lambda vid=v: self._ca_select(vid)).pack(fill="x", pady=1)

    def _ca_select(self, video: dict):
        """Mémorise la vidéo sélectionnée pour l'ajout de contributeurs."""
        self._ca_selected_video = video
        self.ca_selected_lbl.configure(text=f"✅  {video.get('title','')[:60]}", text_color="#22c55e")

    def _ca_pick_user(self):
        """Ouvre OwnerPicker en mode sélection unique pour pré-remplir un contributeur."""
        if not self.api:
            self.ca_msg.configure(text="Connectez-vous d'abord.", text_color="#f59e0b")
            return
        OwnerPicker(self, on_done=lambda *a: None, title="Choisir un utilisateur Pod",
                    single=True, on_single=self._ca_fill_from_user)

    def _ca_fill_from_user(self, u: dict):
        """Pré-remplit le formulaire contributeur à partir d'un compte Pod choisi."""
        name = f"{u.get('first_name','')} {u.get('last_name','')}".strip() or u.get("username", "")
        self.ca_name.delete(0, "end")
        self.ca_name.insert(0, name)
        email = u.get("email", "") or ""
        if email:
            self.ca_email.delete(0, "end")
            self.ca_email.insert(0, email)
        self.ca_msg.configure(text=f"Pré-rempli depuis : {u.get('username','')}", text_color="#22c55e")

    def _ca_add_contributor(self):
        """Vérifie la saisie puis lance l'ajout du contributeur en arrière-plan."""
        if not self._ca_selected_video:
            self.ca_msg.configure(text="Sélectionnez une vidéo.", text_color="#f59e0b")
            return
        name = self.ca_name.get().strip()
        if not name:
            self.ca_msg.configure(text="Le nom est requis.", text_color="#f59e0b")
            return
        video_url = self._ca_selected_video.get("url", "")
        self._run(self._ca_do_add, video_url, name, self.ca_email.get().strip(), self.ca_role.get())

    def _ca_do_add(self, video_url, name, email, role):
        """(Thread) Ajoute un contributeur (crédit) à la vidéo via l'API."""
        try:
            self.api.add_contributor(video_url, name, email, role)
            self._ui(self.ca_msg.configure, text=f"✅  {name} ajouté(e) ({role}).", text_color="#22c55e")
            self._ui(self.ca_name.delete, 0, "end")
            self._ui(self.ca_email.delete, 0, "end")
            self._ui(self._log, f"Contributeur ajouté : {name} ({role})")
        except Exception as e:
            self._ui(self.ca_msg.configure, text=f"❌  {e}", text_color="#ef4444")

    # ═════════════════════════════════════════════════════════════════════
    #  ONGLET CONFIGURATION
    # ═════════════════════════════════════════════════════════════════════

    def _build_tab_config(self):
        """Construit l'onglet Configuration (connexion API + choix de l'agent déposant)."""
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tabs["config"] = frame

        ctk.CTkLabel(frame, text="⚙️  Configuration",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 10))

        # — Connexion API —
        api_box = ctk.CTkFrame(frame)
        api_box.pack(fill="x")
        ctk.CTkLabel(api_box, text="Connexion à l'instance Pod (compte superutilisateur)",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=3,
                                                           padx=12, pady=(12, 4), sticky="w")

        ctk.CTkLabel(api_box, text="URL :", width=70, anchor="e").grid(row=1, column=0, padx=8, pady=8)
        self.url_entry = ctk.CTkEntry(api_box, width=430)
        self.url_entry.insert(0, self.config_data.get("url", ""))
        self.url_entry.grid(row=1, column=1, padx=8, pady=8, sticky="ew")

        ctk.CTkLabel(api_box, text="Token :", width=70, anchor="e").grid(row=2, column=0, padx=8, pady=8)
        self.token_entry = ctk.CTkEntry(api_box, width=430, show="*")
        if self.token:
            self.token_entry.insert(0, self.token)
        self.token_entry.grid(row=2, column=1, padx=8, pady=8, sticky="ew")

        self.show_token = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(api_box, text="Afficher", variable=self.show_token,
                        command=lambda: self.token_entry.configure(
                            show="" if self.show_token.get() else "*")).grid(row=2, column=2, padx=4)

        btn_row = ctk.CTkFrame(api_box, fg_color="transparent")
        btn_row.grid(row=3, column=1, columnspan=2, padx=8, pady=10, sticky="w")
        ctk.CTkButton(btn_row, text="🔌  Tester & se connecter", fg_color="#16a34a",
                      hover_color="#15803d", command=self._connect).pack(side="left")
        ctk.CTkButton(btn_row, text="🚪  Oublier le token / Se déconnecter", width=260,
                      fg_color="gray35", hover_color="#7f1d1d",
                      command=self._forget_token).pack(side="left", padx=10)
        api_box.columnconfigure(1, weight=1)

        self.config_msg = ctk.CTkLabel(frame, text="", font=ctk.CTkFont(size=12))
        self.config_msg.pack(anchor="w", pady=4)

        ctk.CTkFrame(frame, height=1, fg_color="gray30").pack(fill="x", pady=8)

        # — Agent déposant —
        agent_box = ctk.CTkFrame(frame)
        agent_box.pack(fill="x")
        ctk.CTkLabel(agent_box, text="Agent déposant (propriétaire des vidéos)",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=3,
                                                           padx=12, pady=(12, 2), sticky="w")
        ctk.CTkLabel(agent_box, text="Les vidéos déposées appartiendront à ce compte Pod.",
                     text_color="gray70", font=ctk.CTkFont(size=11)).grid(
            row=1, column=0, columnspan=3, padx=12, pady=(0, 6), sticky="w")

        self.agent_filter = ctk.CTkEntry(agent_box, width=300,
                                         placeholder_text="🔍 nom / identifiant…")
        self.agent_filter.grid(row=2, column=0, columnspan=2, padx=8, pady=8, sticky="ew")
        self.agent_filter.bind("<KeyRelease>", lambda e: self._render_users())
        ctk.CTkButton(agent_box, text="🔄  Recharger", width=130,
                      command=lambda: self._run(self._load_all_users)).grid(row=2, column=2, padx=8, pady=8)

        self.users_count_lbl = ctk.CTkLabel(agent_box, text="", text_color="gray",
                                            font=ctk.CTkFont(size=11))
        self.users_count_lbl.grid(row=3, column=0, columnspan=3, padx=12, sticky="w")

        self.agent_results = ctk.CTkScrollableFrame(agent_box, height=220)
        self.agent_results.grid(row=4, column=0, columnspan=3, padx=12, pady=(0, 10), sticky="ew")
        agent_box.columnconfigure(1, weight=1)

        # — Aide token —
        help_box = ctk.CTkFrame(frame, fg_color="gray18", corner_radius=8)
        help_box.pack(fill="x", pady=8)
        ctk.CTkLabel(help_box, text="ℹ️  Créer le token de service",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=14, pady=(10, 2))
        ctk.CTkLabel(
            help_box,
            text="Connecté en administrateur, ouvrez  <URL>/admin/authtoken/  → "
                 "« Add token » → choisissez le compte de service.\n"
                 "⚠️ Le token hérite des droits de ce compte. Il est stocké chiffré "
                 "dans le coffre-fort de votre système (Keychain / Credential Manager).",
            justify="left", text_color="gray70", wraplength=820).pack(anchor="w", padx=14, pady=(0, 12))

    def _forget_token(self):
        """Efface le token de ce poste et se déconnecte."""
        cfg.clear_token()
        self.token = ""
        self.api = None
        self.all_users = []
        if hasattr(self, "token_entry"):
            self.token_entry.delete(0, "end")
        if hasattr(self, "agent_results"):
            self._render_users()
        if hasattr(self, "users_count_lbl"):
            self.users_count_lbl.configure(text="")
        self._set_status(False)
        self.config_msg.configure(
            text="🚪  Token effacé de ce poste. Saisissez-le à nouveau pour vous reconnecter.",
            text_color="#f59e0b")
        self._log("Token effacé du poste — déconnexion.")

    def _connect(self):
        """Lit URL + token saisis et lance la connexion en arrière-plan."""
        url = self.url_entry.get().strip()
        token = self.token_entry.get().strip()
        if not url or not token:
            self.config_msg.configure(text="URL et token requis.", text_color="#ef4444")
            return
        self.config_msg.configure(text="⏳  Connexion…", text_color="gray")
        self._run(self._do_connect, url, token)

    def _do_connect(self, url, token):
        """(Thread) Teste la connexion à l'instance puis bascule l'UI selon le résultat."""
        try:
            api = PodAPI(url, token)
            count = api.test_connection()
            self._ui(self._on_connected, api, url, token, count)
        except Exception as e:
            self._ui(self.config_msg.configure, text=f"❌  Échec : {e}", text_color="#ef4444")
            self._ui(self._set_status, False)

    def _on_connected(self, api, url, token, count):
        """Connexion réussie : mémorise le client, enregistre le token, charge types et comptes."""
        self.api = api
        self.token = token
        self.config_data["url"] = url
        cfg.save_token(token)
        cfg.save_config(self.config_data)
        self._set_status(True)
        self.config_msg.configure(text=f"✅  Connecté — {count} vidéo(s) accessibles.",
                                  text_color="#22c55e")
        self._run(self._load_types)
        self._run(self._load_all_users)

    def _auto_connect(self):
        """(Thread) Reconnexion automatique au démarrage si un token est déjà enregistré."""
        try:
            api = PodAPI(self.config_data["url"], self.token)
            count = api.test_connection()
            self._ui(self._on_auto_ok, api, count)
        except Exception:
            self._ui(self._set_status, False)

    def _on_auto_ok(self, api, count):
        """Reconnexion auto réussie : active l'état connecté et charge types et comptes."""
        self.api = api
        self._set_status(True)
        u = self.config_data.get("agent_username", "")
        if u:
            self.agent_lbl.configure(text=f"Dépôt au nom de :\n{u}")
        self._run(self._load_types)
        self._run(self._load_all_users)

    def _set_status(self, ok: bool):
        """Met à jour l'indicateur de connexion (pastille + libellé) de la barre latérale."""
        self.status_dot.configure(text="🟢" if ok else "🔴")
        self.status_lbl.configure(text="Connecté" if ok else "Non connecté",
                                  text_color="#22c55e" if ok else "#ef4444")

    def _load_types(self):
        """(Thread) Charge les types de vidéo et les sites (champ requis à l'upload)."""
        try:
            self.types = self.api.get_types()
            self.type_map = {t.get("title", f"type-{t.get('id')}"): t.get("url", "")
                             for t in self.types}
            titles = list(self.type_map.keys()) or ["(aucun type)"]
            self._ui(self.type_combo.configure, values=titles)
            self._ui(self.type_combo.set, titles[0])
            # Met aussi à jour les menus de type de l'onglet Vidéos
            self._ui(self._browse_refresh_type_menu)
        except Exception as e:
            self._ui(self._log, f"Impossible de charger les types : {e}")
        # Sites (champ requis à l'upload sur instance multi-établissements)
        try:
            sites = self.api.get_sites()
            self.site_urls = [s.get("url", "") for s in sites if s.get("url")]
            if self.site_urls:
                names = ", ".join(s.get("name", s.get("domain", "?")) for s in sites)
                self._ui(self._log, f"Site(s) détecté(s) : {names}")
            else:
                self._ui(self._log, "⚠️ Aucun site retourné par /rest/sites/ — l'upload pourrait échouer.")
        except Exception as e:
            self._ui(self._log, f"Impossible de charger les sites : {e}")

    def _load_all_users(self):
        """(Thread) Charge tous les comptes Pod (paginé) et rafraîchit les vues qui en dépendent."""
        if not self.api:
            self._ui(self.users_count_lbl.configure,
                     text="Connectez-vous d'abord.", text_color="#f59e0b")
            return
        self._ui(self.users_count_lbl.configure,
                 text="⏳  Chargement de la liste des utilisateurs…", text_color="gray")
        self._ui(self._log, "Chargement des utilisateurs (/rest/users/)…")
        try:
            users = self.api.get_all_users()
            users.sort(key=lambda u: (u.get("username") or "").lower())
            self.all_users = users
            self._ui(self._render_users)
            self._ui(self._render_comptes)   # PodAdmin : rafraîchir l'onglet Comptes
            self._ui(self._refresh_reassign_pickers)  # … et les sélecteurs de réaffectation
            # Présélection : pré-remplir le filtre avec le propriétaire enregistré
            ag = self.config_data.get("agent_username", "")
            if ag:
                self._ui(self._preselect_agent, ag)
            if users:
                self._ui(self.users_count_lbl.configure,
                         text=f"✅  {len(users)} utilisateur(s) chargé(s). Filtrez puis cliquez pour choisir.",
                         text_color="#22c55e")
                self._ui(self._log, f"Utilisateurs chargés : {len(users)}.")
            else:
                self._ui(self.users_count_lbl.configure,
                         text="⚠️  Aucun utilisateur renvoyé. Le compte du token n'a peut-être "
                              "pas le droit de lister les utilisateurs (compte superutilisateur requis).",
                         text_color="#f59e0b")
                self._ui(self._log, "⚠️ /rest/users/ a renvoyé 0 utilisateur — vérifiez les droits du token "
                                    "(ou lancez verifier.py).")
        except Exception as e:
            self._ui(self.users_count_lbl.configure, text=f"❌  Erreur : {e}", text_color="#ef4444")
            self._ui(self._log, f"❌ Erreur chargement utilisateurs : {e}")

    def _user_label(self, u: dict) -> str:
        """Libellé lisible d'un compte : « identifiant — Prénom Nom »."""
        return f"{u.get('username','?')} — {u.get('first_name','')} {u.get('last_name','')}".strip()

    def _preselect_agent(self, username: str):
        """Présélection : pré-remplit le filtre avec le propriétaire enregistré.
        La liste reste entièrement utilisable : effacer le filtre permet de
        choisir un autre compte (le support dépose sur différents comptes)."""
        if hasattr(self, "agent_filter") and not self.agent_filter.get().strip():
            self.agent_filter.insert(0, username)
            self._render_users()

    def _render_users(self):
        """Affiche la liste filtrée des comptes pour choisir l'agent déposant."""
        flt = self.agent_filter.get().strip().lower() if hasattr(self, "agent_filter") else ""
        for w in self.agent_results.winfo_children():
            w.destroy()

        if not self.all_users:
            ctk.CTkLabel(self.agent_results,
                         text="Liste non chargée. Cliquez sur « Recharger ».",
                         text_color="gray").pack(pady=10)
            return

        matches = [u for u in self.all_users if not flt or flt in self._user_label(u).lower()]
        CAP = 300  # éviter de créer des milliers de boutons (Tk gèlerait)
        current_username = self.config_data.get("agent_username", "")

        for u in matches[:CAP]:
            is_current = (u.get("username", "") == current_username)
            label = ("✅  " if is_current else "      ") + self._user_label(u)
            ctk.CTkButton(self.agent_results, text=label, anchor="w",
                          fg_color=("gray75", "gray30") if is_current else "transparent",
                          text_color=("gray10", "gray90"), hover_color=("gray75", "gray28"),
                          height=28, font=ctk.CTkFont(size=12),
                          command=lambda uu=u: self._pick_agent(uu)).pack(fill="x", pady=1)

        if len(matches) > CAP:
            ctk.CTkLabel(self.agent_results,
                         text=f"… +{len(matches) - CAP} autres. Affinez le filtre.",
                         text_color="gray").pack(pady=4)
        elif not matches:
            ctk.CTkLabel(self.agent_results,
                         text="Aucun résultat ne correspond au filtre.",
                         text_color="gray").pack(pady=8)

    def _pick_agent(self, user: dict):
        """Enregistre le compte choisi comme propriétaire par défaut des dépôts."""
        self.config_data["agent_username"] = user.get("username", "")
        self.config_data["agent_owner_url"] = user.get("url", "")
        cfg.save_config(self.config_data)
        self.agent_lbl.configure(text=f"Dépôt au nom de :\n{user.get('username','')}")
        self.config_msg.configure(
            text=f"✅  Propriétaire des vidéos : {user.get('username','')}", text_color="#22c55e")
        if hasattr(self, "agent_results"):
            self._render_users()   # met à jour la coche ✅

    # ═════════════════════════════════════════════════════════════════════
    #  ONGLET COMPTES — statut « équipe » (is_staff)
    # ═════════════════════════════════════════════════════════════════════

    # ═════════════════════════════════════════════════════════════════════
    #  ONGLET ENCODAGE — supervision du transcodage + relance
    # ═════════════════════════════════════════════════════════════════════
    #
    #  L'API n'expose pas de file d'encodage dédiée (vérifié au sondage).
    #  On se base donc sur les champs par vidéo : `encoded`,
    #  `encoding_in_progress`, `get_encoding_step`, `is_draft`. On classe
    #  chaque vidéo par état, et on peut relancer l'encodage (launch_encoding)
    #  à l'unité ou en masse sur les vidéos « à problème ».
    #
    #  États retenus :
    #    ✅ encodée            : encoded == True
    #    ⏳ en cours           : encoding_in_progress == True
    #    📝 non lancée         : brouillon non encodé (is_draft, pas encore lancé)
    #    ❌ à problème         : ni encodée, ni en cours, ni brouillon (suspecte)

    @staticmethod
    def _encode_state(v: dict) -> str:
        """Classe une vidéo dans un état d'encodage (clé interne)."""
        if v.get("encoded"):
            return "ok"
        if v.get("encoding_in_progress"):
            return "running"
        if v.get("is_draft"):
            return "draft"
        return "failed"

    # Libellés lisibles + pastille pour chaque état
    _ENCODE_LABELS = {
        "ok":      "✅ Encodée",
        "running": "⏳ En cours",
        "failed":  "❌ À problème",
        "draft":   "📝 Non lancée",
    }

    def _build_tab_encode(self):
        """Construit l'onglet Encodage (supervision du transcodage + relance)."""
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tabs["encode"] = frame

        ctk.CTkLabel(frame, text="⚙️  Encodage",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            frame,
            text="Supervisez le transcodage : voyez les encodages en cours, terminés ou en "
                 "échec, et relancez l'encodage des vidéos qui posent problème (à l'unité ou "
                 "en masse).",
            text_color="gray70", font=ctk.CTkFont(size=12),
            justify="left", wraplength=860).pack(anchor="w", pady=(0, 8))

        # — Ligne : scan + état —
        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkButton(top, text="📡  Scanner", fg_color="#2563eb",
                      hover_color="#1d4ed8", command=self._encode_scan).pack(side="left")
        self.encode_status = ctk.CTkLabel(top, text="(aucun scan)", text_color="gray",
                                          font=ctk.CTkFont(size=11))
        self.encode_status.pack(side="left", padx=10)

        # — Bandeau de compteurs —
        self.encode_counters = ctk.CTkLabel(frame, text="", justify="left", anchor="w",
                                            font=ctk.CTkFont(size=13))
        self.encode_counters.pack(anchor="w", pady=(8, 4))

        # — Ligne : filtre par état + relance en masse —
        bar = ctk.CTkFrame(frame, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(bar, text="État :").pack(side="left", padx=(0, 4))
        self.encode_filter = ctk.CTkOptionMenu(
            bar, width=150,
            values=["Tous", "En cours", "À problème", "Non lancées", "Encodées"],
            command=lambda _c: self._render_encode())
        self.encode_filter.set("À problème")
        self.encode_filter.pack(side="left")
        # Relance en masse de tout ce qui est affiché
        self.encode_relaunch_btn = ctk.CTkButton(
            bar, text="🔁  Relancer l'encodage des vidéos affichées",
            fg_color="#16a34a", hover_color="#15803d", command=self._encode_relaunch_shown)
        self.encode_relaunch_btn.pack(side="left", padx=10)
        self.encode_progress = ctk.CTkLabel(bar, text="", text_color="gray",
                                            font=ctk.CTkFont(size=11))
        self.encode_progress.pack(side="left", padx=6)

        # — Liste —
        self.encode_list = ctk.CTkScrollableFrame(frame, label_text="Vidéos")
        self.encode_list.pack(fill="both", expand=True, pady=(4, 0))

        # — Données —
        self.encode_videos = []      # scan complet (cache)
        self.encode_filtered = []    # sous-ensemble affiché

    # ── Scan ────────────────────────────────────────────────────────────────

    def _encode_scan(self):
        """Déclenche le scan complet des vidéos (en arrière-plan)."""
        if not self.api:
            self.encode_status.configure(text="Connectez-vous d'abord.", text_color="#f59e0b")
            return
        self.encode_status.configure(text="⏳  Scan…", text_color="gray")
        self._run(self._do_encode_scan)

    def _do_encode_scan(self):
        """(Thread) Récupère toutes les vidéos puis met à jour compteurs + liste."""
        try:
            def prog(n):
                self._ui(self.encode_status.configure,
                         text=f"⏳  {n} vidéos lues…", text_color="gray")
            videos = self.api.get_all_videos(progress_cb=prog)
            self.encode_videos = videos
            self._ui(self._render_encode)
            self._ui(self.encode_status.configure,
                     text=f"✅  {len(videos)} vidéos analysées.", text_color="#22c55e")
            self._ui(self._log, f"Encodage : {len(videos)} vidéos scannées.")
        except Exception as e:
            self._ui(self.encode_status.configure, text=f"❌  {e}", text_color="#ef4444")
            self._ui(self._log, f"❌ Scan encodage : {e}")

    # ── Rendu (compteurs + liste filtrée) ───────────────────────────────────

    def _render_encode(self, *_):
        """Met à jour les compteurs par état et la liste filtrée."""
        if not hasattr(self, "encode_list"):
            return
        for w in self.encode_list.winfo_children():
            w.destroy()

        if not self.encode_videos:
            self.encode_counters.configure(text="")
            ctk.CTkLabel(self.encode_list, text="Cliquez sur « Scanner ».",
                         text_color="gray").pack(pady=10)
            return

        # Comptage par état
        counts = {"ok": 0, "running": 0, "failed": 0, "draft": 0}
        for v in self.encode_videos:
            counts[self._encode_state(v)] += 1
        self.encode_counters.configure(
            text=(f"✅ {counts['ok']} encodées      "
                  f"⏳ {counts['running']} en cours      "
                  f"❌ {counts['failed']} à problème      "
                  f"📝 {counts['draft']} non lancées"))

        # Filtre par état
        sel = self.encode_filter.get()
        wanted = {"En cours": "running", "À problème": "failed",
                  "Non lancées": "draft", "Encodées": "ok"}.get(sel)
        if wanted:
            vids = [v for v in self.encode_videos if self._encode_state(v) == wanted]
        else:
            vids = list(self.encode_videos)
        self.encode_filtered = vids

        # Le bouton de relance en masse n'a de sens que pour les états relançables
        relaunchable = sel in ("À problème", "Non lancées", "En cours", "Tous")
        self.encode_relaunch_btn.configure(state="normal" if (vids and relaunchable) else "disabled")

        if not vids:
            ctk.CTkLabel(self.encode_list, text="Aucune vidéo dans cet état.",
                         text_color="gray").pack(pady=10)
            return

        # Une ligne par vidéo : [pastille état] titre · slug · étape  [Relancer]
        CAP = 400
        for v in vids[:CAP]:
            st = self._encode_state(v)
            row = ctk.CTkFrame(self.encode_list, fg_color=("gray85", "gray17"),
                               corner_radius=6)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=self._ENCODE_LABELS[st], width=110, anchor="w",
                         font=ctk.CTkFont(size=12)).pack(side="left", padx=(10, 4), pady=6)
            title = (v.get("title") or "(sans titre)")[:46]
            step = v.get("get_encoding_step", "")
            ctk.CTkLabel(row, text=f"{title}   ·   {v.get('slug','?')}   ·   {step}",
                         anchor="w", font=ctk.CTkFont(size=12)).pack(
                side="left", padx=4, pady=6, fill="x", expand=True)
            # Bouton de relance individuelle (sauf si déjà encodée — relance possible quand même,
            # mais on la réserve aux états non terminés pour éviter les clics inutiles)
            if st != "ok":
                ctk.CTkButton(row, text="🔁 Relancer", width=100, height=26, fg_color="gray35",
                              command=lambda vv=v: self._encode_relaunch_one(vv)).pack(
                    side="right", padx=8)
        if len(vids) > CAP:
            ctk.CTkLabel(self.encode_list,
                         text=f"… +{len(vids) - CAP} autres. Affinez le filtre.",
                         text_color="gray").pack(pady=4)

    # ── Relance de l'encodage ────────────────────────────────────────────────

    def _encode_relaunch_one(self, v):
        """Relance l'encodage d'une vidéo après confirmation."""
        if not messagebox.askyesno(
                "Relancer l'encodage",
                f"Relancer l'encodage de :\n\n{v.get('title')}  ({v.get('slug')}) ?"):
            return
        self._run(self._do_encode_relaunch, [v])

    def _encode_relaunch_shown(self):
        """Relance l'encodage de toutes les vidéos actuellement affichées."""
        vids = list(self.encode_filtered)
        if not vids:
            return
        if not messagebox.askyesno(
                "Relancer en masse",
                f"Relancer l'encodage de {len(vids)} vidéo(s) ?\n\n"
                "Chaque vidéo sera renvoyée dans la file d'encodage du serveur."):
            return
        self._run(self._do_encode_relaunch, vids)

    def _do_encode_relaunch(self, vids):
        """(Thread) Appelle launch_encoding(slug) pour chaque vidéo, avec bilan."""
        ok = fail = 0
        for i, v in enumerate(vids, 1):
            slug = v.get("slug", "")
            try:
                self.api.launch_encoding(slug)          # GET /rest/launch_encode_view/?slug=
                ok += 1
                self._ui(self._log, f"🔁 Encodage relancé : {slug}")
            except Exception as e:
                fail += 1
                self._ui(self._log, f"❌ Relance {slug} : {e}")
            self._ui(self.encode_progress.configure,
                     text=f"⏳  {i}/{len(vids)}…", text_color="gray")
        self._ui(self.encode_progress.configure,
                 text=f"Terminé : {ok} relancée(s), {fail} échec(s).",
                 text_color="#22c55e" if not fail else "#f59e0b")
        # Re-scan pour refléter les nouveaux états (en cours d'encodage)
        self._do_encode_scan()

    # ═════════════════════════════════════════════════════════════════════
    #  ONGLET COMPTES — statut « équipe » (is_staff)
    # ═════════════════════════════════════════════════════════════════════

    def _build_tab_comptes(self):
        """Construit l'onglet Comptes (statut équipe is_staff)."""
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tabs["comptes"] = frame

        ctk.CTkLabel(frame, text="👤  Comptes — statut « équipe »",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            frame,
            text="Le statut « équipe » (is_staff) autorise un compte à ajouter et gérer "
                 "des vidéos sur Pod. Activez l'interrupteur pour l'accorder, désactivez-le "
                 "pour le retirer. Chaque changement est confirmé puis appliqué immédiatement.",
            text_color="gray70", font=ctk.CTkFont(size=12),
            justify="left", wraplength=860).pack(anchor="w", pady=(0, 10))

        bar = ctk.CTkFrame(frame, fg_color="transparent")
        bar.pack(fill="x")
        self.comptes_filter = ctk.CTkEntry(
            bar, placeholder_text="🔍 nom / prénom / identifiant…")
        self.comptes_filter.pack(side="left", fill="x", expand=True)
        self.comptes_filter.bind("<KeyRelease>", lambda e: self._render_comptes())
        # Filtre par statut équipe (is_staff)
        self.comptes_statut = ctk.CTkOptionMenu(
            bar, width=150,
            values=["Tous", "Équipe", "Sans statut"],
            command=lambda _c: self._render_comptes())
        self.comptes_statut.set("Tous")
        self.comptes_statut.pack(side="left", padx=6)
        # Regrouper : trie pour rassembler les comptes « équipe » en tête
        self.comptes_group = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(bar, text="Regrouper", variable=self.comptes_group,
                        command=self._render_comptes, width=90).pack(side="left", padx=6)
        ctk.CTkButton(bar, text="🔄  Recharger", width=130,
                      command=lambda: self._run(self._reload_users_for_admin)).pack(side="left", padx=8)

        self.comptes_count_lbl = ctk.CTkLabel(frame, text="", text_color="gray",
                                              font=ctk.CTkFont(size=11))
        self.comptes_count_lbl.pack(anchor="w", pady=(6, 2))

        self.comptes_results = ctk.CTkScrollableFrame(frame)
        self.comptes_results.pack(fill="both", expand=True, pady=(0, 4))

        self._render_comptes()

    def _reload_users_for_admin(self):
        """Recharge la liste complète des comptes puis rafraîchit les vues."""
        if not self.api:
            self._ui(self.comptes_count_lbl.configure,
                     text="Connectez-vous d'abord (onglet Configuration).",
                     text_color="#f59e0b")
            return
        self._ui(self.comptes_count_lbl.configure,
                 text="⏳  Chargement des comptes…", text_color="gray")
        try:
            users = self.api.get_all_users()
            users.sort(key=lambda u: (u.get("username") or "").lower())
            self.all_users = users
            self._ui(self._render_comptes)
            if hasattr(self, "agent_results"):
                self._ui(self._render_users)
            self._ui(self._refresh_reassign_pickers)
            self._ui(self._log, f"Comptes rechargés : {len(users)}.")
        except Exception as e:
            self._ui(self.comptes_count_lbl.configure,
                     text=f"❌  Erreur : {e}", text_color="#ef4444")
            self._ui(self._log, f"❌ Erreur chargement comptes : {e}")

    def _render_comptes(self):
        if not hasattr(self, "comptes_results"):
            return
        flt = self.comptes_filter.get().strip().lower() if hasattr(self, "comptes_filter") else ""
        for w in self.comptes_results.winfo_children():
            w.destroy()

        if not self.all_users:
            ctk.CTkLabel(self.comptes_results,
                         text="Liste non chargée. Connectez-vous puis cliquez sur « Recharger ».",
                         text_color="gray").pack(pady=10)
            self.comptes_count_lbl.configure(text="")
            return

        matches = [u for u in self.all_users
                   if not flt or flt in self._user_label(u).lower()]

        # Filtre par statut équipe (menu déroulant)
        statut = self.comptes_statut.get() if hasattr(self, "comptes_statut") else "Tous"
        if statut == "Équipe":
            matches = [u for u in matches if u.get("is_staff")]
        elif statut == "Sans statut":
            matches = [u for u in matches if not u.get("is_staff")]

        # Regroupement : comptes « équipe » d'abord, puis tri alphabétique
        if hasattr(self, "comptes_group") and self.comptes_group.get():
            matches.sort(key=lambda u: (not u.get("is_staff"),
                                        (u.get("username") or "").lower()))

        staff_n = sum(1 for u in self.all_users if u.get("is_staff"))
        self.comptes_count_lbl.configure(
            text=f"{len(self.all_users)} compte(s) — {staff_n} avec statut équipe. "
                 f"{len(matches)} affiché(s).")

        CAP = 300
        for u in matches[:CAP]:
            row = ctk.CTkFrame(self.comptes_results, fg_color=("gray85", "gray17"),
                               corner_radius=6)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=self._user_label(u), anchor="w",
                         font=ctk.CTkFont(size=12)).pack(
                side="left", padx=12, pady=6, fill="x", expand=True)
            var = ctk.BooleanVar(value=bool(u.get("is_staff")))
            sw = ctk.CTkSwitch(row, text="Équipe", variable=var, width=80,
                               command=lambda uu=u, vv=var: self._on_staff_toggle(uu, vv))
            sw.pack(side="right", padx=12, pady=4)

        if len(matches) > CAP:
            ctk.CTkLabel(self.comptes_results,
                         text=f"… +{len(matches) - CAP} autres. Affinez le filtre.",
                         text_color="gray").pack(pady=4)
        elif not matches:
            ctk.CTkLabel(self.comptes_results,
                         text="Aucun résultat ne correspond au filtre.",
                         text_color="gray").pack(pady=8)

    def _on_staff_toggle(self, user: dict, var):
        """Confirme puis applique le changement de statut équipe."""
        want = bool(var.get())
        verb = "DONNER" if want else "RETIRER"
        consequence = ("Ce compte pourra ajouter et gérer des vidéos sur Pod."
                       if want else
                       "Ce compte ne pourra plus ajouter de vidéos (accès équipe retiré).")
        ok = messagebox.askyesno(
            "Confirmer le changement de statut",
            f"{verb} le statut « équipe » à :\n\n"
            f"    {self._user_label(user)}\n\n{consequence}\n\nContinuer ?")
        if not ok:
            var.set(not want)          # annulation → revenir à l'état précédent
            return
        self._run(self._do_staff, user, want, var)

    def _do_staff(self, user: dict, want: bool, var):
        uname = user.get("username", "?")
        try:
            self.api.set_user_staff(user.get("url", ""), want)
            user["is_staff"] = want    # met à jour le cache local
            self._ui(self._log,
                     f"{'✅ Statut équipe ACCORDÉ à' if want else '⛔ Statut équipe RETIRÉ à'} "
                     f"{uname}.")
            self._ui(self._render_comptes)   # rafraîchit compteur + état
        except Exception as e:
            self._ui(var.set, not want)      # échec → revenir à l'état précédent
            self._ui(self.comptes_count_lbl.configure,
                     text=f"❌  Échec pour {uname} : {e}", text_color="#ef4444")
            self._ui(self._log, f"❌ Échec MAJ statut de {uname} : {e}")

    # ═════════════════════════════════════════════════════════════════════
    #  ONGLET VIDÉOS — explorateur + édition d'UNE vidéo
    # ═════════════════════════════════════════════════════════════════════
    #
    #  Rechercher/filtrer une vidéo dans une liste (gauche), puis l'éditer dans
    #  un panneau de détail (droite) : renommer, changer le statut
    #  (brouillon/public, restreinte), gérer les co-propriétaires et les
    #  chaînes, supprimer. Les actions portent sur UNE vidéo à la fois.

    def _build_tab_browse(self):
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tabs["browse"] = frame

        ctk.CTkLabel(frame, text="🎞️  Vidéos",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            frame,
            text="Recherchez une vidéo, sélectionnez-la dans la liste, puis éditez-la dans "
                 "le panneau de droite (titre, statut, co-propriétaires, chaînes, suppression).",
            text_color="gray70", font=ctk.CTkFont(size=12),
            justify="left", wraplength=860).pack(anchor="w", pady=(0, 8))

        # — Ligne : charger + statut —
        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkButton(top, text="📡  Charger les vidéos", fg_color="#2563eb",
                      hover_color="#1d4ed8", command=self._browse_load).pack(side="left")
        self.browse_status = ctk.CTkLabel(top, text="(non chargé)", text_color="gray",
                                          font=ctk.CTkFont(size=11))
        self.browse_status.pack(side="left", padx=10)

        # — Ligne : filtres —
        filt = ctk.CTkFrame(frame, fg_color="transparent")
        filt.pack(fill="x", pady=(8, 4))
        self.browse_text = ctk.CTkEntry(filt, placeholder_text="🔍 titre / slug / propriétaire…")
        self.browse_text.pack(side="left", fill="x", expand=True)
        self.browse_text.bind("<KeyRelease>", lambda e: self._browse_apply_filter())
        self.browse_statut = ctk.CTkOptionMenu(
            filt, width=130, values=["Tous statuts", "Brouillon", "Public", "Restreinte"],
            command=lambda _c: self._browse_apply_filter())
        self.browse_statut.set("Tous statuts")
        self.browse_statut.pack(side="left", padx=6)
        self.browse_encode = ctk.CTkOptionMenu(
            filt, width=150, values=["Tout encodage", "Encodées", "Non-encodées"],
            command=lambda _c: self._browse_apply_filter())
        self.browse_encode.set("Tout encodage")
        self.browse_encode.pack(side="left", padx=6)
        self.browse_chan = ctk.CTkOptionMenu(filt, width=170, values=["Toutes chaînes"],
                                             command=lambda _c: self._browse_apply_filter())
        self.browse_chan.set("Toutes chaînes")
        self.browse_chan.pack(side="left", padx=6)
        self.browse_type = ctk.CTkOptionMenu(filt, width=150, values=["Tous types"],
                                             command=lambda _c: self._browse_apply_filter())
        self.browse_type.set("Tous types")
        self.browse_type.pack(side="left", padx=6)

        # — Action « en masse » : modifier le type des vidéos AFFICHÉES —
        # On la détache nettement des filtres ci-dessus (séparateur + cadre
        # encadré + libellé d'action) pour qu'on ne la confonde pas avec un filtre.
        ctk.CTkFrame(frame, height=1, fg_color="gray30").pack(fill="x", pady=(6, 0))
        massbar = ctk.CTkFrame(frame, fg_color=("gray90", "gray16"),
                               corner_radius=8, border_width=1, border_color="gray30")
        massbar.pack(fill="x", pady=(4, 4))
        ctk.CTkLabel(massbar, text="✏️  Modifier en masse — appliquer ce type aux vidéos affichées :",
                     font=ctk.CTkFont(size=11), text_color="gray70"
                     ).pack(side="left", padx=(10, 8), pady=6)
        self.browse_mass_type = ctk.CTkOptionMenu(massbar, width=170, values=["(aucun type)"])
        self.browse_mass_type.pack(side="left", pady=6)
        ctk.CTkButton(massbar, text="Appliquer", width=110,
                      command=self._browse_mass_set_type).pack(side="left", padx=8, pady=6)

        # — Corps : liste (gauche) + détail (droite) —
        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(1, weight=1)

        self.browse_count_lbl = ctk.CTkLabel(body, text="", text_color="gray",
                                             font=ctk.CTkFont(size=11), anchor="w")
        self.browse_count_lbl.grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.browse_list = ctk.CTkScrollableFrame(body, label_text="Résultats")
        self.browse_list.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        self.browse_detail = ctk.CTkScrollableFrame(body, label_text="Détail / actions")
        self.browse_detail.grid(row=1, column=1, sticky="nsew", padx=(6, 0))

        # — Données —
        self.browse_videos = []         # scan complet (cache)
        self.browse_channels = []       # chaînes (pour filtre + sélecteur)
        self.browse_chan_by_url = {}    # URL chaîne → titre
        self.browse_filtered = []       # sous-ensemble affiché
        self.browse_selected = None     # vidéo en cours d'édition

        self._browse_render_detail()    # affiche le message d'invite

    # ── Chargement (vidéos + chaînes) ──────────────────────────────────────

    def _browse_load(self):
        if not self.api:
            self.browse_status.configure(text="Connectez-vous d'abord.", text_color="#f59e0b")
            return
        self.browse_status.configure(text="⏳  Chargement…", text_color="gray")
        self._run(self._do_browse_load)

    def _do_browse_load(self):
        """(Thread) Récupère toutes les vidéos + les chaînes (pour le filtre/sélecteur)."""
        try:
            def prog(n):
                self._ui(self.browse_status.configure,
                         text=f"⏳  {n} vidéos lues…", text_color="gray")
            videos = self.api.get_all_videos(progress_cb=prog)
            try:
                channels = self.api.get_channels()
            except Exception:
                channels = []
            self.browse_videos = videos
            self.browse_channels = channels
            self.browse_chan_by_url = {str(c.get("url", "")).rstrip("/"): c.get("title", "?")
                                       for c in channels}
            self._ui(self._browse_refresh_channel_menu)
            self._ui(self._browse_apply_filter)
            self._ui(self.browse_status.configure,
                     text=f"✅  {len(videos)} vidéos, {len(channels)} chaîne(s).",
                     text_color="#22c55e")
            self._ui(self._log, f"Explorateur vidéos : {len(videos)} vidéos chargées.")
        except Exception as e:
            self._ui(self.browse_status.configure, text=f"❌  {e}", text_color="#ef4444")
            self._ui(self._log, f"❌ Chargement explorateur : {e}")

    def _browse_refresh_channel_menu(self):
        """Remplit le filtre par chaîne avec les titres chargés."""
        vals = ["Toutes chaînes"] + sorted(self.browse_chan_by_url.values(), key=str.lower)
        self.browse_chan.configure(values=vals)
        self.browse_chan.set("Toutes chaînes")
        self._browse_refresh_type_menu()

    def _browse_refresh_type_menu(self):
        """Remplit le filtre par type et le menu « en masse » avec les types chargés.
        Sans danger si appelé avant que les types soient chargés."""
        titles = sorted((self.type_map or {}).keys(), key=str.lower)
        if hasattr(self, "browse_type"):
            self.browse_type.configure(values=["Tous types"] + titles)
            if self.browse_type.get() not in (["Tous types"] + titles):
                self.browse_type.set("Tous types")
        if hasattr(self, "browse_mass_type"):
            self.browse_mass_type.configure(values=titles or ["(aucun type)"])
            if titles and self.browse_mass_type.get() not in titles:
                self.browse_mass_type.set(titles[0])

    # ── Filtrage ───────────────────────────────────────────────────────────

    def _browse_owner_label(self, v) -> str:
        """Nom lisible du propriétaire d'une vidéo (via la liste des comptes)."""
        oid = str(self._video_owner_id(v)).rstrip("/")
        for u in (self.all_users or []):
            if str(u.get("url", "")).rstrip("/") == oid or u.get("username") == oid:
                return u.get("username", oid)
        return oid or "—"

    def _browse_apply_filter(self, *_):
        if not self.browse_videos:
            self.browse_count_lbl.configure(text="Cliquez sur « Charger les vidéos ».")
            for w in self.browse_list.winfo_children():
                w.destroy()
            return

        vids = self.browse_videos
        # Filtre statut
        st = self.browse_statut.get()
        if st == "Brouillon":
            vids = [v for v in vids if v.get("is_draft")]
        elif st == "Public":
            vids = [v for v in vids if not v.get("is_draft")]
        elif st == "Restreinte":
            vids = [v for v in vids if v.get("is_restricted")]
        # Filtre encodage
        enc = self.browse_encode.get()
        if enc == "Encodées":
            vids = [v for v in vids if v.get("encoded")]
        elif enc == "Non-encodées":
            vids = [v for v in vids if PodAPI.is_unencoded(v)]
        # Filtre chaîne
        ch = self.browse_chan.get()
        if ch and ch != "Toutes chaînes":
            # On retrouve l'URL de la chaîne à partir de son titre
            wanted = [u for u, t in self.browse_chan_by_url.items() if t == ch]
            def in_chan(v):
                cs = v.get("channel") or []
                if isinstance(cs, str):
                    cs = [cs]
                cs = [str(c).rstrip("/") for c in cs]
                return any(w in cs for w in wanted)
            vids = [v for v in vids if in_chan(v)]
        # Filtre type (valeur unique : on compare l'URL du type)
        ty = self.browse_type.get() if hasattr(self, "browse_type") else "Tous types"
        if ty and ty != "Tous types":
            turl = str((self.type_map or {}).get(ty, "")).rstrip("/")
            def has_type(v):
                vt = v.get("type")
                vt = vt.get("url") if isinstance(vt, dict) else vt
                return str(vt).rstrip("/") == turl
            vids = [v for v in vids if has_type(v)]
        # Filtre texte (titre / slug / propriétaire)
        txt = self.browse_text.get().strip().lower()
        if txt:
            def hay(v):
                return f"{v.get('title','')} {v.get('slug','')} {self._browse_owner_label(v)}".lower()
            vids = [v for v in vids if txt in hay(v)]

        self.browse_filtered = vids
        self._render_browse_list()

    def _render_browse_list(self):
        for w in self.browse_list.winfo_children():
            w.destroy()
        self.browse_count_lbl.configure(text=f"{len(self.browse_filtered)} vidéo(s) trouvée(s).")

        if not self.browse_filtered:
            ctk.CTkLabel(self.browse_list, text="Aucune vidéo ne correspond.",
                         text_color="gray").pack(pady=10)
            return

        CAP = 300
        sel_slug = self.browse_selected.get("slug") if self.browse_selected else None
        for v in self.browse_filtered[:CAP]:
            slug = v.get("slug", "?")
            is_sel = slug == sel_slug
            title = (v.get("title") or "(sans titre)")[:48]
            tag = "📝" if v.get("is_draft") else "🌐"        # brouillon / public
            ctk.CTkButton(
                self.browse_list, text=f"{tag}  {title}", anchor="w", height=28,
                fg_color=("gray75", "gray30") if is_sel else "transparent",
                text_color=("gray10", "gray90"), hover_color=("gray75", "gray28"),
                font=ctk.CTkFont(size=12),
                command=lambda vv=v: self._browse_select(vv)).pack(fill="x", pady=1)
        if len(self.browse_filtered) > CAP:
            ctk.CTkLabel(self.browse_list,
                         text=f"… +{len(self.browse_filtered) - CAP} autres. Affinez le filtre.",
                         text_color="gray").pack(pady=4)

    def _browse_select(self, v):
        """Sélectionne une vidéo et affiche son panneau de détail."""
        self.browse_selected = v
        self._render_browse_list()      # met à jour la surbrillance
        self._browse_render_detail()

    # ── Panneau de détail / actions ────────────────────────────────────────

    def _browse_render_detail(self):
        for w in self.browse_detail.winfo_children():
            w.destroy()
        v = self.browse_selected
        if not v:
            ctk.CTkLabel(self.browse_detail,
                         text="Sélectionnez une vidéo dans la liste pour l'éditer.",
                         text_color="gray").pack(pady=14)
            return

        slug = v.get("slug", "?")

        # — Informations —
        ctk.CTkLabel(self.browse_detail, text=v.get("title", "(sans titre)"),
                     font=ctk.CTkFont(size=15, weight="bold"),
                     wraplength=420, justify="left").pack(anchor="w", padx=4, pady=(4, 0))
        chans = v.get("channel") or []
        if isinstance(chans, str):
            chans = [chans]
        chan_names = ", ".join(self.browse_chan_by_url.get(str(c).rstrip("/"), "?")
                               for c in chans) or "(aucune)"
        info = (f"slug : {slug}\n"
                f"propriétaire : {self._browse_owner_label(v)}\n"
                f"durée : {v.get('duration_in_time', '—')}     "
                f"encodée : {'oui' if v.get('encoded') else 'non'}\n"
                f"chaînes : {chan_names}")
        ctk.CTkLabel(self.browse_detail, text=info, justify="left", anchor="w",
                     text_color="gray80", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=4, pady=(2, 10))

        # — Renommer —
        ren = ctk.CTkFrame(self.browse_detail, fg_color="transparent")
        ren.pack(fill="x", padx=4)
        self.browse_title_entry = ctk.CTkEntry(ren)
        self.browse_title_entry.insert(0, v.get("title", ""))
        self.browse_title_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(ren, text="Renommer", width=90, fg_color="gray35",
                      command=lambda: self._browse_rename(v)).pack(side="left", padx=6)

        # — Statut (interrupteurs) —
        # Important : on met à jour le cache local AVANT de lancer le thread,
        # pour que _browse_render_detail() reconstruise le panneau avec la
        # bonne valeur même si la réponse réseau tarde.
        ctk.CTkLabel(self.browse_detail, text="Statut", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=4, pady=(10, 2))
        sw = ctk.CTkFrame(self.browse_detail, fg_color="transparent")
        sw.pack(fill="x", padx=4)
        draft_var = ctk.BooleanVar(value=bool(v.get("is_draft")))
        def _toggle_draft():
            val = draft_var.get()
            v["is_draft"] = val          # mise à jour locale immédiate
            self._browse_patch(v, {"is_draft": val},
                               f"statut → {'brouillon' if val else 'public'}")
        ctk.CTkSwitch(sw, text="Brouillon (sinon public)", variable=draft_var,
                      command=_toggle_draft).pack(side="left", padx=(0, 16))
        restr_var = ctk.BooleanVar(value=bool(v.get("is_restricted")))
        def _toggle_restr():
            val = restr_var.get()
            v["is_restricted"] = val     # mise à jour locale immédiate
            self._browse_patch(v, {"is_restricted": val},
                               f"accès → {'restreint (connexion requise)' if val else 'public'}")
        ctk.CTkSwitch(sw, text="Connexion requise", variable=restr_var,
                      command=_toggle_restr).pack(side="left")

        # — Type (catégorie ; valeur unique) —
        ctk.CTkLabel(self.browse_detail, text="Type", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=4, pady=(12, 2))
        # Titre du type courant de la vidéo (résolu depuis son URL)
        cur_url = v.get("type")
        cur_url = cur_url.get("url") if isinstance(cur_url, dict) else cur_url
        url_to_title = {str(u).rstrip("/"): t for t, u in (self.type_map or {}).items()}
        cur_title = url_to_title.get(str(cur_url).rstrip("/"), "(non défini)")
        titles = sorted((self.type_map or {}).keys(), key=str.lower) or ["(aucun type)"]
        type_menu = ctk.CTkOptionMenu(self.browse_detail, width=220, values=titles)
        type_menu.set(cur_title if cur_title in titles else titles[0])
        type_menu.pack(anchor="w", padx=4)
        def _apply_type(choice):
            # Change le type de la vidéo (PATCH valeur unique = URL du type)
            new_url = (self.type_map or {}).get(choice)
            if new_url and str(new_url).rstrip("/") != str(cur_url).rstrip("/"):
                v["type"] = new_url
                self._browse_patch(v, {"type": new_url}, f"type → {choice}")
        type_menu.configure(command=_apply_type)

        # — Co-propriétaires & chaînes —
        ctk.CTkLabel(self.browse_detail, text="Relations", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=4, pady=(12, 2))
        rel = ctk.CTkFrame(self.browse_detail, fg_color="transparent")
        rel.pack(fill="x", padx=4)
        ctk.CTkButton(rel, text="👥  Co-propriétaires…", fg_color="gray35",
                      command=lambda: self._browse_edit_owners(v)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(rel, text="🗂  Chaînes…", fg_color="gray35",
                      command=lambda: self._browse_edit_channels(v)).pack(side="left")

        # — Sous-titres —
        ctk.CTkLabel(self.browse_detail, text="Sous-titres", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=4, pady=(12, 2))
        # Conteneur listant les pistes existantes (rempli en arrière-plan)
        self.browse_subs = ctk.CTkFrame(self.browse_detail, fg_color="transparent")
        self.browse_subs.pack(fill="x", padx=4)
        ctk.CTkLabel(self.browse_subs, text="Chargement…", text_color="gray",
                     font=ctk.CTkFont(size=11)).pack(anchor="w")
        # Bouton d'ajout d'un fichier .vtt / .srt
        ctk.CTkButton(self.browse_detail, text="➕  Ajouter un sous-titre (.vtt / .srt)",
                      fg_color="gray35",
                      command=lambda: self._sub_add_dialog(v)).pack(anchor="w", padx=4, pady=(6, 0))
        # Chargement des pistes de cette vidéo en arrière-plan
        self._run(self._sub_load, v)

        # — Suppression —
        ctk.CTkLabel(self.browse_detail, text="Zone sensible", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#ef4444").pack(anchor="w", padx=4, pady=(14, 2))
        ctk.CTkButton(self.browse_detail, text="🗑  Supprimer cette vidéo",
                      fg_color="#b91c1c", hover_color="#991b1b",
                      command=lambda: self._browse_delete(v)).pack(anchor="w", padx=4, pady=(0, 8))

        # Zone de message du panneau
        self.browse_msg = ctk.CTkLabel(self.browse_detail, text="", text_color="gray",
                                       font=ctk.CTkFont(size=11), wraplength=420, justify="left")
        self.browse_msg.pack(anchor="w", padx=4, pady=(4, 8))

    # ── Actions sur la vidéo sélectionnée ──────────────────────────────────

    # ── Sous-titres (tracks) ───────────────────────────────────────────────

    def _sub_load(self, v):
        """(Thread) Charge les pistes de sous-titres de la vidéo puis les affiche."""
        try:
            tracks = self.api.get_tracks(v)
            self._ui(self._sub_render, v, tracks)
        except Exception as e:
            self._ui(self._sub_render, v, None, str(e))

    def _sub_render(self, v, tracks, err=None):
        """Affiche la liste des pistes existantes (langue · type · 🗑)."""
        # Le panneau a pu être reconstruit entre-temps : on vérifie qu'il existe
        if not hasattr(self, "browse_subs") or not self.browse_subs.winfo_exists():
            return
        for w in self.browse_subs.winfo_children():
            w.destroy()
        if err:
            ctk.CTkLabel(self.browse_subs, text=f"❌ {err}", text_color="#ef4444",
                         font=ctk.CTkFont(size=11)).pack(anchor="w")
            return
        if not tracks:
            ctk.CTkLabel(self.browse_subs, text="Aucun sous-titre.", text_color="gray",
                         font=ctk.CTkFont(size=11)).pack(anchor="w")
            return
        # Dictionnaires code→libellé pour un affichage lisible
        langs = dict(SUBTITLE_LANGS)
        kinds = dict(SUBTITLE_KINDS)
        for t in tracks:
            row = ctk.CTkFrame(self.browse_subs, fg_color=("gray85", "gray17"),
                               corner_radius=6)
            row.pack(fill="x", pady=2)
            lang = langs.get(t.get("lang"), t.get("lang"))
            kind = kinds.get(t.get("kind"), t.get("kind"))
            ctk.CTkLabel(row, text=f"{lang} · {kind}", anchor="w",
                         font=ctk.CTkFont(size=12)).pack(side="left", padx=10, pady=5,
                                                         fill="x", expand=True)
            ctk.CTkButton(row, text="🗑", width=34, fg_color="#b91c1c",
                          hover_color="#991b1b",
                          command=lambda tt=t: self._sub_delete(v, tt)).pack(side="right", padx=6)

    def _sub_add_dialog(self, v):
        """Fenêtre d'ajout : choix langue + type + fichier .vtt/.srt."""
        if not self.api:
            return
        win = ctk.CTkToplevel(self)
        win.title("Ajouter un sous-titre")
        win.geometry("440x300")
        _focus_toplevel(win, self)

        ctk.CTkLabel(win, text=f"Vidéo : {(v.get('title') or '')[:50]}",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(padx=16, pady=(16, 10), anchor="w")

        # Menu Langue
        ctk.CTkLabel(win, text="Langue :").pack(padx=16, anchor="w")
        lang_labels = [f"{lbl} ({code})" for code, lbl in SUBTITLE_LANGS]
        lang_menu = ctk.CTkOptionMenu(win, values=lang_labels, width=260)
        lang_menu.set("Français (fr)")
        lang_menu.pack(padx=16, pady=(0, 8), anchor="w")

        # Menu Type
        ctk.CTkLabel(win, text="Type :").pack(padx=16, anchor="w")
        kind_menu = ctk.CTkOptionMenu(
            win, values=[lbl for _c, lbl in SUBTITLE_KINDS], width=260)
        kind_menu.set("Sous-titres")
        kind_menu.pack(padx=16, pady=(0, 8), anchor="w")

        # Sélection du fichier
        path_var = {"p": None}
        path_lbl = ctk.CTkLabel(win, text="Aucun fichier choisi.", text_color="gray",
                                font=ctk.CTkFont(size=11), wraplength=400, justify="left")

        def choose():
            # Boîte de sélection limitée aux formats acceptés
            p = filedialog.askopenfilename(
                title="Choisir un fichier de sous-titres",
                filetypes=[("Sous-titres", "*.vtt *.srt"), ("Tous", "*.*")])
            if p:
                path_var["p"] = p
                path_lbl.configure(text=os.path.basename(p), text_color="white")

        ctk.CTkButton(win, text="📄  Choisir un fichier .vtt / .srt",
                      command=choose, fg_color="gray35").pack(padx=16, pady=(4, 2), anchor="w")
        path_lbl.pack(padx=16, anchor="w")

        def valider():
            # Résolution des codes à partir des libellés choisis
            lang_code = SUBTITLE_LANGS[lang_labels.index(lang_menu.get())][0]
            kind_code = next(c for c, lbl in SUBTITLE_KINDS
                             if lbl == kind_menu.get())
            path = path_var["p"]
            if not path:
                path_lbl.configure(text="⚠️ Choisissez d'abord un fichier.",
                                   text_color="#f59e0b")
                return
            # Garde-fou d'extension (la conversion gère .srt, sinon .vtt attendu)
            if not path.lower().endswith((".vtt", ".srt")):
                path_lbl.configure(text="⚠️ Le fichier doit être .vtt ou .srt.",
                                   text_color="#f59e0b")
                return
            win.destroy()
            self._run(self._sub_do_add, v, lang_code, kind_code, path)

        ctk.CTkButton(win, text="Ajouter", fg_color="#16a34a", hover_color="#15803d",
                      command=valider).pack(pady=14)

    def _sub_do_add(self, v, lang, kind, path):
        """(Thread) Téléverse le fichier et crée la piste, puis rafraîchit la liste."""
        try:
            self.api.add_subtitle(v, lang, kind, path)   # conversion .srt incluse
            self._ui(self._log, f"➕ Sous-titre ajouté ({lang}/{kind}) à {v.get('slug')}")
            self._ui(self._browse_set_msg, "✅  Sous-titre ajouté.", "#22c55e")
            self._run(self._sub_load, v)                 # recharge la liste
        except Exception as e:
            self._ui(self._log, f"❌ Ajout sous-titre {v.get('slug')} : {e}")
            self._ui(self._browse_set_msg, f"❌  {e}", "#ef4444")

    def _sub_delete(self, v, track):
        """Supprime une piste après confirmation."""
        langs = dict(SUBTITLE_LANGS)
        lib = langs.get(track.get("lang"), track.get("lang"))
        if not messagebox.askyesno(
                "Supprimer le sous-titre",
                f"Supprimer la piste « {lib} » de cette vidéo ?"):
            return
        self._run(self._sub_do_delete, v, track)

    def _sub_do_delete(self, v, track):
        """(Thread) DELETE de la piste, puis rafraîchit la liste."""
        try:
            self.api.delete_track(track)
            self._ui(self._log, f"🗑 Sous-titre supprimé ({track.get('lang')}) de {v.get('slug')}")
            self._run(self._sub_load, v)
        except Exception as e:
            self._ui(self._log, f"❌ Suppression sous-titre : {e}")
            self._ui(self._browse_set_msg, f"❌  {e}", "#ef4444")

    def _browse_mass_set_type(self):
        """Affecte le type choisi à TOUTES les vidéos actuellement affichées
        (résultat du filtre courant). Double confirmation, puis exécution."""
        choice = self.browse_mass_type.get()
        new_url = (self.type_map or {}).get(choice)
        vids = list(self.browse_filtered)
        if not new_url or not vids:
            self._browse_set_msg("Rien à appliquer (aucun type ou aucune vidéo affichée).",
                                 "#f59e0b")
            return
        if not messagebox.askyesno(
                "Type en masse",
                f"Affecter le type « {choice} » à {len(vids)} vidéo(s) affichée(s) ?\n\n"
                "Cette action écrase le type actuel de chacune."):
            return
        self._run(self._do_browse_mass_set_type, vids, new_url, choice)

    def _do_browse_mass_set_type(self, vids, new_url, choice):
        """(Thread) Applique le type à chaque vidéo affichée, avec bilan."""
        new_n = str(new_url).rstrip("/")
        ok = fail = skip = 0
        for i, v in enumerate(vids, 1):
            cur = v.get("type")
            cur = cur.get("url") if isinstance(cur, dict) else cur
            if str(cur).rstrip("/") == new_n:
                skip += 1                              # déjà ce type : on n'appelle pas l'API
                continue
            try:
                self.api.patch_video(v, {"type": new_url})
                v["type"] = new_url                    # MAJ cache local
                ok += 1
            except Exception as e:
                fail += 1
                self._ui(self._log, f"❌ {v.get('slug')} : {e}")
            self._ui(self.browse_status.configure,
                     text=f"⏳  {i}/{len(vids)}…", text_color="gray")
        self._ui(self.browse_status.configure,
                 text=f"✅  Type « {choice} » : {ok} modifiée(s), {skip} déjà OK, {fail} échec(s).",
                 text_color="#22c55e" if not fail else "#f59e0b")
        self._ui(self._log,
                 f"Type en masse « {choice} » : {ok} modifiée(s), {skip} inchangée(s), "
                 f"{fail} échec(s).")
        self._ui(self._browse_apply_filter)            # rafraîchit l'affichage

    def _browse_rename(self, v):
        new = self.browse_title_entry.get().strip()
        if new and new != v.get("title"):
            self._browse_patch(v, {"title": new}, f"titre → {new}")

    def _browse_patch(self, v, payload, msg):
        """Applique un PATCH sur la vidéo puis met à jour l'affichage."""
        self._run(self._do_browse_patch, v, payload, msg)

    def _do_browse_patch(self, v, payload, msg):
        slug = v.get("slug", "")
        try:
            self.api.patch_video(v, payload)
            v.update(payload)               # met à jour le cache local
            self._ui(self._log, f"✏ {slug} : {msg}")
            self._ui(self._browse_set_msg, f"✅  {msg}", "#22c55e")
            self._ui(self._browse_render_detail)
            self._ui(self._render_browse_list)
        except Exception as e:
            self._ui(self._log, f"❌ {slug} : {e}")
            self._ui(self._browse_set_msg, f"❌  {e}", "#ef4444")
            self._ui(self._browse_render_detail)

    def _browse_set_msg(self, text, color):
        if hasattr(self, "browse_msg") and self.browse_msg.winfo_exists():
            self.browse_msg.configure(text=text, text_color=color)

    def _browse_edit_owners(self, v):
        """Ouvre le sélecteur d'utilisateurs (OwnerPicker) pour les co-propriétaires."""
        # Pré-sélection : co-propriétaires actuels (URL → libellé lisible)
        user_by_url = {str(u.get("url", "")).rstrip("/"): u for u in (self.all_users or [])}
        pre = {}
        for ourl in (v.get("additional_owners") or []):
            u = user_by_url.get(str(ourl).rstrip("/"))
            pre[ourl] = self._user_label(u) if u else ourl
        OwnerPicker(self, on_done=lambda urls, labels: self._browse_apply_owners(v, urls),
                    title="Co-propriétaires de la vidéo", preselected=pre)

    def _browse_apply_owners(self, v, urls):
        self._run(self._do_browse_patch, v, {"additional_owners": list(urls)},
                  f"{len(urls)} co-propriétaire(s)")

    def _browse_edit_channels(self, v):
        """Ouvre le sélecteur de chaînes pour cette vidéo."""
        cur = v.get("channel") or []
        if isinstance(cur, str):
            cur = [cur]
        pre = {c: self.browse_chan_by_url.get(str(c).rstrip("/"), str(c)) for c in cur}
        ChannelPicker(self, self.browse_channels,
                      on_done=lambda urls, labels: self._browse_apply_channels(v, urls),
                      title="Chaînes de la vidéo", preselected=pre)

    def _browse_apply_channels(self, v, urls):
        self._run(self._do_browse_patch, v, {"channel": list(urls)},
                  f"{len(urls)} chaîne(s)")

    def _browse_delete(self, v):
        if not messagebox.askyesno(
                "⚠️  Supprimer la vidéo",
                f"Supprimer DÉFINITIVEMENT « {v.get('title')} » ?\n\n"
                "Cette action est IRRÉVERSIBLE (pas de corbeille sur Pod)."):
            return
        if not messagebox.askyesno("Dernière confirmation",
                                   "Confirmez-vous la suppression de cette vidéo ?"):
            return
        self._run(self._do_browse_delete, v)

    def _do_browse_delete(self, v):
        slug = v.get("slug", "")
        try:
            self.api.delete_video(v)
            if v in self.browse_videos:
                self.browse_videos.remove(v)
            self.browse_selected = None
            self._ui(self._log, f"🗑 Vidéo supprimée : {slug}")
            self._ui(self._browse_render_detail)
            self._ui(self._browse_apply_filter)
        except Exception as e:
            self._ui(self._log, f"❌ Suppression {slug} : {e}")
            self._ui(self._browse_set_msg, f"❌  {e}", "#ef4444")

    # ═════════════════════════════════════════════════════════════════════
    #  ONGLET RÉAFFECTATION — changer le propriétaire de vidéos par lot
    # ═════════════════════════════════════════════════════════════════════
    #
    #  Principe : on choisit un ANCIEN propriétaire (source) et un NOUVEAU
    #  (cible), on liste les vidéos de la source en mode « aperçu » (dry-run),
    #  l'utilisateur coche/décoche, confirme, puis on applique en PATCHant le
    #  champ `owner` de chaque vidéo. Aucune écriture n'a lieu avant le clic
    #  explicite sur « Appliquer ».

    def _build_tab_reassign(self):
        # Cadre racine de l'onglet (enregistré dans self.tabs)
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tabs["reassign"] = frame

        # Titre + courte explication du flux de travail
        ctk.CTkLabel(frame, text="🔄  Réaffectation de propriétaire",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            frame,
            text="Transférer les vidéos d'un compte vers un autre (ex. départ d'un agent). "
                 "Choisissez l'ancien et le nouveau propriétaire, lancez l'aperçu, "
                 "vérifiez la liste, puis appliquez.",
            text_color="gray70", font=ctk.CTkFont(size=12),
            justify="left", wraplength=860).pack(anchor="w", pady=(0, 10))

        # — Deux sélecteurs de comptes côte à côte (source / cible) —
        pickers = ctk.CTkFrame(frame, fg_color="transparent")
        pickers.pack(fill="x")
        pickers.columnconfigure(0, weight=1)   # colonnes de largeur égale
        pickers.columnconfigure(1, weight=1)

        # Liste mémorisant les deux sélecteurs, pour les rafraîchir quand la
        # liste des comptes est (re)chargée. Initialisée AVANT _mini_user_picker.
        self._reassign_pickers = []

        # Sélecteur SOURCE (ancien propriétaire)
        src_box = self._mini_user_picker(
            pickers, "① Ancien propriétaire (source)", self._on_pick_source)
        src_box["frame"].grid(row=0, column=0, padx=(0, 6), sticky="nsew")
        # Sélecteur CIBLE (nouveau propriétaire)
        tgt_box = self._mini_user_picker(
            pickers, "② Nouveau propriétaire (cible)", self._on_pick_target)
        tgt_box["frame"].grid(row=0, column=1, padx=(6, 0), sticky="nsew")

        # Comptes sélectionnés (dicts utilisateur) ; None tant que rien n'est choisi
        self.reassign_source = None
        self.reassign_target = None

        # — Option : garder l'ancien propriétaire en co-propriétaire —
        opt = ctk.CTkFrame(frame, fg_color="transparent")
        opt.pack(fill="x", pady=(8, 2))
        # Si coché, l'ancien propriétaire est ajouté aux additional_owners :
        # il conserve les droits d'édition (mais pas de suppression).
        self.reassign_keep_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            opt, text="Conserver l'ancien propriétaire en co-propriétaire (additional_owners)",
            variable=self.reassign_keep_var).pack(side="left")

        # — Boutons d'action —
        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.pack(fill="x", pady=(6, 4))
        # Aperçu = lecture seule, n'écrit RIEN
        ctk.CTkButton(actions, text="🔍  Aperçu (dry-run)", fg_color="#2563eb",
                      hover_color="#1d4ed8", command=self._reassign_preview).pack(side="left")
        # Appliquer = action en masse ; désactivé tant qu'aucun aperçu n'est fait
        self.reassign_apply_btn = ctk.CTkButton(
            actions, text="✅  Appliquer la réaffectation", fg_color="#16a34a",
            hover_color="#15803d", state="disabled", command=self._reassign_confirm)
        self.reassign_apply_btn.pack(side="left", padx=10)
        # Libellé de progression / d'état
        self.reassign_progress = ctk.CTkLabel(actions, text="", text_color="gray",
                                              font=ctk.CTkFont(size=11))
        self.reassign_progress.pack(side="left", padx=8)

        # — Zone d'aperçu : la liste des vidéos concernées (cases à cocher) —
        self.reassign_results = ctk.CTkScrollableFrame(frame, label_text="Aperçu des vidéos")
        self.reassign_results.pack(fill="both", expand=True, pady=(4, 0))

        # Structures de données de l'aperçu :
        self.reassign_videos = []      # vidéos de la source (liste de dicts)
        self.reassign_rowvars = {}     # slug → BooleanVar (cochée = à réaffecter)
        self.reassign_rowlbls = {}     # slug → label de statut (✔/✗ après application)

    # ── Sélecteur de compte compact et réutilisable ───────────────────────

    def _mini_user_picker(self, parent, title, on_pick):
        """Construit un sélecteur de compte (titre + filtre + liste cliquable +
        libellé du choix). Renvoie un dict d'état réutilisé par _render_mini_picker.
        `on_pick(user)` est appelé quand l'utilisateur clique un compte."""
        box = ctk.CTkFrame(parent)
        ctk.CTkLabel(box, text=title, font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=10, pady=(8, 2))
        # Champ de filtre → filtrage CLIENT instantané (aucun appel serveur)
        fe = ctk.CTkEntry(box, placeholder_text="🔍 nom / identifiant…")
        fe.pack(fill="x", padx=10, pady=(0, 6))
        # Liste défilante des comptes correspondant au filtre
        res = ctk.CTkScrollableFrame(box, height=150)
        res.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        # Rappel du compte actuellement sélectionné
        chosen = ctk.CTkLabel(box, text="Sélection : (aucune)", text_color="gray70",
                              font=ctk.CTkFont(size=11), anchor="w")
        chosen.pack(fill="x", padx=10, pady=(0, 8))
        # État partagé entre le picker et son moteur de rendu
        state = {"frame": box, "filter": fe, "results": res,
                 "chosen": chosen, "on_pick": on_pick, "selected": None}
        # Re-render à chaque frappe dans le filtre
        fe.bind("<KeyRelease>", lambda e, s=state: self._render_mini_picker(s))
        self._reassign_pickers.append(state)
        self._render_mini_picker(state)
        return state

    def _render_mini_picker(self, state):
        """(Ré)affiche la liste filtrée d'un sélecteur de compte."""
        flt = state["filter"].get().strip().lower()
        # Vider la liste précédente
        for w in state["results"].winfo_children():
            w.destroy()
        # Aucun compte encore chargé
        if not self.all_users:
            ctk.CTkLabel(state["results"], text="Connectez-vous puis rechargez les comptes.",
                         text_color="gray").pack(pady=8)
            return
        # Filtrage client + plafond d'affichage (Tk gèle au-delà de quelques centaines)
        matches = [u for u in self.all_users
                   if not flt or flt in self._user_label(u).lower()]
        CAP = 200
        sel = state["selected"]
        for u in matches[:CAP]:
            # Marque ✅ le compte sélectionné dans ce picker
            is_sel = sel is not None and u.get("username") == sel.get("username")
            label = ("✅  " if is_sel else "      ") + self._user_label(u)
            ctk.CTkButton(
                state["results"], text=label, anchor="w", height=26,
                fg_color=("gray75", "gray30") if is_sel else "transparent",
                text_color=("gray10", "gray90"), hover_color=("gray75", "gray28"),
                font=ctk.CTkFont(size=12),
                command=lambda uu=u, s=state: self._mini_pick(s, uu)).pack(fill="x", pady=1)
        # Indications de fin de liste
        if len(matches) > CAP:
            ctk.CTkLabel(state["results"],
                         text=f"… +{len(matches) - CAP} autres. Affinez le filtre.",
                         text_color="gray").pack(pady=4)
        elif not matches:
            ctk.CTkLabel(state["results"], text="Aucun compte.", text_color="gray").pack(pady=6)

    def _mini_pick(self, state, user):
        """Enregistre le compte choisi dans un sélecteur et notifie l'appelant."""
        state["selected"] = user
        state["chosen"].configure(text=f"Sélection : {self._user_label(user)}",
                                  text_color="#22c55e")
        self._render_mini_picker(state)     # met à jour la coche ✅
        state["on_pick"](user)              # callback spécifique (source ou cible)

    def _on_pick_source(self, user):
        # Mémorise l'ancien propriétaire ; tout aperçu précédent devient caduc
        self.reassign_source = user
        self.reassign_apply_btn.configure(state="disabled")

    def _on_pick_target(self, user):
        # Mémorise le nouveau propriétaire
        self.reassign_target = user

    def _refresh_reassign_pickers(self):
        """Rafraîchit les deux sélecteurs (appelé quand les comptes sont chargés)."""
        for st in getattr(self, "_reassign_pickers", []):
            self._render_mini_picker(st)

    # ── Appariement vidéo ↔ propriétaire (robuste au format du champ owner) ─

    def _video_owner_id(self, video):
        """Renvoie l'identifiant du propriétaire d'une vidéo, quel que soit le
        format renvoyé par l'API (URL, dict imbriqué, username ou id)."""
        o = video.get("owner")
        if isinstance(o, dict):                       # owner imbriqué {url, username…}
            return o.get("url") or o.get("username") or ""
        return o if o is not None else ""             # URL (str), username ou id

    def _video_belongs_to(self, video, user):
        """Vrai si la vidéo appartient au compte `user`. On compare l'identifiant
        propriétaire à l'URL, au username et à l'id du compte (couvre tous les cas)."""
        oid = str(self._video_owner_id(video))
        if not oid:
            return False
        candidates = {str(user.get("url", "")).rstrip("/"),
                      str(user.get("username", "")),
                      str(user.get("id", ""))}
        # Comparaison directe, ou URL se terminant par /users/<id>
        return (oid.rstrip("/") in candidates
                or oid.rstrip("/").endswith(f"/users/{user.get('id')}"))

    # ── Aperçu (dry-run) : lister les vidéos de la source ──────────────────

    def _reassign_preview(self):
        """Lance l'aperçu : vérifie les sélections puis scanne l'instance en
        arrière-plan. AUCUNE modification n'est effectuée ici."""
        if not self.api:
            self.reassign_progress.configure(text="Connectez-vous d'abord.",
                                             text_color="#f59e0b")
            return
        if not self.reassign_source:
            self.reassign_progress.configure(text="Choisissez l'ancien propriétaire (source).",
                                             text_color="#f59e0b")
            return
        self.reassign_apply_btn.configure(state="disabled")
        self.reassign_progress.configure(text="⏳  Analyse des vidéos…", text_color="gray")
        self._run(self._do_reassign_preview)

    def _do_reassign_preview(self):
        """(Thread) Scan complet de l'instance + filtrage par propriétaire."""
        try:
            # Callback de progression du scan paginé (mis à jour via le thread UI)
            def prog(n):
                self._ui(self.reassign_progress.configure,
                         text=f"⏳  {n} vidéos lues…", text_color="gray")
            videos = self.api.get_all_videos(progress_cb=prog)
            # Ne conserver que les vidéos appartenant à la source
            mine = [v for v in videos if self._video_belongs_to(v, self.reassign_source)]
            self.reassign_videos = mine
            self._ui(self._render_reassign_preview)
            self._ui(self._log,
                     f"Aperçu réaffectation : {len(mine)} vidéo(s) pour "
                     f"{self.reassign_source.get('username')} (sur {len(videos)} au total).")
        except Exception as e:
            self._ui(self.reassign_progress.configure, text=f"❌  {e}", text_color="#ef4444")
            self._ui(self._log, f"❌ Erreur aperçu réaffectation : {e}")

    def _render_reassign_preview(self):
        """Affiche la liste des vidéos concernées avec une case à cocher chacune."""
        # Vider l'aperçu précédent et réinitialiser les structures
        for w in self.reassign_results.winfo_children():
            w.destroy()
        self.reassign_rowvars = {}
        self.reassign_rowlbls = {}

        if not self.reassign_videos:
            ctk.CTkLabel(self.reassign_results,
                         text="Aucune vidéo trouvée pour ce compte.",
                         text_color="gray").pack(pady=10)
            self.reassign_progress.configure(text="0 vidéo.", text_color="gray")
            self.reassign_apply_btn.configure(state="disabled")
            return

        # En-tête : (dé)sélection globale
        head = ctk.CTkFrame(self.reassign_results, fg_color="transparent")
        head.pack(fill="x", pady=(0, 4))
        ctk.CTkButton(head, text="Tout cocher", width=100, height=24, fg_color="gray35",
                      command=lambda: self._reassign_check_all(True)).pack(side="left", padx=2)
        ctk.CTkButton(head, text="Tout décocher", width=110, height=24, fg_color="gray35",
                      command=lambda: self._reassign_check_all(False)).pack(side="left", padx=2)

        # Une ligne par vidéo : [case] titre · slug … [statut ✔/✗]
        for v in self.reassign_videos:
            slug = v.get("slug", "?")
            row = ctk.CTkFrame(self.reassign_results, fg_color=("gray85", "gray17"),
                               corner_radius=6)
            row.pack(fill="x", pady=2)
            var = ctk.BooleanVar(value=True)        # cochée par défaut = sera réaffectée
            self.reassign_rowvars[slug] = var
            ctk.CTkCheckBox(row, text="", variable=var, width=24).pack(side="left", padx=(8, 0))
            title = (v.get("title") or "(sans titre)")[:70]
            ctk.CTkLabel(row, text=f"{title}   ·   {slug}", anchor="w",
                         font=ctk.CTkFont(size=12)).pack(
                side="left", padx=8, pady=6, fill="x", expand=True)
            stat = ctk.CTkLabel(row, text="", width=24, font=ctk.CTkFont(size=12))
            stat.pack(side="right", padx=8)
            self.reassign_rowlbls[slug] = stat

        self.reassign_progress.configure(
            text=f"{len(self.reassign_videos)} vidéo(s) prêtes à réaffecter.",
            text_color="#22c55e")
        # L'aperçu est prêt → on autorise l'application
        self.reassign_apply_btn.configure(state="normal")

    def _reassign_check_all(self, value: bool):
        """Coche ou décoche toutes les vidéos de l'aperçu."""
        for var in self.reassign_rowvars.values():
            var.set(value)

    # ── Application (action en masse, après confirmation explicite) ────────

    def _reassign_confirm(self):
        """Vérifie la cible, récapitule, puis demande confirmation avant d'écrire."""
        if not self.reassign_target:
            self.reassign_progress.configure(text="Choisissez le nouveau propriétaire (cible).",
                                             text_color="#f59e0b")
            return
        # Vidéos réellement cochées dans l'aperçu
        todo = [v for v in self.reassign_videos
                if self.reassign_rowvars.get(v.get("slug"))
                and self.reassign_rowvars[v.get("slug")].get()]
        if not todo:
            self.reassign_progress.configure(text="Aucune vidéo cochée.", text_color="#f59e0b")
            return
        keep = (" (l'ancien propriétaire reste co-propriétaire)"
                if self.reassign_keep_var.get() else "")
        # Dialogue de confirmation récapitulatif (dernier garde-fou avant écriture)
        ok = messagebox.askyesno(
            "Confirmer la réaffectation",
            f"Réaffecter {len(todo)} vidéo(s)\n\n"
            f"de :   {self._user_label(self.reassign_source)}\n"
            f"vers : {self._user_label(self.reassign_target)}{keep}\n\n"
            "Cette opération modifie le propriétaire de chaque vidéo. Continuer ?")
        if not ok:
            return
        # Désactiver le bouton pendant le traitement (évite les double-clics)
        self.reassign_apply_btn.configure(state="disabled")
        self._run(self._do_reassign_apply, todo)

    def _do_reassign_apply(self, todo):
        """(Thread) Applique la réaffectation vidéo par vidéo via PATCH owner."""
        tgt = self.reassign_target
        keep = self.reassign_keep_var.get()
        ok = fail = 0
        for i, v in enumerate(todo, 1):
            slug = v.get("slug", "")
            try:
                add = None
                if keep:
                    # Conserver les co-propriétaires existants + ajouter l'ancien
                    existing = list(v.get("additional_owners") or [])
                    add = list(dict.fromkeys(existing + [self.reassign_source.get("url")]))
                # ÉCRITURE réelle : PATCH /rest/videos/<id>/ {owner: <url cible>}
                self.api.set_video_owner(v, tgt.get("url"), additional_owner_urls=add)
                v["owner"] = tgt.get("url")       # met à jour le cache local
                ok += 1
                self._ui(self._mark_reassign_row, slug, True)
            except Exception as e:
                fail += 1
                self._ui(self._mark_reassign_row, slug, False)
                self._ui(self._log, f"  ✗ {slug} : {e}")
            # Progression
            self._ui(self.reassign_progress.configure,
                     text=f"⏳  {i}/{len(todo)}…", text_color="gray")
        # Bilan final
        self._ui(self.reassign_progress.configure,
                 text=f"Terminé : {ok} réaffectée(s), {fail} échec(s).",
                 text_color="#22c55e" if not fail else "#f59e0b")
        self._ui(self._log,
                 f"Réaffectation {self.reassign_source.get('username')} → "
                 f"{tgt.get('username')} : {ok} OK, {fail} échec(s).")
        # Réactiver le bouton pour une éventuelle nouvelle opération
        self._ui(self.reassign_apply_btn.configure, state="normal")

    def _mark_reassign_row(self, slug, success: bool):
        """Pose un ✔ (vert) ou ✗ (rouge) sur la ligne d'une vidéo traitée."""
        lbl = self.reassign_rowlbls.get(slug)
        if lbl:
            lbl.configure(text="✔" if success else "✗",
                          text_color="#22c55e" if success else "#ef4444")

    # ═════════════════════════════════════════════════════════════════════
    #  ONGLET NETTOYAGE / MODÉRATION
    # ═════════════════════════════════════════════════════════════════════
    #
    #  Flux : (1) SCANNER l'instance (lecture seule) → (2) choisir une
    #  CATÉGORIE de détection (jamais encodées, brouillons, vieux brouillons,
    #  doublons de titre) + un filtre texte → (3) cocher les vidéos voulues →
    #  (4) appliquer une ACTION (brouillon / publier / restreindre / lever /
    #  SUPPRIMER). La suppression demande une DOUBLE confirmation.
    #  Par sécurité, les cases sont DÉCOCHÉES par défaut (opt-in explicite).

    # Libellé d'action (menu) → code interne utilisé par _do_clean_apply
    _CLEAN_ACTIONS = {
        "Mettre en brouillon":          "draft_on",
        "Publier (retirer brouillon)":  "draft_off",
        "Restreindre l'accès":          "restrict_on",
        "Lever la restriction":         "restrict_off",
        "🗑  Supprimer définitivement": "delete",
    }

    def _build_tab_clean(self):
        # Cadre racine de l'onglet
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tabs["clean"] = frame

        ctk.CTkLabel(frame, text="🧹  Nettoyage / Modération",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            frame,
            text="Scannez l'instance, isolez une catégorie de vidéos (jamais encodées, "
                 "brouillons, doublons…), cochez celles à traiter, puis appliquez une action. "
                 "La suppression est définitive et demande une double confirmation.",
            text_color="gray70", font=ctk.CTkFont(size=12),
            justify="left", wraplength=860).pack(anchor="w", pady=(0, 10))

        # — Ligne 1 : scan (lecture seule) —
        scan_row = ctk.CTkFrame(frame, fg_color="transparent")
        scan_row.pack(fill="x")
        ctk.CTkButton(scan_row, text="📡  Scanner les vidéos", fg_color="#2563eb",
                      hover_color="#1d4ed8", command=self._clean_scan).pack(side="left")
        self.clean_scan_lbl = ctk.CTkLabel(scan_row, text="(aucun scan)", text_color="gray",
                                           font=ctk.CTkFont(size=11))
        self.clean_scan_lbl.pack(side="left", padx=10)

        # — Ligne 2 : critères de détection —
        crit = ctk.CTkFrame(frame, fg_color="transparent")
        crit.pack(fill="x", pady=(8, 2))
        ctk.CTkLabel(crit, text="Catégorie :").pack(side="left", padx=(0, 4))
        # Menu déroulant des catégories ; tout changement relance le filtrage
        self.clean_category = ctk.CTkOptionMenu(
            crit, width=190,
            values=["Toutes", "Jamais encodées", "Brouillons",
                    "Vieux brouillons", "Doublons de titre"],
            command=lambda _choice: self._apply_clean_filter())
        self.clean_category.set("Toutes")
        self.clean_category.pack(side="left")
        # Ancienneté (en mois) utilisée par la catégorie « Vieux brouillons »
        ctk.CTkLabel(crit, text="  brouillons > ").pack(side="left")
        self.clean_months = ctk.CTkEntry(crit, width=46)
        self.clean_months.insert(0, "6")
        self.clean_months.pack(side="left")
        self.clean_months.bind("<KeyRelease>", lambda e: self._apply_clean_filter())
        ctk.CTkLabel(crit, text="mois").pack(side="left", padx=(2, 10))
        # Filtre texte libre (titre / slug / propriétaire)
        ctk.CTkLabel(crit, text="Filtre :").pack(side="left", padx=(0, 4))
        self.clean_text = ctk.CTkEntry(crit, width=200,
                                       placeholder_text="🔍 titre / slug / propriétaire…")
        self.clean_text.pack(side="left", fill="x", expand=True)
        self.clean_text.bind("<KeyRelease>", lambda e: self._apply_clean_filter())

        # Compteur de la sélection courante
        self.clean_count_lbl = ctk.CTkLabel(frame, text="", text_color="gray",
                                            font=ctk.CTkFont(size=11))
        self.clean_count_lbl.pack(anchor="w", pady=(6, 2))

        # — Liste des vidéos (cases à cocher) —
        self.clean_results = ctk.CTkScrollableFrame(frame, label_text="Vidéos détectées")
        self.clean_results.pack(fill="both", expand=True, pady=(0, 4))

        # — Ligne d'action en masse —
        act = ctk.CTkFrame(frame, fg_color="transparent")
        act.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(act, text="Action :").pack(side="left", padx=(0, 4))
        self.clean_action = ctk.CTkOptionMenu(act, width=230,
                                              values=list(self._CLEAN_ACTIONS.keys()))
        self.clean_action.set("Mettre en brouillon")
        self.clean_action.pack(side="left")
        self.clean_apply_btn = ctk.CTkButton(
            act, text="▶  Appliquer l'action", fg_color="#16a34a", hover_color="#15803d",
            command=self._clean_apply)
        self.clean_apply_btn.pack(side="left", padx=10)
        self.clean_progress = ctk.CTkLabel(act, text="", text_color="gray",
                                           font=ctk.CTkFont(size=11))
        self.clean_progress.pack(side="left", padx=8)

        # Structures de données
        self.clean_videos = []     # scan complet (cache)
        self.clean_filtered = []   # sous-ensemble affiché après filtrage
        self.clean_rowvars = {}    # slug → BooleanVar (cochée = à traiter)
        self.clean_rowlbls = {}    # slug → label de statut ✔/✗

    # ── Scan de l'instance (lecture seule) ─────────────────────────────────

    def _clean_scan(self):
        """Déclenche le scan complet des vidéos (en arrière-plan)."""
        if not self.api:
            self.clean_scan_lbl.configure(text="Connectez-vous d'abord.", text_color="#f59e0b")
            return
        self.clean_scan_lbl.configure(text="⏳  Scan en cours…", text_color="gray")
        self._run(self._do_clean_scan)

    def _do_clean_scan(self):
        """(Thread) Récupère toutes les vidéos puis applique le filtre courant."""
        try:
            def prog(n):   # progression du scan paginé
                self._ui(self.clean_scan_lbl.configure,
                         text=f"⏳  {n} vidéos lues…", text_color="gray")
            vids = self.api.get_all_videos(progress_cb=prog)
            self.clean_videos = vids
            self._ui(self.clean_scan_lbl.configure,
                     text=f"✅  {len(vids)} vidéos chargées.", text_color="#22c55e")
            self._ui(self._apply_clean_filter)
            self._ui(self._log, f"Scan nettoyage : {len(vids)} vidéos.")
        except Exception as e:
            self._ui(self.clean_scan_lbl.configure, text=f"❌  {e}", text_color="#ef4444")
            self._ui(self._log, f"❌ Scan nettoyage : {e}")

    # ── Filtrage par catégorie + texte ─────────────────────────────────────

    def _clean_months_value(self) -> int:
        """Lit le champ « mois » (entier ≥ 0, défaut 6 si saisie invalide)."""
        try:
            return max(0, int(self.clean_months.get().strip()))
        except Exception:
            return 6

    def _months_ago_iso(self, months: int) -> str:
        """Renvoie la date d'il y a `months` mois au format AAAA-MM-JJ."""
        import calendar
        today = datetime.now().date()
        m, y = today.month - months, today.year
        while m <= 0:          # report sur les années précédentes
            m += 12
            y -= 1
        # On borne le jour au dernier jour valide du mois cible
        d = min(today.day, calendar.monthrange(y, m)[1])
        return datetime(y, m, d).date().isoformat()

    def _duplicate_title_videos(self, vids: list) -> list:
        """Renvoie les vidéos dont le titre (normalisé) apparaît plus d'une fois,
        triées par titre pour regrouper visuellement les doublons."""
        from collections import Counter
        def norm(v):
            return (v.get("title") or "").strip().lower()
        counts = Counter(norm(v) for v in vids if norm(v))
        dups = [v for v in vids if norm(v) and counts[norm(v)] > 1]
        dups.sort(key=norm)
        return dups

    def _apply_clean_filter(self, *_):
        """Construit self.clean_filtered selon la catégorie + le filtre texte."""
        # Pas encore scanné
        if not self.clean_videos:
            self.clean_count_lbl.configure(
                text="Cliquez sur « Scanner les vidéos » pour commencer.")
            for w in self.clean_results.winfo_children():
                w.destroy()
            self.clean_filtered = []
            return

        cat = self.clean_category.get()
        vids = self.clean_videos

        # Filtre par catégorie de détection
        if cat == "Jamais encodées":
            vids = [v for v in vids if PodAPI.is_unencoded(v)]
        elif cat == "Brouillons":
            vids = [v for v in vids if v.get("is_draft")]
        elif cat == "Vieux brouillons":
            cutoff = self._months_ago_iso(self._clean_months_value())
            vids = [v for v in vids if PodAPI.is_stale_draft(v, cutoff)]
        elif cat == "Doublons de titre":
            vids = self._duplicate_title_videos(vids)
        # "Toutes" → aucun filtre de catégorie

        # Filtre texte (titre / slug / propriétaire)
        txt = self.clean_text.get().strip().lower()
        if txt:
            def hay(v):
                return (f"{v.get('title','')} {v.get('slug','')} "
                        f"{self._video_owner_id(v)}").lower()
            vids = [v for v in vids if txt in hay(v)]

        self.clean_filtered = vids
        self._render_clean_list()

    # ── Rendu de la liste ──────────────────────────────────────────────────

    def _render_clean_list(self):
        """Affiche les vidéos filtrées, chacune avec une case (décochée par défaut)."""
        for w in self.clean_results.winfo_children():
            w.destroy()
        self.clean_rowvars = {}
        self.clean_rowlbls = {}

        cat = self.clean_category.get()
        self.clean_count_lbl.configure(
            text=f"{len(self.clean_filtered)} vidéo(s) — catégorie « {cat} ». "
                 f"Cochez celles à traiter.")

        if not self.clean_filtered:
            ctk.CTkLabel(self.clean_results, text="Aucune vidéo dans cette catégorie.",
                         text_color="gray").pack(pady=10)
            return

        # En-tête : (dé)sélection globale
        head = ctk.CTkFrame(self.clean_results, fg_color="transparent")
        head.pack(fill="x", pady=(0, 4))
        ctk.CTkButton(head, text="Tout cocher", width=100, height=24, fg_color="gray35",
                      command=lambda: self._clean_check_all(True)).pack(side="left", padx=2)
        ctk.CTkButton(head, text="Tout décocher", width=110, height=24, fg_color="gray35",
                      command=lambda: self._clean_check_all(False)).pack(side="left", padx=2)

        # Une ligne par vidéo : [case] titre · slug  [drapeaux]   …  [statut]
        for v in self.clean_filtered:
            slug = v.get("slug", "?")
            row = ctk.CTkFrame(self.clean_results, fg_color=("gray85", "gray17"),
                               corner_radius=6)
            row.pack(fill="x", pady=2)
            var = ctk.BooleanVar(value=False)      # DÉCOCHÉ par défaut (sécurité)
            self.clean_rowvars[slug] = var
            ctk.CTkCheckBox(row, text="", variable=var, width=24).pack(side="left", padx=(8, 0))

            # Drapeaux d'état lisibles d'un coup d'œil
            flags = []
            if v.get("is_draft"):
                flags.append("brouillon")
            if PodAPI.is_unencoded(v):
                flags.append("non-encodé")
            if v.get("is_restricted"):
                flags.append("restreint")
            suffix = f"   [{', '.join(flags)}]" if flags else ""

            title = (v.get("title") or "(sans titre)")[:64]
            ctk.CTkLabel(row, text=f"{title}   ·   {slug}{suffix}", anchor="w",
                         font=ctk.CTkFont(size=12)).pack(
                side="left", padx=8, pady=6, fill="x", expand=True)
            stat = ctk.CTkLabel(row, text="", width=24, font=ctk.CTkFont(size=12))
            stat.pack(side="right", padx=8)
            self.clean_rowlbls[slug] = stat

    def _clean_check_all(self, value: bool):
        """Coche ou décoche toutes les vidéos affichées."""
        for var in self.clean_rowvars.values():
            var.set(value)

    # ── Application de l'action (avec confirmations) ───────────────────────

    def _clean_apply(self):
        """Valide la sélection, confirme (double pour la suppression), puis applique."""
        if not self.api:
            self.clean_progress.configure(text="Connectez-vous d'abord.", text_color="#f59e0b")
            return
        label = self.clean_action.get()
        action = self._CLEAN_ACTIONS.get(label)
        # Vidéos cochées
        todo = [v for v in self.clean_filtered
                if self.clean_rowvars.get(v.get("slug"))
                and self.clean_rowvars[v.get("slug")].get()]
        if not todo:
            self.clean_progress.configure(text="Aucune vidéo cochée.", text_color="#f59e0b")
            return

        # Confirmation — renforcée pour la suppression définitive
        if action == "delete":
            if not messagebox.askyesno(
                    "⚠️  Suppression définitive",
                    f"Supprimer DÉFINITIVEMENT {len(todo)} vidéo(s) ?\n\n"
                    "Cette action est IRRÉVERSIBLE (il n'y a pas de corbeille sur Pod)."):
                return
            # Deuxième garde-fou
            if not messagebox.askyesno(
                    "Dernière confirmation",
                    f"Confirmez-vous la suppression de {len(todo)} vidéo(s) ?"):
                return
        else:
            if not messagebox.askyesno(
                    "Confirmer l'action",
                    f"Appliquer « {label} » à {len(todo)} vidéo(s) ?"):
                return

        # Désactiver le bouton pendant le traitement
        self.clean_apply_btn.configure(state="disabled")
        self._run(self._do_clean_apply, action, todo)

    def _do_clean_apply(self, action, todo):
        """(Thread) Applique l'action choisie à chaque vidéo cochée."""
        ok = fail = 0
        for i, v in enumerate(todo, 1):
            slug = v.get("slug", "")
            try:
                # Aiguillage selon l'action ; on met aussi à jour le cache local
                if action == "draft_on":
                    self.api.set_video_draft(v, True);        v["is_draft"] = True
                elif action == "draft_off":
                    self.api.set_video_draft(v, False);       v["is_draft"] = False
                elif action == "restrict_on":
                    self.api.set_video_restricted(v, True);   v["is_restricted"] = True
                elif action == "restrict_off":
                    self.api.set_video_restricted(v, False);  v["is_restricted"] = False
                elif action == "delete":
                    self.api.delete_video(v)
                    # Retirer du cache pour que les filtres suivants soient cohérents
                    if v in self.clean_videos:
                        self.clean_videos.remove(v)
                ok += 1
                self._ui(self._mark_clean_row, slug, True)
            except Exception as e:
                fail += 1
                self._ui(self._mark_clean_row, slug, False)
                self._ui(self._log, f"  ✗ {slug} : {e}")
            self._ui(self.clean_progress.configure,
                     text=f"⏳  {i}/{len(todo)}…", text_color="gray")

        # Bilan
        self._ui(self.clean_progress.configure,
                 text=f"Terminé : {ok} OK, {fail} échec(s).",
                 text_color="#22c55e" if not fail else "#f59e0b")
        self._ui(self._log,
                 f"Nettoyage « {self.clean_action.get()} » : {ok} OK, {fail} échec(s).")
        self._ui(self.clean_apply_btn.configure, state="normal")

    def _mark_clean_row(self, slug, success: bool):
        """Pose un ✔ (vert) ou ✗ (rouge) sur la ligne d'une vidéo traitée."""
        lbl = self.clean_rowlbls.get(slug)
        if lbl:
            lbl.configure(text="✔" if success else "✗",
                          text_color="#22c55e" if success else "#ef4444")

    # ═════════════════════════════════════════════════════════════════════
    #  ONGLET INVENTAIRE / STATISTIQUES (+ export Excel)
    # ═════════════════════════════════════════════════════════════════════
    #
    #  Lecture seule : on scanne toutes les vidéos (+ types + chaînes pour
    #  obtenir des libellés lisibles), on calcule des agrégats (totaux, par
    #  utilisateur / type / chaîne) et on peut exporter le tout en .xlsx.

    def _build_tab_stats(self):
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tabs["stats"] = frame

        ctk.CTkLabel(frame, text="📊  Inventaire / Statistiques",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            frame,
            text="Vue d'ensemble de l'instance : volumétrie, durées, répartition par "
                 "utilisateur, type et chaîne. Export possible vers un classeur Excel.",
            text_color="gray70", font=ctk.CTkFont(size=12),
            justify="left", wraplength=860).pack(anchor="w", pady=(0, 10))

        # — Ligne d'actions : scan + export —
        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkButton(top, text="📡  Scanner l'instance", fg_color="#2563eb",
                      hover_color="#1d4ed8", command=self._stats_scan).pack(side="left")
        self.stats_export_btn = ctk.CTkButton(
            top, text="📊  Exporter en Excel (.xlsx)", fg_color="#16a34a",
            hover_color="#15803d", state="disabled", command=self._stats_export)
        self.stats_export_btn.pack(side="left", padx=10)
        self.stats_status = ctk.CTkLabel(top, text="(aucun scan)", text_color="gray",
                                         font=ctk.CTkFont(size=11))
        self.stats_status.pack(side="left", padx=8)

        # — Bandeau de chiffres clés —
        self.stats_summary = ctk.CTkLabel(frame, text="", justify="left", anchor="w",
                                          font=ctk.CTkFont(size=13))
        self.stats_summary.pack(anchor="w", pady=(10, 6))

        # — Sélecteur de dimension pour la répartition —
        dim = ctk.CTkFrame(frame, fg_color="transparent")
        dim.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(dim, text="Répartition par :").pack(side="left", padx=(0, 4))
        self.stats_dim = ctk.CTkOptionMenu(
            dim, width=160, values=["Utilisateur", "Type", "Chaîne"],
            command=lambda _c: self._render_stats())
        self.stats_dim.set("Utilisateur")
        self.stats_dim.pack(side="left")

        # — Tableau de répartition —
        self.stats_table = ctk.CTkScrollableFrame(frame, label_text="Répartition")
        self.stats_table.pack(fill="both", expand=True, pady=(4, 0))

        # Données calculées (remplies après un scan)
        self.stats_videos = []     # scan complet
        self.stats_data = None     # agrégats (dict) ; None tant qu'aucun scan

    # ── Scan + calcul ──────────────────────────────────────────────────────

    def _stats_scan(self):
        if not self.api:
            self.stats_status.configure(text="Connectez-vous d'abord.", text_color="#f59e0b")
            return
        self.stats_status.configure(text="⏳  Scan en cours…", text_color="gray")
        self.stats_export_btn.configure(state="disabled")
        self._run(self._do_stats_scan)

    def _do_stats_scan(self):
        """(Thread) Récupère vidéos + types + chaînes, puis calcule les agrégats."""
        try:
            def prog(n):
                self._ui(self.stats_status.configure,
                         text=f"⏳  {n} vidéos lues…", text_color="gray")
            videos = self.api.get_all_videos(progress_cb=prog)

            # Cartes URL → libellé pour afficher des noms plutôt que des URLs
            try:
                type_by_url = {str(t.get("url", "")).rstrip("/"): t.get("title", "?")
                               for t in self.api.get_types()}
            except Exception:
                type_by_url = {}
            try:
                chan_by_url = {str(c.get("url", "")).rstrip("/"): c.get("title", "?")
                               for c in self.api.get_channels()}
            except Exception:
                chan_by_url = {}
            # Carte URL utilisateur → username (à partir des comptes déjà chargés)
            user_by_url = {str(u.get("url", "")).rstrip("/"): u.get("username", "?")
                           for u in (self.all_users or [])}

            self.stats_videos = videos
            self.stats_data = self._compute_stats(videos, user_by_url,
                                                  type_by_url, chan_by_url)
            self._ui(self._render_stats)
            self._ui(self.stats_status.configure,
                     text=f"✅  {len(videos)} vidéos analysées.", text_color="#22c55e")
            self._ui(self.stats_export_btn.configure, state="normal")
            self._ui(self._log, f"Inventaire : {len(videos)} vidéos analysées.")
        except Exception as e:
            self._ui(self.stats_status.configure, text=f"❌  {e}", text_color="#ef4444")
            self._ui(self._log, f"❌ Inventaire : {e}")

    @staticmethod
    def _fmt_duration(seconds) -> str:
        """Formate une durée en secondes → « 1h05m09s » ou « 5m09s »."""
        s = int(seconds or 0)
        h, m, sec = s // 3600, (s % 3600) // 60, s % 60
        return f"{h}h{m:02d}m{sec:02d}s" if h else f"{m}m{sec:02d}s"

    @staticmethod
    def _label_from_ref(ref, by_url, fallback="—"):
        """Libellé lisible d'une relation, qu'elle soit un dict, une URL ou autre."""
        if isinstance(ref, dict):
            return ref.get("title") or ref.get("username") or ref.get("url") or fallback
        if isinstance(ref, str):
            return by_url.get(ref.rstrip("/"), ref) if ref.startswith("http") else ref
        return fallback

    def _compute_stats(self, videos, user_by_url, type_by_url, chan_by_url) -> dict:
        """Calcule tous les agrégats (logique pure, testable sans interface)."""
        from collections import defaultdict
        total = len(videos)
        total_dur = sum(int(v.get("duration") or 0) for v in videos)
        drafts = sum(1 for v in videos if v.get("is_draft"))
        unencoded = sum(1 for v in videos if PodAPI.is_unencoded(v))
        restricted = sum(1 for v in videos if v.get("is_restricted"))

        by_owner = defaultdict(lambda: [0, 0])   # nom → [nombre, durée totale]
        by_type = defaultdict(int)               # type → nombre
        by_chan = defaultdict(int)               # chaîne → nombre
        rows = []                                # inventaire détaillé (pour l'export)

        for v in videos:
            owner = self._label_from_ref(v.get("owner"), user_by_url)
            dur = int(v.get("duration") or 0)
            by_owner[owner][0] += 1
            by_owner[owner][1] += dur

            tlabel = self._label_from_ref(v.get("type"), type_by_url)
            by_type[tlabel] += 1

            # channel = liste d'URLs (M2M) ; gérer aussi le cas chaîne unique / vide
            chans = v.get("channel") or []
            if isinstance(chans, str):
                chans = [chans]
            if not chans:
                by_chan["(aucune)"] += 1
            for c in chans:
                by_chan[self._label_from_ref(c, chan_by_url)] += 1

            rows.append({
                "Titre": v.get("title", ""),
                "Slug": v.get("slug", ""),
                "Propriétaire": owner,
                "Type": tlabel,
                "Brouillon": "oui" if v.get("is_draft") else "non",
                "Encodée": "oui" if v.get("encoded") else "non",
                "Restreinte": "oui" if v.get("is_restricted") else "non",
                "Durée (s)": dur,
                "Durée": self._fmt_duration(dur),
                "Ajoutée le": str(v.get("date_added", ""))[:10],
            })

        return {
            "total": total, "total_dur": total_dur, "drafts": drafts,
            "unencoded": unencoded, "restricted": restricted,
            "by_owner": dict(by_owner), "by_type": dict(by_type),
            "by_chan": dict(by_chan), "rows": rows,
        }

    # ── Rendu ──────────────────────────────────────────────────────────────

    def _render_stats(self):
        d = self.stats_data
        if not d:
            return
        # Chiffres clés
        self.stats_summary.configure(
            text=(f"📁  {d['total']} vidéos       "
                  f"⏱  {self._fmt_duration(d['total_dur'])} au total\n"
                  f"📝  {d['drafts']} brouillon(s)     "
                  f"⚙️  {d['unencoded']} non-encodée(s)     "
                  f"🔒  {d['restricted']} restreinte(s)"))

        # Tableau de répartition selon la dimension choisie
        for w in self.stats_table.winfo_children():
            w.destroy()

        dimension = self.stats_dim.get()
        if dimension == "Utilisateur":
            # [nombre, durée] → on trie par nombre décroissant
            items = sorted(d["by_owner"].items(), key=lambda kv: kv[1][0], reverse=True)
            self._stats_header(("Utilisateur", "Vidéos", "Durée"))
            for name, (cnt, dur) in items:
                self._stats_row((name, str(cnt), self._fmt_duration(dur)))
        else:
            src = d["by_type"] if dimension == "Type" else d["by_chan"]
            items = sorted(src.items(), key=lambda kv: kv[1], reverse=True)
            self._stats_header((dimension, "Vidéos", ""))
            for name, cnt in items:
                self._stats_row((name, str(cnt), ""))

    def _stats_header(self, cols):
        """Ligne d'en-tête du tableau (trois colonnes)."""
        row = ctk.CTkFrame(self.stats_table, fg_color="transparent")
        row.pack(fill="x", pady=(0, 2))
        widths = (360, 80, 120)
        for text, w in zip(cols, widths):
            ctk.CTkLabel(row, text=text, width=w, anchor="w",
                         font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=4)

    def _stats_row(self, cols):
        """Ligne de données du tableau."""
        row = ctk.CTkFrame(self.stats_table, fg_color=("gray85", "gray17"), corner_radius=4)
        row.pack(fill="x", pady=1)
        widths = (360, 80, 120)
        for text, w in zip(cols, widths):
            ctk.CTkLabel(row, text=text, width=w, anchor="w",
                         font=ctk.CTkFont(size=12)).pack(side="left", padx=4, pady=3)

    # ── Export Excel ───────────────────────────────────────────────────────

    def _stats_export(self):
        """Demande où enregistrer puis lance l'export en arrière-plan."""
        if not self.stats_data:
            return
        path = filedialog.asksaveasfilename(
            title="Exporter l'inventaire",
            defaultextension=".xlsx",
            filetypes=[("Classeur Excel", "*.xlsx")],
            initialfile=f"inventaire_pod_{datetime.now():%Y%m%d}.xlsx")
        if not path:        # annulé
            return
        self.stats_status.configure(text="⏳  Export…", text_color="gray")
        self._run(self._do_stats_export, path)

    def _do_stats_export(self, path):
        """(Thread) Construit le classeur Excel (plusieurs feuilles) et l'enregistre."""
        try:
            # openpyxl est importé ici pour ne pas bloquer le lancement de l'appli
            try:
                from openpyxl import Workbook
                from openpyxl.styles import Font
            except ImportError:
                self._ui(self.stats_status.configure,
                         text="❌  Module « openpyxl » manquant (pip install openpyxl).",
                         text_color="#ef4444")
                self._ui(self._log, "❌ Export Excel impossible : openpyxl non installé.")
                return

            d = self.stats_data
            wb = Workbook()
            bold = Font(bold=True)

            # Feuille 1 : Résumé (couples libellé / valeur)
            ws = wb.active
            ws.title = "Résumé"
            ws.append(["Indicateur", "Valeur"])
            for c in ws[1]:
                c.font = bold
            ws.append(["Vidéos (total)", d["total"]])
            ws.append(["Durée totale (s)", d["total_dur"]])
            ws.append(["Durée totale", self._fmt_duration(d["total_dur"])])
            ws.append(["Brouillons", d["drafts"]])
            ws.append(["Non-encodées", d["unencoded"]])
            ws.append(["Restreintes", d["restricted"]])

            # Feuille 2 : Par utilisateur
            ws = wb.create_sheet("Par utilisateur")
            ws.append(["Utilisateur", "Vidéos", "Durée (s)", "Durée"])
            for c in ws[1]:
                c.font = bold
            for name, (cnt, dur) in sorted(d["by_owner"].items(),
                                           key=lambda kv: kv[1][0], reverse=True):
                ws.append([name, cnt, dur, self._fmt_duration(dur)])

            # Feuille 3 : Par type
            ws = wb.create_sheet("Par type")
            ws.append(["Type", "Vidéos"])
            for c in ws[1]:
                c.font = bold
            for name, cnt in sorted(d["by_type"].items(), key=lambda kv: kv[1], reverse=True):
                ws.append([name, cnt])

            # Feuille 4 : Par chaîne
            ws = wb.create_sheet("Par chaîne")
            ws.append(["Chaîne", "Vidéos"])
            for c in ws[1]:
                c.font = bold
            for name, cnt in sorted(d["by_chan"].items(), key=lambda kv: kv[1], reverse=True):
                ws.append([name, cnt])

            # Feuille 5 : Inventaire détaillé (toutes les vidéos)
            ws = wb.create_sheet("Inventaire")
            if d["rows"]:
                headers = list(d["rows"][0].keys())
                ws.append(headers)
                for c in ws[1]:
                    c.font = bold
                for r in d["rows"]:
                    ws.append([r[h] for h in headers])

            wb.save(path)
            self._ui(self.stats_status.configure,
                     text=f"✅  Exporté : {os.path.basename(path)}", text_color="#22c55e")
            self._ui(self._log, f"Inventaire exporté → {path}")
        except Exception as e:
            self._ui(self.stats_status.configure, text=f"❌  {e}", text_color="#ef4444")
            self._ui(self._log, f"❌ Export inventaire : {e}")

    # ═════════════════════════════════════════════════════════════════════
    #  ONGLET CHAÎNES & THÈMES (création / modification / suppression)
    # ═════════════════════════════════════════════════════════════════════
    #
    #  Champs requis relevés au diagnostic :
    #    • Chaîne : title + themes (liste, vide acceptée)
    #    • Thème  : title + channel (URL)  ; hiérarchie possible via parentId
    #  Les thèmes sont regroupés sous leur chaîne grâce à leur champ `channel`.

    def _build_tab_ct(self):
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tabs["ct"] = frame

        ctk.CTkLabel(frame, text="🗂  Chaînes & thèmes",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            frame,
            text="Gérer les chaînes et leurs thèmes : créer, renommer, basculer la visibilité, "
                 "supprimer. Les thèmes apparaissent sous leur chaîne.",
            text_color="gray70", font=ctk.CTkFont(size=12),
            justify="left", wraplength=860).pack(anchor="w", pady=(0, 10))

        # — Ligne d'action : charger —
        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkButton(top, text="🔄  Charger", fg_color="#2563eb", hover_color="#1d4ed8",
                      command=self._ct_load).pack(side="left")
        self.ct_status = ctk.CTkLabel(top, text="(non chargé)", text_color="gray",
                                      font=ctk.CTkFont(size=11))
        self.ct_status.pack(side="left", padx=10)

        # — Liste des chaînes + thèmes —
        self.ct_list = ctk.CTkScrollableFrame(frame, label_text="Chaînes et thèmes")
        self.ct_list.pack(fill="both", expand=True, pady=(8, 6))

        # — Formulaire : nouvelle chaîne —
        cform = ctk.CTkFrame(frame)
        cform.pack(fill="x", pady=(2, 4))
        ctk.CTkLabel(cform, text="Nouvelle chaîne :",
                     font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(10, 6))
        self.ct_new_chan_title = ctk.CTkEntry(cform, placeholder_text="titre", width=180)
        self.ct_new_chan_title.pack(side="left", padx=4)
        self.ct_new_chan_desc = ctk.CTkEntry(cform, placeholder_text="description (option)", width=200)
        self.ct_new_chan_desc.pack(side="left", padx=4)
        self.ct_new_chan_visible = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(cform, text="visible", variable=self.ct_new_chan_visible).pack(side="left", padx=6)
        ctk.CTkButton(cform, text="＋ Créer", width=90, fg_color="#16a34a",
                      hover_color="#15803d", command=self._ct_create_channel).pack(side="left", padx=6, pady=6)

        # — Formulaire : nouveau thème —
        tform = ctk.CTkFrame(frame)
        tform.pack(fill="x", pady=(2, 0))
        ctk.CTkLabel(tform, text="Nouveau thème :",
                     font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(10, 6))
        self.ct_new_theme_title = ctk.CTkEntry(tform, placeholder_text="titre", width=180)
        self.ct_new_theme_title.pack(side="left", padx=4)
        ctk.CTkLabel(tform, text="dans la chaîne :").pack(side="left", padx=(6, 4))
        # Menu des chaînes cibles (rempli après chargement)
        self.ct_theme_channel = ctk.CTkOptionMenu(tform, width=200, values=["(charger d'abord)"])
        self.ct_theme_channel.pack(side="left", padx=4)
        ctk.CTkButton(tform, text="＋ Créer", width=90, fg_color="#16a34a",
                      hover_color="#15803d", command=self._ct_create_theme).pack(side="left", padx=6, pady=6)

        # Données
        self.ct_channels = []           # liste de chaînes (dicts)
        self.ct_themes = []             # liste de thèmes (dicts)
        self.ct_videos = []             # cache des vidéos (pour gérer l'appartenance)
        self.ct_channel_choices = {}    # titre de chaîne → URL (pour le menu thème)

    # ── Chargement ─────────────────────────────────────────────────────────

    def _ct_load(self):
        if not self.api:
            self.ct_status.configure(text="Connectez-vous d'abord.", text_color="#f59e0b")
            return
        self.ct_status.configure(text="⏳  Chargement…", text_color="gray")
        self._run(self._do_ct_load)

    def _do_ct_load(self):
        """(Thread) Récupère chaînes et thèmes, puis rafraîchit l'affichage.
        Peut être appelé depuis un autre thread (création/édition) pour recharger."""
        try:
            chans = self.api.get_channels()
            themes = self.api.get_themes()
            # Tri alphabétique pour un affichage stable
            self.ct_channels = sorted(chans, key=lambda c: (c.get("title") or "").lower())
            self.ct_themes = themes
            # Carte titre → URL pour le menu de création de thème
            self.ct_channel_choices = {c.get("title", "?"): c.get("url")
                                       for c in self.ct_channels}
            self._ui(self._render_ct)
            self._ui(self._refresh_ct_channel_menu)
            self._ui(self.ct_status.configure,
                     text=f"✅  {len(chans)} chaîne(s), {len(themes)} thème(s).",
                     text_color="#22c55e")
        except Exception as e:
            self._ui(self.ct_status.configure, text=f"❌  {e}", text_color="#ef4444")
            self._ui(self._log, f"❌ Chargement chaînes/thèmes : {e}")

    def _refresh_ct_channel_menu(self):
        """Met à jour la liste déroulante des chaînes (création de thème)."""
        titles = list(self.ct_channel_choices.keys())
        if titles:
            self.ct_theme_channel.configure(values=titles)
            self.ct_theme_channel.set(titles[0])
        else:
            self.ct_theme_channel.configure(values=["(aucune chaîne)"])
            self.ct_theme_channel.set("(aucune chaîne)")

    # ── Rendu de la liste (chaînes + thèmes imbriqués) ─────────────────────

    def _render_ct(self):
        for w in self.ct_list.winfo_children():
            w.destroy()

        if not self.ct_channels:
            ctk.CTkLabel(self.ct_list,
                         text="Aucune chaîne. Cliquez « Charger » ou créez-en une ci-dessous.",
                         text_color="gray").pack(pady=10)
            return

        # Regrouper les thèmes par URL de chaîne (champ `channel` du thème)
        from collections import defaultdict
        themes_by_chan = defaultdict(list)
        for t in self.ct_themes:
            themes_by_chan[str(t.get("channel", "")).rstrip("/")].append(t)

        for ch in self.ct_channels:
            curl = str(ch.get("url", "")).rstrip("/")

            # — Ligne de la chaîne —
            crow = ctk.CTkFrame(self.ct_list, fg_color=("gray80", "gray20"), corner_radius=6)
            crow.pack(fill="x", pady=(6, 0))
            vis = "👁" if ch.get("visible") else "🚫"
            ctk.CTkLabel(crow, text=f"{vis}  {ch.get('title', '(sans titre)')}",
                         anchor="w", font=ctk.CTkFont(size=13, weight="bold")).pack(
                side="left", padx=10, pady=6, fill="x", expand=True)
            # Actions de la chaîne
            ctk.CTkButton(crow, text="✏", width=34, fg_color="gray35",
                          command=lambda c=ch: self._ct_rename_channel(c)).pack(side="left", padx=2)
            ctk.CTkButton(crow, text="🎬 Vidéos", width=80, fg_color="gray35",
                          command=lambda c=ch: self._ct_manage_videos(c)).pack(side="left", padx=2)
            ctk.CTkButton(crow, text="👤 Admins", width=80, fg_color="gray35",
                          command=lambda c=ch: self._ct_manage_owners(c)).pack(side="left", padx=2)
            ctk.CTkButton(crow, text="👁/🚫", width=54, fg_color="gray35",
                          command=lambda c=ch: self._ct_toggle_visible(c)).pack(side="left", padx=2)
            ctk.CTkButton(crow, text="🗑", width=34, fg_color="#b91c1c", hover_color="#991b1b",
                          command=lambda c=ch: self._ct_delete_channel(c)).pack(side="left", padx=(2, 8))

            # — Thèmes de cette chaîne (indentés) —
            for t in themes_by_chan.get(curl, []):
                trow = ctk.CTkFrame(self.ct_list, fg_color="transparent")
                trow.pack(fill="x", padx=(28, 0))
                ctk.CTkLabel(trow, text=f"└  {t.get('title', '(sans titre)')}",
                             anchor="w", font=ctk.CTkFont(size=12)).pack(
                    side="left", padx=6, pady=2, fill="x", expand=True)
                ctk.CTkButton(trow, text="✏", width=34, height=24, fg_color="gray30",
                              command=lambda th=t: self._ct_rename_theme(th)).pack(side="left", padx=2)
                ctk.CTkButton(trow, text="🗑", width=34, height=24, fg_color="#7f1d1d",
                              hover_color="#991b1b",
                              command=lambda th=t: self._ct_delete_theme(th)).pack(side="left", padx=(2, 8))

    # ── Création ───────────────────────────────────────────────────────────

    def _ct_create_channel(self):
        title = self.ct_new_chan_title.get().strip()
        if not title:
            self.ct_status.configure(text="Titre de chaîne requis.", text_color="#f59e0b")
            return
        desc = self.ct_new_chan_desc.get().strip()
        visible = self.ct_new_chan_visible.get()
        self._run(self._do_ct_create_channel, title, desc, visible)

    def _do_ct_create_channel(self, title, desc, visible):
        try:
            # themes=[] : le champ est requis par l'API mais peut être vide
            self.api.create_channel(title, theme_urls=[], description=desc, visible=visible)
            self._ui(self._log, f"Chaîne créée : {title}")
            self._ui(self._ct_clear_new_channel)
            self._do_ct_load()      # recharge (on est déjà dans un thread)
        except Exception as e:
            self._ui(self.ct_status.configure, text=f"❌  {e}", text_color="#ef4444")
            self._ui(self._log, f"❌ Création chaîne : {e}")

    def _ct_clear_new_channel(self):
        self.ct_new_chan_title.delete(0, "end")
        self.ct_new_chan_desc.delete(0, "end")

    def _ct_create_theme(self):
        title = self.ct_new_theme_title.get().strip()
        if not title:
            self.ct_status.configure(text="Titre de thème requis.", text_color="#f59e0b")
            return
        channel_url = self.ct_channel_choices.get(self.ct_theme_channel.get())
        if not channel_url:
            self.ct_status.configure(text="Choisissez une chaîne pour le thème.",
                                     text_color="#f59e0b")
            return
        self._run(self._do_ct_create_theme, title, channel_url)

    def _do_ct_create_theme(self, title, channel_url):
        try:
            self.api.create_theme(title, channel_url)
            self._ui(self._log, f"Thème créé : {title}")
            self._ui(lambda: self.ct_new_theme_title.delete(0, "end"))
            self._do_ct_load()
        except Exception as e:
            self._ui(self.ct_status.configure, text=f"❌  {e}", text_color="#ef4444")
            self._ui(self._log, f"❌ Création thème : {e}")

    # ── Modification ───────────────────────────────────────────────────────

    def _ct_rename_channel(self, ch):
        dlg = ctk.CTkInputDialog(text=f"Nouveau nom pour « {ch.get('title')} » :",
                                 title="Renommer la chaîne")
        new = dlg.get_input()              # bloque jusqu'à fermeture ; None si annulé
        if new and new.strip():
            self._run(self._do_ct_patch, "channel", ch.get("url"),
                      {"title": new.strip()}, f"Chaîne renommée : {new.strip()}")

    def _ct_rename_theme(self, th):
        dlg = ctk.CTkInputDialog(text=f"Nouveau nom pour « {th.get('title')} » :",
                                 title="Renommer le thème")
        new = dlg.get_input()
        if new and new.strip():
            self._run(self._do_ct_patch, "theme", th.get("url"),
                      {"title": new.strip()}, f"Thème renommé : {new.strip()}")

    def _ct_manage_videos(self, ch):
        """Ouvre la gestion des vidéos d'une chaîne. Si la chaîne a des thèmes,
        propose de gérer la chaîne entière OU l'un de ses thèmes (Option 1).
        Scanne les vidéos au besoin (en arrière-plan)."""
        if not self.api:
            self.ct_status.configure(text="Connectez-vous d'abord.", text_color="#f59e0b")
            return
        self.ct_status.configure(text="⏳  Chargement des vidéos…", text_color="gray")
        self._run(self._do_ct_prepare_organizer, ch)

    def _do_ct_prepare_organizer(self, ch):
        """(Thread) Scanne les vidéos puis ouvre soit le sélecteur de chaîne
        (si aucun thème), soit le petit menu chaîne/thèmes."""
        try:
            if not self.ct_videos:
                self.ct_videos = self.api.get_all_videos()
            curl = str(ch.get("url", "")).rstrip("/")
            # Thèmes appartenant à CETTE chaîne (cohérence : on ne propose que ceux-là)
            themes = [t for t in self.ct_themes
                      if str(t.get("channel")).rstrip("/") == curl]
            self._ui(self.ct_status.configure,
                     text=f"{len(self.ct_videos)} vidéos chargées.", text_color="gray")
            if themes:
                self._ui(lambda: self._ct_organizer_dialog(ch, themes))
            else:
                # Pas de thème : on va directement au sélecteur de la chaîne entière
                self._ui(lambda: self._ct_open_channel_picker(ch))
        except Exception as e:
            self._ui(self.ct_status.configure, text=f"❌  {e}", text_color="#ef4444")
            self._ui(self._log, f"❌ Chargement vidéos (chaîne) : {e}")

    def _ct_organizer_dialog(self, ch, themes):
        """Petit menu : gérer les vidéos de la chaîne entière ou d'un de ses thèmes."""
        win = ctk.CTkToplevel(self)
        win.title(f"Organiser « {ch.get('title')} »")
        win.geometry("440x420")
        _focus_toplevel(win, self)

        ctk.CTkLabel(win, text=f"Chaîne : {ch.get('title')}",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(padx=16, pady=(16, 4), anchor="w")
        ctk.CTkLabel(win, text="Choisissez ce que vous voulez organiser :",
                     text_color="gray70", font=ctk.CTkFont(size=12)).pack(padx=16, anchor="w")

        # La chaîne entière (appartenance vidéo ↔ chaîne)
        row = ctk.CTkFrame(win, fg_color=("gray85", "gray17"), corner_radius=6)
        row.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(row, text="📁  La chaîne entière", anchor="w",
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=10, pady=8, fill="x", expand=True)
        ctk.CTkButton(row, text="Gérer", width=80,
                      command=lambda: (win.destroy(), self._ct_open_channel_picker(ch))
                      ).pack(side="right", padx=8)

        # Un bloc par thème de la chaîne
        ctk.CTkLabel(win, text="Thèmes (rubriques de la chaîne) :",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(padx=16, pady=(10, 2), anchor="w")
        holder = ctk.CTkScrollableFrame(win, height=200)
        holder.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        for t in themes:
            r = ctk.CTkFrame(holder, fg_color=("gray85", "gray17"), corner_radius=6)
            r.pack(fill="x", pady=2)
            ctk.CTkLabel(r, text=f"🏷  {t.get('title')}", anchor="w",
                         font=ctk.CTkFont(size=12)).pack(side="left", padx=10, pady=6,
                                                         fill="x", expand=True)
            ctk.CTkButton(r, text="Gérer", width=80,
                          command=lambda th=t: (win.destroy(),
                                                self._ct_open_theme_picker(ch, th))
                          ).pack(side="right", padx=8)

    def _videos_in_relation(self, field, url):
        """Dict {slug: titre} des vidéos dont le champ relation (`channel`/`theme`)
        contient l'URL donnée. Sert à pré-cocher le sélecteur."""
        target = str(url).rstrip("/")
        pre = {}
        for v in self.ct_videos:
            rel = v.get(field) or []
            if isinstance(rel, str):
                rel = [rel]
            urls = [str(x.get("url") if isinstance(x, dict) else x).rstrip("/") for x in rel]
            if target in urls:
                pre[v.get("slug")] = v.get("title", "?")
        return pre

    def _ct_open_channel_picker(self, ch):
        """Ouvre le sélecteur pour gérer l'appartenance à la chaîne entière."""
        pre = self._videos_in_relation("channel", ch.get("url"))
        VideoPicker(self, self.ct_videos,
                    on_done=lambda slugs: self._ct_apply_channel_videos(ch, slugs),
                    title=f"Vidéos de « {ch.get('title')} »", preselected=pre)

    def _ct_open_theme_picker(self, ch, theme):
        """Ouvre le sélecteur pour ranger des vidéos dans un thème de la chaîne."""
        pre = self._videos_in_relation("theme", theme.get("url"))
        VideoPicker(self, self.ct_videos,
                    on_done=lambda slugs: self._ct_apply_theme_videos(ch, theme, slugs),
                    title=f"Vidéos du thème « {theme.get('title')} »", preselected=pre)

    def _ct_apply_channel_videos(self, ch, selected_slugs):
        """Callback du sélecteur : applique les ajouts/retraits en arrière-plan."""
        self._run(self._do_ct_apply_channel_videos, ch, set(selected_slugs))

    def _do_ct_apply_channel_videos(self, ch, desired):
        """(Thread) Met le champ `channel` à jour sur chaque vidéo ajoutée ou retirée.
        On préserve les AUTRES chaînes de chaque vidéo (on n'ajoute/retire que celle-ci)."""
        curl = ch.get("url", "")
        curl_n = str(curl).rstrip("/")
        by_slug = {v.get("slug"): v for v in self.ct_videos}

        # Membres actuels de la chaîne (d'après le cache)
        current = set()
        for v in self.ct_videos:
            chans = v.get("channel") or []
            if isinstance(chans, str):
                chans = [chans]
            if curl_n in [str(c).rstrip("/") for c in chans]:
                current.add(v.get("slug"))

        to_add = desired - current        # à rattacher à la chaîne
        to_remove = current - desired     # à détacher de la chaîne
        ok = fail = 0

        for slug in (to_add | to_remove):
            v = by_slug.get(slug)
            if not v:
                continue
            chans = v.get("channel") or []
            if isinstance(chans, str):
                chans = [chans]
            chans = [str(c) for c in chans]
            chans_n = [c.rstrip("/") for c in chans]
            if slug in to_add and curl_n not in chans_n:
                chans.append(curl)                                     # ajout de cette chaîne
            if slug in to_remove:
                chans = [c for c in chans if c.rstrip("/") != curl_n]  # retrait
            try:
                # PATCH du champ channel (liste complète d'URLs) — préserve les autres
                self.api.assign_video_to_channels(v, chans)
                v["channel"] = chans                                   # MAJ cache local
                ok += 1
            except Exception as e:
                fail += 1
                self._ui(self._log, f"❌ {slug} : {e}")

        self._ui(self.ct_status.configure,
                 text=f"✅  Chaîne « {ch.get('title')} » : "
                      f"+{len(to_add)} / -{len(to_remove)} vidéo(s).",
                 text_color="#22c55e" if not fail else "#f59e0b")
        self._ui(self._log,
                 f"Chaîne « {ch.get('title')} » : {len(to_add)} ajout(s), "
                 f"{len(to_remove)} retrait(s), {fail} échec(s).")

    def _ct_apply_theme_videos(self, ch, theme, selected_slugs):
        """Callback du sélecteur de thème : applique les changements en arrière-plan."""
        self._run(self._do_ct_apply_theme_videos, ch, theme, set(selected_slugs))

    def _do_ct_apply_theme_videos(self, ch, theme, desired):
        """(Thread) Range les vidéos dans un thème (champ `theme`).
        GARDE-FOU DE COHÉRENCE : l'API n'empêche pas de mettre une vidéo dans un
        thème sans qu'elle soit dans la chaîne parente. On le corrige donc nous-
        mêmes : toute vidéo ajoutée à un thème est AUSSI ajoutée à la chaîne
        parente du thème si elle n'y est pas déjà. Le retrait d'un thème ne
        touche pas la chaîne (la vidéo reste dans la chaîne, hors rubrique)."""
        turl = theme.get("url", "")
        turl_n = str(turl).rstrip("/")
        curl = ch.get("url", "")
        curl_n = str(curl).rstrip("/")
        by_slug = {v.get("slug"): v for v in self.ct_videos}

        def norm(rel):
            """Normalise un champ relation en liste d'URLs (str)."""
            if not rel:
                return []
            if isinstance(rel, str):
                rel = [rel]
            return [str(x.get("url") if isinstance(x, dict) else x) for x in rel]

        # Membres actuels du thème (d'après le cache)
        current = set()
        for v in self.ct_videos:
            if turl_n in [u.rstrip("/") for u in norm(v.get("theme"))]:
                current.add(v.get("slug"))

        to_add = desired - current        # à ranger dans le thème
        to_remove = current - desired     # à sortir du thème
        ok = fail = forced = 0

        for slug in (to_add | to_remove):
            v = by_slug.get(slug)
            if not v:
                continue
            themes = norm(v.get("theme"))
            themes_n = [u.rstrip("/") for u in themes]
            chans = norm(v.get("channel"))
            chans_n = [u.rstrip("/") for u in chans]
            payload = {}

            if slug in to_add:
                if turl_n not in themes_n:
                    themes.append(turl)                       # ajout du thème
                    payload["theme"] = themes
                # COHÉRENCE : forcer l'appartenance à la chaîne parente
                if curl_n not in chans_n:
                    chans.append(curl)
                    payload["channel"] = chans
                    forced += 1
            if slug in to_remove:
                themes = [u for u in themes if u.rstrip("/") != turl_n]  # retrait du thème
                payload["theme"] = themes
                # On NE touche PAS à la chaîne au retrait (la vidéo y reste)

            if not payload:
                continue
            try:
                self.api.patch_video(v, payload)              # PATCH theme (+ channel si forcé)
                v.update(payload)                             # MAJ cache local
                ok += 1
            except Exception as e:
                fail += 1
                self._ui(self._log, f"❌ {slug} : {e}")

        msg = (f"✅  Thème « {theme.get('title')} » : "
               f"+{len(to_add)} / -{len(to_remove)} vidéo(s).")
        if forced:
            msg += f"  ({forced} ajoutée(s) aussi à la chaîne pour cohérence.)"
        self._ui(self.ct_status.configure,
                 text=msg, text_color="#22c55e" if not fail else "#f59e0b")
        self._ui(self._log,
                 f"Thème « {theme.get('title')} » : {len(to_add)} ajout(s), "
                 f"{len(to_remove)} retrait(s), {forced} forcé(s) en chaîne, {fail} échec(s).")

    def _ct_manage_owners(self, ch):
        """Ouvre un sélecteur de comptes pour gérer les ADMINISTRATEURS (owners)
        de la chaîne. Les owners sont des comptes individuels (pas des groupes)
        qui peuvent administrer la chaîne. Pré-coche les administrateurs actuels."""
        if not self.api:
            self.ct_status.configure(text="Connectez-vous d'abord.", text_color="#f59e0b")
            return
        if not self.all_users:
            self.ct_status.configure(text="⏳  Chargement des comptes…", text_color="gray")
            self._run(lambda: (self._reload_users_for_admin(),
                               self._ui(lambda: self._ct_open_owner_picker(ch))))
            return
        self._ct_open_owner_picker(ch)

    def _ct_open_owner_picker(self, ch):
        """Construit la pré-sélection (owners actuels) et ouvre OwnerPicker."""
        owners = ch.get("owners") or []
        if isinstance(owners, str):
            owners = [owners]
        # Table URL de compte → libellé lisible (à partir des comptes chargés)
        label_by_url = {str(u.get("url", "")).rstrip("/"): self._user_label(u)
                        for u in (self.all_users or [])}
        pre = {}
        for o in owners:
            ourl = o.get("url") if isinstance(o, dict) else o
            pre[ourl] = label_by_url.get(str(ourl).rstrip("/"), ourl)
        OwnerPicker(self,
                    on_done=lambda urls, labels: self._ct_apply_owners(ch, urls),
                    title=f"Administrateurs de « {ch.get('title')} »",
                    preselected=pre)

    def _ct_apply_owners(self, ch, urls):
        """Callback : applique la nouvelle liste d'administrateurs en arrière-plan."""
        self._run(self._do_ct_apply_owners, ch, list(urls))

    def _do_ct_apply_owners(self, ch, urls):
        """(Thread) PATCH du champ `owners` de la chaîne (liste d'URLs de comptes)."""
        try:
            self.api.patch_channel(ch.get("url"), {"owners": urls})
            ch["owners"] = urls                       # MAJ cache local
            self._ui(self.ct_status.configure,
                     text=f"✅  Chaîne « {ch.get('title')} » : "
                          f"{len(urls)} administrateur(s).", text_color="#22c55e")
            self._ui(self._log,
                     f"Chaîne « {ch.get('title')} » : {len(urls)} administrateur(s) défini(s).")
        except Exception as e:
            self._ui(self.ct_status.configure, text=f"❌  {e}", text_color="#ef4444")
            self._ui(self._log, f"❌ Administrateurs « {ch.get('title')} » : {e}")

    def _ct_toggle_visible(self, ch):
        # Inverse la visibilité de la chaîne
        new_val = not bool(ch.get("visible"))
        self._run(self._do_ct_patch, "channel", ch.get("url"),
                  {"visible": new_val},
                  f"Chaîne « {ch.get('title')} » → {'visible' if new_val else 'masquée'}")

    def _do_ct_patch(self, kind, url, payload, logmsg):
        """(Thread) PATCH générique sur une chaîne ou un thème, puis rechargement."""
        try:
            if kind == "channel":
                self.api.patch_channel(url, payload)
            else:
                self.api.patch_theme(url, payload)
            self._ui(self._log, logmsg)
            self._do_ct_load()
        except Exception as e:
            self._ui(self.ct_status.configure, text=f"❌  {e}", text_color="#ef4444")
            self._ui(self._log, f"❌ Modification {kind} : {e}")

    # ── Suppression (double confirmation) ──────────────────────────────────

    def _ct_delete_channel(self, ch):
        if not messagebox.askyesno(
                "⚠️  Supprimer la chaîne",
                f"Supprimer la chaîne « {ch.get('title')} » ?\n\n"
                "Ses thèmes seront supprimés. Les vidéos ne sont pas supprimées "
                "mais perdront ce classement."):
            return
        if not messagebox.askyesno("Dernière confirmation",
                                   "Confirmez-vous la suppression de cette chaîne ?"):
            return
        self._run(self._do_ct_delete, "channel", ch.get("url"), ch.get("title"))

    def _ct_delete_theme(self, th):
        if not messagebox.askyesno(
                "Supprimer le thème",
                f"Supprimer le thème « {th.get('title')} » ?"):
            return
        self._run(self._do_ct_delete, "theme", th.get("url"), th.get("title"))

    def _do_ct_delete(self, kind, url, label):
        """(Thread) DELETE d'une chaîne ou d'un thème, puis rechargement."""
        try:
            if kind == "channel":
                self.api.delete_channel(url)
            else:
                self.api.delete_theme(url)
            self._ui(self._log, f"{kind.capitalize()} supprimé(e) : {label}")
            self._do_ct_load()
        except Exception as e:
            self._ui(self.ct_status.configure, text=f"❌  {e}", text_color="#ef4444")
            self._ui(self._log, f"❌ Suppression {kind} : {e}")

    # ═════════════════════════════════════════════════════════════════════
    #  ONGLET JOURNAL
    # ═════════════════════════════════════════════════════════════════════

    def _build_tab_log(self):
        """Construit l'onglet Journal (zone de texte horodatée + bouton Effacer)."""
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tabs["log"] = frame
        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(top, text="📋  Journal", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(top, text="🗑 Effacer", width=100, fg_color="gray35",
                      hover_color="gray28", command=self._clear_log).pack(side="right")
        self.log_box = ctk.CTkTextbox(frame, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_box.pack(fill="both", expand=True)
        self.log_box.configure(state="disabled")
        self._log("Application démarrée.")

    def _log(self, msg: str):
        """Ajoute une ligne horodatée au journal."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{ts}]  {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _clear_log(self):
        """Vide le journal."""
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")


# ════════════════════════════════════════════════════════════════════════════
#  FENÊTRE : sélection de propriétaires additionnels
# ════════════════════════════════════════════════════════════════════════════

def _focus_toplevel(win, master=None):
    """Amène une fenêtre secondaire au premier plan, lui donne le focus et la
    rend modale (focus capturé jusqu'à fermeture). Corrige le cas où une
    CTkToplevel s'ouvre derrière la fenêtre principale.
    Les appels sont légèrement différés (after) car la fenêtre n'est pas encore
    dessinée à l'instant de sa création."""
    try:
        if master is not None:
            win.transient(master)          # la fenêtre reste au-dessus de son parent
    except Exception:
        pass
    win.lift()
    win.attributes("-topmost", True)        # passe au-dessus, le temps de s'afficher
    # On retire 'topmost' juste après (sinon elle resterait au-dessus de TOUTES
    # les applications), puis on capture le focus.
    win.after(150, lambda: (win.attributes("-topmost", False), win.focus_force()))
    win.after(200, lambda: win.grab_set())  # modale : bloque la fenêtre principale


class OwnerPicker(ctk.CTkToplevel):
    """Sélecteur multi-utilisateurs : même système que l'agent (liste + filtre + clic)."""

    def __init__(self, master: App, on_done, title="Propriétaires additionnels",
                 preselected: dict | None = None, single: bool = False, on_single=None):
        super().__init__(master)
        self.master_app = master
        self.on_done = on_done
        self.single = single
        self.on_single = on_single
        self.title(title)
        self.geometry("500x560")
        _focus_toplevel(self, master)
        self.selected: dict[str, str] = dict(preselected or {})   # url → libellé

        intro = ("Cliquez sur un utilisateur pour le choisir." if single else
                 "Cochez les comptes Pod à ajouter comme propriétaires\n"
                 "additionnels. Filtrez la liste puis cliquez pour (dé)cocher.")
        ctk.CTkLabel(self, text=intro, justify="left").pack(padx=14, pady=(14, 8), anchor="w")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=14)
        self.filter = ctk.CTkEntry(bar, placeholder_text="🔍 nom / identifiant…")
        self.filter.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.filter.bind("<KeyRelease>", lambda e: self._render())
        ctk.CTkButton(bar, text="🔄", width=40, command=self._reload).pack(side="left")

        self.count_lbl = ctk.CTkLabel(self, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self.count_lbl.pack(anchor="w", padx=14, pady=(4, 0))

        self.listbox = ctk.CTkScrollableFrame(self, height=320)
        self.listbox.pack(fill="both", expand=True, padx=14, pady=8)

        self.chosen_lbl = ctk.CTkLabel(self, text="Sélection : aucun", text_color="gray",
                                       wraplength=460, justify="left")
        self.chosen_lbl.pack(padx=14, anchor="w")

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=10)
        ctk.CTkButton(btns, text="Valider", fg_color="#16a34a", hover_color="#15803d",
                      command=self._validate).pack(side="right")
        ctk.CTkButton(btns, text="Annuler", fg_color="gray35", hover_color="gray28",
                      command=self.destroy).pack(side="right", padx=8)

        self.after(80, self._init_list)

    def _init_list(self):
        """Affiche la liste si les comptes sont déjà chargés, sinon déclenche un chargement."""
        if self.master_app.all_users:
            self._render()
            self._update_chosen()
        else:
            self.count_lbl.configure(text="⏳  Chargement des utilisateurs…")
            self._reload()

    def _reload(self):
        """(Thread) Charge la liste des comptes si nécessaire, puis rafraîchit l'affichage."""
        def work():
            try:
                if not self.master_app.all_users:
                    users = self.master_app.api.get_all_users()
                    users.sort(key=lambda u: (u.get("username") or "").lower())
                    self.master_app.all_users = users
                self.after(0, self._render)
                self.after(0, self._update_chosen)
            except Exception as e:
                self.after(0, lambda: self.count_lbl.configure(text=f"Erreur : {e}", text_color="#ef4444"))
        threading.Thread(target=work, daemon=True).start()

    def _label(self, u: dict) -> str:
        """Libellé lisible d'un compte."""
        return f"{u.get('username','?')} — {u.get('first_name','')} {u.get('last_name','')}".strip()

    def _render(self):
        """Affiche la liste filtrée (cases à cocher)."""
        flt = self.filter.get().strip().lower()
        for w in self.listbox.winfo_children():
            w.destroy()
        users = self.master_app.all_users
        if not users:
            ctk.CTkLabel(self.listbox, text="Liste non disponible.", text_color="gray").pack(pady=10)
            return
        matches = [u for u in users if not flt or flt in self._label(u).lower()]
        CAP = 300
        for u in matches[:CAP]:
            url = u.get("url", "")
            sel = url in self.selected
            if self.single:
                prefix = "   "
            else:
                prefix = "☑  " if sel else "☐  "
            ctk.CTkButton(self.listbox, text=prefix + self._label(u), anchor="w",
                          fg_color=("gray75", "gray30") if (sel and not self.single) else "transparent",
                          text_color=("gray10", "gray90"), hover_color=("gray75", "gray28"),
                          height=28, font=ctk.CTkFont(size=12),
                          command=lambda uu=u: self._toggle(uu)).pack(fill="x", pady=1)
        self.count_lbl.configure(text=f"{len(matches)} affiché(s) sur {len(users)} — "
                                      f"{len(self.selected)} sélectionné(s)", text_color="gray")
        if len(matches) > CAP:
            ctk.CTkLabel(self.listbox, text=f"… affinez le filtre ({len(matches) - CAP} de plus)",
                         text_color="gray").pack(pady=4)
        elif not matches:
            ctk.CTkLabel(self.listbox, text="Aucun résultat.", text_color="gray").pack(pady=8)

    def _toggle(self, u: dict):
        """Coche/décoche un compte (ou valide directement en mode sélection unique)."""
        if self.single:
            if self.on_single:
                self.on_single(u)
            self.destroy()
            return
        url = u.get("url", "")
        if not url:
            return
        if url in self.selected:
            del self.selected[url]
        else:
            self.selected[url] = self._label(u)
        self._render()
        self._update_chosen()

    def _update_chosen(self):
        """Met à jour le libellé récapitulant la sélection courante."""
        if self.selected:
            self.chosen_lbl.configure(text="Sélection : " + ", ".join(self.selected.values()),
                                      text_color="#22c55e")
        else:
            self.chosen_lbl.configure(text="Sélection : aucun", text_color="gray")

    def _validate(self):
        """Renvoie la sélection à l'appelant (on_done) puis ferme la fenêtre."""
        self.on_done(list(self.selected.keys()), list(self.selected.values()))
        self.destroy()


# ════════════════════════════════════════════════════════════════════════════


class VideoPicker(ctk.CTkToplevel):
    """Sélecteur multi-vidéos (recherche + cases à cocher).
    `videos` : liste de dicts {slug, title, …}. `on_done(slugs)` au Valider.
    `preselected` : dict {slug: titre} cochés au départ (membres actuels)."""

    def __init__(self, master, videos, on_done, title="Vidéos",
                 preselected: dict | None = None):
        super().__init__(master)
        self.on_done = on_done
        self.videos = videos or []
        self.selected: dict[str, str] = dict(preselected or {})   # slug → titre
        self.title(title)
        self.geometry("520x560")
        _focus_toplevel(self, master)

        ctk.CTkLabel(self, text="Cochez les vidéos à inclure dans la chaîne "
                                "(décochez pour les retirer).",
                     justify="left", wraplength=480).pack(padx=14, pady=(14, 8), anchor="w")

        self.filter = ctk.CTkEntry(self, placeholder_text="🔍 titre / slug…")
        self.filter.pack(fill="x", padx=14)
        self.filter.bind("<KeyRelease>", lambda e: self._render())

        self.listbox = ctk.CTkScrollableFrame(self, height=360)
        self.listbox.pack(fill="both", expand=True, padx=14, pady=8)

        self.chosen_lbl = ctk.CTkLabel(self, text="0 vidéo sélectionnée", text_color="gray")
        self.chosen_lbl.pack(padx=14, anchor="w")

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=10)
        ctk.CTkButton(btns, text="Valider", fg_color="#16a34a", hover_color="#15803d",
                      command=self._validate).pack(side="right")
        ctk.CTkButton(btns, text="Annuler", fg_color="gray35", hover_color="gray28",
                      command=self.destroy).pack(side="right", padx=8)

        self._render()
        self._update_chosen()

    def _render(self):
        """Affiche la liste filtrée des vidéos (cases à cocher)."""
        flt = self.filter.get().strip().lower()
        for w in self.listbox.winfo_children():
            w.destroy()
        matches = [v for v in self.videos
                   if not flt or flt in f"{v.get('title','')} {v.get('slug','')}".lower()]
        CAP = 500
        for v in matches[:CAP]:
            slug = v.get("slug", "")
            sel = slug in self.selected
            title = (v.get("title") or "(sans titre)")[:54]
            ctk.CTkButton(self.listbox, text=("☑  " if sel else "☐  ") + f"{title}  ·  {slug}",
                          anchor="w", height=26,
                          fg_color=("gray75", "gray30") if sel else "transparent",
                          text_color=("gray10", "gray90"), hover_color=("gray75", "gray28"),
                          font=ctk.CTkFont(size=12),
                          command=lambda vv=v: self._toggle(vv)).pack(fill="x", pady=1)
        if len(matches) > CAP:
            ctk.CTkLabel(self.listbox, text=f"… +{len(matches) - CAP} autres. Affinez le filtre.",
                         text_color="gray").pack(pady=4)
        elif not matches:
            ctk.CTkLabel(self.listbox, text="Aucune vidéo.", text_color="gray").pack(pady=8)

    def _toggle(self, v: dict):
        """Coche/décoche une vidéo dans la sélection."""
        slug = v.get("slug", "")
        if not slug:
            return
        if slug in self.selected:
            del self.selected[slug]
        else:
            self.selected[slug] = v.get("title", "?")
        self._render()
        self._update_chosen()

    def _update_chosen(self):
        """Met à jour le compteur de sélection."""
        n = len(self.selected)
        self.chosen_lbl.configure(
            text=f"{n} vidéo(s) sélectionnée(s)",
            text_color="#22c55e" if n else "gray")

    def _validate(self):
        """Renvoie la liste des slugs sélectionnés à l'appelant puis ferme."""
        self.on_done(list(self.selected.keys()))
        self.destroy()


class ChannelPicker(ctk.CTkToplevel):
    """Sélecteur multi-chaînes (sur le modèle d'OwnerPicker).
    `channels` : liste de dicts {url, title}. `on_done(urls, labels)` au Valider."""

    def __init__(self, master, channels, on_done, title="Chaînes",
                 preselected: dict | None = None):
        super().__init__(master)
        self.on_done = on_done
        self.channels = channels or []
        self.selected: dict[str, str] = dict(preselected or {})   # url → titre
        self.title(title)
        self.geometry("460x520")
        _focus_toplevel(self, master)

        ctk.CTkLabel(self, text="Cochez les chaînes où la vidéo doit apparaître.",
                     justify="left").pack(padx=14, pady=(14, 8), anchor="w")

        self.filter = ctk.CTkEntry(self, placeholder_text="🔍 titre…")
        self.filter.pack(fill="x", padx=14)
        self.filter.bind("<KeyRelease>", lambda e: self._render())

        self.listbox = ctk.CTkScrollableFrame(self, height=320)
        self.listbox.pack(fill="both", expand=True, padx=14, pady=8)

        self.chosen_lbl = ctk.CTkLabel(self, text="Sélection : aucune", text_color="gray",
                                       wraplength=420, justify="left")
        self.chosen_lbl.pack(padx=14, anchor="w")

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=10)
        ctk.CTkButton(btns, text="Valider", fg_color="#16a34a", hover_color="#15803d",
                      command=self._validate).pack(side="right")
        ctk.CTkButton(btns, text="Annuler", fg_color="gray35", hover_color="gray28",
                      command=self.destroy).pack(side="right", padx=8)

        self._render()
        self._update_chosen()

    def _render(self):
        """Affiche la liste filtrée (cases à cocher)."""
        flt = self.filter.get().strip().lower()
        for w in self.listbox.winfo_children():
            w.destroy()
        matches = [c for c in self.channels
                   if not flt or flt in (c.get("title", "")).lower()]
        for c in matches:
            url = c.get("url", "")
            sel = url in self.selected
            ctk.CTkButton(self.listbox, text=("☑  " if sel else "☐  ") + c.get("title", "?"),
                          anchor="w", height=28,
                          fg_color=("gray75", "gray30") if sel else "transparent",
                          text_color=("gray10", "gray90"), hover_color=("gray75", "gray28"),
                          font=ctk.CTkFont(size=12),
                          command=lambda cc=c: self._toggle(cc)).pack(fill="x", pady=1)
        if not matches:
            ctk.CTkLabel(self.listbox, text="Aucune chaîne.", text_color="gray").pack(pady=8)

    def _toggle(self, c: dict):
        """Coche/décoche une chaîne dans la sélection."""
        url = c.get("url", "")
        if not url:
            return
        if url in self.selected:
            del self.selected[url]
        else:
            self.selected[url] = c.get("title", "?")
        self._render()
        self._update_chosen()

    def _update_chosen(self):
        """Met à jour le libellé récapitulant la sélection courante."""
        if self.selected:
            self.chosen_lbl.configure(text="Sélection : " + ", ".join(self.selected.values()),
                                      text_color="#22c55e")
        else:
            self.chosen_lbl.configure(text="Sélection : aucune", text_color="gray")

    def _validate(self):
        """Renvoie la sélection à l'appelant (on_done) puis ferme la fenêtre."""
        self.on_done(list(self.selected.keys()), list(self.selected.values()))
        self.destroy()


# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()
