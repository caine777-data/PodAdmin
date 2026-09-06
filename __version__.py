"""
Source UNIQUE de la version de PodAdmin.
========================================
La version était auparavant recopiée dans une vingtaine de fichiers, avec le
risque classique d'en oublier un lors d'une publication. Tous les modules
l'importent désormais d'ici : il n'y a plus qu'un seul endroit à modifier.

Le fichier `version.txt` (métadonnées de l'exécutable Windows) et le numéro de
l'installeur restent à mettre à jour lors d'une publication : ils ne peuvent pas
importer de code Python.
"""

__version__ = "1.5.8"

# Décomposition (entiers), utile pour les métadonnées Windows : (majeur, mineur,
# correctif, build).
VERSION_TUPLE = tuple(int(x) for x in __version__.split(".")) + (0,)
