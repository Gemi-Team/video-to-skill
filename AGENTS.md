# Instructions pour les agents IA

- **Installer / faire marcher ce repo** (dépendances, ffmpeg, Whisper, yt-dlp) : suis [LLM_SETUP.md](LLM_SETUP.md). Une commande fait tout : `python scripts/bootstrap.py --json` (10 min de délai).
- **Télécharger une vidéo YouTube** : `python scripts/download.py <URL>` (JSON sur stdout, lis `hint` en cas d'échec).
- **Transformer une vidéo en skill** : suis [SKILL.md](SKILL.md).
- Sous Windows, `python3` peut être le faux raccourci du Microsoft Store : utilise `py -3` ou `python`.
