# Mission: part {{N}}/{{TOTAL}} of "{{TITLE}}" ({{FROM}} → {{TO}})

You are a **sub-agent** of video-to-skill. An orchestrator split a long video ({{URL}}) into {{TOTAL}} parts.
You handle **only your part** and write your notes. You do not write the final skill: the orchestrator will assemble the notes of all parts.

Chapters in your part:
{{CHAPTERS}}

Segments already identified as useless (do not look at them):
{{SKIPPED}}

## Learning principle: methods, not information

We do not learn what the video **says**, we learn what it **lets you do**. Keep only what another Claude can **apply, adapt or draw inspiration from** in a new situation.

**Extract:**
- step-by-step processes, frameworks, analysis grids, checklists;
- reusable structures and templates (structure of a brief, a landing page, a script, a campaign…);
- decision rules ("if … then …", criteria to choose between options) and heuristics;
- ways to evaluate a result: what to measure, which signals to watch, which thresholds if the video gives any;
- mistakes to avoid, **with the reason**;
- the *why* of a method when the video explains it (that is what makes it adaptable).

**Drop** (one line under "Skipped" is enough): isolated facts or figures, anecdotes, name-dropping, news, opinions without a method, self-promotion, sponsors, digressions, repetitions, intro/outro.

**Special cases:**
- An anecdote or case study may hide a method: extract the principle and keep the anecdote in one sentence as an **example** of the method.
- A figure is kept only if it helps **decide** (threshold, order of magnitude, criterion), never for its own sake.
- Technical procedure (command, setting, formula): the exact value seen on screen **is** the method → copy it verbatim.

## What you watch: your whole part, frame by frame

Folder: `{{PART_DIR}}`

Your part was sampled so that **nothing shown on screen escapes you**: one frame at every screen change (analysed at 2 frames/s) and at least one frame every {{EVERY}} seconds. That is **{{NFRAMES}} frames** on **{{NSHEETS}} contact sheets** of 9 timestamped thumbnails. You must look at all of them; the orchestrator's check rejects incomplete notes.

1. Read `timeline.md` in full: every frame with what is said around it, timestamps in **full-video** time.
2. Open **every contact sheet, in order, skipping none**, with your image-reading tool: {{SHEETS}}
   For each sheet, write one line in your **visual log** (format below): what is actually on screen.
3. Whenever a thumbnail shows something other than a person talking (slide, diagram, whiteboard, interface, text, table, product, demonstration), **open the full-resolution frame** `frames/f_…jpg` and read all the text exactly.
4. Passages where the screen changes quickly (tool demo, slides flipping, writing on a whiteboard): densify to **1 frame/s** on that passage:
   `PY {{SCRIPTS_DIR}}/frame_at.py {{WORK_DIR}} --window H:MM:SS H:MM:SS --step 1`
   Text too small: `PY {{SCRIPTS_DIR}}/frame_at.py {{WORK_DIR}} H:MM:SS --crop x,y,w,h` (fractions, e.g. `0,0.5,1,0.5` = bottom half).
   (`PY` = `python3`; on Windows `python` or `py -3`. Run the command from the current folder, unchanged.)
5. `transcript.md` only if you need the text of a passage without a frame.

Stay within {{FROM}}–{{TO}}. If an idea is cut at the boundary, you may read 1 extra minute in a neighbouring part's `transcript.md`.

## What you write

**A single file: `{{NOTES_FILE}}`**, exactly in the format below. Every citation is written `[t=H:MM:SS]` (with `t=`, never a bare `[H:MM:SS]`), in full-video time, and every method, step, rule or example carries at least one.
Keep the section headings exactly as in the template (they are read by a script). Write the content in the language the orchestrator asked for (English by default); keep tool names and on-screen quotes as they appear.

{{NOTES_TEMPLATE}}

The **Visual log** section must contain **one line per contact sheet, all of them** ({{NSHEETS}}):
{{SHEET_LIST}}

## Rules

- When the screen and the narration disagree, **the screen wins**.
- Nothing invented: anything unclear goes under "Uncertain" with the reason.
- No secret or personal data seen on screen: use a placeholder (`<API_KEY>`, `<EMAIL>`).
- Write in the imperative, without narration ("Write the brief as…", not "he explains that…").
- Write **only** `{{NOTES_FILE}}`. Do not modify any other file.
- Your final reply to the orchestrator is 3 lines: number of methods, useful / skipped minutes, main uncertainties. All the content is in the file.
