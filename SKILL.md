---
name: video-to-skill
description: Regarde une vidéo (URL YouTube ou autre, ou fichier vidéo joint) — narration ET images à l'écran — puis en tire un skill réutilisable (SKILL.md + références) fondé sur ce que la vidéo montre vraiment, avec chaque étape citée [t=MM:SS]. À utiliser quand l'utilisateur dit « transforme cette vidéo en skill », « apprends de cette vidéo », « regarde ce tuto et fais-en un skill », « video to skill », ou envoie une vidéo/URL avec l'intention d'en garder une méthode réutilisable.
---

# Video → Skill

Tu « regardes » une vidéo : tu lis la narration (sous-titres ou transcription) **et** tu examines les images clés, puis tu écris un skill qui permet à un futur Claude de **refaire** ce que la vidéo enseigne — pas de la résumer.

Principe directeur : **tu n'écris pas une transcription, tu écris des instructions exécutables.**
L'écran prime sur la narration : une commande se recopie depuis l'image, jamais depuis ce que dit l'audio.

## 0. Où sont les scripts

`SKILL_DIR` = le dossier qui contient ce fichier (ex. `~/.claude/skills/video-to-skill`).
Si `SKILL_DIR/scripts/extract.py` n'existe pas (skill installé sans ses fichiers), utilise le **mode de secours** en bas de page.

`PY` = l'interpréteur Python : `python3` (macOS/Linux) ; sous **Windows** `py -3` ou `python` (`python3` y est souvent un faux raccourci du Microsoft Store).

Dépendances : `ffmpeg` + `ffprobe`, Python 3.9+ avec `pillow`. Pour les URL : `yt-dlp` ; pour la transcription : `faster-whisper`.
**Si quelque chose manque, une seule commande installe et vérifie tout** (sans sudo, idempotent, 2–10 min) :
```bash
PY "$SKILL_DIR/scripts/bootstrap.py" --json        # --check pour un simple diagnostic
```
Annonce-le à l'utilisateur avant de le lancer. Détails et dépannage : `SKILL_DIR/LLM_SETUP.md`.

## 1. Extraire

```bash
PY "$SKILL_DIR/scripts/extract.py" "<URL ou chemin>" --out ./v2s_work [--lang fr]
```

Produit dans `v2s_work/` : `manifest.json`, `transcript.md`, `timeline.md`, `frames/`, `sheets/` (planches 3×3 annotées `#n  M:SS`).
Pour une URL, `extract.py` télécharge lui-même la vidéo (≤ 720p) + sous-titres + chapitres via `scripts/download.py`, qui met yt-dlp à jour et réessaie tout seul si YouTube a changé.

- **Plusieurs vidéos / playlist / juste télécharger** : `PY "$SKILL_DIR/scripts/download.py" URL1 URL2 --out downloads` (ou `--playlist --max-videos 10`), puis `extract.py` sur chaque fichier : sous-titres et chapitres voisins sont repris automatiquement.
- **Échec de téléchargement** : lis le `hint` affiché. « not a bot » / âge / membres → demande à l'utilisateur s'il accepte `--cookies-from-browser firefox` (lit les cookies de son navigateur). Réseau bloqué (fréquent dans un espace de travail cloud) : dis-le en une phrase et demande le fichier vidéo. Ne contourne pas le blocage.
- **Pas de transcription** (pas de sous-titres, Whisper indisponible) : continue avec les images seules et signale-le dans le skill (`transcript_source: aucune`). Si l'utilisateur a un .srt, `--subs fichier.srt`. Sous-titres auto de mauvaise qualité → `--whisper` (ignore les sous-titres, transcrit en local ; `--whisper-model medium` pour plus de précision).
- Vidéo > 45 min : propose de cibler une partie (chapitres dans `manifest.json`) ou augmente `--max-frames`.

## 2. Regarder (ne saute aucune étape)

1. Lis `manifest.json` (titre, durée, chapitres, avertissements) puis `timeline.md` en entier.
2. **Regarde toutes les planches `sheets/*.jpg` dans l'ordre** avec l'outil de lecture d'images. C'est ta vision d'ensemble.
3. Pour chaque moment important (commande tapée, réglage, formule, schéma, résultat affiché), **ouvre l'image pleine résolution** `frames/f_XXXX_*.jpg` et lis le texte à l'écran mot pour mot.
4. Si une action reste ambiguë entre deux images (texte coupé, clic rapide, valeur qui change), zoome :
   ```bash
   PY "$SKILL_DIR/scripts/frame_at.py" v2s_work --window 1:20 1:30 --step 1
   PY "$SKILL_DIR/scripts/frame_at.py" v2s_work 1:24 --crop 0,0.6,1,0.4   # bas de l'écran
   ```
5. Prends des notes de travail (pas dans le skill) : `[t] ce qui est dit | ce qui est visible | ce que ça implique`. Note tout désaccord narration/écran — **l'écran gagne**, et c'est souvent là que se cachent les vraies valeurs (versions, options, noms exacts).

## 3. Qualifier la vidéo

| Type | Exemple | Ce que devient le skill |
|---|---|---|
| **Procédure** | tuto logiciel, CLI, config, recette technique | étapes ordonnées, commandes exactes, critères de réussite |
| **Méthode / savoir** | cours, explication d'un concept, méthode de résolution | méthode applicable + règles + exemples travaillés, théorie dans `references/` |
| **Mixte** | cours avec démo | méthode dans SKILL.md, démo en procédure |
| **Non instructif** | vlog, débat, pub, contenu sans méthode | **pas de skill** : rapport court expliquant pourquoi + ce qui serait récupérable |

Ne fabrique jamais d'étapes pour remplir un skill.

## 4. Écrire le skill

Langue : celle de la demande de l'utilisateur (sauf consigne contraire). Structure détaillée : `references/skill-template.md`. Si ce fichier est absent, utilise dans l'ordre : frontmatter → titre → bloc « Vérification » → Prérequis → Étapes (ou Méthode) avec commande exacte, `✔ Réussite :` et `[t=MM:SS]` → Exemple travaillé → Variantes → Dépannage → Source.

Règles :
- **Frontmatter** : `name` kebab-case (≤ 64 car., sans « claude »/« anthropic »), `description` ≤ 1024 car. qui dit **quoi** et **quand l'utiliser** (phrases déclencheuses), sans `<` ni `>`.
- **Impératif, sans narration** : « Lance `npm run build` » et non « Ensuite il lance le build ». Supprime intro, sponsors, « abonnez-vous ».
- **Cite chaque étape** : `[t=MM:SS]` à la fin de l'étape. Une affirmation sans citation doit venir d'une source externe nommée.
- **Exact > joli** : commandes, chemins, options, noms de menus, formules recopiés de l'écran. Versions visibles notées dans « Prérequis ».
- **Incertitude visible** : ce qui n'est pas clairement montré est marqué `⚠ incertain` avec la raison (« texte coupé à [t=3:12] »). Ne devine pas en silence.
- **Combler les trous** seulement si nécessaire pour que le skill marche (étape sautée, commande obsolète), en le marquant `➕ ajouté` + source (doc officielle). Si tu as une recherche web, vérifie les commandes qui ont pu changer depuis la vidéo.
- **Critères de réussite** : pour chaque étape importante, comment savoir que ça a marché (sortie attendue, ce qui doit apparaître).
- **Secrets** : jamais de mot de passe, clé, token ou e-mail personnel vu à l'écran → placeholder `<VOTRE_CLE_API>`.
- **Progressive disclosure** : SKILL.md < 500 lignes, opérationnel. Théorie, longues explications, tableaux de référence → `references/*.md`. Scripts réutilisables vus dans la vidéo → `scripts/`.
- **Source** : section finale avec titre, auteur/chaîne, URL, date, source de la transcription, et ce qui n'a pas pu être vérifié.

## 5. Vérifier

```bash
PY "$SKILL_DIR/scripts/validate_skill.py" ./<name>/
```
Corrige toutes les erreurs ✗, traite les avertissements ⚠ pertinents.

Puis **test d'exécution** quand c'est sans risque (procédures CLI/code) : rejoue les étapes dans un dossier jetable (`mktemp -d`), sans toucher aux fichiers de l'utilisateur, sans `sudo`, sans rien de destructif ni d'irréversible. Note le résultat en tête du skill :
`> Vérification : 6/7 étapes exécutées avec succès le AAAA-MM-JJ ; étape 5 (interface graphique) non vérifiable.`
Si rien n'a pu être exécuté, écris « non vérifié par exécution » — jamais de badge mensonger.

Relis enfin le skill comme un Claude qui n'a **pas** vu la vidéo : pourrait-il faire la tâche avec ce seul texte ? Sinon, complète.

## 6. Livrer

- **Claude Code / machine locale** : montre le plan (nom, emplacement, fichiers) puis, après accord, installe dans `~/.claude/skills/<name>/` (personnel) ou `.claude/skills/<name>/` (projet).
- **claude.ai / Claude app** : si l'outil `propose_skills` est disponible, propose le skill avec (l'utilisateur l'enregistre depuis la carte) ; sinon envoie le dossier (zip) et explique où le placer. Note : une carte de skill n'enregistre que SKILL.md → si le skill a des `references/`, intègre l'essentiel dans SKILL.md ou livre aussi le zip.
- **Skill du même nom déjà existant** : fusionne au lieu d'écraser — étapes confirmées par les deux vidéos = plus sûres ; divergences gardées comme variantes citées.

Message final : nom du skill, type de vidéo, nb d'étapes, ce qui a été vérifié, ce qui reste incertain. Court.

## Mode de secours (sans scripts)

```bash
mkdir -p v2s_work/frames v2s_work/sheets && cd v2s_work
# URL : vidéo + sous-titres (pas de « fr.* » : ça télécharge des dizaines de traductions auto → HTTP 429
# et yt-dlp abandonne la vidéo). --js-runtimes node si deno absent ; --ignore-errors : un sous-titre raté ne bloque pas.
python3 -m pip install -U "yt-dlp[default]"
python3 -m yt_dlp -f "bv*[height<=720]+ba/b[height<=720]/b" --merge-output-format mp4 --ignore-errors --no-playlist \
  --write-subs --write-auto-subs --sub-langs "fr,fr-orig,en,en-orig" --convert-subs srt -o "video.%(ext)s" "<URL>"
# 1 image toutes les 10 s (adapter : 5 s pour un tuto rapide)
ffmpeg -i video.mp4 -vf "fps=1/10,scale=1280:-2" -q:v 3 frames/f_%04d.jpg
# planches 3x3 (image n ≈ (n-1)*10 s)
ffmpeg -i frames/f_%04d.jpg -vf "scale=640:-2,tile=3x3" -q:v 4 sheets/sheet_%02d.jpg
# image précise
ffmpeg -ss 00:01:24 -i video.mp4 -frames:v 1 zoom_1m24.png
```
Transcription sans sous-titres (si faster-whisper installé) :
```python
from faster_whisper import WhisperModel
for s in WhisperModel("small", compute_type="int8").transcribe("video.mp4", vad_filter=True)[0]:
    print(f"[{int(s.start//60)}:{int(s.start%60):02d}] {s.text.strip()}")
```
Puis reprends à l'étape 2. Valide le frontmatter à la main (règles de l'étape 4).
