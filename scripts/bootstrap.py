#!/usr/bin/env python3
"""
bootstrap.py — installs AND verifies everything video-to-skill needs (Windows, macOS, Linux).
No admin rights required, never sudo. Idempotent: safe to rerun.

  python scripts/bootstrap.py                      # everything: packages, ffmpeg, JS runtime, Whisper (small),
                                                   #             self-test, Claude Code skill install
  python scripts/bootstrap.py --check              # diagnostics only, installs nothing
  python scripts/bootstrap.py --minimal            # pillow + ffmpeg (no URLs, no transcription)
  python scripts/bootstrap.py --whisper-model medium   # tiny | base | small | medium | large-v3 | turbo
  python scripts/bootstrap.py --skip-model         # do not pre-download the Whisper model
  python scripts/bootstrap.py --no-skill           # do not copy the skill to ~/.claude/skills
  python scripts/bootstrap.py --project            # copy the skill to ./.claude/skills (current project)
  python scripts/bootstrap.py --test-url URL       # also test a real YouTube download
  python scripts/bootstrap.py --json               # JSON report on stdout (for an LLM / CI)

Exit code: 0 = everything required works; 1 = at least one ✗ (see the "fix" field).
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from _common import PY, ensure_ffmpeg, find_js_runtime, pip_install, utf8_console, which  # noqa: E402

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # useless noise on Windows
REPORT = []
JSON_MODE = False


def log(msg):
    print(f"[bootstrap] {msg}", file=sys.stderr, flush=True)


def add(name, status, detail="", fix=""):
    """status: ok | warn | fail | skip"""
    REPORT.append({"name": name, "status": status, "detail": detail, "fix": fix})
    icon = {"ok": "✔", "warn": "⚠", "fail": "✗", "skip": "–"}[status]
    log(f"{icon} {name}: {detail}" + (f"  → {fix}" if fix and status in ("warn", "fail") else ""))


def sh(cmd, timeout=900):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError:
        return 127, f"not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"timed out ({timeout}s)"


def importable(mod):
    import importlib.util
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


# ---------------------------------------------------------------- steps
def step_python():
    v = sys.version_info
    detail = f"{platform.python_version()} ({PY})"
    if v < (3, 9):
        add("python", "fail", detail, "Python 3.9+ required (3.11+ recommended): https://www.python.org/downloads/")
        return False
    if v < (3, 11):
        add("python", "warn", detail, "works, but yt-dlp is dropping Python 3.10: move to 3.11+ when possible")
    else:
        add("python", "ok", detail)
    return True


def step_pip(check):
    code, out = sh([PY, "-m", "pip", "--version"], 60)
    if code != 0 and not check:
        log("pip missing → python -m ensurepip")
        sh([PY, "-m", "ensurepip", "--upgrade"], 300)
        code, out = sh([PY, "-m", "pip", "--version"], 60)
    if code != 0:
        add("pip", "fail", "pip unavailable",
            "Debian/Ubuntu: sudo apt install python3-pip python3-venv; otherwise reinstall Python with pip")
        return False
    add("pip", "ok", out.split(" from ")[0].strip())
    return True


def step_package(label, module, spec, check, upgrade=False, required=True):
    present = importable(module)
    if check or (present and not upgrade):
        if present:
            add(label, "ok", version_of(module))
        else:
            add(label, "fail" if required else "warn", "not installed", f'"{PY}" -m pip install -U "{spec}"')
        return present
    log(f"pip install {'-U ' if upgrade else ''}{spec} …")
    ok, msg = pip_install([spec], upgrade=upgrade)
    if ok and importable(module):
        add(label, "ok", version_of(module))
        return True
    add(label, "fail" if required else "warn", f"install failed: {msg[-300:]}",
        f'"{PY}" -m pip install -U "{spec}"  (or in a venv: python -m venv .venv)')
    return False


def version_of(module):
    try:
        from importlib.metadata import version
        dist = {"PIL": "pillow", "yt_dlp": "yt-dlp", "yt_dlp_ejs": "yt-dlp-ejs",
                "faster_whisper": "faster-whisper", "curl_cffi": "curl_cffi"}.get(module, module)
        return version(dist)
    except Exception:
        return "installed"


def step_ffmpeg(check, allow_system):
    ff, fp = ensure_ffmpeg(fetch=True)
    if not ff and not check:
        sysname = platform.system()
        tried = None
        if allow_system and sysname == "Windows" and which("winget"):
            tried = "winget install Gyan.FFmpeg"
            log(f"{tried} … (may take a few minutes)")
            sh(["winget", "install", "-e", "--id", "Gyan.FFmpeg", "--accept-source-agreements",
                "--accept-package-agreements", "--disable-interactivity"], 1200)
        elif allow_system and sysname == "Darwin" and which("brew"):
            tried = "brew install ffmpeg"
            log(f"{tried} …")
            sh(["brew", "install", "ffmpeg"], 1800)
        elif allow_system and sysname == "Linux" and hasattr(os, "geteuid") and os.geteuid() == 0 and which("apt-get"):
            tried = "apt-get install ffmpeg"
            log(f"{tried} …")
            sh(["apt-get", "install", "-y", "ffmpeg"], 1800)
        ff, fp = ensure_ffmpeg(fetch=False)
        if not ff:  # universal fallback, no rights needed: portable binaries via pip
            log("fallback: pip install static-ffmpeg (portable binaries)")
            pip_install(["static-ffmpeg"])
            ff, fp = ensure_ffmpeg(fetch=True)
    if ff and fp:
        _, out = sh([ff, "-version"], 30)
        add("ffmpeg", "ok", (out.splitlines() or ["?"])[0][:80] + f" ({ff})")
        return True
    add("ffmpeg", "fail", "ffmpeg/ffprobe not found",
        "Windows: winget install Gyan.FFmpeg | macOS: brew install ffmpeg | Linux: sudo apt install ffmpeg "
        "| no rights: pip install static-ffmpeg")
    return False


def step_js(check):
    name, path = find_js_runtime()
    if not name and not check:
        log("no JS runtime → pip install deno (needed by yt-dlp for YouTube)")
        pip_install(["deno"])
        name, path = find_js_runtime()
    if name:
        add("JS runtime (yt-dlp)", "ok", f"{name} ({path})")
        return True
    add("JS runtime (yt-dlp)", "warn", "no deno, node or bun",
        "pip install deno (or winget install DenoLand.Deno / brew install deno); without it YouTube may refuse formats")
    return False


def step_whisper(check, model, skip_model):
    if not importable("faster_whisper"):
        return False
    gpu = 0
    try:
        import ctranslate2
        gpu = ctranslate2.get_cuda_device_count()
    except Exception:
        pass
    add("CUDA GPU", "ok" if gpu else "skip", f"{gpu} GPU(s) detected" if gpu else "none → Whisper will run on CPU (slower)")
    if check or skip_model:
        add(f"whisper model {model}", "skip", "not tested (--check / --skip-model)")
        return True
    ff, _ = ensure_ffmpeg(fetch=False)
    tmp = Path(tempfile.mkdtemp(prefix="v2s_wh_"))
    wav = tmp / "tone.wav"
    if ff:
        sh([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-ar", "16000", "-ac", "1",
            str(wav)], 60)
    from faster_whisper import WhisperModel
    errors = []
    for dev in (["auto", "cpu"] if gpu else ["cpu"]):
        try:
            log(f"downloading / loading Whisper model \"{model}\" ({dev})… (first time: 75 MB to 3 GB)")
            m = WhisperModel(model, device=dev, compute_type="int8")
            if wav.exists():
                list(m.transcribe(str(wav), vad_filter=False)[0])
            add(f"whisper model {model}", "ok", f"ready on {'GPU' if dev == 'auto' and gpu else 'CPU'}"
                + ("" if dev == "auto" or not gpu else " (GPU present but unusable: CUDA/cuDNN libraries missing)"))
            shutil.rmtree(tmp, ignore_errors=True)
            return True
        except Exception as e:
            errors.append(f"{dev}: {type(e).__name__}: {str(e)[:200]}")
    shutil.rmtree(tmp, ignore_errors=True)
    add(f"whisper model {model}", "fail", " | ".join(errors),
        "HuggingFace download blocked? proxy: HTTPS_PROXY=…; mirror: HF_ENDPOINT=https://hf-mirror.com; "
        "or --whisper-model tiny to test")
    return False


def step_skill(dest):
    if dest is None:
        add("Claude Code skill", "skip", "--no-skill")
        return True
    dest = Path(dest).expanduser().resolve()
    if dest == ROOT:
        add("Claude Code skill", "ok", f"already in place ({dest})")
        return True
    dest.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for item in ("SKILL.md", "LLM_SETUP.md", "requirements.txt", "scripts", "references"):
        src = ROOT / item
        if not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, dest / item, dirs_exist_ok=True, ignore=ignore)
        else:
            shutil.copy2(src, dest / item)
    add("Claude Code skill", "ok", f"copied to {dest}  (Claude Code: /video-to-skill <URL>)")
    return True


def step_selftest():
    gen = ROOT / "tests" / "make_test_video.py"
    if not gen.exists():
        add("self-test", "skip", "tests/ missing (skill installed without the repo)")
        return True
    tmp = Path(tempfile.mkdtemp(prefix="v2s_selftest_"))
    try:
        code, out = sh([PY, str(gen), str(tmp / "src")], 300)
        if code != 0:
            add("self-test", "fail", f"test video generation: {out.strip()[-300:]}", "see the ffmpeg step")
            return False
        code, out = sh([PY, str(HERE / "extract.py"), str(tmp / "src" / "tuto_venv.mp4"), "--out", str(tmp / "work"),
                        "--no-transcribe"], 600)
        man = tmp / "work" / "manifest.json"
        if code != 0 or not man.exists():
            add("self-test", "fail", f"extract.py: {out.strip()[-400:]}", "rerun with --check and read the error")
            return False
        m = json.loads(man.read_text(encoding="utf-8"))
        ok = len(m["frames"]) >= 5 and m["sheets"] and str(m["transcript_source"]).startswith("subtitles")
        code2, out2 = sh([PY, str(HERE / "validate_skill.py"), str(ROOT / "examples" / "python-venv-requests")], 60)
        # simulated long-video split: 20-second parts on the test video
        code3, out3 = sh([PY, str(HERE / "parts.py"), str(tmp / "work"), "--max-minutes", "0.34"], 300)
        try:  # sh() returns stdout (the JSON) followed by stderr (the logs)
            nparts = len(json.JSONDecoder().raw_decode(out3.lstrip())[0]) if code3 == 0 else 0
        except ValueError:
            nparts = 0
        prompt_ok = (tmp / "work" / "part_01" / "AGENT_PROMPT.md").exists()
        detail = (f"test video → {len(m['frames'])} frames, {len(m['sheets'])} sheets, "
                  f"transcript: {m['transcript_source']}; validate_skill: {'OK' if code2 == 0 else 'FAILED'}; "
                  f"split: {nparts} parts{'' if prompt_ok else ' (AGENT_PROMPT.md missing)'}")
        ok = ok and code2 == 0 and nparts >= 2 and prompt_ok
        add("self-test", "ok" if ok else "fail", detail,
            "" if ok else "unexpected output: rerun the failing step by hand and read the error")
        return ok
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def step_test_url(url):
    from download import download_one
    tmp = Path(tempfile.mkdtemp(prefix="v2s_dl_"))
    try:
        r = download_one(url, tmp, progress=False)
        if r["ok"]:
            add("YouTube download", "ok",
                f"\"{r['title']}\" ({r['duration']} s), {len(r['subtitles'])} subtitle file(s)")
        else:
            add("YouTube download", "fail", (r["error"] or "")[-300:], r["hint"] or "")
        return r["ok"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- main
def main():
    global JSON_MODE
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="diagnostics only, install nothing")
    ap.add_argument("--minimal", action="store_true", help="pillow + ffmpeg only")
    ap.add_argument("--whisper-model", default="small")
    ap.add_argument("--skip-model", action="store_true")
    ap.add_argument("--no-system", action="store_true", help="do not use winget/brew/apt (pip only)")
    ap.add_argument("--no-skill", action="store_true")
    ap.add_argument("--project", action="store_true", help="skill in ./.claude/skills/video-to-skill")
    ap.add_argument("--skill-dir", default=None, help="destination folder for the skill")
    ap.add_argument("--no-selftest", action="store_true")
    ap.add_argument("--test-url", default=None, help="short URL to download to test yt-dlp")
    ap.add_argument("--json", action="store_true", help="JSON report on stdout")
    a = ap.parse_args()
    JSON_MODE = a.json

    log(f"{platform.system()} {platform.release()} — {'diagnostics' if a.check else 'install'}")
    if step_python() and step_pip(a.check):
        step_package("pillow", "PIL", "pillow>=10", a.check)
        step_ffmpeg(a.check, not a.no_system)
        if not a.minimal:
            # yt-dlp often breaks when YouTube changes → always the latest version
            step_package("yt-dlp", "yt_dlp", "yt-dlp[default]", a.check, upgrade=True)
            step_package("yt-dlp-ejs (YouTube JS challenges)", "yt_dlp_ejs", "yt-dlp-ejs", a.check, required=False)
            # through yt-dlp's extra: it pins a compatible curl_cffi (otherwise "no impersonate target")
            step_package("curl_cffi (impersonation)", "curl_cffi", "yt-dlp[curl-cffi]", a.check, upgrade=True,
                         required=False)
            step_js(a.check)
            if step_package("faster-whisper", "faster_whisper", "faster-whisper", a.check):
                step_whisper(a.check, a.whisper_model, a.skip_model)
        if not a.check:
            dest = None if a.no_skill else (a.skill_dir or (Path.cwd() / ".claude/skills/video-to-skill" if a.project
                                                            else Path.home() / ".claude/skills/video-to-skill"))
            step_skill(dest)
            if not a.no_selftest:
                step_selftest()
            if a.test_url:
                step_test_url(a.test_url)

    fails = [r for r in REPORT if r["status"] == "fail"]
    summary = {"ok": not fails, "python": PY, "platform": platform.platform(), "steps": REPORT,
               "next": [f'"{PY}" scripts/download.py <URL>',
                        f'"{PY}" scripts/extract.py <URL or file> --out v2s_work']}
    if a.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("\n" + ("✔ All set." if not fails else f"✗ {len(fails)} problem(s) to fix:"))
        for r in fails:
            print(f"  - {r['name']}: {r['detail'][:200]}\n    fix: {r['fix']}")
        warns = [r for r in REPORT if r["status"] == "warn"]
        for r in warns:
            print(f"  ⚠ {r['name']}: {r['fix']}")
        print(f"\nPython to use: {PY}")
        print(f'  "{PY}" scripts/download.py "https://www.youtube.com/watch?v=…"')
        print(f'  "{PY}" scripts/extract.py "<URL or file>" --out v2s_work')
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
