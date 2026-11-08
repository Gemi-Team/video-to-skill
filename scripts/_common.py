"""
_common.py — helpers shared by the video-to-skill scripts.

- utf8_console()        : no UnicodeEncodeError on Windows consoles (cp1252)
- which(name)           : like shutil.which, but also looks where winget / brew / pip / deno
                          put binaries that are not on PATH yet (fresh install, new shell needed)
- ensure_ffmpeg()       : finds ffmpeg + ffprobe (PATH, winget, static-ffmpeg) and puts them on PATH
- find_js_runtime()     : deno / node / bun, needed by yt-dlp for YouTube
- pip_install(pkgs)     : installs into the interpreter running the script (venv, then --user)
"""
import glob
import importlib
import os
import shutil
import site
import subprocess
import sys
import sysconfig

PY = sys.executable


def utf8_console():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _extra_dirs():
    dirs = []
    for scheme in (None, f"{os.name}_user"):
        try:
            dirs.append(sysconfig.get_path("scripts", scheme) if scheme else sysconfig.get_path("scripts"))
        except KeyError:
            pass
    home = os.path.expanduser("~")
    if os.name == "nt":
        la = os.environ.get("LOCALAPPDATA", "")
        if la:
            dirs.append(os.path.join(la, "Microsoft", "WinGet", "Links"))
            dirs += glob.glob(os.path.join(la, "Microsoft", "WinGet", "Packages", "*FFmpeg*", "*", "bin"))
            dirs += glob.glob(os.path.join(la, "Microsoft", "WinGet", "Packages", "DenoLand.Deno*"))
        dirs += [r"C:\ffmpeg\bin", os.path.expandvars(r"%ProgramFiles%\ffmpeg\bin"),
                 os.path.expandvars(r"%ProgramFiles%\nodejs"), os.path.join(home, "scoop", "shims"),
                 r"C:\ProgramData\chocolatey\bin"]
    else:
        dirs += ["/opt/homebrew/bin", "/usr/local/bin", os.path.join(home, ".local", "bin")]
    dirs += [os.path.join(home, ".deno", "bin"), os.path.join(home, ".bun", "bin")]
    return [d for d in dirs if d and os.path.isdir(d)]


def which(name):
    p = shutil.which(name)
    if p:
        return p
    for d in _extra_dirs():
        p = shutil.which(name, path=d)
        if p:
            return p
    return None


def _prepend_path(exe):
    d = os.path.dirname(exe)
    if d and d not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def ensure_ffmpeg(fetch=True):
    """Return (ffmpeg, ffprobe) paths, or (None, None). Makes both callable as plain 'ffmpeg'."""
    ff, fp = which("ffmpeg"), which("ffprobe")
    if not (ff and fp) and fetch:
        try:  # pip install static-ffmpeg → downloads portable binaries on first use
            from static_ffmpeg import run as sf
            ff, fp = sf.get_or_fetch_platform_executables_else_raise()
        except Exception:
            pass
    if ff and fp:
        _prepend_path(ff)
        _prepend_path(fp)
        return ff, fp
    return None, None


def find_js_runtime():
    """yt-dlp needs a JS runtime to solve YouTube challenges. Deno is preferred, node/bun work."""
    for name in ("deno", "node", "bun"):
        p = which(name)
        if p:
            return name, p
    return None, None


def pip_install(pkgs, upgrade=False):
    """Install into the current interpreter. Returns (ok, message)."""
    base = [PY, "-m", "pip", "install", "-q", "--disable-pip-version-check"] + (["-U"] if upgrade else [])
    in_venv = sys.prefix != sys.base_prefix
    attempts = [base + pkgs]
    if not in_venv:
        attempts += [base + ["--user"] + pkgs, base + ["--user", "--break-system-packages"] + pkgs]
    err = ""
    for cmd in attempts:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            importlib.invalidate_caches()
            try:
                site.addsitedir(site.getusersitepackages())
            except Exception:
                pass
            return True, " ".join(cmd[1:])
        err = (r.stderr or r.stdout).strip()
    return False, err[-1500:]


def fmt_ts(sec):
    sec = max(0, sec)
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
