# PodAdmin — Ajout : chunk + choix du propriétaire (Phase 1)

Nouveautés par rapport à ton PodAdmin habituel. Rien ne change à l'usage tant
que tu déposes des fichiers ≤ 500 Mo.

## Ce qui a été ajouté

- **Compte véhicule (onglet Configuration)** : deux champs Identifiant + Mot de
  passe d'un compte LOCAL, stockés chiffrés (keyring, espace PodAdmin). Ils
  servent à ouvrir la session web pour le chunké. **Optionnels** : requis
  seulement si un fichier dépasse 500 Mo. « Tester & se connecter » vérifie aussi
  cette session si elle est renseignée.
- **Téléversement > 500 Mo** : bascule automatique en chunké via le véhicule,
  puis **réattribution** de la vidéo au **propriétaire que tu as choisi** dans
  l'onglet (le sélecteur de propriétaire est conservé), + métadonnées + encodage.
  ≤ 500 Mo : chemin token habituel, inchangé.
- **Garde-fou réattribution** : si le PATCH `owner` échoue après la création,
  la vidéo resterait au nom du véhicule. L'appli le signale FORT (statut rouge
  « ⚠️ NON réattribuée » + log détaillé invitant à réattribuer via l'onglet
  Réaffectation). Jamais de fausse attribution silencieuse.
- **Récupération après 504** : si nginx coupe la finalisation d'un gros fichier,
  l'appli attend et sonde l'API jusqu'à **30 min** que la vidéo apparaisse, puis
  enchaîne réattribution + métadonnées + encodage.
- Noms de fichiers accentués assainis (en-têtes HTTP), morceaux ré-essayés sur
  502/503/504.
- **pod_api.py** : nouvelle méthode `get_video_by_slug()` (résolution robuste).
- **pod_chunked.py** : nouveau module (moteur chunké), identique à celui d'eformation.

## À tester sur l'instance (ce que la sandbox ne peut pas valider)

1. Configuration : token + compte véhicule (local) → « token OK + véhicule OK ».
2. Petit fichier (< 500 Mo) → chemin habituel, propriétaire choisi.
3. Gros fichier (> 500 Mo) → Journal « bascule chunkée » ; vérifier côté web que
   la vidéo appartient bien au **propriétaire choisi** (pas au véhicule), avec
   type/brouillon/co-propriétaires + encodage lancé.
4. Cas 504 : la vidéo doit être reprise automatiquement après quelques minutes.

## Note build

`pod_chunked.py` est un module local importé par `app.py` : PyInstaller le prend
automatiquement, aucun `--collect-all` à ajouter.
