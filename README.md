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
- produit `PodAdmin.exe` (Windows) et `PodAdmin-macOS.zip` (Apple Silicon).

Compilation locale (Windows) :

```bash
python -m PyInstaller --onefile --windowed --name PodAdmin ^
  --collect-all customtkinter --collect-all keyring --collect-all tkinterdnd2 ^
  --collect-all openpyxl --add-data "assets;assets" app.py
```

> Séparateur `--add-data` : `;` sous Windows, `:` sous macOS/Linux.
> macOS : app non signée → premier lancement via clic droit → Ouvrir.

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

Version : **1.5.3**

---

## Droits

© Copyright 2026 Cédric MONNA

Développé pour l'Université de Toulouse, avec Philippe BAQUÉ et Michel JACOB.

**Tous droits réservés.** La réutilisation, la diffusion ou l'adaptation de cet
outil, en tout ou partie, sont soumises à l'autorisation préalable de l'auteur.

Contact : support-pod@utoulouse.fr
