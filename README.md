# video-to-skill

Envoie une vidéo à Claude → il la **regarde** (narration + images à l'écran) → il en tire un **skill** (`SKILL.md`) qu'il pourra réutiliser ensuite.

```
/video-to-skill https://youtube.com/watch?v=…        (ou un fichier .mp4 joint)
        │
        ▼
 extract.py ── télécharge, transcrit, détecte chaque « état d'écran » stable
        │      → frames/  sheets/ (planches 3×3)  timeline.md  transcript.md
        ▼
 Claude regarde les planches, zoome sur les détails (frame_at.py),
 classe la vidéo (procédure / méthode / non instructive) et écrit le skill
        │
        ▼
 validate_skill.py + rejoue les étapes dans un dossier jetable
        │
        ▼
 ~/.claude/skills/<nom>/SKILL.md   (ou carte « enregistrer le skill » sur claude.ai)
```

## Démarrage (associés) — 3 étapes, rien d'autre

1. Récupère le repo et ouvre Claude Code dedans :
   ```bash
   git clone <url-du-repo> video-to-skill
   ```
   ```bash
   cd video-to-skill && claude
   ```
   (ou ouvre le dossier dans l'app Claude, onglet Code)
2. Demande, par exemple :
   ```
   /video-to-skill https://www.youtube.com/watch?v=…
   ```
   ou en clair : *« Lis le repo et transforme cette vidéo en skill : https://… »*
3. Réponds aux éventuelles demandes d'autorisation (installation des dépendances la première fois) et, à la fin, dis si tu veux installer le skill.

Claude lit [`CLAUDE.md`](CLAUDE.md) et fait tout le reste lui-même : installation (Python, ffmpeg, yt-dlp, Whisper), téléchargement, analyse image par image, découpage et sous-agents pour les vidéos longues, contrôle, assemblage, validation. Le skill généré est écrit dans `skills_out/<nom>/`.

**Moins de demandes d'autorisation (optionnel)** : pour que Claude lance les scripts du tool sans te demander à chaque fois, crée `.claude/settings.local.json` (non versionné) avec :
```json
{
  "permissions": {
    "allow": [
      "Bash(python scripts/extract.py:*)", "Bash(python scripts/parts.py:*)",
      "Bash(python scripts/frame_at.py:*)", "Bash(python scripts/assemble.py:*)",
      "Bash(python scripts/validate_skill.py:*)", "Bash(python scripts/download.py:*)",
      "Bash(python scripts/bootstrap.py --check:*)",
      "Edit(v2s_work/**)", "Edit(skills_out/**)"
    ]
  }
}
```
(Remplace `python` par `python3` sur macOS/Linux. L'installation complète des dépendances reste soumise à ton accord.)

## Ce qui le distingue d'un résumé de transcription

- **L'écran prime sur l'audio.** Les commandes, formules, options sont recopiées depuis l'image. Dans le test fourni, la narration dit « request, version 2.32 », l'écran montre `requests==2.32.3` : le skill généré contient la bonne valeur.
- **Détection des états d'écran stabilisés**, pas des « changements de scène » : sur un enregistrement d'écran, taper une commande ne déclenche presque aucun changement de scène (score ffmpeg ≈ 0,04). `extract.py` garde l'image quand l'écran a changé *puis s'est arrêté de bouger* → commande complète, menu ouvert, résultat affiché.
- **Chaque étape est citée** `[t=MM:SS]`, l'incertain est marqué `⚠ incertain`, ce qui est ajouté hors vidéo est marqué `➕ ajouté` + source.
- **Vérification honnête** : les étapes sûres sont rejouées dans un dossier jetable ; le skill dit ce qui a été vérifié et ce qui ne l'a pas été.
- **Pas de skill bidon** : une vidéo sans méthode (vlog, débat) donne un rapport, pas des étapes inventées.

## Installation

**Le plus simple : rien à faire.** À la première vidéo demandée, Claude vérifie l'environnement et installe ce qui manque (voir « Démarrage » ci-dessus). Pour installer à l'avance, dis-lui *« installe ce repo »* : il suit [`LLM_SETUP.md`](LLM_SETUP.md), Whisper compris.

**À la main — une commande, Windows / macOS / Linux, sans droits admin :**
```bash
python scripts/bootstrap.py          # Windows : py -3 scripts/bootstrap.py   (ou .\install.ps1)
./install.sh                         # macOS / Linux / Git Bash (même chose)
```
`bootstrap.py` installe et **vérifie** : `pillow`, `yt-dlp` (+ résolveur JS YouTube, `curl_cffi`), `faster-whisper` + modèle Whisper `small` pré-téléchargé (GPU si dispo, sinon CPU), `ffmpeg` (winget / brew, ou binaires portables via pip), un runtime JS (deno/node), puis copie le skill dans `~/.claude/skills/video-to-skill` et lance un autotest. `--check` = diagnostic seul, `--json` = rapport pour un LLM, `--help` pour le reste.

**claude.ai / app Claude :** enregistre le skill depuis la carte proposée dans la conversation (seul `SKILL.md` est enregistré ; le skill bascule alors sur son « mode de secours » en commandes ffmpeg intégrées) ou envoie le zip du repo. Dans l'espace de travail cloud, YouTube et le téléchargement des modèles Whisper peuvent être bloqués : **joins le fichier vidéo** (et son .srt si tu l'as).

## Utilisation

```
/video-to-skill https://www.youtube.com/watch?v=…
/video-to-skill ~/Downloads/tuto.mp4
Transforme cette vidéo en skill, surtout la partie 12:00–25:00
```

Télécharger depuis YouTube (ou tout site supporté par yt-dlp) :
```bash
python scripts/download.py "https://www.youtube.com/watch?v=…"           # vidéo ≤720p + sous-titres + chapitres
python scripts/download.py URL1 URL2 --out downloads --lang fr
python scripts/download.py --file urls.txt                               # une URL par ligne
python scripts/download.py URL --playlist --max-videos 20                # playlist / chaîne
python scripts/download.py URL --audio-only                              # audio seul
python scripts/download.py URL --section 12:00-25:00                     # un passage
python scripts/download.py URL --cookies-from-browser firefox            # âge / membres / « not a bot »
```
Il installe yt-dlp si besoin, le met à jour et réessaie quand YouTube change, ne récupère que les sous-titres utiles (fr/en, pas les traductions auto qui déclenchent des 429), et imprime un JSON (`files`, `subtitles`, `chapters`, `error`, `hint`).

Scripts du pipeline :
```bash
python scripts/extract.py <url|fichier> --out v2s_work [--lang fr] [--subs sous-titres.srt] [--max-frames 90]
python scripts/extract.py <fichier> --out v2s_work --whisper --whisper-model medium   # ignorer les sous-titres
python scripts/frame_at.py v2s_work 1:23 --crop 0,0.5,1,0.5      # zoom bas de l'écran
python scripts/frame_at.py v2s_work --window 1:20 1:30 --step 1  # 1 image/s
python scripts/validate_skill.py chemin/vers/skill/
```
(`python3` sur macOS/Linux ; sous Windows `py -3` ou `python`.)

### Vidéos longues (2 h, 4 h…)

Au-delà de 45 min, `extract.py` découpe la vidéo en parties (chapitres regroupés, ≤ 45 min chacune), chacune avec ses propres images (une à chaque changement d'écran, analysé à 2 images/s, et au moins une toutes les 10 s), planches, transcript et une consigne prête pour un sous-agent (`part_NN/AGENT_PROMPT.md`). Claude joue l'orchestrateur : il ajuste le découpage si besoin, lance **un sous-agent par partie** (contexte neuf à chaque fois), chacun regarde **toutes** les planches de sa partie et rend `notes/part_NN.md` avec un journal visuel (une ligne par planche). `assemble.py --check` refuse des notes incomplètes ; puis Claude assemble le tout en **un seul skill** dans `skills_out/<nom>/`.
```bash
python scripts/parts.py v2s_work --plan                        # voir le découpage
python scripts/parts.py v2s_work --at 38:00,1:18:00,2:02:00    # imposer des bornes (rapide, pas de ré-analyse)
```
Règle d'apprentissage : **des méthodes, pas des informations**. On garde processus, frameworks, règles de décision, critères et erreurs à éviter ; on écarte anecdotes, chiffres isolés, autopromo et digressions. Sur YouTube, les passages balisés par **SponsorBlock** (sponsor, intro, autopromo…) sont sautés d'office.

Transcription, par ordre de préférence : sous-titres manuels → sous-titres auto YouTube → Whisper local (`--whisper-model small`, `medium` pour plus de précision ; GPU auto avec repli CPU) → aucune (images seules, signalé).

## Autotest

`bootstrap.py` le lance tout seul. À la main :
```bash
python tests/make_test_video.py v2s_test        # fausse vidéo tuto terminal (50 s) + .srt piégé
python scripts/extract.py v2s_test/tuto_venv.mp4 --out v2s_work
python scripts/validate_skill.py examples/python-venv-requests
```
`examples/python-venv-requests/` est le skill que Claude a généré à partir de cette vidéo de test (6/6 étapes rejouées avec succès).

## Limites

- Claude voit des **images clés**, pas un flux continu : un geste rapide entre deux états stables peut échapper → `frame_at.py --window` pour densifier.
- Les démonstrations physiques (cuisine, sport, bricolage) perdent du détail ; c'est fait pour les écrans, les slides et les tableaux.
- Les étapes d'interface graphique ne sont pas rejouables automatiquement : elles sont marquées « non vérifiées ».
- Vidéo longue : découpée en parties traitées par des sous-agents (Claude Code). Sans sous-agents (claude.ai), les parties sont traitées l'une après l'autre, ce qui est moins fiable.
- SponsorBlock ne couvre que les vidéos balisées par sa communauté ; le reste du tri est fait par Claude.

## Structure

```
SKILL.md                  instructions que Claude suit
LLM_SETUP.md              guide d'installation pour un agent IA (Whisper, ffmpeg, yt-dlp, dépannage)
CLAUDE.md                 point d'entrée lu automatiquement par Claude Code (tout le déroulé)
AGENTS.md                 pointeur pour les autres agents IA
.claude/commands/         commande /video-to-skill
skills_out/               skills générés
scripts/bootstrap.py      installation + vérification de tout, multi-OS, rapport JSON
scripts/download.py       téléchargement YouTube & co (vidéo, sous-titres, chapitres, playlists)
scripts/extract.py        ingestion, transcription, états d'écran, planches, timeline, SponsorBlock
scripts/parts.py          découpage des vidéos longues en parties (une par sous-agent)
scripts/assemble.py       contrôle des notes des sous-agents + assemblage en un skill
references/part-agent-prompt.md, part-notes-template.md   consigne et format des notes des sous-agents
scripts/frame_at.py       zoom temporel / recadrage
scripts/validate_skill.py lint du skill généré (frontmatter, secrets, citations, liens)
scripts/_common.py        recherche de ffmpeg / runtime JS, pip, console UTF-8
references/skill-template.md  squelette + règles d'écriture du skill généré
tests/make_test_video.py  vidéo de test
examples/                 skill généré par le test
install.sh, install.ps1   raccourcis vers bootstrap.py
```

Licence MIT.
