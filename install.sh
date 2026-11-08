#!/usr/bin/env bash
# Installe video-to-skill comme skill Claude Code personnel (~/.claude/skills/video-to-skill)
#   ./install.sh            → skill + dépendances Python (pillow, yt-dlp, faster-whisper)
#   ./install.sh --minimal  → skill + pillow seulement (pas d'URL, pas de transcription)
#   ./install.sh --project  → installe dans ./.claude/skills du projet courant
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.claude/skills/video-to-skill"
MINIMAL=0
for a in "$@"; do
  case "$a" in
    --minimal) MINIMAL=1 ;;
    --project) DEST="$PWD/.claude/skills/video-to-skill" ;;
    *) echo "option inconnue : $a"; exit 1 ;;
  esac
done

command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null || {
  echo "⚠ ffmpeg manquant. Installe-le :"
  echo "   macOS : brew install ffmpeg | Debian/Ubuntu : sudo apt install ffmpeg | Windows : winget install ffmpeg"
}
PY=$(command -v python3 || command -v python) || { echo "Python 3 requis"; exit 1; }

PKGS="pillow"; [ "$MINIMAL" = 1 ] || PKGS="pillow yt-dlp faster-whisper"
echo "→ pip install $PKGS"
"$PY" -m pip install --user -q $PKGS 2>/dev/null || "$PY" -m pip install --user -q --break-system-packages $PKGS

mkdir -p "$DEST"
cp -R "$HERE/SKILL.md" "$HERE/scripts" "$HERE/references" "$DEST/"
chmod +x "$DEST/scripts/"*.py
echo "✔ Installé dans $DEST"
echo "  Dans Claude Code : /video-to-skill <URL ou fichier vidéo>"
