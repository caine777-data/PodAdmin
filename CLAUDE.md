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
| `app.py` | toute l'interface : classe `App` (~8 800 lignes, ~275 méthodes), 12 onglets |
| `pod_api.py` | client REST (jeton superutilisateur) |
| `pod_chunked.py` | envoi par morceaux via une session web du compte véhicule DEPOT ; indépendant de `pod_api.py` |
| `config.py` | réglages, seuils, compte DEPOT **embarqué en clair** |
| `maj.py` | lecture de `version.json` et `etat.json` (dépôt public) |
| `__version__.py` | source UNIQUE de la version |
| `tests/` | ~370 tests pytest |
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
- ⚠️ Les tests qui créent `App()` écrivent dans le VRAI Journal
  (`~/.podadmin/journal-AAAA-MM.log`) et lisent le vrai `~/.podadmin.json` :
  `os.environ.setdefault("HOME", …)` ne redirige rien sous Windows
  (`expanduser` y lit `USERPROFILE`). À corriger ; en attendant, ne pas prendre
  ces lignes du Journal pour de vrais événements (« 9.9.9 », « FausseAPI »…).
- Préférer des tests sur faux objets (`App.methode(SimpleNamespace(...))`) à une
  nouvelle instance `App()` : chaque instance aggrave le problème ci-dessus.

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

- `config.py` contient le mot de passe du compte **DEPOT** : dépôt `PodAdmin`
  **privé**, toujours. DEPOT doit rester local et sans privilège.
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

## Décisions déjà prises — ne pas reproposer

- Découpage d'`app.py` en modules : refusé pour l'instant (à revoir après l'ouverture aux enseignants).
- Refonte de la navigation en 5 espaces : refusée.
- Parallélisation des opérations par lot : refusée (charge sur la production).
- Ne pas « harmoniser » `create_type` / `create_discipline`, ni les couleurs du panneau de lot (`COULEURS_LOT`) : des tests les figent.

## Ouvert

Voir la fiche §7 : captures des tutoriels, sauvegarde JSON avant opération de
masse, listes de lecture, vocabulaire des tutoriels, notification de mise à jour
du Téléverseur. Plus : tests qui écrivent dans le vrai Journal, 404 d'encodage
après envoi par morceaux, marqueur visible dans le slug.
