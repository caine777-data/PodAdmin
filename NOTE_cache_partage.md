# PodAdmin — cache de vidéos partagé (chantier terminé)

## Ce qui a changé

Avant, les onglets **Vidéos**, **Explorateur** et **Chaînes** possédaient chacun
leur propre liste de vidéos, remplie par son propre appel réseau. La même vidéo
existait donc en trois exemplaires distincts : modifier l'un ne modifiait pas
les autres, d'où les désynchronisations (vidéo supprimée qui reste « fantôme »
ailleurs, propriétaire périmé, calculs de groupes faussés).

Désormais il existe **une seule liste**, `self.videos`, partagée par les trois
onglets. Chacun garde sa propre vue (filtres, sélection, présentation), mais
tous lisent la même source.

## Conséquences concrètes

- **La désynchronisation est devenue impossible** : il n'y a plus qu'un objet
  par vidéo. Une suppression ou une modification est vue partout immédiatement,
  sans qu'aucun mécanisme n'ait à « prévenir » les autres onglets.
- **Moins d'appels réseau** : la liste est chargée UNE fois. Ouvrir un deuxième
  puis un troisième onglet n'entraîne plus aucun rechargement.
- **Rafraîchir reste explicite** : les boutons « Rafraîchir » (Vidéos) et
  « Scanner » (Explorateur) forcent une vraie relecture du serveur. La simple
  ouverture d'un onglet, elle, réutilise le cache.

## Mécanique

- `self.videos` — la liste unique (source de vérité), avec `videos_loaded_at`
  (horodatage) et `videos_loading` (verrou).
- `ensure_videos(on_ready, force, progress_cb)` — point d'entrée unique,
  asynchrone. Sert depuis le cache si possible, lance un scan sinon.
  **Gère la concurrence** : si trois onglets demandent la liste en même temps,
  un seul scan est lancé et les trois sont servis à la fin.
- `ensure_videos_sync()` — variante synchrone pour l'onglet Chaînes, qui
  travaille déjà dans un thread.
- `videos_stamp()` — libellé de fraîcheur (« 10 vidéo(s) — chargées à 14:32 »).
- `_sync_video_caches()` — conservée mais **simplifiée** : elle n'agit plus que
  sur la liste unique. Gardée pour compatibilité avec les appels existants et
  comme filet de sécurité.

## Précautions prises

- `browse_videos`, `clean_videos` et `ct_videos` sont devenus des **alias** du
  magasin (le même objet liste). Tout code résiduel qui y accéderait fonctionne
  donc encore : la migration ne casse rien, et un retour en arrière reste possible.
- **Sélection ré-associée par slug** après un rechargement (onglet Vidéos) :
  sinon le panneau de détail pointerait vers un objet qui n'est plus dans le
  magasin.
- **Cases à cocher réinitialisées** après un rechargement (Explorateur) : une
  action par lot ne doit jamais porter sur des vidéos disparues.

## Défaut trouvé et corrigé pendant le chantier

Au premier test, l'onglet Vidéos déclenchait **deux** appels réseau au lieu d'un.
Cause : le rechargement était forcé à chaque appel de `_browse_load`, y compris
à la simple ouverture de l'onglet — ce qui annulait le bénéfice du cache. Le
`force` est désormais explicite : ouverture = cache, bouton = rechargement réel.

## Tests automatisés passés

- 3 onglets demandant la liste simultanément → **1 seul appel réseau**, les 3 servis
- demande ultérieure → servie depuis le cache, 0 appel
- « Rafraîchir » (force) → relance bien un scan
- les 3 onglets pointent sur la même liste
- suppression dans un onglet → vue par les deux autres instantanément
- modification d'un titre → vue par les autres onglets
- non-régression : filtres, sélection, surbrillance, plafond 300,
  appartenance aux chaînes, fenêtre de progression

## À vérifier sur l'instance

1. Ouvrir Vidéos, puis Explorateur, puis Chaînes → seul le premier doit charger
   (les suivants s'affichent immédiatement).
2. Supprimer une vidéo dans Vidéos → elle doit disparaître des deux autres
   onglets sans aucun rafraîchissement manuel.
3. Cliquer sur « Rafraîchir » → la liste doit réellement être relue (l'horodatage
   change).
4. Réaffecter un propriétaire, changer un type en masse → vérifier la cohérence
   entre onglets.
5. Vérifier que les actions par lot de l'Explorateur portent bien sur les
   vidéos attendues (rappel : plafond de 300 lignes affichées).
