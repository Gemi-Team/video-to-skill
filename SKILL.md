---
name: video-to-skill
description: Watches a video (YouTube or other URL, or an attached video file) — narration AND what is on screen — then turns it into a reusable skill (SKILL.md + references) grounded in what the video actually shows, with every step cited [t=MM:SS]. Use when the user says "turn this video into a skill", "learn from this video", "watch this tutorial and make a skill", "video to skill", or sends a video/URL intending to keep a reusable method from it.
---

# Video → Skill

You "watch" a video: you read the narration (subtitles or transcript) **and** examine the key frames, then you write a skill that lets a future Claude **redo** what the video teaches — not summarize it.

Guiding principle: **you are not writing a transcript, you are writing executable instructions.**
The screen beats the narration: a command is copied from the image, never from what the audio says.
Write the skill in the language of the user's request unless they ask otherwise.

### What we learn: methods, not information

The skill must contain what a future Claude can **apply, adapt or draw inspiration from** in a new situation, not what the video tells.
- **Keep**: step-by-step processes, frameworks, reusable structures and templates, decision rules ("if … then …"), heuristics, evaluation criteria, mistakes to avoid with their reason, and the *why* of a method when it is given.
- **Drop**: isolated facts or figures, anecdotes, name-dropping, news, opinions without a method, self-promotion, sponsors, digressions, repetitions.
- An anecdote that hides a method → extract the principle, keep the anecdote in one sentence as an example. A figure only stays if it helps decide (threshold, order of magnitude).
- Technical procedure: the exact command or value seen on screen **is** the method → copy it verbatim.

## 0. Where the scripts are

`SKILL_DIR` = the folder containing this file (e.g. `~/.claude/skills/video-to-skill`, or the repo root).
If `SKILL_DIR/scripts/extract.py` does not exist (skill installed without its files), use the **fallback mode** at the bottom of this page.

`PY` = the Python interpreter: `python3` (macOS/Linux); on **Windows** `py -3` or `python` (`python3` is often a fake Microsoft Store shortcut there).

Dependencies: `ffmpeg` + `ffprobe`, Python 3.9+ with `pillow`. For URLs: `yt-dlp`; for transcription: `faster-whisper`.
**If anything is missing, one command installs and verifies everything** (no sudo, idempotent, 2–10 min):
```bash
PY "$SKILL_DIR/scripts/bootstrap.py" --json        # --check for diagnostics only
```
Tell the user before running it. Details and troubleshooting: `SKILL_DIR/LLM_SETUP.md`.

## 1. Extract

```bash
PY "$SKILL_DIR/scripts/extract.py" "<URL or path>" --out ./v2s_work [--lang en]
```

Produces in `v2s_work/`: `manifest.json`, `transcript.md`, `timeline.md`, `frames/`, `sheets/` (3×3 contact sheets labelled `#n  M:SS`).
For a URL, `extract.py` downloads the video itself (≤ 720p) + subtitles + chapters via `scripts/download.py`, which updates yt-dlp and retries on its own when YouTube has changed.
On YouTube, segments tagged by **SponsorBlock** (sponsor, intro, self-promotion, filler…) are marked `⏭` and get no frames: do not look at them.

**Video longer than 45 min**: `extract.py` also splits it into parts `part_01/`, `part_02/`… (`manifest.json` → `parts` not empty). In that case, **go to the "Long-video mode" section** instead of sections 2 and 3.

- **Several videos / playlist / just download**: `PY "$SKILL_DIR/scripts/download.py" URL1 URL2 --out downloads` (or `--playlist --max-videos 10`), then `extract.py` on each file: neighbouring subtitles and chapters are picked up automatically.
- **Download failure**: read the `hint` printed. "not a bot" / age / members-only → ask the user whether they accept `--cookies-from-browser firefox` (reads their browser cookies). Network blocked (common in a cloud workspace): say so in one sentence and ask for the video file. Do not work around the block.
- **No transcript** (no subtitles, Whisper unavailable): continue with the frames only and flag it in the skill (`transcript_source: none`). If the user has an .srt, `--subs file.srt`. Poor auto-captions → `--whisper` (ignores subtitles, transcribes locally; `--whisper-model medium` for more accuracy).
- The user only wants one section of a long video: build the skill from the relevant parts only (see "Long-video mode", step 2).

## 2. Watch (skip nothing)

Frames were chosen so that nothing shown on screen escapes you: one frame at **every screen change** (analysed at 2 frames/s) and **at least one every 10 s** (`--every`). Look at all of them.

1. Read `manifest.json` (title, duration, chapters, warnings) then `timeline.md` in full.
2. **Look at every contact sheet `sheets/*.jpg` in order, skipping none**, with the image-reading tool.
3. Whenever a thumbnail shows something other than a person talking (command, setting, formula, diagram, slide, displayed result), **open the full-resolution frame** `frames/f_XXXX_*.jpg` and read the on-screen text word for word.
4. Where the screen changes quickly (demo, slides flipping) or an action is ambiguous between two frames: densify to 1 frame/s and zoom:
   ```bash
   PY "$SKILL_DIR/scripts/frame_at.py" v2s_work --window 1:20 1:30 --step 1
   PY "$SKILL_DIR/scripts/frame_at.py" v2s_work 1:24 --crop 0,0.6,1,0.4   # bottom of the screen
   ```
5. Take working notes (not in the skill): `[t] what is said | what is visible | what it implies`. Note every narration/screen disagreement — **the screen wins**, and that is often where the real values hide (versions, options, exact names).

## 3. Classify the video

| Type | Example | What the skill becomes |
|---|---|---|
| **Procedure** | software tutorial, CLI, configuration, technical recipe | ordered steps, exact commands, success criteria |
| **Method / knowledge** | course, concept explanation, problem-solving method | applicable method + rules + worked examples, theory in `references/` |
| **Mixed** | course with a demo | method in SKILL.md, demo as a procedure |
| **Not instructional** | vlog, debate, ad, content without a method | **no skill**: short report explaining why + what could be salvaged |

Never invent steps to fill a skill.

## Long-video mode (> 45 min) — you are the orchestrator

A single pass over 2 to 4 hours of video means skimming. So you split the video, hand each part to a **sub-agent that starts with an empty context**, and assemble their notes into **one single skill**.

1. **Overview**: read `manifest.json` (duration, chapters, `skip_segments`, `parts`) and `parts.json`. Skim the global contact sheets `sheets/` (not the frames). If the video is not instructional (section 3), stop there and report.
2. **Decide the split.** By default `extract.py` grouped the chapters into parts of at most 45 min; each part holds one frame per screen change + at least one every 10 s (≈ 250 to 300 frames, ~30 contact sheets). Adjust if a boundary cuts a demonstration or an idea, if a part is pure noise (no sub-agent for it, note why), or if the user only wants one section:
   ```bash
   PY "$SKILL_DIR/scripts/parts.py" v2s_work --plan                         # show the split
   PY "$SKILL_DIR/scripts/parts.py" v2s_work --at 38:00,1:18:00,2:02:00     # boundaries you choose
   PY "$SKILL_DIR/scripts/parts.py" v2s_work --max-minutes 30               # shorter parts
   ```
   It is fast: the video is not re-analysed. Announce the plan in one line per part (range, chapters).
3. **Launch one sub-agent per part, all in parallel** (Claude Code: `general-purpose` sub-agent). Each part holds its full instructions: `part_NN/AGENT_PROMPT.md` (methods to extract, look at **every contact sheet**, densify demos, notes format, visual log). Instruction to give:
   > Read and carry out `<absolute path>/part_NN/AGENT_PROMPT.md`. Write the notes in <the user's language>. Only write the notes file it names. Reply in 3 lines.

   Each sub-agent writes `<work>/notes/part_NN.md`.
   **Without a sub-agent tool** (claude.ai): process the parts yourself, one after another, with the same `AGENT_PROMPT.md`. Write each notes file before moving on to the next part and do not reread the raw material of a finished part.
4. **Automatic check**:
   ```bash
   PY "$SKILL_DIR/scripts/assemble.py" v2s_work --check
   ```
   For each part it checks: notes present, required sections, every method cited `[t=…]`, citations within the part's range, and a **complete visual log** (one line per contact sheet: the proof that every frame was looked at). Failing part → relaunch **its** sub-agent with the reason shown, then check again. Do not assemble until it says `OK`.
5. **Assembly plan**: read the notes (not the raw material), then
   ```bash
   PY "$SKILL_DIR/scripts/assemble.py" v2s_work --list                 # every method: P2.M7 + title
   PY "$SKILL_DIR/scripts/assemble.py" v2s_work --plan-template        # draft JSON plan
   ```
   Write `v2s_work/plan.json`: **one file per theme, in the logical order of application** (not the order of the video). A method present in several parts → keep one, put the others in `"drop"` with the reason ("merged into 04, 4.7").
6. **Assemble**:
   ```bash
   PY "$SKILL_DIR/scripts/assemble.py" v2s_work --plan v2s_work/plan.json --out skills_out/<name>
   ```
   It writes `references/NN-<theme>.md` (methods renumbered `N.k`, citations normalized) and `references/99-uncertainties-and-skipped.md`. Then, by hand:
   - carry out the **merges** listed in `"drop"` (one method, all its citations) and fix cross-references between methods;
   - write `SKILL.md`: when to use it, how to use it, **order of attack**, **method map** (problem → method → link), condensed core methods, merged cross-cutting principles, **Source** section (video, parts, useful/skipped minutes, uncertainties); under 500 lines.
7. Then sections **4** (writing rules), **5** (verify) and **6** (deliver) as for a short video.

## 4. Write the skill

Language: that of the user's request (unless told otherwise). Detailed structure: `references/skill-template.md`. If that file is missing, use in order: frontmatter → title → "Verification" block → Prerequisites → Steps (or Method) with exact command, `✔ Success:` and `[t=MM:SS]` → Worked example → Variants → Troubleshooting → Source.

Rules:
- **Frontmatter**: `name` in kebab-case (≤ 64 chars, no "claude"/"anthropic"), `description` ≤ 1024 chars saying **what** and **when to use it** (trigger phrases), without `<` or `>`.
- **Imperative, no narration**: "Run `npm run build`", not "Then he runs the build". Remove intros, sponsors, "subscribe".
- **Cite every step**: `[t=MM:SS]` at the end of the step. A claim without a citation must come from a named external source.
- **Exact > pretty**: commands, paths, options, menu names, formulas copied from the screen. Versions seen on screen go in "Prerequisites".
- **Visible uncertainty**: anything not clearly shown is marked `⚠ uncertain` with the reason ("text cut off at [t=3:12]"). Never guess silently.
- **Fill gaps** only when needed for the skill to work (skipped step, outdated command), marked `➕ added` + source (official docs). If you have web search, check commands that may have changed since the video.
- **Success criteria**: for every important step, how to know it worked (expected output, what should appear).
- **Secrets**: never a password, key, token or personal email seen on screen → placeholder `<YOUR_API_KEY>`.
- **Progressive disclosure**: SKILL.md < 500 lines, operational. Theory, long explanations, reference tables → `references/*.md`. Reusable scripts shown in the video → `scripts/`.
- **Source**: final section with title, author/channel, URL, date, transcript source, and what could not be verified.

## 5. Verify

```bash
PY "$SKILL_DIR/scripts/validate_skill.py" ./<name>/
```
Fix every ✗ error, handle the relevant ⚠ warnings.

Then run an **execution test** when it is safe (CLI/code procedures): replay the steps in a throwaway folder (`mktemp -d`), without touching the user's files, without `sudo`, nothing destructive or irreversible. Note the result at the top of the skill:
`> Verification: 6/7 steps executed successfully on YYYY-MM-DD; step 5 (GUI) not verifiable.`
If nothing could be executed, write "not verified by execution" — never a misleading badge.

Finally, reread the skill as a Claude that has **not** seen the video: could it do the task with this text alone? If not, fill the gaps.

## 6. Deliver

- **Claude Code / local machine**: write the skill first to `skills_out/<name>/` (inside the video-to-skill repo; otherwise in the current folder), then install it **automatically, without asking**:
  ```bash
  PY "$SKILL_DIR/scripts/install_skill.py" skills_out/<name>             # → ~/.claude/skills/<name>/
  ```
  It refuses a skill that fails validation and backs up any previous version to `~/.claude/skills-backup/`. Use `--project` (→ `.claude/skills/<name>/`) or skip installing only if the user asked for it. Tell the user where it is installed and that deleting that folder removes it.
- **claude.ai / Claude app**: if the `propose_skills` tool is available, offer the skill with it (the user saves it from the card); otherwise send the folder (zip) and explain where to put it. Note: a skill card only saves SKILL.md → if the skill has `references/`, fold the essentials into SKILL.md or also deliver the zip.
- **A skill with the same name already exists**: merge instead of overwriting — steps confirmed by both videos are more reliable; disagreements are kept as cited variants.

Final message: skill name, video type, number of steps, what was verified, what remains uncertain. Short.

## Fallback mode (no scripts)

```bash
mkdir -p v2s_work/frames v2s_work/sheets && cd v2s_work
# URL: video + subtitles (no "en.*": it downloads dozens of auto-translations → HTTP 429
# and yt-dlp gives up on the video). --js-runtimes node if deno is missing; --ignore-errors: a failed subtitle does not block.
python3 -m pip install -U "yt-dlp[default]"
python3 -m yt_dlp -f "bv*[height<=720]+ba/b[height<=720]/b" --merge-output-format mp4 --ignore-errors --no-playlist \
  --write-subs --write-auto-subs --sub-langs "en,en-orig" --convert-subs srt -o "video.%(ext)s" "<URL>"
# 1 frame every 10 s (adjust: 5 s for a fast tutorial)
ffmpeg -i video.mp4 -vf "fps=1/10,scale=1280:-2" -q:v 3 frames/f_%04d.jpg
# 3x3 contact sheets (frame n ≈ (n-1)*10 s)
ffmpeg -i frames/f_%04d.jpg -vf "scale=640:-2,tile=3x3" -q:v 4 sheets/sheet_%02d.jpg
# exact frame
ffmpeg -ss 00:01:24 -i video.mp4 -frames:v 1 zoom_1m24.png
```
Transcription without subtitles (if faster-whisper is installed):
```python
from faster_whisper import WhisperModel
for s in WhisperModel("small", compute_type="int8").transcribe("video.mp4", vad_filter=True)[0]:
    print(f"[{int(s.start//60)}:{int(s.start%60):02d}] {s.text.strip()}")
```
Then resume at step 2. Check the frontmatter by hand (rules of step 4).
