# PodAdmin & Pod Téléverseur — fiche de reprise

> Document de passation, à fournir au démarrage d'une nouvelle discussion (ici
> ou dans Claude Code) pour reprendre le travail sans tout réexpliquer.
>
> **État au moment de la rédaction** : PodAdmin **1.5.1**, Pod Téléverseur **2.0.1**.
> 12 onglets · 107 tests · documentation 100 % · 18 sondes.

---

## 1. Le contexte en dix lignes

Cédric MONNA (service e-formation / MFCA, Université de Toulouse) développe et
maintient une suite d'outils autour de l'instance Esup-Pod
**videos.utoulouse.fr** (Pod v4).

- **PodAdmin** — console d'administration (Windows/macOS), 12 onglets.
- **Pod Téléverseur** — outil enseignant, dépôt par lot. Versions 2.x et 3.x.
- Dépôts GitHub, compte **caine777-data** : `PodAdmin` (privé),
  `PodTeleverseur-2.0`, `podadmin-releases` (public, binaires + `version.json`).
- Collègues : **Philippe BAQUÉ**, **Michel JACOB**, **Marie PHILIPOT**.
- Support : `support-pod@utoulouse.fr`.

**La plateforme n'est pas encore ouverte aux enseignants.** C'est important pour
interpréter les chiffres : peu de vues, peu de listes de lecture, c'est normal.

---

## 2. Méthode de travail établie

Ces règles ont émergé de l'expérience ; s'y tenir évite de refaire les mêmes
erreurs.

**Sonde avant développement.** Ne jamais supposer ce que l'API expose : écrire
un script autonome (`verifier_*.py`) qui interroge l'instance, le faire lancer
par Cédric, décider ensuite. Cette méthode a évité deux développements inutiles
(statistiques d'encodage, onglet Co-auteurs) et corrigé deux intuitions fausses.

**Tester le test.** À plusieurs reprises, un test passait alors que le bug était
présent — contenu d'essai trop pauvre, minutage fantaisiste. Systématiquement :
réintroduire volontairement le défaut et vérifier que le test échoue.

**Vérifier avant d'affirmer.** Lire le code plutôt que se fier à sa mémoire.
Plusieurs « bugs » signalés étaient en fait des fonctions existantes mal
trouvées, et plusieurs « corrections » ont révélé que le problème était ailleurs.

**Livrables clés en main.** ZIP complet prêt à pousser, jamais de fragments.
Code abondamment commenté **en français**, en expliquant le *pourquoi* (surtout
les pièges) et non le *quoi*.

**Validation systématique** avant livraison : `ast.parse`, instanciation sous
`xvfb`, `pytest`, et capture d'écran quand l'aspect visuel compte.

---

## 3. Pièges rencontrés — à ne pas réintroduire

| Piège | Conséquence | Règle |
|---|---|---|
| Comparer un statut par égalité (`== "terminé"`) | l'émoji `✅` faisait échouer le test → tout le lot réenvoyé | utiliser un booléen (`it.done`), jamais le libellé affiché |
| `CTkFrame` vide | occupe **200 px** par défaut ; transparent + hauteur 0 = **carré noir sur macOS** | ne créer le widget qu'au moment de l'afficher |
| Fenêtre à taille fixe | contenu tronqué, bouton inaccessible | `tests/test_fenetres.py` compare hauteur requise et déclarée |
| `urllib` dans un exécutable macOS | échec TLS silencieux | utiliser `requests`, collecter `certifi` au build |
| `zip` sur un `.app` | signature cassée → « application endommagée » | `ditto` + `codesign --force --deep --sign -` |
| Échec silencieux | panne indiagnosticable | toujours tracer dans le Journal |
| Relations API (`channel`, `owner`…) | tantôt URL, tantôt objet imbriqué | passer par `App._rel_urls()` |
| Supprimer un bloc de code | emporte des méthodes utilisées ailleurs | vérifier les références **avant**, tester **après** |
| Fenêtre à taille fixe, en LARGEUR | 485 px tronqués : tri et filtres invisibles | tester la largeur autant que la hauteur, à la taille MINIMALE |
| Drapeau d'état sur un objet partagé | un scan concurrent efface l'alerte d'un autre | état **par ressource**, jamais global |
| Correction appliquée à moitié | le commentaire dit une chose, le code une autre | relire le code après, pas seulement le commentaire |
| Test qui partage une instance | passe seul, échoue dans la suite | préparer un état de départ explicite |

---

## 4. Architecture

### PodAdmin (`app.py`, ~7 570 lignes)

**12 onglets** : Téléversement, Encodage, Comptes, Vidéos, Réaffectation,
Inventaire, Chaînes, Groupes d'accès, Configuration, Aide, Journal, À propos.

L'ancien **Explorateur** a été fusionné dans l'onglet Vidéos (ses filtres de
détection, la sélection globale et la suppression en masse s'y trouvent), et
l'onglet **Co-auteurs** supprimé (aucun contributeur sur l'instance).

**Magasin de vidéos partagé** — `self.videos` est la source unique, alimentée
par `ensure_videos()` (asynchrone, gère la concurrence) ou `ensure_videos_sync()`
(depuis un thread). Un verrou `_videos_lock` protège les écritures. Chaque onglet
en garde une **projection filtrée** (`browse_filtered`) qu'il faut recalculer
après toute mutation — d'où `_refresh_video_views()` et `schedule_refresh()`
(différé de 1,5 s, ce qui regroupe les rafraîchissements d'un lot).

**Point d'accroche unique** : toute modification de vidéo passe par
`_sync_video_caches()`, toute modification de chaîne par `_do_ct_load()`. Ces
deux fonctions déclenchent le rafraîchissement — ne pas ajouter d'appels
dispersés ailleurs.

Les **cinq** onglets à liste passent par le magasin : un seul scan réseau les
alimente tous. Un test statique vérifie qu'aucun ne réintroduit d'appel direct
à `get_all_videos()`.

Une **CRÉATION** est le seul cas imposant une relecture serveur : après un
dépôt, `_recharger_apres_depot()` relit l'instance — une vidéo nouvelle ne peut
pas se déduire de ce qu'on a en mémoire.

**Palette** : les couleurs passent par des constantes sémantiques en tête de
`app.py` (`C_ACTION`, `C_SUCCES`, `C_ALERTE`, `C_ERREUR`, `C_DESTRUCTIF`,
`C_NEUTRE`, `C_ACCENT`). Chacune est un COUPLE (clair, sombre) : c'est ce qui
rend la bascule de thème possible. **Ne jamais réintroduire de couleur en
hexadécimal dans un appel de widget** — un test le vérifie.

**Téléversement des gros fichiers** — au-delà de `CHUNK_THRESHOLD_BYTES`
(150 Mo), envoi par morceaux via une session web du compte véhicule **DEPOT**,
puis réattribution au propriétaire choisi. En cas de coupure de l'envoi direct
(erreur SSL de la passerelle), repli automatique sur cette voie
(`_est_coupure_reseau` distingue une coupure d'un refus métier).

**Version** — source unique dans `__version__.py`, lue automatiquement par le
workflow. `version.txt` et `AppVersion` (installeur) sont à mettre à jour en
parallèle : ils ne peuvent pas importer de Python.

### Fichiers

```
app.py            interface (12 onglets)
pod_api.py        client REST Esup-Pod
pod_chunked.py    envoi par morceaux (session web)
config.py         réglages, seuils, compte DEPOT embarqué
maj.py            vérification de mise à jour
__version__.py    source unique de la version
tests/            84 tests (logique pure + dimensions de fenêtres)
verifier_*.py     sondes de diagnostic autonomes
```

---

## 5. Points de sécurité

- Le mot de passe du compte **DEPOT** est **en clair** dans `config.py` de
  PodAdmin et du Téléverseur → **les dépôts de code doivent rester PRIVÉS**.
  DEPOT doit rester un compte **local et sans privilège**.
- Le dépôt **`podadmin-releases` est public** : il ne contient que les binaires
  de PodAdmin (aucun secret) et `version.json`.
  ⚠️ **Ne jamais y publier le Téléverseur** : son exécutable contient le mot de
  passe DEPOT.
- Le jeton d'administration est stocké dans le coffre-fort de l'OS ; un
  avertissement s'affiche si l'application bascule sur le fichier de repli.
- Journal persistant : `~/.podadmin/journal-AAAA-MM.log`.

---

## 6. Publication d'une version

1. Mettre à jour `__version__.py`, `version.txt`, `AppVersion` dans
   `build.yml`, `README.md`, `version.json`.
2. Pousser (GitHub Desktop).
3. GitHub → **Actions** → *Build installers* → **Run workflow** :
   - champ **version** rempli → publie (Release + `version.json` sur le dépôt
     public, notification aux postes installés) ;
   - champ **vide** → compilation d'essai, aucune publication.

Le numéro publié est **lu dans le code**, pas dans le formulaire : impossible
qu'ils divergent.

---

## 7. Ce qui reste ouvert

### Décisions en attente (elles bloquent du développement)

- **Disciplines et catégories** — les deux tables sont VIDES. Ce sont des
  classements d'établissement (à ne pas confondre avec les listes de lecture,
  qui sont personnelles). Les créer suppose de les faire remonter dans l'onglet
  Vidéos (filtre, champ de détail, action groupée) et dans le Téléverseur.
  **À trancher avec Philippe et Michel, AVANT l'ouverture** : rattacher des
  centaines de vidéos après coup serait bien plus lourd. Développer avant la
  décision reviendrait à construire pour une nomenclature qui changera.
- **Copyright** — `© Copyright 2026 Cédric MONNA` est en place. Reste à décider
  si l'adresse personnelle y figure. Réserve émise : elle serait visible de tous
  les utilisateurs et extractible du binaire.

### Développements envisagés, par ordre d'intérêt

1. **Captures d'écran des tutoriels** — le tutoriel Word et les tutoriels HTML
   Moodle montrent une interface qui n'existe plus (14 onglets, ancienne
   palette, filtres sur une rangée). Peu gratifiant, mais c'est ce qui a le plus
   d'impact avant l'ouverture : un tutoriel décalé de la réalité fait perdre
   confiance.
2. **Sauvegarde avant opération de masse** — écrire un fichier JSON de l'état
   antérieur (propriétaire, statut, chaînes) avant une action sur des centaines
   de vidéos. Ne défait rien automatiquement, mais permet de savoir exactement
   ce qui a été modifié.
3. **Listes de lecture** — 24 sur l'instance, dont plusieurs « Favorites » vides
   créées automatiquement par Pod. Onglet de consultation envisagé ; peu
   d'intérêt avant que les enseignants s'en servent.
4. **Vocabulaire des tutoriels** — le tutoriel Word parle encore de « jeton » et
   « Token » ; le mail et le Téléverseur disent « clé d'activation ».
5. **Notification de mise à jour pour le Téléverseur** — attention : son binaire
   contient le mot de passe DEPOT, donc **pas de dépôt public de binaires**.
   Formule recommandée : un dépôt public ne contenant QUE `version.json`, le
   bouton de téléchargement renvoyant vers la page Moodle.

### Écarté après vérification par sonde

| Piste | Raison |
|---|---|
| Diagnostic d'encodage | 0 anomalie réelle sur 79 vidéos |
| Onglet Co-auteurs | 0 contributeur → onglet supprimé |
| Chapitrage | 28 chapitres, probablement tous les tutoriels internes |
| Enrichissements, incrustations, documents, enregistrements | ressources vides |
| Page d'accueil | hors API (réglage serveur) → boutons de renvoi vers l'admin |
| Statut du jeton dans l'onglet Comptes | jetons non exposés : ni ressource REST, ni champ sur `/users/`, ni admin lisible. Le bouton garde son comportement — mémoriser localement donnerait une information trompeuse (jetons créés ailleurs ou avant) |
| Statistiques de consultation | **réalisé** — module en place, prendra de la valeur avec l'usage |

### À savoir pour plus tard

- `/rest/users/` expose un champ **`groups`** (groupes Django, 3 sur l'instance).
  Sans rapport avec les jetons, mais l'information est là si vous voulez un jour
  filtrer les comptes par appartenance.

### Écarté après discussion

- **Refonte de la navigation en 5 espaces métier** (proposée par un audit) —
  réécriture complète pour trois utilisateurs qui connaissent l'outil. Bénéfice
  esthétique, risque de régression réel.
- **Découpage de `app.py` en modules** — justifié sur le papier (7 600 lignes,
  219 méthodes), mais plusieurs jours sans gain visible. À reconsidérer six mois
  après l'ouverture, jamais pendant un cycle de publication.
- **Parallélisation des opérations par lot** — quadruplerait la charge sur
  l'instance de production pour un gain de confort.

## 8. Sondes disponibles

**18 sondes** dans le dépôt, toutes autonomes (`python verifier_xxx.py` depuis
n'importe quel poste, seule dépendance : `requests`) et en LECTURE SEULE, sauf
`verifier_images.py` dont le test d'écriture est optionnel et confirmé.

Les plus utiles pour reprendre :

| Sonde | Objet |
|---|---|
| `verifier_ressources.py` | balaie les 16 ressources API inexploitées — le point de départ pour toute nouvelle fonctionnalité |
| `verifier_habillage.py` | champs modifiables des chaînes et thèmes |
| `verifier_images.py` | dépôt de bannières (écriture optionnelle) |
| `verifier_encodages.py` | anomalies d'encodage |
| `verifier_contributeurs.py` | usage réel des crédits |
| `verifier_champ_360.py` | champ « vidéo 360 » |
| `verifier_chunked_upload.py` | envoi par morceaux |
| `verifier_admin.py` | droits du jeton |
| `verifier_jetons.py` | **à lancer** : les jetons sont-ils exposés par l'API ? |

Les autres (`verifier_acces_prod`, `verifier_accessgroup_id`,
`verifier_accessgroups_cycle`, `verifier_diff_restriction`,
`verifier_draft_encode`, `verifier_encodage`, `verifier_encodage_500`,
`verifier_lecture_restriction`, `verifier_remplace_source`) ont servi à des
diagnostics ponctuels ; elles restent utilisables comme modèles.

**Modèle pour en écrire une nouvelle** : reprendre `verifier_ressources.py`, qui
gère l'installation de `requests`, la saisie de l'URL et du jeton, la pagination
et une synthèse conclusive.

## 9. Ce qui a été fait depuis la 1.3.0

Récapitulatif utile pour comprendre l'état actuel — et ne pas refaire.

| Version | Apport |
|---|---|
| 1.3.1 | Corrections d'audit : onglet ouvert avant connexion, message d'erreur qui levait une erreur, réaffectation vers le même compte, bannières de section trompeuses |
| 1.3.2 | **Filtres sur deux rangées** — 485 px étaient tronqués : le tri et les filtres de détection existaient dans le code mais restaient invisibles à l'écran |
| 1.4.0 | **Magasin partagé complété** — Encodage, Réaffectation et Inventaire rechargeaient l'instance chacun de leur côté et gardaient une copie périmée. Un seul scan désormais |
| 1.4.1 | Alerte de troncature **par ressource** ; **interruption** des traitements par lot |
| 1.5.0 | **Palette unifiée** (386 remplacements, 7 rôles sémantiques), **mode clair/sombre**, rechargement après dépôt, documentation 100 % |
| 1.5.1 | Icônes distinctes, **Échap/Entrée** sur les modales, suppressions isolées derrière un séparateur |

Deux constats se répètent dans cet historique, et méritent d'être retenus :

- plusieurs défauts venaient de **corrections précédentes appliquées à moitié**
  (le magasin partagé annoncé complet mais couvrant deux onglets sur cinq, un
  paramètre ajouté sans supprimer la ligne qu'il remplaçait) ;
- plusieurs fois, un **test a échoué alors que le code était bon** — banc
  d'essai mal construit, focus manquant, minutage, nom d'événement. D'où la
  règle : quand un test échoue, vérifier d'abord le test.

---

## 10. Comment reprendre

Fournir cette fiche, puis préciser **le point de départ** : un bug rencontré,
une demande d'utilisateur, ou un élément de la section 7.

Fournir aussi le **ZIP courant** de l'application concernée : le code fait foi,
cette fiche ne le remplace pas.

Rappel de méthode : sonde avant développement, tester le test, vérifier avant
d'affirmer.
