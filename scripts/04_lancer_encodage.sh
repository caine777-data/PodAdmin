#!/usr/bin/env bash
# ============================================================================
#  04_lancer_encodage.sh — Lancer l'encodage d'une vidéo déjà téléversée
#
#  Appel : GET /rest/launch_encode_view/?slug=...
#  L'upload (script 03) crée la vidéo mais ne lance PAS l'encodage : il faut
#  cet appel séparé. Un courriel est envoyé en fin d'encodage par Pod.
#
#  Usage :   source ./config.sh && ./04_lancer_encodage.sh mon-slug-video
# ============================================================================
set -uo pipefail
source "$(dirname "$0")/config.sh"

# Le slug est renvoyé par le script 03 lors de la création de la vidéo.
SLUG="${1:?slug requis}"

echo "▶ Lancement de l'encodage pour : ${SLUG}"
# Simple GET avec le slug en paramètre d'URL. head -c 600 limite l'affichage.
curl -s -H "${AUTH_HEADER}" -H "Accept: application/json" \
  "${POD_URL}/rest/launch_encode_view/?slug=${SLUG}" \
  | head -c 600
echo -e "\n  ✅ Demande d'encodage envoyée (un mail sera envoyé en fin d'encodage)."
