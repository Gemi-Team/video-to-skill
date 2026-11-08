# video-to-skill

Give Claude a video → it **watches** it (narration + what is on screen) → it turns it into a reusable **skill** (`SKILL.md`).

```
/video-to-skill https://youtube.com/watch?v=…        (or an attached .mp4 file)
        │
        ▼
 extract.py ── downloads, transcribes, detects every settled "screen state"
        │      → frames/  sheets/ (3×3 contact sheets)  timeline.md  transcript.md
        ▼
 Claude looks at every contact sheet, zooms into details (frame_at.py),
 classifies the video (procedure / method / not instructional) and writes the skill
        │
        ▼
 validate_skill.py + replays the steps in a throwaway folder
        │
        ▼
 skills_out/<name>/SKILL.md  →  ~/.claude/skills/<name>/  (installed automatically)
```

## Quick start (for teammates) — 3 steps, nothing else

1. Get the repo and open Claude Code in it:
   ```bash
   git clone https://github.com/Gemi-Team/video-to-skill.git
   ```
   ```bash
   cd video-to-skill && claude
   ```
   (or open the folder in the Claude desktop app, Code tab)
2. Ask, for example:
   ```
   /video-to-skill https://www.youtube.com/watch?v=…
   ```
   or in plain words: *"Read the repo and turn this video into a skill: https://…"*
3. Approve the permission prompts (dependency install the first time). That's it: at the end, the skill is installed automatically in `~/.claude/skills/<name>/` and Claude uses it in your next sessions.

Claude reads [`CLAUDE.md`](CLAUDE.md) and does everything else itself: setup (Python, ffmpeg, yt-dlp, Whisper), download, frame-by-frame analysis, splitting and sub-agents for long videos, checks, assembly, validation. The generated skill is written to `skills_out/<name>/` and installed in `~/.claude/skills/<name>/` (delete that folder to remove it).

**Fewer permission prompts (optional):** to let Claude run the tool's scripts without asking each time, create `.claude/settings.local.json` (not versioned) with:
```json
{
  "permissions": {
    "allow": [
      "Bash(python scripts/extract.py:*)", "Bash(python scripts/parts.py:*)",
      "Bash(python scripts/frame_at.py:*)", "Bash(python scripts/assemble.py:*)",
      "Bash(python scripts/validate_skill.py:*)", "Bash(python scripts/download.py:*)",
      "Bash(python scripts/bootstrap.py --check:*)", "Bash(python scripts/install_skill.py:*)",
      "Edit(v2s_work/**)", "Edit(skills_out/**)"
    ]
  }
}
```
(Use `python3` instead of `python` on macOS/Linux. The full dependency install still asks for your approval.)

## What makes it different from a transcript summary

- **The screen beats the audio.** Commands, formulas and options are copied from the image. In the bundled test, the narration says "request, version 2.32" while the screen shows `requests==2.32.3`: the generated skill has the right value.
- **Settled screen states, not "scene changes":** in a screen recording, typing a command barely registers as a scene change (ffmpeg score ≈ 0.04). `extract.py` keeps a frame when the screen has changed *and then stopped moving* → full command, open menu, displayed result.
- **Every step is cited** `[t=MM:SS]`; anything unclear is marked `⚠ uncertain`; anything added from outside the video is marked `➕ added` with its source.
- **Honest verification:** safe steps are replayed in a throwaway folder; the skill says what was verified and what was not.
- **No fake skills:** a video without a method (vlog, debate) produces a short report, not invented steps.
- **Methods, not information:** the skill keeps what Claude can apply — processes, frameworks, decision rules, criteria, mistakes to avoid — and drops anecdotes, isolated figures, self-promotion and digressions.

## Installation

**Easiest: nothing to do.** On the first video request, Claude checks the environment and installs what is missing (see "Quick start"). To install ahead of time, tell Claude *"install this repo"*: it follows [`LLM_SETUP.md`](LLM_SETUP.md), Whisper included.

**By hand — one command, Windows / macOS / Linux, no admin rights:**
```bash
python scripts/bootstrap.py          # Windows: py -3 scripts/bootstrap.py   (or .\install.ps1)
./install.sh                         # macOS / Linux / Git Bash (same thing)
```
`bootstrap.py` installs and **verifies**: `pillow`, `yt-dlp` (+ YouTube JS challenge solver, `curl_cffi`), `faster-whisper` + the Whisper `small` model pre-downloaded (GPU if available, otherwise CPU), `ffmpeg` (winget / brew, or portable binaries via pip), a JS runtime (deno/node), then copies the skill to `~/.claude/skills/video-to-skill` and runs a self-test. `--check` = diagnostics only, `--json` = report for an LLM, `--help` for the rest.

**claude.ai / Claude app:** save the skill from the card offered in the conversation (only `SKILL.md` is saved; the skill then falls back to its built-in ffmpeg commands) or upload the repo zip. In the cloud workspace, YouTube and Whisper model downloads may be blocked: **attach the video file** (and its .srt if you have one).

## Usage

```
/video-to-skill https://www.youtube.com/watch?v=…
/video-to-skill ~/Downloads/tutorial.mp4
Turn this video into a skill, mostly the 12:00–25:00 part
```

Download from YouTube (or any site yt-dlp supports):
```bash
python scripts/download.py "https://www.youtube.com/watch?v=…"           # video ≤720p + subtitles + chapters
python scripts/download.py URL1 URL2 --out downloads --lang en
python scripts/download.py --file urls.txt                               # one URL per line
python scripts/download.py URL --playlist --max-videos 20                # playlist / channel
python scripts/download.py URL --audio-only                              # audio only
python scripts/download.py URL --section 12:00-25:00                     # one section
python scripts/download.py URL --cookies-from-browser firefox            # age / members-only / "not a bot"
```
It installs yt-dlp when needed, updates it and retries when YouTube changes, only fetches useful subtitles (your language + English, not the dozens of auto-translations that trigger HTTP 429), and prints JSON (`files`, `subtitles`, `chapters`, `error`, `hint`).

Pipeline scripts:
```bash
python scripts/extract.py <url|file> --out v2s_work [--lang en] [--subs subtitles.srt] [--every 10]
python scripts/extract.py <file> --out v2s_work --whisper --whisper-model medium   # ignore subtitles
python scripts/frame_at.py v2s_work 1:23 --crop 0,0.5,1,0.5      # zoom on the bottom half
python scripts/frame_at.py v2s_work --window 1:20 1:30 --step 1  # 1 frame per second
python scripts/validate_skill.py path/to/skill/
```
(`python3` on macOS/Linux; on Windows `py -3` or `python`.)

### Frame coverage

Frames are chosen so that nothing shown on screen is missed: the video is analysed at **2 frames per second**, a frame is kept at **every screen change**, plus **at least one every 10 seconds** (`--every`). Claude (or each sub-agent) must look at every contact sheet, open full-resolution frames whenever there is something to read, and densify fast demos to 1 frame/s.

### Long videos (2 h, 4 h…)

Beyond 45 min, `extract.py` splits the video into parts (chapters grouped, ≤ 45 min each), each with its own frames (~250–300), contact sheets, transcript and a ready-made prompt for a sub-agent (`part_NN/AGENT_PROMPT.md`). Claude acts as the orchestrator: it adjusts the split if needed, launches **one sub-agent per part** (fresh context each time, all in parallel); each one looks at **every** contact sheet of its part and returns `notes/part_NN.md` with a visual log (one line per sheet). `assemble.py --check` rejects incomplete notes; then Claude assembles everything into **a single skill** in `skills_out/<name>/`.
```bash
python scripts/parts.py v2s_work --plan                        # show the split
python scripts/parts.py v2s_work --at 38:00,1:18:00,2:02:00    # force boundaries (fast, no re-analysis)
python scripts/assemble.py v2s_work --check                    # are the sub-agents' notes complete?
```
On YouTube, segments tagged by **SponsorBlock** (sponsor, intro, self-promotion…) are skipped automatically.

Transcript, in order of preference: manual subtitles → YouTube auto-captions → local Whisper (`--whisper-model small`, `medium` for more accuracy; GPU when available with CPU fallback) → none (frames only, flagged).

## Self-test

`bootstrap.py` runs it automatically. By hand:
```bash
python tests/make_test_video.py v2s_test        # fake terminal tutorial (50 s) + a misleading .srt
python scripts/extract.py v2s_test/tuto_venv.mp4 --out v2s_work
python scripts/validate_skill.py examples/python-venv-requests
```
`examples/python-venv-requests/` is the skill Claude generated from that test video (6/6 steps replayed successfully).

## Limitations

- Claude sees **key frames**, not a continuous stream: a quick gesture between two settled states can slip through → `frame_at.py --window` to densify.
- Physical demonstrations (cooking, sport, DIY) lose detail; the tool is built for screens, slides and whiteboards.
- GUI steps cannot be replayed automatically: they are marked "not verified".
- Long videos are split into parts handled by sub-agents (Claude Code). Without sub-agents (claude.ai), parts are processed one after another, which is less reliable.
- SponsorBlock only covers videos tagged by its community; Claude filters the rest.
- Cost: a dense sub-agent uses ~250k tokens and 6–7 minutes per 45-minute part.

## Structure

```
SKILL.md                  instructions Claude follows
CLAUDE.md                 entry point read automatically by Claude Code (the whole workflow)
AGENTS.md                 pointer for other AI agents
LLM_SETUP.md              setup guide for an AI agent (Whisper, ffmpeg, yt-dlp, troubleshooting)
.claude/commands/         /video-to-skill command
skills_out/               generated skills
scripts/bootstrap.py      install + verify everything, cross-platform, JSON report
scripts/download.py       YouTube & co download (video, subtitles, chapters, playlists)
scripts/extract.py        ingestion, transcript, screen states, contact sheets, timeline, SponsorBlock
scripts/parts.py          long-video split into parts (one per sub-agent)
scripts/assemble.py       sub-agent notes check + assembly into one skill
scripts/frame_at.py       time zoom / crop
scripts/validate_skill.py lint for the generated skill (frontmatter, secrets, citations, links)
scripts/install_skill.py  validate + install the generated skill in ~/.claude/skills (backs up any previous version)
scripts/_common.py        ffmpeg / JS runtime lookup, pip, UTF-8 console
references/skill-template.md  skeleton + writing rules for the generated skill
references/part-agent-prompt.md, part-notes-template.md   sub-agent prompt and notes format
tests/make_test_video.py  test video
examples/                 skill generated by the test
install.sh, install.ps1   shortcuts to bootstrap.py
```

MIT License.
