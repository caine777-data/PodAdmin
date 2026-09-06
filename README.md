# PodAdmin — Console d'administration Esup-Pod

Application de bureau (Université de Toulouse — MFCA) pour administrer une
instance **Esup-Pod** via son API REST, sans passer par l'interface
d'administration Django du serveur.

PodAdmin est un **fork de « Pod Téléverseur »** : il conserve le téléversement
de vidéos par lot et y ajoute des modules d'administration.

> ⚠️ PodAdmin agit sur l'ensemble de l'instance (comptes, vidéos de tous les
> utilisateurs, chaînes…). Il nécessite un **token de compte superutilisateur**.

---

## Modules

| Onglet | Rôle |
|---|---|
| **Téléversement** | Dépôt de vidéos par lot (hérité du Téléverseur) : glisser-déposer, propriétaire, co-auteurs, lancement de l'encodage. |
| **Comptes** | Donner / retirer le statut « équipe » (`is_staff`) à un compte — l'autorisation d'ajouter et gérer des vidéos sur Pod. |
| **Réaffectation** | Transférer en masse les vidéos d'un compte vers un autre (départ d'un agent), avec aperçu *dry-run* et option de conserver l'ancien propriétaire en co-propriétaire. |
| **Nettoyage / Modération** | Détecter (jamais encodées, brouillons, vieux brouillons, doublons de titre) puis agir par lot : mettre en brouillon, publier, restreindre, lever la restriction, **supprimer** (double confirmation). |
| **Inventaire / Stats** | Volumétrie, durées, répartition par utilisateur / type / chaîne, **export Excel** (`.xlsx`). |
| **Chaînes & thèmes** | Créer, renommer, basculer la visibilité et supprimer chaînes et thèmes. |
| **Configuration** | Connexion à l'instance, stockage chiffré du token. |
| **Journal** | Historique horodaté de toutes les actions. |

---

## Sécurité

- **Token** stocké dans le coffre-fort de l'OS (`keyring`, service `PodAdmin-UToulouse`),
  jamais dans le code ni l'exécutable, **par poste**. Identifiant distinct du
  Téléverseur : les deux applis cohabitent sans se mélanger les tokens.
- **Actions destructives** (suppression, opérations en masse) : aperçu *dry-run*,
  cases décochées par défaut, et confirmation explicite (double pour la suppression).

---

## Installation (depuis les sources)

```bash
python -m venv .venv
# Windows : .venv\Scripts\activate   |   macOS/Linux : source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Prérequis : Python 3.11. Dépendances dans `requirements.txt`
(`openpyxl` est requis pour l'export Excel).

---

## Diagnostic de l'instance

Avant tout, valider ce que l'API autorise avec un **token superadmin** :

```bash
python verifier_admin.py
```

Le script vérifie (en lecture seule via `OPTIONS`) la faisabilité de chaque
module, et propose un **test aller-retour optionnel** (création/modification/
suppression d'objets jetables, nettoyés ensuite) pour confirmer PATCH/DELETE
sur les chaînes et thèmes.

`verifier.py` reste disponible pour les diagnostics liés au téléversement.

**Disciplines** — deux sondes ont tranché la faisabilité d'un futur module :

```bash
python verifier_disciplines.py        # la ressource est-elle créable ?
python verifier_discipline_forme.py   # sous quelle forme l'écrire ?
```

Résultat sur `videos.utoulouse.fr` : la table `discipline` est vide, créable par
l'API (seul `title` obligatoire), sans champ de propriétaire — c'est donc bien un
classement d'établissement — et le champ est modifiable sur la vidéo.
En revanche, **les catégories ne sont pas exposées par l'API** (404 sur les
quatre orthographes testées) : il n'y a qu'une nomenclature à décider, pas deux.

---

## Compilation (exécutables)

Automatique via **GitHub Actions** (`.github/workflows/build.yml`) :
- déclenchée par un tag `v*` (crée une *Release*) ou manuellement (« Run workflow ») ;
- produit un **dossier** `PodAdmin/` (Windows), l'installeur `PodAdmin-Setup.exe`
  et `PodAdmin-macOS.zip` (Apple Silicon).

⚠️ **Compilation en `--onedir`, pas `--onefile`.** En `--onefile`, l'exécutable
est une archive auto-extractible : à chaque lancement, tout l'interpréteur
Python est décompressé dans un dossier temporaire avant que quoi que ce soit ne
s'affiche. En `--onedir`, le démarrage est 3 à 5 fois plus rapide. Sur macOS,
cela règle en outre la dépréciation de `--onefile --windowed`, bloquante à
partir de PyInstaller 7.

Conséquence : le portable Windows est un **dossier à dézipper en entier**.
`PodAdmin.exe` seul ne démarre pas — il lui faut ses fichiers voisins.
L'installeur, lui, ne change pas d'usage.

Compilation locale (Windows) :

```bash
python -m PyInstaller --onedir --windowed --name PodAdmin ^
  --collect-all customtkinter --collect-all keyring --collect-all tkinterdnd2 ^
  --collect-all openpyxl --add-data "assets;assets" app.py
```

> Séparateur `--add-data` : `;` sous Windows, `:` sous macOS/Linux.
> macOS : app non signée → premier lancement via clic droit → Ouvrir.

---

## Bascule d'onglet

Les onglets sont **empilés** dans une grille à une seule cellule ; changer
d'onglet ne fait que remonter le bon (`tkraise`). L'ancienne version dépackait
les treize onglets puis replaçait le bon : quatorze recalculs de mise en page
par clic, en repassant par un écran vide — d'où le clignotement.

⚠️ **`winfo_manager()` sur un widget composite ment.** Sur un
`CTkScrollableFrame` (l'onglet Configuration), il répond « canvas », le
gestionnaire de son widget *interne*. Tester et placer doit se faire sur le
widget réellement enfant de la zone de contenu, que `_widget_empilable`
retrouve. Sans cela, Configuration n'était jamais posé dans la grille : on
demandait Configuration, l'écran affichait Vidéos, **sans aucune erreur**.

Ce défaut n'a été vu que par capture d'écran — les tests qui cherchaient le
titre *à l'intérieur* du widget le trouvaient et concluaient à tort.
`TestBasculeDOnglet` vérifie désormais le placement et l'ordre d'empilement.

---

## Performance

La bascule clair/sombre parcourt **tous** les widgets de l'application. Mesuré :
871 widgets → 85 ms, 1 771 widgets → 175 ms, et deux à trois fois plus sur
Windows. Le nombre de widgets est donc directement la lenteur ressentie.

Conséquence pratique : **une page de texte statique ne se construit pas à coups
d'étiquettes.** L'onglet Aide pesait 134 widgets pour dix-sept sections ; une
zone de texte unique fait le même travail pour 14, et rend le texte copiable.
Deux tests plafonnent le poids (`TestPoidsDeLInterface`).

⚠️ Les balises d'une zone de texte n'acceptent qu'une couleur **simple**, là où
le reste emploie des couples (clair, sombre) résolus par CustomTkinter. Toute
couleur posée par balise doit donc être réadaptée à chaque bascule.

---

## Nomenclatures : types et disciplines

Deux ressources voisines, **quatre conventions différentes**, toutes établies
par sonde :

| | Type | Discipline |
|---|---|---|
| champ site | `sites` (pluriel), **liste** | `site` (singulier), **chaîne** |
| obligatoire | **oui** | non |
| sur la vidéo | une seule URL | une **liste** d'URLs |
| au départ | 4 entrées, 73 vidéos | table vide |

⚠️ Envoyer une liste là où une chaîne est attendue donne un HTTP 400 :
« Type incorrect. Attendait une URL, a reçu list. » Ne pas « harmoniser »
`create_type` et `create_discipline` : quatre tests l'interdisent
(`TestNomenclatures`).

Conséquence côté interface : supprimer un **type** touche des contenus en
production, supprimer une **discipline** ne touchera longtemps rien. Le nombre
de vidéos rattachées est donc affiché avant toute confirmation, et un refus du
serveur est présenté tel quel plutôt que masqué.

### ⚠️ Suppression d'un type = suppression de ses vidéos

**Établi par sonde sur l'instance réelle, au prix d'une vidéo de test.**
Supprimer un type supprime AUSSI toutes les vidéos qui le portent. Le serveur
ne proteste pas : il répond `HTTP 204` et les vidéos n'existent plus.

PodAdmin **interdit** donc la suppression d'un type non vide — un avertissement
ne suffit pas, une confirmation se clique. Pour supprimer un type, il faut
d'abord réaffecter ses vidéos via « Modifier en masse » dans l'onglet Vidéos.

⚠️ Ce garde-fou n'existe **que dans PodAdmin**. La même suppression depuis
l'administration Django détruira les vidéos sans rien demander.

Le renommage des disciplines, lui, a été confirmé (PATCH accepté, valeur relue).

---

## Conventions visuelles

Deux échelles, à respecter pour toute nouvelle interface.

**Surfaces** — une échelle d'élévation. Une surface posée est plus claire que
son support, dans les deux modes :

| Constante | Usage | Clair | Sombre |
|---|---|---|---|
| `S_FOND` | fond de la fenêtre | gray88 | gray11 |
| `S_BARRE` | barre latérale | gray92 | gray15 |
| `S_CARTE` | panneau, encart de formulaire | gray96 | gray18 |
| `S_LIGNE` / `S_LIGNE_ALT` | ligne de liste, en-tête, zébrure | gray91 / gray95 | gray22 / gray19 |
| `S_SELECTION` | élément actif | gray78 | gray30 |
| `S_PUCE` | pastille ou aperçu dans une ligne | gray84 | gray26 |
| `S_FILET` | trait de séparation | gray80 | gray32 |

Douze gris différents désignaient auparavant ces quelques niveaux, et le fond de
fenêtre tombait sur la même teinte que la barre latérale.

⚠️ **Un `CTkScrollableFrame` ou un `CTkFrame` sans `fg_color` retombe sur le
défaut de CustomTkinter** (`gray86`/`gray17`), qui n'appartient à aucun niveau :
le panneau devient alors invisible sur le fond. Tout panneau doit recevoir
`S_CARTE` explicitement.

**Suppressions répétées en liste** — icône poubelle seule, fond neutre, rouge
**au survol**, libellé rendu par `ajouter_infobulle`. Un libellé rouge répété
sur chaque ligne saturait l'écran : sur vingt chaînes, l'action la plus
dangereuse devenait la plus visible et l'œil s'y habituait. Les suppressions
**uniques** (panneau de détail d'une vidéo) gardent leur libellé rouge : c'est
la répétition qui posait problème, pas la couleur.

**Icônes de navigation** — l'espacement entre l'icône et le libellé est
**calculé à l'exécution** (`_prefixe_aligne`), jamais écrit en dur. Les glyphes
n'ayant pas la même largeur, trois espaces fixes décalaient les libellés jusqu'à
11 px — et comme cette largeur dépend de la police du système, les entrées
fautives changeaient d'un poste à l'autre. Une icône ne doit désigner qu'un seul
onglet, et le titre de l'onglet doit reprendre celle de la navigation
(`TestCoherenceDesIcones`).

**Actions de masse** — la CARDINALITÉ figure dans le bouton (« Appliquer aux 74
vidéos »), mise à jour à chaque filtrage, et la teinte est `C_ALERTE` et non
`C_ACTION`. Un « Appliquer » nu à côté d'un libellé qui ne dit jamais combien
était le seul élément saturé de l'écran, pour l'action la plus lourde de
conséquences.

**Place dans la barre latérale** — la navigation doit tenir SANS DÉFILEMENT à la
taille par défaut, **1180×760** (et non 1280×800 : mesurer dans une fenêtre
confortable a fait passer pour correcte une navigation qui débordait chez tout
le monde). « Aide » et « À propos » sont épinglés en pied sur une seule ligne à
deux colonnes ; les épingler sans les compacter n'aurait rien rapporté.

**Filtres** — chaque filtre porte son intitulé AU-DESSUS du menu (`bloc_filtre`),
jamais enfermé dans sa valeur par défaut. « Tous statuts » disparaissait dès
qu'on filtrait : l'écran affichait « Public », « MFCA », « Cours » sans plus
dire ce que chaque valeur filtrait. À gauche plutôt qu'au-dessus, le libellé
coûterait 139 px sur une rangée qui n'en a que 3 de marge en fenêtre minimale.

⚠️ Renommer une valeur « tout afficher » oblige à mettre à jour les
comparaisons dans `_browse_do_filter` : sinon le filtre devient **silencieusement
inopérant**, sans erreur.

**Répartition de l'onglet Vidéos** — la liste garde `weight=2` et le détail
`weight=3`. Décision prise sur captures : inverser les poids ne rend que 90 px
à la liste, sans faire tenir une ligne de plus, et tasse le panneau le plus
chargé de l'application (co-propriétaires, chaînes, groupes, sous-titres,
suppression). Le vrai gain serait un panneau de détail **escamotable**, affiché
seulement à la sélection — non retenu pour l'instant.

**Actions** — un seul bouton coloré par écran. Les filtres et les listes
déroulantes prennent `STYLE_CHAMP` (gris), les boutons secondaires `C_NEUTRE`
accompagné de `T_SUR_NEUTRE` (sans quoi ils paraissent désactivés en mode
clair), et la couleur est réservée à l'action qui produit un effet.

⚠️ **Toute couleur doit être un couple `(clair, sombre)`.** Une teinte écrite
seule s'applique telle quelle aux deux thèmes : c'est ainsi qu'une ligne sur
deux du tableau de téléversement s'affichait presque noire en mode clair. Deux
tests le vérifient (`TestEchelleDeSurfaces`).

---

## Architecture

```
PodAdmin/
├── app.py              # Interface CustomTkinter (onglets)
├── pod_api.py          # Client API REST Esup-Pod (upload + admin)
├── config.py           # Config + stockage chiffré du token
├── verifier.py         # Diagnostic API (téléversement)
├── verifier_admin.py   # Diagnostic API (administration)
├── requirements.txt
├── assets/logo_ut.png
├── scripts/            # Scripts curl de référence (commentés)
└── .github/workflows/build.yml
```

Version : **1.5.6**

---

## Droits

© Copyright 2026 Cédric MONNA

Développé pour l'Université de Toulouse, avec Philippe BAQUÉ et Michel JACOB.

**Tous droits réservés.** La réutilisation, la diffusion ou l'adaptation de cet
outil, en tout ou partie, sont soumises à l'autorisation préalable de l'auteur.

Contact : support-pod@utoulouse.fr
