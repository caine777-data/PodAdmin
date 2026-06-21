#!/usr/bin/env bash
# ============================================================================
#  00_test_connexion.sh — Test de connexion + DÉCOUVERTE de l'API
#
#  Objectif : vérifier que le token fonctionne ET révéler les champs EXACTS
#  attendus par VOTRE instance (ils peuvent varier selon la configuration).
#
#  Usage :   source ./config.sh && ./00_test_connexion.sh
# ============================================================================

# set -u : erreur si une variable non définie est utilisée.
# set -o pipefail : un pipe (commande | commande) échoue si l'une des étapes échoue.
set -uo pipefail

# Charger l'URL, le token et l'en-tête d'authentification (voir config.sh).
source "$(dirname "$0")/config.sh"

echo "════════════════════════════════════════════════════════════"
echo "  Test de connexion à : ${POD_URL}/rest/"
echo "════════════════════════════════════════════════════════════"

# ── 1) Le token est-il valide ? ────────────────────────────────────────────
#    On demande la liste des vidéos en se limitant à 1 résultat (?limit=1).
#    Options curl utilisées :
#      -s              : mode silencieux (pas de barre de progression)
#      -o FICHIER      : écrire le CORPS de la réponse dans un fichier
#      -w "%{http_code}": afficher (write-out) UNIQUEMENT le code HTTP de retour
#      -H "..."        : ajouter un en-tête HTTP (ici l'authentification)
echo -e "\n▶ 1. Test du token (GET /rest/videos/) ..."
HTTP_CODE=$(curl -s -o /tmp/pod_test.json -w "%{http_code}" \
  -H "${AUTH_HEADER}" -H "Accept: application/json" \
  "${POD_URL}/rest/videos/?limit=1")

# Code 200 = OK. Sinon, on affiche le début de la réponse pour diagnostiquer.
if [[ "${HTTP_CODE}" == "200" ]]; then
  # grep extrait "count":NOMBRE depuis le JSON, cut récupère la partie après ":".
  COUNT=$(grep -o '"count":[0-9]*' /tmp/pod_test.json | head -1 | cut -d: -f2)
  echo "  ✅ Connexion OK — ${COUNT:-?} vidéo(s) accessibles avec ce token."
else
  echo "  ❌ Échec (HTTP ${HTTP_CODE}). Vérifiez l'URL et le token."
  echo "     Réponse : $(head -c 300 /tmp/pod_test.json)"
  exit 1
fi

# ── 2) DÉCOUVERTE des champs attendus à l'upload ──────────────────────────
#    La méthode HTTP OPTIONS sur un point d'accès DRF renvoie son "schéma" :
#    la liste des champs, leur type, et s'ils sont obligatoires.
#      -X OPTIONS : forcer la méthode HTTP OPTIONS (au lieu de GET par défaut)
#    On passe le JSON à un petit script Python pour l'afficher proprement.
echo -e "\n▶ 2. Champs attendus par POST /rest/videos/ (OPTIONS) ..."
curl -s -X OPTIONS -H "${AUTH_HEADER}" -H "Accept: application/json" \
  "${POD_URL}/rest/videos/" \
  | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    # 'actions' -> 'POST' contient le schéma des champs pour créer une vidéo.
    post = d.get('actions', {}).get('POST', {})
    if not post:
        print('   (OPTIONS ne renvoie pas le schéma — utilisez la page web /rest/videos/)')
    for name, meta in post.items():
        req = '★ REQUIS' if meta.get('required') else '  optionnel'
        typ = meta.get('type', '?')
        print(f'   {req:12} {name:24} ({typ})')
except Exception as e:
    print('   Impossible de parser le schéma :', e)
" 2>/dev/null || echo "   (python3 indisponible — ouvrez ${POD_URL}/rest/videos/ dans un navigateur)"

# ── 3) Vérifier la présence des points d'accès utilisés par l'appli ───────
echo -e "\n▶ 3. Endpoints disponibles ..."
for ep in users types videos channels contributors; do
  # On ne garde que le code HTTP (-o /dev/null jette le corps de la réponse).
  code=$(curl -s -o /dev/null -w "%{http_code}" -H "${AUTH_HEADER}" "${POD_URL}/rest/${ep}/?limit=1")
  [[ "${code}" == "200" ]] && echo "   ✅ /rest/${ep}/" || echo "   ⚠️  /rest/${ep}/  (HTTP ${code})"
done

echo -e "\n════════════════════════════════════════════════════════════"
echo "  Astuce : ouvrez ${POD_URL}/rest/ dans un navigateur (connecté"
echo "  en admin) pour explorer visuellement tous les champs."
echo "════════════════════════════════════════════════════════════"
