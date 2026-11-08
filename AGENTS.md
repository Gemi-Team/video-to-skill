# Instructions pour les agents IA

- **Transformer une vidéo en skill** : suis [CLAUDE.md](CLAUDE.md) (déroulé complet : prérequis, extraction, sous-agents, assemblage, livraison dans `skills_out/`).
- **Installer / réparer l'environnement** (Python, ffmpeg, yt-dlp, Whisper) : [LLM_SETUP.md](LLM_SETUP.md). Une commande fait tout : `python scripts/bootstrap.py --json` (10 min de délai).
- **Télécharger une vidéo YouTube** : `python scripts/download.py <URL>` (JSON sur stdout, lis `hint` en cas d'échec).
- Sous Windows, `python3` peut être le faux raccourci du Microsoft Store : utilise `python` ou `py -3`.
