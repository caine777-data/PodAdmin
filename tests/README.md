# Tests de PodAdmin

Tests de la **logique pure** : aucune dépendance au réseau ni à l'interface
graphique. Ils couvrent les fonctions qui ont déjà causé des régressions
(relations dict/URL, doublons, conversion de sous-titres, états d'encodage).

## Lancer les tests

```
pip install pytest
python -m pytest tests/ -v
```

## Pourquoi ces fonctions-là

L'historique du dépôt (« corection bug », « bug owner », « pb brouillon group
restreint ») montre que ce sont ces zones qui cassent et re-cassent. Un test qui
échoue ici signale une régression **avant** la compilation, pas après le
déploiement.

Vérification faite : en réintroduisant volontairement le bug historique de
`_rel_urls` (ne plus gérer les relations sous forme d'objets), 4 tests échouent
immédiatement — dont celui qui reproduit l'appartenance à une chaîne.

## Deux suites

- **`test_logique.py`** — logique pure : aucune dépendance au réseau ni à
  l'interface. Rapide, exécutable partout.
- **`test_fenetres.py`** — dimensions des fenêtres : ouvre réellement
  l'interface et vérifie que le contenu tient dans la taille déclarée.
  Nécessite un affichage (`xvfb-run` sous Linux sans écran).

La seconde suite est née de trois défauts du même type, tous signalés par
l'utilisateur et jamais par les tests : une fenêtre non redimensionnable dont
le contenu débordait, rendant un bouton inaccessible. Les tests vérifiaient que
les fenêtres s'ouvrent, jamais que leur contenu tient dedans.

**Leçon retenue** : la première version de ce test employait un contenu minimal
(un sous-titre d'un caractère). Il passait même après réintroduction volontaire
du bug. Un test doit reproduire le cas RÉEL, pas le cas commode — sans quoi il
donne une fausse assurance.
