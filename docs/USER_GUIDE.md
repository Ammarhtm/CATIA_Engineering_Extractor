# Guide d'utilisation — Windows / CATIA V5

## Prérequis

- Windows, CATIA V5 installé et lancé ; pièce `.CATPart` ouverte dans la fenêtre active.
- Python 3.10 ou ultérieur, idéalement Python 3.11 pour reproduire les essais.
- Tesseract OCR Windows installé séparément, accessible par `tesseract --version`.
- Dépendances Python déclarées dans `pyproject.toml` : `pywin32`, `numpy`, `opencv-python`, `pyautogui`, `pytesseract`, `Pillow`, `openpyxl`.

## Installation

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

En cas de blocage de l'activation PowerShell, lancer directement `\.venv\Scripts\python.exe -m pip install -e ".[dev]"` et utiliser le même exécutable pour démarrer le logiciel.

## Utilisation graphique

1. Lancer `python -m catia_extractor.frontend.desktop_app` depuis la racine du dépôt (ou le fichier `.bat`).
2. Ouvrir la pièce dans CATIA. Garder CATIA visible et éviter de manipuler l'écran pendant les captures.
3. Cliquer **Start Extraction**, confirmer que la pièce est ouverte ; la GUI se minimise et suit les étapes dans le journal.
4. Dans **Human Review**, parcourir les images `full_frame.png`, comparer les valeurs avec le modèle CATIA, saisir nom et notes si nécessaire.
5. Pour chaque annotation, choisir explicitement **Approuver**, **Corriger & approuver**, **Rejeter** ou **Passer**. Les avertissements restent visibles dans la traçabilité.
6. Dans **Export Center**, choisir Excel / CSV ZIP / JSON, puis le chemin de sauvegarde.

## Rapport de revue

Un statut `needs_attention` signale une lecture qui doit être vérifiée (par exemple la tolérance `0` ou une ambiguïté OCR). Un statut `ready_for_human_review` indique seulement que les contrôles automatiques ne détectent pas d'anomalie ; la signature humaine reste nécessaire. Ne pas approuver une valeur sans inspection réelle.

## Dépannage

- **`pywin32 n'est pas installé`** : `python -m pip install pywin32`, dans le même interpréteur.
- **`tesseract` introuvable** : ajouter l'exécutable à `PATH` ou renseigner `pytesseract.pytesseract.tesseract_cmd` ; installer la bibliothèque Python seule ne suffit pas.
- **L'image de GD&T est petite** : vérifier le module `frontend/desktop_app.py`, Pillow et ouvrir l'image source ; la résolution native reste limitée par la capture.
- **`ModuleNotFoundError: catia_extractor`** : lancer depuis la racine après `pip install -e .`, ou définir `$env:PYTHONPATH = 'src'`.
- **`source code string cannot contain null bytes`** : enregistrer le fichier concerné en UTF-8 (pas UTF-16).
- **Approbation supprimée après une nouvelle extraction** : comportement attendu si les données/signatures de preuve changent ; recommencer la revue humaine.
- **Excel absent** : vérifier `python -c "import openpyxl; print(openpyxl.__version__)"`.

## Données personnelles / industrielles

Tous les rapports et images restent dans `output/` local, ignoré par Git. Ne publiez pas de CATParts client ou de rapports comportant des informations industrielles confidentielles.
