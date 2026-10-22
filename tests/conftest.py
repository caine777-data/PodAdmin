"""Isolement de TOUTE la suite de tests.

Chargé par pytest avant le moindre test, donc avant que `config`,
`enrichissement.reglages` ou `app` ne calculent leurs chemins. Deux choses :

  • DOSSIER PERSONNEL TEMPORAIRE. Les tests créent des `App()` : sans cela,
    ils lisaient le vrai ~/.podadmin.json et écrivaient dans le vrai Journal
    (~/.podadmin/journal-*.log), où leurs lignes (« 9.9.9 », « FausseAPI »…)
    se mêlaient aux vrais événements. Depuis l'onglet Enrichissement IA, ils
    auraient aussi lu et modifié les vrais projets de ~/.soustitreur.
    Sous Windows, `expanduser` lit USERPROFILE ; ailleurs, HOME : on règle
    les deux. Les sous-processus lancés par les tests héritent du réglage.

  • COFFRE-FORT VIDE. Avec le vrai coffre, le jeton de l'utilisateur était
    trouvé et l'application SE CONNECTAIT réellement à l'instance pendant les
    tests. Le coffre « null » ne renvoie rien et ignore les écritures.
"""

import os
import tempfile

DOSSIER_PERSONNEL_REEL = os.path.expanduser("~")
DOSSIER_PERSONNEL_TESTS = tempfile.mkdtemp(prefix="podadmin-tests-")

os.environ["USERPROFILE"] = DOSSIER_PERSONNEL_TESTS
os.environ["HOME"] = DOSSIER_PERSONNEL_TESTS
os.environ["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
