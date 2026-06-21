#!/usr/bin/env bash
# ============================================================================
#  03_upload_video.sh — Téléverser UNE vidéo (sans lancer l'encodage)
#
#  Appel : POST /rest/videos/  en multipart/form-data (envoi de fichier).
#  IMPORTANT : owner et type doivent être des URLs (voir scripts 01 et 02).
#  L'upload NE lance PAS l'encodage → voir le script 04.
#
#  Usage :
#    source ./config.sh
#    ./03_upload_video.sh "/chemin/video.mp4" "Mon titre" \
#         "https://videos.utoulouse.fr/rest/users/42/" \
#         "https://videos.utoulouse.fr/rest/types/4/"
# ============================================================================
set -uo pipefail
source "$(dirname "$0")/config.sh"

# Arguments du script. La syntaxe ${1:?message} arrête le script avec un
# message d'erreur clair si l'argument est manquant.
FILE="${1:?chemin du fichier requis}"
TITLE="${2:?titre requis}"
OWNER_URL="${3:?url owner requise}"
TYPE_URL="${4:?url type requise}"

# Champs souvent requis selon l'instance. ${VAR:-defaut} = valeur par défaut
# si la variable n'est pas définie dans l'environnement. Le script 00 révèle
# les champs réellement requis sur VOTRE instance (ici notamment "sites").
MAIN_LANG="${MAIN_LANG:-fr}"
CURSUS="${CURSUS:-0}"          # 0 = "Aucun / Tous"
IS_DRAFT="${IS_DRAFT:-true}"   # true = Brouillon/Privé par défaut

# Vérifier que le fichier existe avant de tenter l'envoi.
if [[ ! -f "${FILE}" ]]; then
  echo "❌ Fichier introuvable : ${FILE}"; exit 1
fi

# ── Envoi multipart ────────────────────────────────────────────────────────
#    -F "champ=valeur"   : ajoute un champ de formulaire (multipart/form-data)
#    -F "video=@/chemin" : le @ indique que la valeur est le CONTENU d'un
#                          fichier à téléverser (et non le texte "/chemin").
echo "▶ Upload de « ${TITLE} » (${FILE}) ..."
RESP=$(curl -s -H "${AUTH_HEADER}" \
  -F "owner=${OWNER_URL}" \
  -F "type=${TYPE_URL}" \
  -F "title=${TITLE}" \
  -F "main_lang=${MAIN_LANG}" \
  -F "cursus=${CURSUS}" \
  -F "is_draft=${IS_DRAFT}" \
  -F "video=@${FILE}" \
  "${POD_URL}/rest/videos/")

# La réponse JSON contient le "slug" de la vidéo créée : c'est cet identifiant
# qui sert ensuite à lancer l'encodage (script 04).
SLUG=$(echo "${RESP}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('slug',''))" 2>/dev/null)

if [[ -n "${SLUG}" ]]; then
  echo "  ✅ Vidéo créée. slug = ${SLUG}"
  echo "     Pour lancer l'encodage : ./04_lancer_encodage.sh ${SLUG}"
else
  echo "  ❌ Échec ou réponse inattendue :"
  echo "${RESP}" | head -c 600
fi
