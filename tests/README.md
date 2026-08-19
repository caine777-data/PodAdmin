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
