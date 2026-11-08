#!/usr/bin/env python3
"""
download.py — télécharge des vidéos YouTube (ou tout site supporté par yt-dlp) + sous-titres
+ métadonnées, prêtes pour extract.py ou pour Whisper.

  python scripts/download.py "https://www.youtube.com/watch?v=…"
  python scripts/download.py URL1 URL2 --out downloads --lang fr
  python scripts/download.py --file liste_urls.txt          # une URL par ligne, # = commentaire
  python scripts/download.py URL --playlist --max-videos 10  # playlist / chaîne
  python scripts/download.py URL --audio-only                # audio seul (pour transcription)
  python scripts/download.py URL --section 12:00-25:00       # seulement un passage
  python scripts/download.py URL --cookies-from-browser firefox   # vidéo âge / membres / « not a bot »

Ce que le script fait tout seul :
  - installe yt-dlp s'il manque, le met à jour et réessaie si YouTube a changé (403, nsig…)
  - trouve ffmpeg (PATH, winget, static-ffmpeg) et un runtime JS (deno/node/bun) pour yt-dlp
  - ne prend que les sous-titres utiles (pas les 100 traductions auto qui déclenchent un 429)
  - un échec de sous-titres n'empêche jamais le téléchargement de la vidéo

Sortie : progression sur stderr, puis un JSON récapitulatif sur stdout
  [{"url", "ok", "files", "subtitles", "info_json", "title", "duration", "error", "hint"}]
Code retour : 0 si tout a réussi, 1 sinon.
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

# (motif dans la sortie de yt-dlp, catégorie, conseil)
ERRORS = [
    (r"sign in to confirm|not a bot", "bot",
     "YouTube demande une connexion : relance avec --cookies-from-browser firefox (ou chrome/edge, navigateur fermé)."),
    (r"confirm your age|age.restricted|inappropriate for some users", "age",
     "Vidéo soumise à l'âge : relance avec --cookies-from-browser <navigateur connecté à un compte adulte>."),
    (r"private video|members.only|join this channel", "private",
     "Vidéo privée / réservée aux membres : --cookies-from-browser avec un compte qui y a accès."),
    (r"not available in your country|geo.?restrict", "geo", "Vidéo bloquée dans ce pays."),
    (r"video unavailable|video is unavailable|isn't available|has been removed|account .* terminated|"
     r"does not exist", "unavailable",
     "Vidéo indisponible ou supprimée."),
    (r"429|too many requests", "ratelimit",
     "YouTube limite les requêtes : attendre quelques minutes, ou --cookies-from-browser."),
    (r"getaddrinfo|name or service not known|temporary failure in name resolution|timed out|"
     r"network is unreachable|connection refused|proxy|certificate verify failed", "network",
     "Réseau bloqué ou proxy : télécharge la vidéo à la main et donne le fichier local."),
    (r"http error 403|nsig|signature|unable to extract|requested format is not available|"
     r"precondition check failed|no video formats found|unsupported url|po token", "outdated",
     "yt-dlp est probablement trop vieux pour le YouTube actuel : python -m pip install -U \"yt-dlp[default]\"."),
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
    """yt-dlp-ejs = scripts qui résolvent les défis JS de YouTube (sinon : « some formats may be missing »)."""
    import importlib.util
    return importlib.util.find_spec("yt_dlp_ejs") is not None


def ensure_ytdlp(auto_install=True, upgrade=False):
    v = ytdlp_version()
    if v and not upgrade and (has_ejs() or not auto_install):
        return v
    if not auto_install:
        return v
    log(("mise à jour" if v else "installation") + " de yt-dlp…")
    ok, msg = pip_install(["yt-dlp[default]"], upgrade=True)
    if not ok:
        log(f"échec pip : {msg}")
    for m in [m for m in sys.modules if m == "yt_dlp" or m.startswith("yt_dlp.")]:
        del sys.modules[m]
    return ytdlp_version() or v


def classify(text):
    low = text.lower()
    for pat, cat, hint in ERRORS:
        if re.search(pat, low):
            return cat, hint
    return "unknown", "Voir les dernières lignes de yt-dlp ci-dessus."


# ---------------------------------------------------------------- core
def sub_langs(lang):
    langs = [lang] if lang else ["fr"]
    if "en" not in langs:
        langs.append("en")
    # pas de « fr.* » : ça attrape aussi les traductions auto (fr-de, fr-ja…) → HTTP 429 de YouTube
    # {l}-XX (majuscules) = variante régionale manuelle (fr-FR, en-US) ; yt-dlp compare sans casse → (?-i:)
    return ",".join(f"{l},{l}-orig,{l}-(?-i:[A-Z]{{2}})" for l in langs)


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
    else:  # sans ffmpeg pas de fusion audio+vidéo possible → fichier déjà fusionné (souvent 360p)
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
    stem = glob.escape(str(media.with_suffix("")))  # les titres contiennent souvent [ ] → glob.escape
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
        res.update(error="yt-dlp absent", hint='python -m pip install -U "yt-dlp[default]"')
        return res
    ff, _ = ensure_ffmpeg()
    if not ff:
        log("⚠ ffmpeg introuvable : qualité limitée (pas de fusion audio+vidéo). Lance scripts/setup.py.")
    updated = False
    for attempt in range(3):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tf:
            paths_file = Path(tf.name)
        cmd = build_cmd(url, out_dir, template, paths_file, max_height=max_height, audio_only=audio_only,
                        subs=subs, lang=lang, section=section, playlist=playlist, max_videos=max_videos,
                        cookies_browser=cookies_browser, cookies_file=cookies_file, progress=progress,
                        has_ffmpeg=bool(ff), version=version)
        log(f"{url}  (yt-dlp {version}{', tentative ' + str(attempt + 1) if attempt else ''})")
        code, tail = run_streaming(cmd)
        files = [l.strip() for l in paths_file.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
        paths_file.unlink(missing_ok=True)
        files = [f for f in dict.fromkeys(files) if Path(f).exists()]
        if files:
            break
        errors = "\n".join(l for l in tail if "ERROR" in l) or "\n".join(tail[-5:])
        cat, hint = classify(errors)
        res.update(error=errors[-800:] or f"yt-dlp code {code}", hint=hint)
        if cat == "outdated" and not updated and auto_install:
            log("yt-dlp semble dépassé → mise à jour puis nouvel essai")
            version = ensure_ytdlp(auto_install, upgrade=True)
            updated = True
            continue
        if cat == "ratelimit" and attempt == 0:
            log("HTTP 429 → pause de 30 s puis nouvel essai")
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
        log("aucun sous-titre récupéré → extract.py utilisera Whisper")
    return res


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="*")
    ap.add_argument("-f", "--file", help="fichier texte : une URL par ligne")
    ap.add_argument("-o", "--out", default="downloads", help="dossier de sortie (défaut : downloads)")
    ap.add_argument("--name", default=DEFAULT_TEMPLATE, help=f"modèle de nom yt-dlp (défaut : {DEFAULT_TEMPLATE})")
    ap.add_argument("-q", "--max-height", type=int, default=720, help="hauteur max de la vidéo (défaut 720)")
    ap.add_argument("--audio-only", action="store_true", help="audio seul (pour transcription)")
    ap.add_argument("--no-subs", action="store_true", help="ne pas récupérer les sous-titres")
    ap.add_argument("--lang", default=None, help="langue des sous-titres préférée (fr, en, es…) ; + en en secours")
    ap.add_argument("--section", default=None, help="passage à télécharger, ex. 12:00-25:00")
    ap.add_argument("--playlist", action="store_true", help="si l'URL est une playlist/chaîne, tout télécharger")
    ap.add_argument("--max-videos", type=int, default=None, help="avec --playlist : nombre max de vidéos")
    ap.add_argument("--cookies-from-browser", default=None, metavar="NAVIGATEUR",
                    help="firefox, chrome, edge, brave… (vidéos âge/membres, « not a bot »)")
    ap.add_argument("--cookies", default=None, help="fichier cookies.txt (format Netscape)")
    ap.add_argument("--update", action="store_true", help="mettre à jour yt-dlp avant de commencer")
    ap.add_argument("--no-auto-install", action="store_true", help="ne rien installer automatiquement")
    ap.add_argument("--no-progress", action="store_true", help="pas de barre de progression (logs plus courts)")
    a = ap.parse_args()

    urls = list(a.urls)
    if a.file:
        urls += [l.strip() for l in Path(a.file).read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.strip().startswith("#")]
    if not urls:
        ap.error("donne au moins une URL (ou --file)")
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
