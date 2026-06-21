#!/usr/bin/env bash
# ============================================================================
#  config.sh — Configuration commune à tous les scripts
#  Université de Toulouse — Esup-Pod (https://videos.utoulouse.fr)
#
#  À "sourcer" par les autres scripts (source = exécuter dans le shell courant
#  pour que les variables restent disponibles) :
#       source ./config.sh
# ============================================================================

# ── URL de l'instance Pod, SANS slash final ────────────────────────────────
#    La racine de l'API REST est ${POD_URL}/rest/  (et non /api/).
export POD_URL="https://videos.utoulouse.fr"

# ── Token d'authentification (compte de service) ───────────────────────────
#    Se crée dans l'interface d'admin Django :  ${POD_URL}/admin/authtoken/
#    Le token hérite des droits du compte choisi.
#
#    ${POD_TOKEN:-...}  signifie : "utiliser la variable POD_TOKEN si elle est
#    déjà définie dans l'environnement, sinon la valeur par défaut ci-dessous".
#    Bonne pratique : ne PAS écrire le vrai token ici, mais le définir avant :
#         export POD_TOKEN="votre_token"
export POD_TOKEN="${POD_TOKEN:-COLLEZ_VOTRE_TOKEN_ICI}"

# ── En-tête d'authentification réutilisable ────────────────────────────────
#    Toutes les requêtes envoient cet en-tête HTTP. C'est le mécanisme
#    d'authentification de l'API Esup-Pod (jeton, pas login/mot de passe).
export AUTH_HEADER="Authorization: Token ${POD_TOKEN}"

# ── Garde-fou : avertir si le token n'a pas été renseigné ──────────────────
if [[ "${POD_TOKEN}" == "COLLEZ_VOTRE_TOKEN_ICI" ]]; then
  echo "⚠️  Token non configuré. Faites : export POD_TOKEN=\"votre_token\"  (ou éditez config.sh)" >&2
fi
