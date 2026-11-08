# LLM_SETUP — guide d'installation pour un agent IA

> **Tu es un LLM (Claude Code, Cursor, Codex, Copilot…) et un développeur t'a demandé d'installer ou de faire marcher ce repo.**
> Suis ce fichier dans l'ordre. Le développeur ne doit **rien** avoir à faire, sauf s'il faut une décision ou un droit admin.

Ce que tu dois obtenir à la fin :
- les dépendances Python (`pillow`, `yt-dlp[default,curl-cffi]`, `faster-whisper`) ;
- `ffmpeg` + `ffprobe` utilisables ;
- un runtime JavaScript pour yt-dlp (deno, node ou bun) ;
- un modèle **Whisper** téléchargé et testé (transcription locale, hors ligne ensuite) ;
- le skill copié dans `~/.claude/skills/video-to-skill/` (pour Claude Code) ;
- un autotest qui passe, et un vrai téléchargement YouTube qui marche.

**Tout ça se fait avec une seule commande : `scripts/bootstrap.py`.** Ton travail : choisir le bon Python, lancer la commande, lire le rapport, corriger les ✗, vérifier, rendre compte.

---

## Étape 0 — Trouver le bon interpréteur Python

Teste dans l'ordre et garde le **premier qui affiche une version ≥ 3.9** (3.11+ conseillé) :

| OS | Commandes à essayer |
|---|---|
| Windows | `py -3 --version` → `python --version` |
| macOS / Linux | `python3 --version` → `python --version` |

⚠ **Piège Windows** : `python3` (et parfois `python`) peut être un faux raccourci du Microsoft Store qui affiche « Python est introuvable… » ou ouvre le Store. Ce n'est **pas** un Python. Passe à la commande suivante.

Aucun Python ≥ 3.9 ? Propose au développeur (ne le fais pas sans accord, ça modifie le système) :
- Windows : `winget install -e --id Python.Python.3.12`
- macOS : `brew install python@3.12`
- Debian/Ubuntu : `sudo apt install python3 python3-pip python3-venv`

Dans la suite, `PY` = la commande retenue (ex. `py -3`, `python3`).

**Quel Python ?** Utilise celui avec lequel le skill sera lancé ensuite (en général le Python global de l'utilisateur, car Claude Code appelle `python`/`python3`). Si le développeur veut isoler les paquets, crée un venv (`PY -m venv .venv`) et utilise `.venv/Scripts/python` (Windows) ou `.venv/bin/python` — dans ce cas, signale-lui que les scripts devront être lancés avec ce Python-là.

---

## Étape 1 — Lancer l'installation

Depuis la racine du repo :

```bash
PY scripts/bootstrap.py --json
```

- **C'est long** (2 à 10 min : téléchargement des paquets, de ffmpeg si absent, et du modèle Whisper). Donne à la commande un délai d'au moins **10 minutes** ou lance-la en arrière-plan. Ne l'interromps pas parce qu'elle est silencieuse.
- La progression s'affiche sur stderr, le **rapport JSON** sur stdout.
- C'est **idempotent** : tu peux relancer autant de fois que nécessaire.
- **Aucun droit admin**, jamais de `sudo`. Si ffmpeg manque, le script essaie `winget` (Windows) / `brew` (macOS), puis se rabat sur des binaires portables via pip (`static-ffmpeg`).

Options utiles :

| Option | Quand |
|---|---|
| `--check` | diagnostic seul, n'installe rien (à faire d'abord si tu veux montrer l'état au dev) |
| `--whisper-model tiny\|base\|small\|medium\|large-v3\|turbo` | choix du modèle (défaut `small`, voir tableau plus bas) |
| `--skip-model` | ne pas pré-télécharger le modèle (il le sera à la 1re transcription) |
| `--minimal` | pillow + ffmpeg seulement (fichiers locaux, sans URL ni transcription) |
| `--no-system` | n'utiliser ni winget ni brew (machine verrouillée) → pip uniquement |
| `--no-skill` / `--project` / `--skill-dir DIR` | où copier le skill Claude Code |
| `--test-url URL` | tester aussi un vrai téléchargement (prends une vidéo courte) |

Rapport JSON :
```json
{ "ok": true, "python": "C:\\…\\python.exe",
  "steps": [ {"name": "ffmpeg", "status": "ok|warn|fail|skip", "detail": "…", "fix": "…"} ],
  "next": ["…/python scripts/download.py <URL>", "…"] }
```
`ok: true` ⇔ aucune étape en `fail`. Les `warn` sont non bloquants (mentionne-les au dev).

---

## Étape 2 — Corriger les ✗

Pour chaque étape `fail`, applique son champ `fix`, puis **relance `bootstrap.py`**. Cas fréquents :

| Symptôme | Cause | Correctif |
|---|---|---|
| `externally-managed-environment` (Debian/Ubuntu, Homebrew) | PEP 668 : pip refuse le Python système | Le script réessaie déjà avec `--user --break-system-packages`. Si ça échoue encore : crée un venv (étape 0) et relance avec ce Python |
| `pip indisponible` | Python sans pip | `PY -m ensurepip --upgrade` ; Debian : `sudo apt install python3-pip` (demande au dev) |
| ffmpeg introuvable après `winget` | le PATH n'est mis à jour que dans les **nouveaux** terminaux | rien à faire : les scripts cherchent aussi dans les dossiers WinGet. Sinon relance avec `--no-system` (binaires pip) |
| `modèle whisper … fail` + erreur réseau / SSL / 403 | HuggingFace bloqué (proxy d'entreprise) | `HTTPS_PROXY=http://proxy:port` ; ou miroir `HF_ENDPOINT=https://hf-mirror.com` ; ou copier le dossier du modèle dans le cache HF d'une autre machine. Teste d'abord avec `--whisper-model tiny` |
| `cublas64_12.dll`, `libcudnn`, `CUDA failed` | GPU NVIDIA présent mais libs CUDA 12 / cuDNN 9 absentes | Rien d'obligatoire : bascule automatique sur CPU. Pour le GPU : installer CUDA 12 + cuDNN 9 (Linux : `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`) |
| `runtime JS … warn` | ni deno, ni node, ni bun | le script installe `deno` via pip ; sinon `winget install DenoLand.Deno` / `brew install deno` |
| Python 3.10 `warn` | yt-dlp abandonne 3.10 | marche encore ; conseille au dev de passer à 3.11+ |
| `certificate verify failed` | proxy qui intercepte le TLS | demande au dev le certificat de l'entreprise ; **ne désactive pas** la vérification TLS |

Ne contourne jamais une protection (antivirus, politique d'entreprise, blocage réseau) : explique le blocage au développeur et propose l'alternative (fichier vidéo local, autre réseau).

---

## Étape 3 — Vérifier en conditions réelles

```bash
# 1. Téléchargement YouTube (vidéo de 19 s, sous-titres + métadonnées)
PY scripts/download.py "https://www.youtube.com/watch?v=jNQXAC9IVRw" --out downloads --no-progress

# 2. Pipeline complet, en forçant la transcription Whisper (ignore les sous-titres YouTube)
PY scripts/extract.py "downloads/<fichier>.mp4" --out v2s_work --whisper
```
✔ Réussite : `download.py` affiche `"ok": true` ; `extract.py` affiche `"transcript": "whisper small"` (ou le modèle choisi) et `v2s_work/transcript.md` contient du texte daté `[0:00] …`.

Supprime ensuite `downloads/` et `v2s_work/` si le dev n'en a pas besoin (ils sont dans `.gitignore`).

---

## Étape 4 — Rendre compte au développeur

Court, dans ce format :
```
✔ video-to-skill installé (Python 3.12, C:\…\python.exe)
- ffmpeg 7.1 (winget) · yt-dlp 2026.x + deno · Whisper small sur CPU
- Skill Claude Code : ~/.claude/skills/video-to-skill → /video-to-skill <URL>
- Testé : autotest OK, téléchargement YouTube OK, transcription OK
⚠ À savoir : <warnings éventuels, ex. Python 3.10>
```

---

## Utiliser les scripts (référence rapide)

```bash
# Télécharger
PY scripts/download.py URL [URL…] [--out downloads] [--lang fr] [--max-height 720]
PY scripts/download.py --file urls.txt                     # une URL par ligne
PY scripts/download.py URL --playlist --max-videos 20      # playlist / chaîne
PY scripts/download.py URL --audio-only                    # audio seul, pour transcrire
PY scripts/download.py URL --section 12:00-25:00           # un passage
PY scripts/download.py URL --cookies-from-browser firefox  # âge / membres / « not a bot »

# Transformer une vidéo en matériau « regardable » (images clés + transcript)
PY scripts/extract.py <URL ou fichier> --out v2s_work [--lang fr] [--whisper-model small] [--whisper-device cpu]
```
`download.py` imprime sur stdout une liste JSON : `url, ok, files, subtitles, info_json, title, duration, chapters, error, hint`. En cas d'échec, **lis `hint`** : il dit quoi faire (cookies, mise à jour, réseau…). yt-dlp est mis à jour et l'essai relancé automatiquement si YouTube a changé.

Un fichier téléchargé par `download.py` peut être donné directement à `extract.py` : ses sous-titres et ses chapitres (`.info.json`) voisins sont repris automatiquement.

### Choisir le modèle Whisper

| Modèle | Taille | Précision | Vitesse sur CPU | Usage |
|---|---|---|---|---|
| `tiny` | ~75 Mo | faible | très rapide | tests |
| `base` | ~145 Mo | moyenne | rapide | brouillon |
| `small` | ~480 Mo | bonne | correcte | **défaut**, bon compromis |
| `medium` | ~1,5 Go | très bonne | lente | accents, jargon technique |
| `turbo` | ~1,6 Go | très bonne | lente | GPU recommandé |
| `large-v3` | ~3 Go | meilleure | très lente | GPU recommandé |

Un GPU NVIDIA (CUDA 12 + cuDNN 9) accélère fortement les gros modèles ; sans GPU, reste sur `small`.

### « Sign in to confirm you're not a bot » / vidéo soumise à l'âge

Relance avec `--cookies-from-browser firefox` (ou `edge`, `chrome`, `brave`) en utilisant un navigateur **où le dev est connecté à YouTube**. Sous Windows, Chrome/Edge verrouillent et chiffrent leurs cookies tant qu'ils sont ouverts : Firefox est le plus fiable, sinon demande au dev de fermer le navigateur. Demande toujours l'accord du dev avant de lire les cookies de son navigateur.

---

## Règles pour l'agent

- **Annonce** ce que tu installes avant de le faire (une phrase suffit).
- Pas de `sudo`, pas de modification des réglages de sécurité, pas de désactivation TLS / antivirus. Si un droit admin est indispensable, **demande**.
- Télécharge uniquement des vidéos que le développeur a le droit d'utiliser (apprentissage, documentation interne) ; ne redistribue pas les fichiers.
- N'affiche ni ne copie de cookies, tokens ou mots de passe dans tes messages ou dans les fichiers du repo.
- Si quelque chose a échoué ou n'a pas été vérifié, **dis-le** ; ne déclare pas « installé » sur la base d'un rapport `ok: false`.
