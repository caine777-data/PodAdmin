#!/usr/bin/env bash
# ============================================================================
#  02_lister_types.sh — Lister les "types" de vidéo
#
#  POURQUOI : le champ "type" d'une vidéo est OBLIGATOIRE et doit être l'URL
#  complète d'un type (ex : .../rest/types/4/), pas un libellé ni un ID.
#  Ce script liste les types disponibles et leur URL.
#
#  Usage :   source ./config.sh && ./02_lister_types.sh
# ============================================================================
set -uo pipefail
source "$(dirname "$0")/config.sh"

echo "▶ Types de vidéo disponibles :"
# GET simple sur /rest/types/ ; on demande du JSON via l'en-tête Accept.
curl -s -H "${AUTH_HEADER}" -H "Accept: application/json" \
  "${POD_URL}/rest/types/" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
# Pour chaque type : son titre lisible + l'URL à mettre dans le champ 'type'.
for t in d.get('results', []):
    print(f\"  {t.get('title','?'):24} → type = {t.get('url','?')}\")
"
