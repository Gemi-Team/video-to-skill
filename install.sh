#!/usr/bin/env bash
# Installe video-to-skill (macOS / Linux / Git Bash). Tout le travail est fait par scripts/bootstrap.py :
#   ./install.sh            → paquets, ffmpeg, runtime JS, Whisper small, autotest, skill ~/.claude/skills
#   ./install.sh --minimal  → pillow + ffmpeg seulement (pas d'URL, pas de transcription)
#   ./install.sh --project  → skill dans ./.claude/skills du projet courant
#   ./install.sh --check    → diagnostic seul
# Toutes les options : python3 scripts/bootstrap.py --help
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
[ -n "$PY" ] || { echo "Python 3.9+ requis (python3 introuvable)"; exit 1; }
exec "$PY" "$HERE/scripts/bootstrap.py" "$@"
