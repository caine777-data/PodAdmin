#!/usr/bin/env bash
# ============================================================================
#  05_ajouter_proprietaire.sh — Ajouter un PROPRIÉTAIRE ADDITIONNEL
#  ("co-auteur" au sens du formulaire d'upload de Pod)
#
#  Appel : PATCH /rest/videos/<slug>/  avec le champ additional_owners.
#  PATCH = mise à jour PARTIELLE d'une ressource existante (on ne modifie
#  que les champs fournis, ici la liste des propriétaires additionnels).
#
#  ⚠️ additional_owners attend une LISTE d'URLs utilisateurs. Pour en mettre
#     plusieurs, on répète l'option -F "additional_owners=URL".
#
#  Rappel : propriétaire additionnel = compte Pod avec droits d'édition
#           (à distinguer du "contributeur" du script 06, simple crédit).
#
#  Usage :
#    source ./config.sh
#    ./05_ajouter_proprietaire.sh mon-slug \
#       "https://videos.utoulouse.fr/rest/users/42/" \
#       "https://videos.utoulouse.fr/rest/users/7/"
# ============================================================================
set -uo pipefail
source "$(dirname "$0")/config.sh"

SLUG="${1:?slug requis}"   # 1er argument = identifiant de la vidéo
shift                       # "décale" les arguments : $2 devient $1, etc.
                            # → il ne reste que les URLs utilisateurs dans "$@"
if [[ $# -eq 0 ]]; then echo "Fournissez au moins une URL utilisateur."; exit 1; fi

# Construire dynamiquement les options -F, une par URL fournie.
ARGS=()
for url in "$@"; do ARGS+=(-F "additional_owners=${url}"); done

echo "▶ Ajout de $# propriétaire(s) additionnel(s) à ${SLUG} ..."
# -X PATCH : forcer la méthode HTTP PATCH. "${ARGS[@]}" injecte toutes les
# options -F construites ci-dessus.
curl -s -H "${AUTH_HEADER}" -X PATCH "${ARGS[@]}" \
  "${POD_URL}/rest/videos/${SLUG}/" | head -c 600
echo -e "\n  ✅ Terminé."
