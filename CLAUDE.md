# video-to-skill — instructions for Claude

This repo turns a video (YouTube URL or file) into a reusable **Claude skill**.
The user has nothing to prepare or run: **you install, extract, orchestrate and assemble.** Never ask them to run a command.
Talk to the user in their language. Write the generated skill in the language of their request unless they ask otherwise.

## When the user gives a video

Triggers: a video URL or file, "turn this video into a skill", "learn from this video", "read the repo and do it", `/video-to-skill <URL>`.

1. **Python** — `PY` = `python` or `py -3` on Windows (never `python3`, often a fake Microsoft Store shortcut there); `python3` on macOS/Linux.
2. **Prerequisites** — `PY scripts/bootstrap.py --check --json` (a few seconds).
   If `"ok": false`: say so in one sentence, then run `PY scripts/bootstrap.py --json --no-skill` (2 to 10 min: give it a 15-minute timeout or run it in the background, do not interrupt it). Only if that fails, follow [LLM_SETUP.md](LLM_SETUP.md).
3. **Method** — follow [SKILL.md](SKILL.md) with `SKILL_DIR` = the root of this repo. Always run the scripts with a **relative path** from the root (`PY scripts/extract.py …`): those are the commands the repo's permission rules allow.
   Working folder: `v2s_work/<short-id>/` (e.g. the YouTube id).
4. **Video longer than 45 min** — long-video mode of SKILL.md:
   - one `general-purpose` sub-agent **per part, all launched in parallel**, with the instruction: "Read and carry out `<absolute path>/part_NN/AGENT_PROMPT.md`. Write the notes in <the user's language>. Only write the notes file it names. Reply in 3 lines.";
   - then `PY scripts/assemble.py v2s_work/<id> --check`: a failing part (incomplete visual log, missing notes) → relaunch **its** sub-agent with the reason;
   - then plan → `assemble.py --plan … --out skills_out/<name>` → merges → the skill's `SKILL.md`.
5. **Delivery** — the final skill goes to `skills_out/<name>/` and must pass `PY scripts/validate_skill.py skills_out/<name>`. Only then ask whether the user wants it installed in `~/.claude/skills/<name>/`. That is the only question to ask, plus cookies if YouTube requires them.
6. **Final message**, short: skill name and location, number of methods, coverage (parts, contact sheets reviewed, densified passages), main uncertainties.

## Other requests

- **Just download**: `PY scripts/download.py <URL> [--out downloads]` (JSON on stdout; on failure, read `hint`).
- **Install / repair the environment**: [LLM_SETUP.md](LLM_SETUP.md).
- **Change the tool itself**: scripts live in `scripts/`, sub-agent templates in `references/`. After a change, run `PY scripts/bootstrap.py --no-skill --skip-model` (its self-test covers extraction, splitting and validation).
