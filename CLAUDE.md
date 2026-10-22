# PodAdmin — consignes pour Claude

Console d'administration Esup-Pod (Windows / macOS) de Cédric MONNA, service
MFCA, Université de Toulouse. Instance : **videos.utoulouse.fr**. Superutilisateur.

Ce fichier résume ce qu'il faut savoir AVANT de toucher au code. Le détail est
ailleurs, et fait foi :
- `README.md` : fonctionnement, conventions visuelles, pièges par thème ;
- `FICHE_REPRISE_PodAdmin.md` : méthode, pièges, décisions, historique (écrite en 1.5.1 : chiffres datés) ;
- `NOTE_lot1_audit.md` : audits précédents et leurs corrections ;
- `MISE_A_JOUR.md`, `BLOCAGE.md` : publication, mise à jour obligatoire, blocage à distance.

**Toujours répondre en français, accents compris. Commentaires en français, qui
expliquent le POURQUOI (surtout les pièges), pas le quoi.**

## Fichiers

| Fichier | Rôle |
|---|---|
| `app.py` | toute l'interface : classe `App` (~8 800 lignes, ~275 méthodes), 13 onglets ; en fin de fichier, `PanneauEnrichissement` et ses fenêtres (onglet « Enrichissement IA ») |
| `enrichissement/` | modules sans interface repris de SousTitreur : Aristote, découpage aux normes, projets, éditeur web local, journal des écritures ; données dans `~/.soustitreur` |
| `pod_api.py` | client REST (jeton superutilisateur) |
| `pod_chunked.py` | envoi par morceaux via une session web du compte véhicule DEPOT ; indépendant de `pod_api.py` |
| `config.py` | réglages, seuils, compte DEPOT et identifiants Aristote **embarqués en clair** |
| `maj.py` | lecture de `version.json` et `etat.json` (dépôt public) |
| `__version__.py` | source UNIQUE de la version |
| `tests/` | ~530 tests pytest |
| `verifier_*.py` | sondes autonomes, lecture seule, lancées par Cédric sur l'instance |

## Méthode (établie par l'expérience — s'y tenir)

- **Sonde avant développement.** Ne jamais supposer ce que l'API expose : écrire
  une sonde `verifier_*.py`, la faire lancer par Cédric, décider ensuite.
- **Tester le test.** Réintroduire volontairement le défaut et vérifier que le
  test échoue. Le faire dans une COPIE du projet (dossier temporaire), jamais
  dans le dépôt.
- **Vérifier avant d'affirmer.** Lire le code, pas sa mémoire ni un commentaire.
  Plusieurs défauts venaient de corrections appliquées à moitié.
- **Quand un test échoue, vérifier d'abord le test** (banc d'essai, minutage).
- Ne rien commiter ni pousser sans demande explicite de Cédric.

## Lancer les tests

```bash
PYTHONUTF8=1 python -m pytest tests/test_logique.py -q
```

- **Fichier par fichier sous Windows.** La suite complète en un seul processus
  plante sous Python 3.14 (poste de Cédric) : trop d'instances Tk cumulées
  (« Can't find a usable tk.tcl / init.tcl »). Ce n'est pas un défaut du code.
  La CI (`qualite.yml`) tourne sous Ubuntu, Python 3.12, xvfb.
- Échec connu et préexistant : `test_fenetres.py::TestLibellesDeFiltres::test_tient_en_fenetre_minimale`
  (largeur mesurée à 1 px sur ce poste). Des erreurs Tk intermittentes dans
  `TestSelectionMultiple` / `TestInfobulle` existent aussi avant toute modification.
- `tests/conftest.py` ISOLE toute la suite : dossier personnel temporaire
  (USERPROFILE et HOME : sous Windows, `expanduser` lit USERPROFILE) et coffre-fort
  vide (`keyring.backends.null`), donc aucune connexion réelle. Avant lui, les
  tests écrivaient dans le vrai Journal et se connectaient à la production avec
  le jeton de Cédric. Ne jamais contourner ce fichier ; `test_isolement.py` le garde.
  Les lignes « 9.9.9 » ou « FausseAPI » antérieures au 2026-10-04 dans le vrai
  Journal viennent des tests, pas d'événements réels.
- Préférer des tests sur faux objets (`App.methode(SimpleNamespace(...))`) à une
  nouvelle instance `App()` : chaque instance aggrave le cumul Tk ci-dessus.

## Publier une version

1. Mettre à jour `__version__.py`, `version.txt` (4 endroits), la ligne « Version » du `README.md`.
   `AppVersion` de l'installeur est lu automatiquement (test le garantit).
2. Pousser. Puis Cédric : Actions → **Build installers** → Run workflow →
   champ **version** = `OUI` (vide = compilation d'essai).
3. **obligatoire** décoché par défaut. Coché, il BLOQUE tous les postes plus
   anciens (voir `MISE_A_JOUR.md`). Un poste trop ancien pour connaître ce
   mécanisme ne verra qu'un bandeau : seule une mise à jour manuelle le rattrape.
4. Champ **blocage** (bloquer / débloquer / ne rien changer par défaut) :
   interrupteur indépendant, ne compile rien (`BLOCAGE.md`).
5. Workflows en `contents: read`. Si la Release échoue en 403, remettre
   `contents: write` au job `release` (retiré en 1.9.1, jamais vérifié depuis).

## Sécurité — non négociable

- `config.py` contient le mot de passe du compte **DEPOT** et les identifiants
  **Aristote** (ce compte peut supprimer des enrichissements) : dépôt `PodAdmin`
  **privé**, toujours. DEPOT doit rester local et sans privilège. Ne jamais
  recopier ces valeurs dans une réponse ; les copier par script.
- Dépôt **public** `podadmin-releases` : binaires PodAdmin + `version.json` +
  `etat.json`. **Jamais le Téléverseur** (son binaire contient aussi DEPOT).
- Le jeton superutilisateur ne part que vers l'instance, en https :
  `PodAPI._abs()` refuse tout autre hôte. **Tout appel HTTP porteur du jeton
  doit passer par `_abs()`**, y compris les liens `next` de pagination.
  Les médias se téléchargent SANS jeton (`telecharger_media`).
- Pas d'adresse personnelle dans les fichiers livrés : `support-pod@utoulouse.fr`.

## Envoi de vidéos — ce qui a coûté cher

- Seuil de bascule : `CHUNK_THRESHOLD_BYTES` = **150 Mo** (`config.py`). Ce qui
  fait échouer un envoi direct est sa DURÉE (nginx coupe vers 1 min), pas sa
  taille : repli automatique sur les morceaux si coupure (`_est_coupure_reseau`).
- Par morceaux, la vidéo naît au nom de DEPOT puis est réattribuée par PATCH.
  Un échec de réattribution est signalé en rouge, jamais en silence.
- **Après une coupure de finalisation, ne JAMAIS retrouver la vidéo par son nom
  de fichier** : DEPOT est partagé avec le Téléverseur. Chaque envoi porte un
  marqueur unique (`pa` + 12 hex) dans son nom → titre provisoire → retrouvé par
  `_verify_chunked_creation`. Plusieurs correspondances : refus. Le marqueur est
  écrit au Journal. Effet de bord connu : il reste dans le SLUG de la vidéo.
- **504** : Pod continue → attente jusqu'à 30 min. **502 / 503** : Pod a échoué
  → attente de 3 min (`CHUNK_VERIFY_TIMEOUT_502_S`).
- 🛑 Interrompre (onglet Téléversement, `depot_interrompu`) coupe aussi la
  vidéo en cours : bloc par bloc, morceau par morceau, pendant l'attente
  post-504. Arrêt pendant l'attente → élément « à vérifier », jamais renvoyé
  seul (doublon possible). Distinct de `lot_interrompu` (onglet Vidéos).
- Liste de téléversement pendant un lot (`depot_en_cours`) : AJOUTER est permis
  (la boucle `_do_batch_upload` parcourt la liste vivante par index), RETIRER
  est interdit (un retrait décalait les index et sautait une vidéo en silence).
  `deposes_session` (mémoire de session) fait confirmer le renvoi d'un fichier
  déjà envoyé ; chemins comparés via `_cle_fichier` (écritures différentes sous Windows).
- Délai des envois : `UPLOAD_TIMEOUT = (30, 600)`, jamais `timeout=None`.
- Position des morceaux : l'offset annoncé par le serveur doit valoir `end + 1`.
- « Encodage non lancé … HTTP 404 » après un envoi par morceaux : constaté dès
  août 2026, non élucidé.

## Enrichissement IA (SousTitreur fusionné en 1.10.0, refondu en 1.11.0)

Détail dans le README, rubrique « Enrichissement IA ».

- Pas d'ffmpeg : une vidéo du poste part entière. Limite
  `reglages.LIMITE_ENVOI_OCTETS` (780 Mo) tirée de la sonde
  `verifier_ilaas_taille.py` (ILaaS refuse vers 811 Mo). Ne jamais l'écrire en
  dur dans un texte (test). Ne rien réimporter qui demande ffmpeg (test).
- Règles métier à ne pas « améliorer » : correction toujours en « fr »,
  remplacement d'une piste seulement sur demande avec sauvegarde préalable,
  métadonnées champ par champ, discipline jamais retirée, quiz en GIFT.
- Erreurs vers la page de l'éditeur : `message_editeur(e)` ; chaque écriture
  sur Pod va au Journal (`journal_hote`) et à `journal_pod.jsonl`.
- Trois parties, UNE demande Aristote par partie (`lancer_demande`). Ne pas
  revenir à une demande groupée. Les notes de cours d'Aristote sont écartées
  (gabarit « réunion ») : décision de Cédric.
- Page de l'éditeur : un résultat se repère à sa VERSION (`versions`), et la
  page n'écrase jamais ce qu'Aristote a livré (`fusionner_page`). Un banc
  Node exécute les vraies fonctions de la page (`test_page_editeur.py`).
- Onglet : `cartes_ia` (fonction pure) décide pastilles et boutons ; un seul
  bouton coloré par écran (`carte_principale_ia`).
- Audit 1.11.1 : une coupure pendant l'attente n'est plus un échec
  (`est_passagere`, tolérance de 15 min, demande « reprenable » : Réessayer
  reprend le suivi sans renvoyer). Les envois POST ne sont JAMAIS rejoués.
- La page interroge `/etat` (~400 octets) et ne relit le bloc complet que si
  une version change. Lecture et remplacement des projets sous
  `_VERROU_FICHIERS` : sous Windows, os.replace échoue tant qu'un autre fil
  lit le fichier (reproduit à six fils).
- SousTitreur autonome (Téléchargements\SousTitreur) est GELÉ en 0.6.1 : les
  corrections se font ici, plus là-bas.

## Pièges d'interface (liste complète : README et fiche §3)

- Jamais de widget Tk lu ou modifié depuis un thread : lire dans le thread
  principal, passer en argument, revenir par `self._ui(...)`.
- Magasin de vidéos UNIQUE `self.videos` (`ensure_videos` / `ensure_videos_sync`) ;
  toute modification passe par `_sync_video_caches` ; aucun appel direct à
  `get_all_videos()` ailleurs (test statique).
- Cible d'une action de lot : `_browse_videos_multi()` (filtrées ∩ cochées), seule définition.
- Couleurs : constantes sémantiques en couples (clair, sombre), jamais d'hexa
  dans un widget. Contraste ≥ 4,5:1 calculé par test.
- Un `CTkFrame` vide / transparent = carré noir sur macOS : créer au moment d'afficher.
- Fenêtre de blocage : jamais de boucle `focus_force` (Alt+F4 inopérant),
  toujours une issue « Quitter ».
- Exception montrée à l'utilisateur : `message_utilisateur(e)` / `self._signaler(...)`, jamais `str(e)` brut.
- `bind_all` agit aussi dans les champs : `_saisie_active()` d'abord.
- Relations de l'API (owner, channel…) : URL ou objet → `App._rel_urls()`.
- Vidéo désignée par son URL ou son id, pas son slug (`/videos/<slug>/` peut répondre 404).
- Navigation : elle DÉFILE en 1180×760 depuis l'onglet Enrichissement IA
  (décision de Cédric) ; Aide et À propos restent épinglés. Toute entrée doit
  rester dans la zone défilante (test).
- Onglet Enrichissement IA : construit à la PREMIÈRE ouverture
  (`_enrich_construire`) ; la reprise du suivi Aristote passe par
  `_auto_loaders` (PodAdmin connecté) ; le serveur de l'éditeur ne démarre
  qu'au premier « Corriger ». Ne rien y ajouter qui travaille au démarrage.
- CustomTkinter 6 : un `CTkScrollableFrame` ne descend pas sous ~212 px de
  haut, quel que soit `height`. Agrandir la fenêtre plutôt que réduire le cadre.

## Décisions déjà prises — ne pas reproposer

- Découpage d'`app.py` en modules : refusé pour l'instant (à revoir après l'ouverture aux enseignants).
- Refonte de la navigation en 5 espaces : refusée.
- Parallélisation des opérations par lot : refusée (charge sur la production).
- Ne pas « harmoniser » `create_type` / `create_discipline`, ni les couleurs du panneau de lot (`COULEURS_LOT`) : des tests les figent.

## Ouvert

Voir la fiche §7 : captures des tutoriels, sauvegarde JSON avant opération de
masse, listes de lecture, vocabulaire des tutoriels, notification de mise à jour
du Téléverseur. Plus : 404 d'encodage
après envoi par morceaux, marqueur visible dans le slug.

## Liste de l'onglet Vidéos (1.12.0)

- `ttk.Treeview` (`browse_tree`, thème ttk « clam », style `Pod.Treeview`)
  au lieu d'un CTkButton par vidéo : 300 boutons = 7 à 8 s par filtrage sur
  ~600 vidéos, le Treeview affiche tout en 0,05 s. Plus de plafond à 300.
- Sélection native coupée (`selectmode="none"`) : sélection simple et
  multiple gardent leur logique ; teintes par UNE étiquette par ligne
  (`multi` > `courante` > `alt`/`pair`, voir `_browse_teinte`).
- Couleurs simples seulement : `_browse_styler_liste` choisit la teinte du
  mode actif, rappelée par `_basculer_theme`.
- Propriétaire via `_index_proprietaires` (reconstruit si `all_users` est
  remplacée), plus de parcours vidéos × comptes à chaque frappe.
- 1.13.0 : composant commun `ListeNative` (+ `styler_tableaux`,
  `enregistrer_tableau`) pour toutes les longues listes : agent déposant,
  sélecteurs de Réaffectation, OwnerPicker, VideoPicker (un clic ne met à
  jour que sa ligne), Encodage (`multi=True` : sélection puis « Relancer la
  sélection », double-clic = une vidéo), Comptes (liste + fiche à droite,
  actions libellées). Plus aucun plafond d'affichage.
- Filtres de l'onglet Vidéos en pastilles (`PastilleFiltre`, même interface
  qu'un CTkOptionMenu : get, set, configure(values=…) ; 1re valeur = neutre)
  dans une `RangeeFluide` (passage à la ligne par `pack(in_=…)`). Recherche
  seule en haut. Tri sans menu (`browse_tri` = `ValeurSimple`, réglé par les
  en-têtes). « Anomalies » remplace Détecter + case mois (`ANOMALIES_VIDEOS`).
- Panneau de détail de l'onglet Vidéos construit UNE fois puis rempli
  (`_browse_construire_detail` / `_browse_remplir_detail`, refs dans
  `_detail_w`) : 0,6 s → 0,08 s par clic. Toute commande du panneau lit
  `self.browse_selected` au clic, jamais une vidéo capturée. Reconstruit
  après l'état vide, le panneau de lot, ou si `access_groups` change.
