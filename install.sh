#!/usr/bin/env bash
# Installs video-to-skill (macOS / Linux / Git Bash). All the work is done by scripts/bootstrap.py:
#   ./install.sh            → packages, ffmpeg, JS runtime, Whisper small, self-test, skill ~/.claude/skills
#   ./install.sh --minimal  → pillow + ffmpeg only (no URLs, no transcription)
#   ./install.sh --project  → skill in ./.claude/skills of the current project
#   ./install.sh --check    → diagnostics only
# All options: python3 scripts/bootstrap.py --help
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
[ -n "$PY" ] || { echo "Python 3.9+ required (python3 not found)"; exit 1; }
exec "$PY" "$HERE/scripts/bootstrap.py" "$@"
