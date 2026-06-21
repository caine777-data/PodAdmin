#!/usr/bin/env bash
# ============================================================================
#  06_ajouter_contributeur.sh — Ajouter un CONTRIBUTEUR (crédit)
#
#  Appel : POST /rest/contributors/  (modèle DISTINCT des propriétaires).
#  Un contributeur est un crédit libre : nom + rôle + email + lien. Il N'A PAS
#  besoin d'être un utilisateur Pod (ex : un intervenant externe).
#  → À distinguer du "propriétaire additionnel" (script 05) qui, lui, est un
#    compte Pod disposant de droits d'édition sur la vidéo.
#
#  Le champ "video" relie le crédit à une vidéo et attend son URL complète.
#
#  Rôles usuels : actor author designer consultant editor speaker
#                 soundman writer publisher ...
#
#  Usage :
#    source ./config.sh
#    ./06_ajouter_contributeur.sh \
#       "https://videos.utoulouse.fr/rest/videos/123/" \
#       "Jean Dupont" "jean.dupont@univ-tlse.fr" "author" "https://exemple.fr"
# ============================================================================
set -uo pipefail
source "$(dirname "$0")/config.sh"

VIDEO_URL="${1:?url de la vidéo requise}"   # URL de la vidéo à créditer
NAME="${2:?nom requis}"                      # nom affiché du contributeur
EMAIL="${3:-}"                               # email (facultatif)
ROLE="${4:-author}"                          # rôle (défaut : author)
WEBLINK="${5:-}"                             # lien web (facultatif)

echo "▶ Ajout du contributeur « ${NAME} » (${ROLE}) ..."
# POST multipart : chaque -F est un champ du contributeur à créer.
# Attention au nom de champ "email_address" (et non "email") côté Pod.
curl -s -H "${AUTH_HEADER}" \
  -F "video=${VIDEO_URL}" \
  -F "name=${NAME}" \
  -F "email_address=${EMAIL}" \
  -F "role=${ROLE}" \
  -F "weblink=${WEBLINK}" \
  "${POD_URL}/rest/contributors/" | head -c 600
echo -e "\n  ✅ Terminé."
