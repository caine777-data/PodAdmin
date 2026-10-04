"""
enrichissement — onglet « Enrichissement IA » (repris de SousTitreur 0.6.1).

Sous-titres aux normes par Aristote, relecture dans un éditeur web local,
traduction, métadonnées et quiz, puis publication sur Pod.

Modules sans interface :
  aristote_api   client de l'API Aristote (instance ILaaS)
  sous_titres    découpage aux normes, lecture et écriture VTT / SRT
  projet         stockage des projets en cours
  editeur        serveur local de l'éditeur (assets/editeur.html)
  journal        journal JSON de chaque écriture sur Pod
  reglages       dossier de données et réglages propres à l'onglet

Les données restent dans ~/.soustitreur (projets, sauvegardes, journal) : les
travaux commencés dans SousTitreur se retrouvent tels quels dans PodAdmin.
"""
