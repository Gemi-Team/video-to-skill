# Instructions for AI agents

- **Turn a video into a skill**: follow [CLAUDE.md](CLAUDE.md) (full workflow: prerequisites, extraction, sub-agents, assembly, delivery to `skills_out/`).
- **Install / repair the environment** (Python, ffmpeg, yt-dlp, Whisper): [LLM_SETUP.md](LLM_SETUP.md). One command does it all: `python scripts/bootstrap.py --json` (10-minute timeout).
- **Download a YouTube video**: `python scripts/download.py <URL>` (JSON on stdout, read `hint` on failure).
- On Windows, `python3` may be the fake Microsoft Store shortcut: use `python` or `py -3`.
