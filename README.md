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

Version : **1.1.1**

---

## Droits

© Copyright 2026 Cédric MONNA

Développé pour l'Université de Toulouse, avec Philippe BAQUÉ et Michel JACOB.

**Tous droits réservés.** La réutilisation, la diffusion ou l'adaptation de cet
outil, en tout ou partie, sont soumises à l'autorisation préalable de l'auteur.

Contact : support-pod@utoulouse.fr
