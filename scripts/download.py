#!/usr/bin/env python3
"""
download.py — downloads YouTube videos (or any site yt-dlp supports) + subtitles + metadata,
ready for extract.py or Whisper.

  python scripts/download.py "https://www.youtube.com/watch?v=…"
  python scripts/download.py URL1 URL2 --out downloads --lang en
  python scripts/download.py --file urls.txt                 # one URL per line, # = comment
  python scripts/download.py URL --playlist --max-videos 10  # playlist / channel
  python scripts/download.py URL --audio-only                # audio only (for transcription)
  python scripts/download.py URL --section 12:00-25:00       # only one section
  python scripts/download.py URL --cookies-from-browser firefox   # age / members-only / "not a bot"

What the script does on its own:
  - installs yt-dlp if missing, updates it and retries when YouTube has changed (403, nsig…)
  - finds ffmpeg (PATH, winget, static-ffmpeg) and a JS runtime (deno/node/bun) for yt-dlp
  - only fetches useful subtitles (not the hundred auto-translations that trigger HTTP 429)
  - a subtitle failure never prevents the video download

Output: progress on stderr, then a JSON summary on stdout
  [{"url", "ok", "files", "subtitles", "info_json", "title", "duration", "error", "hint"}]
Exit code: 0 if everything succeeded, 1 otherwise.
"""
import argparse
import glob
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PY, ensure_ffmpeg, find_js_runtime, pip_install, utf8_console  # noqa: E402

VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov", ".m4v")
AUDIO_EXT = (".m4a", ".mp3", ".opus", ".ogg", ".wav", ".aac", ".flac", ".webm")
DEFAULT_TEMPLATE = "%(title).70B [%(id)s].%(ext)s"

# (pattern in yt-dlp's output, category, hint)
ERRORS = [
    (r"sign in to confirm|not a bot", "bot",
     "YouTube asks for a sign-in: rerun with --cookies-from-browser firefox (or chrome/edge, browser closed)."),
    (r"confirm your age|age.restricted|inappropriate for some users", "age",
     "Age-restricted video: rerun with --cookies-from-browser <browser signed in to an adult account>."),
    (r"private video|members.only|join this channel", "private",
     "Private / members-only video: --cookies-from-browser with an account that has access."),
    (r"not available in your country|geo.?restrict", "geo", "Video blocked in this country."),
    (r"video unavailable|video is unavailable|isn't available|has been removed|account .* terminated|"
     r"does not exist", "unavailable",
     "Video unavailable or removed."),
    (r"429|too many requests", "ratelimit",
     "YouTube is rate-limiting: wait a few minutes, or use --cookies-from-browser."),
    (r"getaddrinfo|name or service not known|temporary failure in name resolution|timed out|"
     r"network is unreachable|connection refused|proxy|certificate verify failed", "network",
     "Network blocked or proxy: download the video by hand and pass the local file."),
    (r"http error 403|nsig|signature|unable to extract|requested format is not available|"
     r"precondition check failed|no video formats found|unsupported url|po token", "outdated",
     "yt-dlp is probably too old for the current YouTube: python -m pip install -U \"yt-dlp[default]\"."),
]


def log(msg):
    print(f"[download] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------- dependencies
def ytdlp_version():
    try:
        import yt_dlp.version
        return yt_dlp.version.__version__
    except Exception:
        return None


def has_ejs():
    """yt-dlp-ejs = scripts that solve YouTube's JS challenges (otherwise: "some formats may be missing")."""
    import importlib.util
    return importlib.util.find_spec("yt_dlp_ejs") is not None


def ensure_ytdlp(auto_install=True, upgrade=False):
    v = ytdlp_version()
    if v and not upgrade and (has_ejs() or not auto_install):
        return v
    if not auto_install:
        return v
    log(("updating" if v else "installing") + " yt-dlp…")
    ok, msg = pip_install(["yt-dlp[default]"], upgrade=True)
    if not ok:
        log(f"pip failed: {msg}")
    for m in [m for m in sys.modules if m == "yt_dlp" or m.startswith("yt_dlp.")]:
        del sys.modules[m]
    return ytdlp_version() or v


def classify(text):
    low = text.lower()
    for pat, cat, hint in ERRORS:
        if re.search(pat, low):
            return cat, hint
    return "unknown", "See the last yt-dlp lines above."


# ---------------------------------------------------------------- core
def sub_langs(lang):
    langs = [lang] if lang else ["en"]
    if "en" not in langs:
        langs.append("en")
    # no "en.*": it also matches the auto-translations (en-de, en-ja…) → HTTP 429 from YouTube
    # {l}-XX (upper case) = manual regional variant (fr-FR, en-US); yt-dlp matches case-insensitively → (?-i:)
    # ".*-orig" = auto-captions in the video's original language, whatever it is
    return ",".join([f"{l},{l}-orig,{l}-(?-i:[A-Z]{{2}})" for l in langs] + [".*-orig"])


def build_cmd(url, out_dir, template, paths_file, *, max_height, audio_only, subs, lang, section,
              playlist, max_videos, cookies_browser, cookies_file, progress, has_ffmpeg, version):
    cmd = [PY, "-m", "yt_dlp", "--ignore-errors", "--no-write-playlist-metafiles",
           "--write-info-json", "-P", str(out_dir), "-o", template,
           "--print-to-file", "after_move:filepath", str(paths_file)]
    cmd += ["--newline", "--progress-delta", "5"] if progress else ["--no-progress"]
    cmd += ["--yes-playlist"] if playlist else ["--no-playlist"]
    if playlist and max_videos:
        cmd += ["--playlist-end", str(max_videos)]
    if audio_only:
        cmd += ["-f", "ba[ext=m4a]/ba/b"] + (["-x"] if has_ffmpeg else [])
    elif has_ffmpeg:
        h = max_height
        cmd += ["-f", f"bv*[height<={h}]+ba/b[height<={h}]/b", "--merge-output-format", "mp4"]
    else:  # without ffmpeg audio+video cannot be merged → pre-merged file (often 360p)
        cmd += ["-f", f"b[height<={max_height}]/b"]
    if subs:
        cmd += ["--write-subs", "--write-auto-subs", "--sub-langs", sub_langs(lang),
                "--sub-format", "vtt/srt/best"]
    if section:
        cmd += ["--download-sections", "*" + section]
    if cookies_browser:
        cmd += ["--cookies-from-browser", cookies_browser]
    if cookies_file:
        cmd += ["--cookies", str(cookies_file)]
    js_name, js_path = find_js_runtime()
    if js_name and version and version >= "2025.11":
        cmd += ["--js-runtimes", f"{js_name}:{js_path}"]
    cmd.append(url)
    return cmd


def run_streaming(cmd):
    """Run yt-dlp, echo its output to stderr, return (returncode, last lines)."""
    tail = []
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace")
    for line in p.stdout:
        sys.stderr.write("  " + line)
        tail.append(line.rstrip())
        tail = tail[-60:]
    p.wait()
    return p.returncode, tail


def sidecars(media: Path):
    stem = glob.escape(str(media.with_suffix("")))  # titles often contain [ ] → glob.escape
    subs = sorted(glob.glob(stem + ".*.vtt") + glob.glob(stem + ".*.srt"))
    info = media.with_suffix(".info.json")
    return subs, (str(info) if info.exists() else None)


def download_one(url, out_dir, template=DEFAULT_TEMPLATE, *, max_height=720, audio_only=False, subs=True,
                 lang=None, section=None, playlist=False, max_videos=None, cookies_browser=None,
                 cookies_file=None, progress=True, auto_install=True):
    """Download one URL (video or playlist). Returns a result dict (see module docstring)."""
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    res = {"url": url, "ok": False, "files": [], "subtitles": [], "info_json": None,
           "title": None, "duration": None, "chapters": [], "error": None, "hint": None}
    version = ensure_ytdlp(auto_install)
    if not version:
        res.update(error="yt-dlp missing", hint='python -m pip install -U "yt-dlp[default]"')
        return res
    ff, _ = ensure_ffmpeg()
    if not ff:
        log("⚠ ffmpeg not found: limited quality (no audio+video merge). Run scripts/bootstrap.py.")
    updated = False
    for attempt in range(3):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tf:
            paths_file = Path(tf.name)
        cmd = build_cmd(url, out_dir, template, paths_file, max_height=max_height, audio_only=audio_only,
                        subs=subs, lang=lang, section=section, playlist=playlist, max_videos=max_videos,
                        cookies_browser=cookies_browser, cookies_file=cookies_file, progress=progress,
                        has_ffmpeg=bool(ff), version=version)
        log(f"{url}  (yt-dlp {version}{', attempt ' + str(attempt + 1) if attempt else ''})")
        code, tail = run_streaming(cmd)
        files = [l.strip() for l in paths_file.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
        paths_file.unlink(missing_ok=True)
        files = [f for f in dict.fromkeys(files) if Path(f).exists()]
        if files:
            break
        errors = "\n".join(l for l in tail if "ERROR" in l) or "\n".join(tail[-5:])
        cat, hint = classify(errors)
        res.update(error=errors[-800:] or f"yt-dlp exit code {code}", hint=hint)
        if cat == "outdated" and not updated and auto_install:
            log("yt-dlp looks outdated → updating, then retrying")
            version = ensure_ytdlp(auto_install, upgrade=True)
            updated = True
            continue
        if cat == "ratelimit" and attempt == 0:
            log("HTTP 429 → waiting 30 s, then retrying")
            time.sleep(30)
            continue
        return res

    res.update(ok=True, files=files, error=None, hint=None)
    for f in files:
        s, info = sidecars(Path(f))
        res["subtitles"] += s
        res["info_json"] = res["info_json"] or info
    if res["info_json"]:
        try:
            d = json.loads(Path(res["info_json"]).read_text(encoding="utf-8"))
            res.update(title=d.get("title"), duration=d.get("duration"),
                       chapters=[{"start": c["start_time"], "title": c["title"]} for c in (d.get("chapters") or [])])
        except Exception:
            pass
    if subs and not res["subtitles"]:
        log("no subtitles fetched → extract.py will use Whisper")
    return res


# ---------------------------------------------------------------- SponsorBlock
# Community database of "useless" segments in YouTube videos: https://sponsor.ajay.app
SB_LABELS = {"sponsor": "sponsor", "selfpromo": "self-promotion", "interaction": "like/subscribe reminder",
             "intro": "intro / animation", "outro": "outro / credits", "preview": "preview / recap",
             "filler": "filler / tangent", "music_offtopic": "off-topic music"}


def fetch_sponsorblock(video_id, timeout=10):
    """Segments to skip [{start, end, category, label}]; [] if none; None if the API is unreachable.
    Anonymous request: only a 4-character prefix of the id's hash is sent."""
    import hashlib
    import urllib.error
    import urllib.parse
    import urllib.request
    prefix = hashlib.sha256(video_id.encode()).hexdigest()[:4]
    q = urllib.parse.urlencode({"categories": json.dumps(list(SB_LABELS)), "actionTypes": json.dumps(["skip"])})
    req = urllib.request.Request(f"https://sponsor.ajay.app/api/skipSegments/{prefix}?{q}",
                                 headers={"User-Agent": "video-to-skill"})
    data = None
    for attempt in range(3):  # the API occasionally hiccups
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    if data is None:
        return None
    for v in data:
        if v.get("videoID") == video_id:
            segs = [{"start": round(s["segment"][0], 2), "end": round(s["segment"][1], 2),
                     "category": s["category"], "label": SB_LABELS.get(s["category"], s["category"])}
                    for s in v.get("segments", []) if s["segment"][1] > s["segment"][0]]
            return sorted(segs, key=lambda s: s["start"])
    return []


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="*")
    ap.add_argument("-f", "--file", help="text file: one URL per line")
    ap.add_argument("-o", "--out", default="downloads", help="output folder (default: downloads)")
    ap.add_argument("--name", default=DEFAULT_TEMPLATE, help=f"yt-dlp name template (default: {DEFAULT_TEMPLATE})")
    ap.add_argument("-q", "--max-height", type=int, default=720, help="max video height (default 720)")
    ap.add_argument("--audio-only", action="store_true", help="audio only (for transcription)")
    ap.add_argument("--no-subs", action="store_true", help="do not fetch subtitles")
    ap.add_argument("--lang", default=None,
                    help="preferred subtitle language (en, fr, es…); English and the original language as fallback")
    ap.add_argument("--section", default=None, help="section to download, e.g. 12:00-25:00")
    ap.add_argument("--playlist", action="store_true", help="if the URL is a playlist/channel, download everything")
    ap.add_argument("--max-videos", type=int, default=None, help="with --playlist: max number of videos")
    ap.add_argument("--cookies-from-browser", default=None, metavar="BROWSER",
                    help='firefox, chrome, edge, brave… (age / members-only videos, "not a bot")')
    ap.add_argument("--cookies", default=None, help="cookies.txt file (Netscape format)")
    ap.add_argument("--update", action="store_true", help="update yt-dlp before starting")
    ap.add_argument("--no-auto-install", action="store_true", help="never install anything automatically")
    ap.add_argument("--no-progress", action="store_true", help="no progress bar (shorter logs)")
    a = ap.parse_args()

    urls = list(a.urls)
    if a.file:
        urls += [l.strip() for l in Path(a.file).read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.strip().startswith("#")]
    if not urls:
        ap.error("give at least one URL (or --file)")
    if a.update:
        ensure_ytdlp(not a.no_auto_install, upgrade=True)

    results = []
    for u in urls:
        r = download_one(u, a.out, a.name, max_height=a.max_height, audio_only=a.audio_only, subs=not a.no_subs,
                         lang=a.lang, section=a.section, playlist=a.playlist, max_videos=a.max_videos,
                         cookies_browser=a.cookies_from_browser, cookies_file=a.cookies,
                         progress=not a.no_progress, auto_install=not a.no_auto_install)
        log(("✔ " + ", ".join(Path(f).name for f in r["files"])) if r["ok"] else f"✗ {u} — {r['hint']}")
        results.append(r)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    sys.exit(0 if all(r["ok"] for r in results) else 1)


if __name__ == "__main__":
    main()
