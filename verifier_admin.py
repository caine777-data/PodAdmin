#!/usr/bin/env python3
"""
verifier_admin.py — Diagnostic Phase 0 pour la CONSOLE D'ADMINISTRATION Pod
===========================================================================
Étend verifier.py : au lieu de valider seulement l'upload, ce script vérifie
ce que l'API REST de l'instance autorise pour les futures fonctions d'admin :

  - Comptes / statut « équipe » (is_staff) : modifiable via l'API ou non ?
  - Réaffectation de propriétaire : le champ owner d'une vidéo est-il modifiable ?
  - Nettoyage / modération : quels champs indiquent le statut d'encodage ?
  - Chaînes & thèmes : création / MODIFICATION (PATCH) / SUPPRESSION (DELETE) ?

Sections 1 à 5 : LECTURE SEULE (uniquement GET et OPTIONS) — sans danger.
Section 6  : test aller-retour OPTIONNEL et explicitement consenti. Il écrit
            réellement, mais UNIQUEMENT sur un objet jetable qu'il crée lui-même
            (préfixe « ZZZ_TEST_PODADMIN »), jamais sur des données existantes,
            et il nettoie derrière lui. Tapez OUI pour l'activer, sinon il est
            ignoré et le diagnostic reste 100 % lecture seule.

À lancer avec un token de compte SUPERUTILISATEUR (sinon la plupart des
endpoints d'admin renverront 403).

Lancement :  python verifier_admin.py
"""

import sys
import requests

DEFAULT_URL = "https://videos.utoulouse.fr"

# Mots-clés repérant un champ lié au statut d'encodage (pour le module Nettoyage)
ENCODING_HINTS = ("encod", "encoded", "is_video", "is_audio", "process",
                  "draft", "duration", "transcript")


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def get_json(rest, ep, headers, params=None):
    """GET simple, renvoie (status, data|None)."""
    try:
        r = requests.get(f"{rest}{ep}", headers=headers, params=params, timeout=20)
        data = r.json() if r.text else None
        return r.status_code, data
    except Exception as e:
        return None, {"_error": str(e)}


def first_result(data):
    """Renvoie le 1er élément d'une réponse paginée {results:[...]} ou d'une liste."""
    if isinstance(data, dict):
        res = data.get("results", [])
        return res[0] if res else None
    if isinstance(data, list) and data:
        return data[0]
    return None


def options_report(url, headers, label):
    """
    OPTIONS sur une URL. Affiche les méthodes autorisées (en-tête Allow)
    et renvoie un dict {allow, actions, status} pour analyse.
    """
    print(f"\n   ▷ OPTIONS {label}")
    try:
        r = requests.options(url, headers=headers, timeout=20)
    except Exception as e:
        print(f"     ❌ {e}")
        return None
    allow = r.headers.get("Allow", "(en-tête Allow non fourni)")
    print(f"     Méthodes autorisées : {allow}")
    actions = {}
    try:
        actions = (r.json() or {}).get("actions", {})
    except Exception:
        pass
    return {"allow": allow, "actions": actions, "status": r.status_code}


def field_is_writable(actions, verb, field):
    """
    Vrai si <field> apparaît dans actions[verb] et n'est pas read_only.
    DRF n'expose actions['PUT'] que si la méthode est réellement permise.
    """
    meta = actions.get(verb, {}).get(field)
    if meta is None:
        return None  # champ non exposé pour cette méthode
    return not meta.get("read_only", False)


def verdict(label, ok):
    mark = {True: "✅ OK", False: "⛔ NON", None: "⚠️  À VÉRIFIER"}[ok]
    print(f"   {mark:18} {label}")


def _all_true(results, *keys):
    """Synthèse de plusieurs résultats : True si tous vrais, False si l'un est
    faux, None si indéterminé."""
    vals = [results.get(k) for k in keys]
    if all(v is True for v in vals):
        return True
    if any(v is False for v in vals):
        return False
    return None


# --------------------------------------------------------------------------- #
#  Helpers d'ÉCRITURE (utilisés uniquement par le test aller-retour, section 6)
# --------------------------------------------------------------------------- #
def post_json(rest, ep, headers, payload):
    """POST JSON, renvoie (status, data|None)."""
    r = requests.post(f"{rest}{ep}",
                      headers={**headers, "Content-Type": "application/json"},
                      json=payload, timeout=20)
    return r.status_code, (r.json() if r.text else None)


def patch_json(url, headers, payload):
    """PATCH JSON sur une URL absolue, renvoie (status, data|None)."""
    r = requests.patch(url, headers={**headers, "Content-Type": "application/json"},
                       json=payload, timeout=20)
    return r.status_code, (r.json() if r.text else None)


def delete_req(url, headers):
    """DELETE sur une URL absolue, renvoie le status HTTP."""
    return requests.delete(url, headers=headers, timeout=20).status_code


def live_write_test(rest, headers, results):
    """
    Test aller-retour OPTIONNEL confirmant PATCH et DELETE sur chaînes/thèmes.

    ⚠️ Ce test ÉCRIT réellement, mais UNIQUEMENT sur un objet qu'il crée lui-même
       (préfixe « ZZZ_TEST_PODADMIN ») : il ne touche JAMAIS à vos chaînes ou
       thèmes existants, et il supprime ce qu'il a créé (y compris en cas
       d'erreur, via le bloc finally).
    """
    print("\n" + "─" * 70)
    print("▶ 6. Test aller-retour PATCH/DELETE (OPTIONNEL — écrit puis nettoie)")
    print("─" * 70)
    print("  Ce test va CRÉER une chaîne et un thème temporaires, les RENOMMER,")
    print("  puis les SUPPRIMER. Il ne touche à AUCUN objet existant.")
    ans = input("  Tapez OUI pour lancer (toute autre entrée = ignorer) : ").strip()
    if ans != "OUI":
        print("  → Ignoré. Le diagnostic reste 100 % lecture seule.")
        return

    import time
    tag = f"ZZZ_TEST_PODADMIN_{int(time.time())}"  # nom unique et reconnaissable
    chan_url = None
    theme_url = None
    try:
        # 1) Créer une chaîne temporaire (champs requis : title + themes)
        payload = {"title": tag, "themes": []}
        st, body = post_json(rest, "/channels/", headers, payload)
        # Certaines instances exigent aussi un 'site' → on réessaie avec
        if st == 400 and isinstance(body, dict) and "site" in body:
            _, sites = get_json(rest, "/sites/", headers, {"limit": 1})
            site = first_result(sites)
            if site and site.get("url"):
                payload["site"] = site["url"]
                st, body = post_json(rest, "/channels/", headers, payload)
        if st in (200, 201) and isinstance(body, dict):
            chan_url = body.get("url")
            results["live_channel_create"] = True
            print(f"  ✅ Chaîne créée : {chan_url}")
        else:
            results["live_channel_create"] = False
            print(f"  ⛔ Création chaîne refusée (HTTP {st}) : {str(body)[:200]}")
            return   # inutile de continuer sans chaîne

        # 2) PATCH la chaîne (renommage)
        st, _ = patch_json(chan_url, headers, {"title": tag + "_MOD"})
        results["live_channel_patch"] = st in (200, 202)
        print(f"  {'✅' if results['live_channel_patch'] else '⛔'} PATCH chaîne → HTTP {st}")

        # 3) Créer un thème dans cette chaîne (champs requis : title + channel)
        st, body = post_json(rest, "/themes/", headers,
                             {"title": tag, "channel": chan_url})
        if st in (200, 201) and isinstance(body, dict):
            theme_url = body.get("url")
            results["live_theme_create"] = True
            print(f"  ✅ Thème créé : {theme_url}")
        else:
            results["live_theme_create"] = False
            print(f"  ⛔ Création thème refusée (HTTP {st}) : {str(body)[:200]}")

        # 4) PATCH le thème
        if theme_url:
            st, _ = patch_json(theme_url, headers, {"title": tag + "_MOD"})
            results["live_theme_patch"] = st in (200, 202)
            print(f"  {'✅' if results['live_theme_patch'] else '⛔'} PATCH thème → HTTP {st}")

        # 5) DELETE le thème
        if theme_url:
            st = delete_req(theme_url, headers)
            results["live_theme_delete"] = st in (200, 204)
            print(f"  {'✅' if results['live_theme_delete'] else '⛔'} DELETE thème → HTTP {st}")
            if results["live_theme_delete"]:
                theme_url = None   # supprimé → plus rien à nettoyer

        # 6) DELETE la chaîne
        st = delete_req(chan_url, headers)
        results["live_channel_delete"] = st in (200, 204)
        print(f"  {'✅' if results['live_channel_delete'] else '⛔'} DELETE chaîne → HTTP {st}")
        if results["live_channel_delete"]:
            chan_url = None

    except Exception as e:
        print(f"  ❌ Erreur pendant le test : {e}")
    finally:
        # Filet de sécurité : supprimer tout objet de test encore présent
        for u, kind in ((theme_url, "thème"), (chan_url, "chaîne")):
            if u:
                try:
                    st = delete_req(u, headers)
                    print(f"  🧹 Nettoyage {kind} → HTTP {st}")
                except Exception as e:
                    print(f"  ⚠️  Nettoyage {kind} échoué ({e}). "
                          f"À supprimer manuellement : {u}")


# --------------------------------------------------------------------------- #
#  Main
# --------------------------------------------------------------------------- #
def main():
    print("=" * 70)
    print("  Console d'admin Pod — Diagnostic Phase 0 (lecture seule)")
    print("=" * 70)

    url = input(f"\nURL de l'instance [{DEFAULT_URL}] : ").strip() or DEFAULT_URL
    url = url.rstrip("/")
    print("\nCollez le token d'un compte SUPERUTILISATEUR :")
    token = input("Token : ").strip()
    if not token:
        print("\n❌ Aucun token saisi. Abandon.")
        return

    rest = f"{url}/rest"
    headers = {"Authorization": f"Token {token}", "Accept": "application/json"}

    results = {}  # pour le verdict final

    # ----------------------------------------------------------------- #
    # 1) Le token fonctionne-t-il ?
    # ----------------------------------------------------------------- #
    print("\n▶ 1. Validité du token (GET /rest/videos/) ...")
    status, data = get_json(rest, "/videos/", headers, {"limit": 1})
    if status == 200 and isinstance(data, dict):
        print(f"   ✅ Connexion OK — {data.get('count', '?')} vidéo(s) visibles.")
    else:
        print(f"   ❌ Échec (HTTP {status}). Vérifiez URL et token.")
        if isinstance(data, dict) and data.get("_error"):
            print(f"      {data['_error']}")
        return

    # ----------------------------------------------------------------- #
    # 2) Le token est-il superutilisateur ? (liste des utilisateurs)
    # ----------------------------------------------------------------- #
    print("\n▶ 2. Droits superutilisateur (GET /rest/users/) ...")
    status, data = get_json(rest, "/users/", headers, {"limit": 5})
    sample_user = None
    if status == 200:
        sample_user = first_result(data)
        count = data.get("count") if isinstance(data, dict) else len(data or [])
        if sample_user:
            print(f"   ✅ Utilisateurs listables — {count} compte(s).")
            print(f"      Champs exposés : {list(sample_user.keys())}")
            results["is_superuser"] = True
        else:
            print("   ⚠️  Liste VIDE → token probablement NON superutilisateur.")
            results["is_superuser"] = False
    elif status in (401, 403):
        print(f"   ⛔ Accès refusé (HTTP {status}). Ce token n'est PAS superadmin.")
        print("      → Beaucoup de fonctions d'admin seront indisponibles.")
        results["is_superuser"] = False
    else:
        print(f"   ⚠️  Réponse inattendue (HTTP {status}).")
        results["is_superuser"] = None

    # ----------------------------------------------------------------- #
    # 3) MODULE COMPTES : peut-on modifier is_staff via l'API ?
    # ----------------------------------------------------------------- #
    print("\n▶ 3. Module COMPTES — statut « équipe » (is_staff) modifiable ?")
    if sample_user and sample_user.get("url"):
        rep = options_report(sample_user["url"], headers, "/rest/users/<id>/")
        if rep:
            can_write = ("PATCH" in rep["allow"]) or ("PUT" in rep["allow"])
            staff_writable = field_is_writable(rep["actions"], "PUT", "is_staff")
            print(f"     'is_staff' présent dans les champs ? "
                  f"{'is_staff' in sample_user}")
            print(f"     'is_staff' modifiable (non read_only) ? {staff_writable}")
            if can_write and staff_writable:
                results["module_comptes"] = True
                print("     → 🎯 Modifiable directement : "
                      "PATCH /rest/users/<id>/ {\"is_staff\": true}")
            elif not can_write:
                results["module_comptes"] = False
                print("     → Endpoint utilisateurs en LECTURE SEULE.")
                print("       Plan B : petite extension côté serveur Pod "
                      "(sérialiseur + permission admin).")
            else:
                results["module_comptes"] = None
                print("     → PATCH permis mais 'is_staff' non modifiable. "
                      "À confirmer dans l'interface /rest/.")
    else:
        results["module_comptes"] = None
        print("   ⚠️  Pas d'utilisateur exploitable (token non superadmin ?).")

    # ----------------------------------------------------------------- #
    # 4) MODULES VIDÉOS : owner modifiable + champs d'encodage
    # ----------------------------------------------------------------- #
    print("\n▶ 4. Modules RÉAFFECTATION & NETTOYAGE (sur une vidéo) ...")
    status, data = get_json(rest, "/videos/", headers, {"limit": 1})
    sample_video = first_result(data)
    if sample_video:
        slug = sample_video.get("slug", "?")
        vurl = sample_video.get("url") or f"{rest}/videos/{slug}/"
        print(f"   Vidéo témoin : slug={slug}")
        print(f"   Champs exposés : {list(sample_video.keys())}")

        # Champs liés au statut d'encodage (pour le module Nettoyage)
        enc_fields = [k for k in sample_video
                      if any(h in k.lower() for h in ENCODING_HINTS)]
        print(f"   Champs utiles au nettoyage : {enc_fields or '(aucun repéré)'}")
        for k in enc_fields:
            print(f"     • {k} = {sample_video.get(k)!r}")

        rep = options_report(vurl, headers, "/rest/videos/<slug>/")
        if rep:
            can_patch = "PATCH" in rep["allow"]
            owner_w = field_is_writable(rep["actions"], "PUT", "owner")
            draft_w = field_is_writable(rep["actions"], "PUT", "is_draft")
            results["module_reaffect"] = bool(can_patch and owner_w)
            results["module_nettoyage"] = bool(can_patch)
            print(f"     PATCH autorisé ? {can_patch}")
            print(f"     'owner' modifiable ? {owner_w}")
            print(f"     'is_draft' modifiable ? {draft_w}")
            print(f"     DELETE autorisé ? {'DELETE' in rep['allow']}")
    else:
        results["module_reaffect"] = None
        results["module_nettoyage"] = None
        print("   ⚠️  Aucune vidéo disponible pour tester.")

    # ----------------------------------------------------------------- #
    # 5) MODULE CHAÎNES & THÈMES : création / modification possibles ?
    # ----------------------------------------------------------------- #
    print("\n▶ 5. Module CHAÎNES & THÈMES ...")
    for ep in ("channels", "themes"):
        status, data = get_json(rest, f"/{ep}/", headers, {"limit": 1})
        print(f"   /rest/{ep}/ → HTTP {status}")
        if status != 200:
            results[f"module_{ep}"] = None
            continue
        sample = first_result(data)
        if sample:
            print(f"     Champs : {list(sample.keys())}")
        rep = options_report(f"{rest}/{ep}/", headers, f"/rest/{ep}/ (liste)")
        if rep:
            can_create = "POST" in rep["allow"] or bool(rep["actions"].get("POST"))
            print(f"     Création (POST) autorisée ? {can_create}")
            if rep["actions"].get("POST"):
                req = [n for n, m in rep["actions"]["POST"].items()
                       if m.get("required")]
                print(f"     Champs requis à la création : {req}")
            results[f"module_{ep}"] = bool(can_create)

        # Détail : MODIFIER (PATCH/PUT) et SUPPRIMER (DELETE) sont-ils permis ?
        if sample and sample.get("url"):
            rep2 = options_report(sample["url"], headers, f"/rest/{ep}/<id>/ (détail)")
            if rep2:
                can_patch = ("PATCH" in rep2["allow"]) or ("PUT" in rep2["allow"])
                can_delete = "DELETE" in rep2["allow"]
                title_w = field_is_writable(rep2["actions"], "PUT", "title")
                print(f"     Modification (PATCH) autorisée ? {can_patch}")
                print(f"     'title' modifiable ? {title_w}")
                print(f"     Suppression (DELETE) autorisée ? {can_delete}")
                results[f"module_{ep}_patch"] = bool(can_patch)
                results[f"module_{ep}_delete"] = bool(can_delete)
        else:
            print("     (aucun élément existant pour tester le détail)")

    # ----------------------------------------------------------------- #
    # 6) Test aller-retour optionnel (écrit puis nettoie un objet jetable)
    # ----------------------------------------------------------------- #
    live_write_test(rest, headers, results)

    # ----------------------------------------------------------------- #
    # VERDICT
    # ----------------------------------------------------------------- #
    print("\n" + "=" * 70)
    print("  VERDICT — faisabilité par module")
    print("=" * 70)
    verdict("Token superutilisateur", results.get("is_superuser"))
    verdict("Comptes / statut équipe (is_staff)", results.get("module_comptes"))
    verdict("Réaffectation de propriétaire (owner)", results.get("module_reaffect"))
    verdict("Nettoyage / modération (PATCH vidéos)", results.get("module_nettoyage"))
    verdict("Chaînes — création", results.get("module_channels"))
    verdict("Chaînes — modification (PATCH)", results.get("module_channels_patch"))
    verdict("Chaînes — suppression (DELETE)", results.get("module_channels_delete"))
    verdict("Thèmes — création", results.get("module_themes"))
    verdict("Thèmes — modification (PATCH)", results.get("module_themes_patch"))
    verdict("Thèmes — suppression (DELETE)", results.get("module_themes_delete"))

    # Résultats du test aller-retour réel, si l'utilisateur l'a lancé
    if any(k.startswith("live_") for k in results):
        print("\n  — Confirmation par test aller-retour réel —")
        verdict("Chaîne : créer + modifier + supprimer",
                _all_true(results, "live_channel_create",
                          "live_channel_patch", "live_channel_delete"))
        verdict("Thème : créer + modifier + supprimer",
                _all_true(results, "live_theme_create",
                          "live_theme_patch", "live_theme_delete"))

    print("\n  Inventaire / stats : toujours faisable (lecture seule), non testé ici.")
    print("=" * 70)
    print("  Copie ce verdict ici : il pilote l'ordre de développement.")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
    input("\nAppuyez sur Entrée pour fermer...")
