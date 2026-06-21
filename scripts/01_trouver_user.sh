#!/usr/bin/env bash
# ============================================================================
#  01_trouver_user.sh — Résoudre un utilisateur → son URL REST
#
#  POURQUOI : dans Esup-Pod, le champ "owner" (propriétaire) d'une vidéo doit
#  être l'URL COMPLÈTE de l'utilisateur (ex : .../rest/users/42/), pas son ID.
#  Ce script trouve cette URL à partir d'un nom d'utilisateur.
#
#  Usage :   source ./config.sh && ./01_trouver_user.sh p.dupont
# ============================================================================
set -uo pipefail
source "$(dirname "$0")/config.sh"

# $1 = premier argument passé au script. ${1:-} = "" s'il est absent (évite l'erreur).
QUERY="${1:-}"
if [[ -z "${QUERY}" ]]; then
  echo "Usage : $0 <username ou nom à rechercher>"
  exit 1
fi

# ── Recherche via le paramètre ?search= de l'API ──────────────────────────
#    L'endpoint /rest/users/ accepte une recherche plein texte sur le nom.
echo "▶ Recherche de « ${QUERY} » ..."
curl -s -H "${AUTH_HEADER}" -H "Accept: application/json" \
  "${POD_URL}/rest/users/?search=${QUERY}" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
# La réponse paginée a la forme {count, next, previous, results:[...]}.
results = d.get('results', d if isinstance(d, list) else [])
if not results:
    print('  Aucun utilisateur trouvé.'); sys.exit()
for u in results:
    print(f\"  {u.get('username','?'):20} {u.get('first_name','')} {u.get('last_name','')}\")
    # C'est cette URL qu'il faut utiliser comme valeur du champ owner.
    print(f\"      → owner = {u.get('url','?')}\")
"
