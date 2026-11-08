---
name: python-venv-requests
description: Crée un environnement virtuel Python isolé pour un projet, y installe une version figée de requests et enregistre les dépendances dans requirements.txt. À utiliser quand l'utilisateur veut « créer un venv », « isoler les dépendances d'un projet Python », « installer requests proprement » ou « générer un requirements.txt ».
---

# Environnement virtuel Python + requests figé

> Vérification : 6/6 étapes exécutées avec succès le 2026-11-08 (Linux, Python 3.13) dans un dossier jetable.
> Non vérifié : Windows (commande d'activation différente, voir Variantes).

À la fin : un dossier `.venv/` isolé, `requests` 2.32.3 installé dedans, et un `requirements.txt` qui permet de recréer l'environnement à l'identique.

## Prérequis
- Python 3 accessible via `python3` [t=0:08]
- Terminal ouvert à la racine du projet (`~/projet` dans la vidéo) [t=0:05]

## Étapes

### 1. Créer l'environnement virtuel
```bash
python3 -m venv .venv
```
✔ Réussite : aucun message d'erreur, un dossier `.venv/` existe. [t=0:08]

### 2. L'activer
```bash
source .venv/bin/activate
```
✔ Réussite : le prompt commence par `(.venv)`. [t=0:19]

### 3. Installer requests en version figée
```bash
pip install requests==2.32.3
```
La version exacte vient de l'écran : la narration dit « request, version 2.32 », l'écran montre `requests==2.32.3` [t=0:23].
✔ Réussite : la dernière ligne contient `Successfully installed … requests-2.32.3`, avec les dépendances certifi, charset-normalizer, idna, urllib3. [t=0:23]

### 4. Vérifier l'installation
```bash
python -c "import requests; print(requests.__version__)"
```
✔ Réussite : affiche `2.32.3`. [t=0:31]

### 5. Figer les dépendances
```bash
pip freeze > requirements.txt
```
[t=0:36]

### 6. Contrôler le fichier
```bash
grep requests requirements.txt
```
✔ Réussite : affiche `requests==2.32.3`. [t=0:45]

## Variantes
- ➕ ajouté : sous Windows (PowerShell), l'activation est `.venv\Scripts\Activate.ps1` (source : https://docs.python.org/3/library/venv.html).
- ➕ ajouté : recréer l'environnement ailleurs → `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` (même source).
- Autre version de requests : remplacer `2.32.3` à l'étape 3 ; la vidéo ne traite que celle-ci.

## Dépannage
- `(.venv)` n'apparaît pas → l'étape 2 a été lancée avec `sh` au lieu de `bash`/`zsh` : utiliser `. .venv/bin/activate`. (➕ ajouté, même source)
- ➕ ajouté : ajouter `.venv/` au `.gitignore` pour ne pas versionner l'environnement.

## Source
- Vidéo : « Python : environnement virtuel » — vidéo de test générée par `tests/make_test_video.py`
- Transcription : sous-titres fournis (.srt)
- Extrait le 2026-11-08 avec video-to-skill
