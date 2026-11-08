# LLM_SETUP — setup guide for an AI agent

> **You are an LLM (Claude Code, Cursor, Codex, Copilot…) and a developer asked you to install or fix this repo.**
> Follow this file in order. The developer should have **nothing** to do, except when a decision or admin rights are needed.

What you must end up with:
- the Python dependencies (`pillow`, `yt-dlp[default,curl-cffi]`, `faster-whisper`);
- working `ffmpeg` + `ffprobe`;
- a JavaScript runtime for yt-dlp (deno, node or bun);
- a **Whisper** model downloaded and tested (local transcription, offline afterwards);
- the skill copied to `~/.claude/skills/video-to-skill/` (for Claude Code);
- a passing self-test, and a real YouTube download that works.

**All of this takes a single command: `scripts/bootstrap.py`.** Your job: pick the right Python, run the command, read the report, fix the ✗, verify, report back.

> If the user asked to **turn a video into a skill**, this file is only a detour: follow [CLAUDE.md](CLAUDE.md), which runs `bootstrap.py --check` and then the install if needed, and come back here only on failure. Inside this repo, use `--no-skill`: the repo itself is the skill.

---

## Step 0 — Find the right Python interpreter

Try in order and keep the **first one that prints a version ≥ 3.9** (3.11+ recommended):

| OS | Commands to try |
|---|---|
| Windows | `py -3 --version` → `python --version` |
| macOS / Linux | `python3 --version` → `python --version` |

⚠ **Windows trap**: `python3` (and sometimes `python`) can be a fake Microsoft Store shortcut that prints "Python was not found…" or opens the Store. It is **not** Python. Move on to the next command.

No Python ≥ 3.9? Suggest to the developer (do not do it without approval, it changes the system):
- Windows: `winget install -e --id Python.Python.3.12`
- macOS: `brew install python@3.12`
- Debian/Ubuntu: `sudo apt install python3 python3-pip python3-venv`

From here on, `PY` = the chosen command (e.g. `py -3`, `python3`).

**Which Python?** Use the one the skill will be run with later (usually the user's global Python, since Claude Code calls `python`/`python3`). If the developer wants isolated packages, create a venv (`PY -m venv .venv`) and use `.venv/Scripts/python` (Windows) or `.venv/bin/python` — then tell them the scripts must be run with that Python.

---

## Step 1 — Run the install

From the repo root:

```bash
PY scripts/bootstrap.py --json
```

- **It takes a while** (2 to 10 min: packages, ffmpeg if missing, and the Whisper model). Give the command a timeout of at least **10 minutes** or run it in the background. Do not interrupt it because it is quiet.
- Progress goes to stderr, the **JSON report** to stdout.
- It is **idempotent**: rerun it as often as needed.
- **No admin rights**, never `sudo`. If ffmpeg is missing, the script tries `winget` (Windows) / `brew` (macOS), then falls back to portable binaries via pip (`static-ffmpeg`).

Useful options:

| Option | When |
|---|---|
| `--check` | diagnostics only, installs nothing (do this first to show the developer the current state) |
| `--whisper-model tiny\|base\|small\|medium\|large-v3\|turbo` | model choice (default `small`, see table below) |
| `--skip-model` | do not pre-download the model (it will be fetched on the first transcription) |
| `--minimal` | pillow + ffmpeg only (local files, no URLs, no transcription) |
| `--no-system` | use neither winget nor brew (locked-down machine) → pip only |
| `--no-skill` / `--project` / `--skill-dir DIR` | where to copy the Claude Code skill |
| `--test-url URL` | also test a real download (pick a short video) |

JSON report:
```json
{ "ok": true, "python": "C:\\…\\python.exe",
  "steps": [ {"name": "ffmpeg", "status": "ok|warn|fail|skip", "detail": "…", "fix": "…"} ],
  "next": ["…/python scripts/download.py <URL>", "…"] }
```
`ok: true` ⇔ no step in `fail`. `warn` steps are not blocking (mention them to the developer).

---

## Step 2 — Fix the ✗

For every `fail` step, apply its `fix` field, then **rerun `bootstrap.py`**. Common cases:

| Symptom | Cause | Fix |
|---|---|---|
| `externally-managed-environment` (Debian/Ubuntu, Homebrew) | PEP 668: pip refuses the system Python | The script already retries with `--user --break-system-packages`. If that still fails: create a venv (step 0) and rerun with that Python |
| `pip unavailable` | Python without pip | `PY -m ensurepip --upgrade`; Debian: `sudo apt install python3-pip` (ask the developer) |
| ffmpeg not found after `winget` | PATH is only updated in **new** terminals | nothing to do: the scripts also look in the WinGet folders. Otherwise rerun with `--no-system` (pip binaries) |
| `whisper model … fail` + network / SSL / 403 error | HuggingFace blocked (corporate proxy) | `HTTPS_PROXY=http://proxy:port`; or mirror `HF_ENDPOINT=https://hf-mirror.com`; or copy the model folder into the HF cache from another machine. Test with `--whisper-model tiny` first |
| `cublas64_12.dll`, `libcudnn`, `CUDA failed` | NVIDIA GPU present but CUDA 12 / cuDNN 9 libraries missing | Nothing required: automatic CPU fallback. For the GPU: install CUDA 12 + cuDNN 9 (Linux: `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`) |
| `JS runtime … warn` | no deno, node or bun | the script installs `deno` via pip; otherwise `winget install DenoLand.Deno` / `brew install deno` |
| Python 3.10 `warn` | yt-dlp is dropping 3.10 | still works; suggest upgrading to 3.11+ |
| `certificate verify failed` | proxy intercepting TLS | ask the developer for the company certificate; **do not disable** TLS verification |

Never work around a protection (antivirus, company policy, network block): explain the block to the developer and offer the alternative (local video file, another network).

---

## Step 3 — Verify for real

```bash
# 1. YouTube download (19-second video, subtitles + metadata)
PY scripts/download.py "https://www.youtube.com/watch?v=jNQXAC9IVRw" --out downloads --no-progress

# 2. Full pipeline, forcing Whisper transcription (ignores YouTube subtitles)
PY scripts/extract.py "downloads/<file>.mp4" --out v2s_work --whisper
```
✔ Success: `download.py` prints `"ok": true`; `extract.py` prints `"transcript": "whisper small"` (or the chosen model) and `v2s_work/transcript.md` contains timestamped text `[0:00] …`.

Then delete `downloads/` and `v2s_work/` if the developer does not need them (they are in `.gitignore`).

---

## Step 4 — Report to the developer

Short, in this format:
```
✔ video-to-skill installed (Python 3.12, C:\…\python.exe)
- ffmpeg 7.1 (winget) · yt-dlp 2026.x + deno · Whisper small on CPU
- Claude Code skill: ~/.claude/skills/video-to-skill → /video-to-skill <URL>
- Tested: self-test OK, YouTube download OK, transcription OK
⚠ Good to know: <warnings if any, e.g. Python 3.10>
```

---

## Using the scripts (quick reference)

```bash
# Download
PY scripts/download.py URL [URL…] [--out downloads] [--lang en] [--max-height 720]
PY scripts/download.py --file urls.txt                     # one URL per line
PY scripts/download.py URL --playlist --max-videos 20      # playlist / channel
PY scripts/download.py URL --audio-only                    # audio only, for transcription
PY scripts/download.py URL --section 12:00-25:00           # one section
PY scripts/download.py URL --cookies-from-browser firefox  # age / members-only / "not a bot"

# Turn a video into "watchable" material (key frames + transcript)
PY scripts/extract.py <URL or file> --out v2s_work [--lang en] [--whisper-model small] [--whisper-device cpu]
```
`download.py` prints a JSON list on stdout: `url, ok, files, subtitles, info_json, title, duration, chapters, error, hint`. On failure, **read `hint`**: it says what to do (cookies, update, network…). yt-dlp is updated and the attempt retried automatically when YouTube has changed.

A file downloaded by `download.py` can be passed straight to `extract.py`: its neighbouring subtitles and chapters (`.info.json`) are picked up automatically.

### Choosing the Whisper model

| Model | Size | Accuracy | CPU speed | Use |
|---|---|---|---|---|
| `tiny` | ~75 MB | low | very fast | tests |
| `base` | ~145 MB | medium | fast | drafts |
| `small` | ~480 MB | good | fair | **default**, good trade-off |
| `medium` | ~1.5 GB | very good | slow | accents, technical jargon |
| `turbo` | ~1.6 GB | very good | slow | GPU recommended |
| `large-v3` | ~3 GB | best | very slow | GPU recommended |

An NVIDIA GPU (CUDA 12 + cuDNN 9) speeds up the large models a lot; without a GPU, stay on `small`.

### "Sign in to confirm you're not a bot" / age-restricted video

Rerun with `--cookies-from-browser firefox` (or `edge`, `chrome`, `brave`) using a browser **where the developer is signed in to YouTube**. On Windows, Chrome/Edge lock and encrypt their cookies while open: Firefox is the most reliable, otherwise ask the developer to close the browser. Always ask the developer before reading their browser cookies.

---

## Rules for the agent

- **Announce** what you install before doing it (one sentence is enough).
- No `sudo`, no changes to security settings, no disabling TLS / antivirus. If admin rights are truly needed, **ask**.
- Only download videos the developer has the right to use (learning, internal documentation); do not redistribute the files.
- Never display or copy cookies, tokens or passwords in your messages or in the repo's files.
- If something failed or was not verified, **say so**; never declare "installed" based on an `ok: false` report.
