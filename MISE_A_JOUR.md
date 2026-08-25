# Notification de mise à jour

PodAdmin vérifie discrètement, au démarrage, si une version plus récente existe.
Le cas échéant, un bandeau apparaît en bas de la barre latérale avec un bouton
« Télécharger ».

**Rien n'est jamais bloqué** : sans réseau ou en cas d'erreur, la vérification
échoue en silence et l'application démarre normalement.

---

# PARTIE 1 — Installation (à faire UNE SEULE FOIS, ~10 minutes)

## Étape 1. Créer le dépôt public

Le dépôt de code reste **privé** (il contient le mot de passe du compte
véhicule). On crée un second dépôt, **public**, qui ne contiendra que le fichier
de version et les exécutables — aucun secret.

1. Sur GitHub, cliquer sur **+** (en haut à droite) → **New repository**
2. **Repository name** : `podadmin-releases`
3. Cocher **Public**
4. Cocher **Add a README file**
5. **Create repository**

## Étape 2. Créer le jeton d'écriture

Ce jeton autorisera la compilation à écrire dans le dépôt public.

1. Aller sur : **https://github.com/settings/tokens?type=beta**
2. **Generate new token**
3. **Token name** : `podadmin-releases`
4. **Expiration** : choisir **No expiration** (sinon il faudra le refaire)
5. **Repository access** → **Only select repositories** → choisir
   `podadmin-releases`
6. **Permissions** → **Repository permissions** → ligne **Contents** →
   choisir **Read and write**
7. **Generate token**, puis **COPIER le jeton affiché** (il ne sera plus jamais
   visible)

## Étape 3. Enregistrer le jeton dans le dépôt du code

1. Aller dans le dépôt **privé** de PodAdmin → onglet **Settings**
2. Menu de gauche : **Secrets and variables** → **Actions**
3. Bouton **New repository secret**
4. **Name** : `RELEASES_TOKEN`
5. **Secret** : coller le jeton copié à l'étape 2
6. **Add secret**

## Étape 4. Rien à faire

L'adresse est **déjà renseignée** dans `config.py` :

```python
UPDATE_URL = ("https://raw.githubusercontent.com/"
              "caine777-data/podadmin-releases/main/version.json")
```

Elle correspond au dépôt créé à l'étape 1. Si vous le nommez autrement que
`podadmin-releases`, adaptez cette ligne — sinon, il n'y a rien à modifier.

C'est terminé.

---

# PARTIE 2 — À chaque nouvelle version

**Vous continuez exactement comme aujourd'hui**, avec un champ à remplir en plus.

1. Dézipper la livraison dans votre dossier local
2. Pousser avec **GitHub Desktop** (dépôt privé)
3. Sur GitHub : onglet **Actions** → workflow **Build installers** →
   **Run workflow**
4. **NOUVEAU** — deux champs apparaissent :
   - **Numéro de version** : saisir `1.1.0` (par exemple)
   - **Phrase du bandeau** (facultatif) : « Correction de l'affichage des
     groupes d'accès »
5. **Run workflow**

C'est tout. La compilation produit les exécutables, crée la Release **sur le
dépôt public** `podadmin-releases` avec les fichiers à télécharger, et y écrit
`version.json`. Les applications déjà installées afficheront le bandeau à leur
prochain démarrage.

> Les Releases sont publiées sur le dépôt **public**, jamais sur le dépôt de
> code. C'est volontaire : le bouton « Télécharger » du bandeau doit mener à une
> page accessible à tous, sans compte ni autorisation. Le dépôt de code reste
> privé (il contient le mot de passe du compte véhicule).

## Compiler sans publier (essai)

**Laisser le champ « Numéro de version » VIDE.** La compilation se déroule
normalement et vous récupérez les exécutables dans les artefacts du run, mais
aucune Release n'est créée et personne n'est prévenu.

C'est le comportement à utiliser pour un test.

## Et les tags ?

Ils continuent de fonctionner (pousser un tag `v1.1.0` déclenche la même
publication), mais **vous n'êtes pas obligé de les utiliser**. Le bouton suffit.

---

# Questions pratiques

**Le jeton RELEASES_TOKEN est-il indispensable ?**
**Oui.** Les exécutables sont publiés sur le dépôt PUBLIC, ce qui permet à vos
collègues de les télécharger sans avoir accès au dépôt de code, qui reste privé.
Sans ce jeton, l'écriture sur le dépôt public est impossible et la publication
échoue.

En revanche, une **compilation d'essai** (champ « Numéro de version » laissé
vide) fonctionne sans jeton : elle produit les exécutables en artefacts, sans
rien publier.

**Comment forcer une mise à jour vraiment importante ?**
Par exemple après une rotation du mot de passe du compte véhicule, qui rend les
anciennes versions incapables de téléverser les gros fichiers : éditer une fois
`version.json` sur le dépôt public et renseigner `version_minimale` avec la
version en dessous de laquelle le bandeau devient orange et insistant.
L'application reste utilisable — le bandeau insiste, il n'interdit pas.

**Comment désactiver complètement la vérification ?**
Mettre `UPDATE_URL = ""` dans `config.py`.

**Le dépôt public expose-t-il quelque chose de sensible ?**
Non pour PodAdmin : il ne contient aucun secret et ne fait rien sans un jeton
d'administration valide.
⚠️ **En revanche, ne jamais y publier le Pod Téléverseur** : son exécutable
contient le mot de passe du compte véhicule. Il lui faudra son propre dépôt, ou
un hébergement universitaire.
