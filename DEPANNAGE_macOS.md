# macOS — « PodAdmin est endommagé et ne peut pas être ouvert »

## Ce que ça veut dire

**L'application n'est pas endommagée.** macOS affiche ce message trompeur dans
deux situations, qu'il faut distinguer :

1. l'application n'est pas signée par un développeur identifié par Apple ;
2. **sa signature a été abîmée** pendant le transfert ou l'archivage.

Le cas n°2 est le plus probable ici — voir « Cause identifiée » plus bas.

---

## Pour Marie : la marche à suivre (dans cet ordre)

L'ordre compte : un `.dmg` est en **lecture seule**, on ne peut donc rien y
réparer. Il faut d'abord en sortir l'application.

1. Ouvrir le `.dmg`, **glisser PodAdmin dans Applications** (ou sur le Bureau,
   ça évite le mot de passe administrateur).
2. **Éjecter le `.dmg`** (clic droit sur son icône → Éjecter).
3. Ouvrir le **Terminal** (⌘ + Espace, taper « Terminal », Entrée).
4. Taper ceci **avec un espace à la fin**, sans valider :
   ```
   xattr -cr 
   ```
   puis **glisser l'application** depuis le Finder dans la fenêtre du Terminal
   (le chemin s'écrit tout seul), et appuyer sur Entrée.
5. Lancer l'application.

**Si le message revient**, la signature est cassée : réparer avec la même
méthode (taper, espace, glisser-déposer, Entrée) :
```
codesign --force --deep --sign - 
```
puis relancer l'application.

---

## Cause identifiée (côté compilation)

Le processus de compilation comportait deux défauts, tous deux capables de
produire ce message :

**1. Aucune signature.** Sur Apple Silicon, macOS exige que tout exécutable
porte une signature valide, même « ad hoc » (anonyme). Sans elle, le système
refuse l'application en la déclarant endommagée.

**2. Archive fabriquée avec `zip`.** La commande `zip` ne préserve ni les liens
symboliques internes d'un paquet `.app`, ni ses attributs étendus : la signature
est donc cassée à la décompression. Apple fournit `ditto` précisément pour
archiver un paquet applicatif sans l'altérer.

### Corrections apportées au workflow de compilation

- **signature ad hoc** (`codesign --force --deep --sign -`) après la
  compilation, suivie d'une vérification qui fait échouer la compilation si la
  signature est invalide ;
- **`ditto`** remplace `zip` pour l'archive, et `cp -R` pour la préparation du
  DMG.

Les prochaines versions compilées ne devraient donc plus provoquer ce message.

---

## Recommandations de diffusion

- **Diffuser le `.dmg`**, pas l'archive `.zip` du `.app`.
- **Ne pas transmettre l'application par messagerie** (Telegram, WhatsApp…) :
  ces services recompressent les fichiers et cassent la signature. Passer par un
  lien de téléchargement (page Moodle, dépôt de fichiers).

---

## Limite connue : Mac Intel

Les exécutables macOS sont produits par les serveurs de GitHub, qui sont en
**Apple Silicon** : l'application est donc **arm64 uniquement** et ne fonctionne
pas sur un Mac Intel. Le message y serait différent (« ne peut pas être ouvert
sur ce type de Mac »), mais aucune commande n'y changerait rien.

Si des postes Intel sont concernés, il faudra produire une version universelle —
à traiter séparément.
