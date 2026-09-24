# Blocage à distance

Un interrupteur qui rend toutes les copies installées de PodAdmin inutilisables, puis à nouveau
utilisables. **Indépendant de la mise à jour obligatoire** (voir [MISE_A_JOUR.md](MISE_A_JOUR.md)) :
celle-ci ne se déclenche que si une version publiée dépasse un seuil ; celui-ci se déclenche
uniquement sur une action manuelle, explicite, dans l'onglet Actions — **jamais tout seul**.

Inspiré du même mécanisme déjà en place sur EnqueteGen : **invisible** tant que rien n'est bloqué —
pas de bandeau, pas de message.

## Ce que voient les utilisateurs

- **Normalement** : rien. L'application lit l'état en arrière-plan au démarrage, puis toutes les
  heures, et n'attend jamais la réponse.
- **Bloquée** : la fenêtre est entièrement recouverte par « PodAdmin n'est pas disponible —
  L'utilisation de l'application est suspendue », avec un seul bouton, **Quitter**. Les fenêtres
  secondaires ouvertes (Réglages, À propos…) sont fermées. On peut toujours fermer l'application
  (croix, Alt+F4).
- **Débloquée** : l'application redevient normale, sans rien réinstaller, au lancement suivant ou
  dans l'heure si elle est déjà ouverte.

## Règles

- Seule une **réponse du serveur** change l'état. Réseau coupé, dépôt injoignable, fichier absent
  ou illisible : rien ne change, ni blocage ni déblocage.
- Un blocage reçu est **mémorisé sur le poste** (`"blocage_distant": true` dans
  `~/.podadmin.json`) : couper le réseau ne le contourne pas. Il n'est levé que par un
  « débloquer » lu sur le serveur.
- Un poste qui n'a jamais reçu le blocage (resté hors ligne) n'est pas bloqué : il le sera à sa
  première connexion.
- Délai : GitHub garde le fichier en cache jusqu'à 5 minutes ; une application déjà ouverte le
  relit dans l'heure.
- Ce n'est pas une protection forte : une personne qui sait modifier `~/.podadmin.json` et couper
  le réseau peut s'en affranchir.

## Installation

**Rien à faire.** Ce mécanisme réutilise le dépôt public `podadmin-releases` et le secret
`RELEASES_TOKEN` déjà configurés pour la mise à jour (voir MISE_A_JOUR.md, Partie 1) : le fichier
d'état, `etat.json`, est publié à côté de `version.json`, sur le même dépôt, avec le même jeton.

L'adresse est déjà renseignée dans `config.py` :

```python
BLOCAGE_URL = ("https://raw.githubusercontent.com/"
               "caine777-data/podadmin-releases/main/etat.json")
```

## Bloquer ou débloquer

Dépôt PodAdmin → **Actions** → workflow **Build installers** → **Run workflow** → champ
**Blocage** : choisir **bloquer** ou **débloquer** → **Run workflow**.

Ce choix **ne compile rien** : le run écrit seulement `etat.json` (`{"bloque": true}` ou `false`)
sur le dépôt public, en moins d'une minute, et ignore les autres champs du formulaire (version,
notes, obligatoire…).

Laisser **« ne rien changer »** (valeur par défaut) pour une compilation ou une publication
normale — c'est l'état par défaut du champ : sans action volontaire dans Actions, ce blocage ne
s'active donc jamais.

## Désactiver complètement la vérification

Mettre `BLOCAGE_URL = ""` dans `config.py` : plus aucune lecture réseau.

## Dans le code

- `maj.py` : `etat_blocage()` — interroge `etat.json`, renvoie `True`/`False`/`None` (jamais
  bloquant, voir `_telecharger_json`, factorisée avec `recuperer_info` pour la mise à jour).
- `config.py` : `BLOCAGE_URL`, `BLOCAGE_PERIODE_MS`, `BLOCAGE_TIMEOUT_S` ; mémorisation locale via
  `enregistrer_blocage_distant()` / `blocage_distant_actif()`.
- `app.py`, classe `App` : `_surveiller_blocage()` (thread, puis toutes les `BLOCAGE_PERIODE_MS`),
  `_appliquer_blocage()`, `_bloquer_application()`. Contrôle local au tout premier démarrage
  (`cfg.blocage_distant_actif()`), avant même la mise à jour obligatoire.
- `.github/workflows/build.yml` : entrée `blocage` (`ne rien changer` / `bloquer` / `débloquer`),
  job `blocage` (n'écrit que `etat.json`), et garde ajoutée aux jobs de compilation et de release
  pour qu'ils s'ignorent quand `blocage` est actionné.
