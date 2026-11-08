#!/usr/bin/env python3
"""
extract.py — turn a video (URL or local file) into material Claude can "watch":

  work/
    video.mp4              the media (downloaded or symlinked)
    manifest.json          metadata, duration, chapters, frame list, warnings
    transcript.md          timestamped transcript (subtitles > whisper > none)
    timeline.md            transcript interleaved with key frames, in order
    frames/f_0001_t0012.5.jpg   key frames (each settled screen state + periodic fallback)
    sheets/sheet_01.jpg    contact sheets (3x3 grids, timestamp on each tile)
    states.json, segments.json  every detected screen state + transcript segments (used by parts.py)
    part_01/ …             LONG VIDEOS ONLY (> --part-minutes): one self-contained folder per part,
                           each with its own frames, sheets, transcript, timeline and AGENT_PROMPT.md

Usage:
  python extract.py <url-or-file> [--out work] [--lang fr] [--interval 15]
                    [--max-frames 90] [--whisper-model small] [--whisper-device auto]
                    [--no-transcribe] [--subs path.srt] [--cookies-from-browser firefox]
                    [--part-minutes 45] [--frames-per-part 300] [--every 10] [--no-parts] [--no-sponsorblock]

YouTube: passages tagged by SponsorBlock (sponsor, intro, self-promo…) are marked « ⏭ » and get no frames.

Only hard dependency: ffmpeg/ffprobe + Pillow.
Optional: yt-dlp (URLs, subtitles — see download.py), faster-whisper (transcription).
Missing something? python scripts/bootstrap.py
"""
import argparse
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ensure_ffmpeg, fmt_ts, utf8_console  # noqa: E402

try:
    from PIL import Image, ImageDraw, ImageFont, ImageChops
except ImportError:
    sys.exit("Pillow manquant : python scripts/bootstrap.py  (ou pip install pillow)")

WARNINGS = []


def warn(msg):
    WARNINGS.append(msg)
    print(f"[warn] {msg}", file=sys.stderr)


def log(msg):
    print(f"[v2s] {msg}", file=sys.stderr)


def run(cmd, check=True, capture=True):
    r = subprocess.run(cmd, capture_output=capture, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(map(str, cmd))[:200]}\n{r.stderr[-2000:]}")
    return r


# ---------------------------------------------------------------- ingest
VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi")


def is_url(s):
    return re.match(r"^https?://", s) is not None


def read_info_json(path: Path, info):
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    info.update(title=d.get("title") or info.get("title"), description=(d.get("description") or "")[:3000],
                chapters=[{"start": c["start_time"], "title": c["title"]} for c in (d.get("chapters") or [])],
                uploader=d.get("uploader"), upload_date=d.get("upload_date"),
                webpage_url=d.get("webpage_url"), video_id=d.get("id"), extractor=d.get("extractor_key"))


def in_skip(t, skips):
    return any(s["start"] <= t < s["end"] for s in skips or [])


def pick_subs(cands, lang):
    """Preferred language first, then the original-language track, then the rest."""
    if not cands:
        return None
    def score(p):
        n = Path(p).name.lower()
        code = Path(n).suffixes[-2][1:] if len(Path(n).suffixes) >= 2 else ""
        # langue voulue > piste d'origine (xx-orig) > code simple « fr » > traduction « fr-de »
        return (0 if lang and f".{lang}" in n else 1, 0 if "orig" in code else 1, "-" in code, n)
    return Path(sorted(cands, key=score)[0])


def ingest(source, out: Path, lang, cookies_browser=None):
    info = {"source": source, "title": None, "chapters": [], "description": None}
    if is_url(source):
        from download import download_one
        for old in out.glob("video.*"):  # pas de mélange avec un ancien téléchargement
            old.unlink()
        log("téléchargement (≤720p) + sous-titres…")
        r = download_one(source, out, "video.%(ext)s", lang=lang, max_height=720,
                         cookies_browser=cookies_browser, progress=False)
        if not r["ok"]:
            last = ((r["error"] or "erreur inconnue").strip().splitlines() or ["erreur inconnue"])[-1]
            sys.exit(f"Échec du téléchargement : {last}\n"
                     f"→ {r['hint']}\n"
                     "→ Sinon : télécharge la vidéo à la main et donne le fichier local.")
        vids = [Path(f) for f in r["files"] if Path(f).suffix.lower() in VIDEO_EXT]
        if not vids:
            sys.exit("Aucune vidéo téléchargée.")
        video = vids[0]
        if r["info_json"]:
            read_info_json(Path(r["info_json"]), info)
        return video, info, pick_subs(r["subtitles"], lang)

    src = Path(source).expanduser().resolve()
    if not src.exists():
        sys.exit(f"Fichier introuvable : {src}")
    video = out / ("video" + src.suffix.lower())
    if video.resolve() != src:
        if video.exists() or video.is_symlink():
            video.unlink()
        try:
            video.symlink_to(src)
        except OSError:  # Windows sans droits de lien symbolique
            shutil.copy2(src, video)
    info["title"] = src.stem
    # fichiers voisins : « nom.srt », « nom.fr.vtt »… et « nom.info.json » (produits par download.py)
    stem = glob.escape(str(src.with_suffix("")))
    cands = [p for ext in ("srt", "vtt") for p in glob.glob(f"{stem}.{ext}") + glob.glob(f"{stem}.*.{ext}")]
    ij = src.with_suffix(".info.json")
    if ij.exists():
        read_info_json(ij, info)
    return video, info, pick_subs(cands, lang)


def probe(video):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,avg_frame_rate",
             "-of", "json", str(video)])
    d = json.loads(r.stdout)
    dur = float(d["format"].get("duration") or 0)
    v = next((s for s in d["streams"] if s.get("codec_type") == "video"), {})
    has_audio = any(s.get("codec_type") == "audio" for s in d["streams"])
    num, _, den = (v.get("avg_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0
    return {"duration": dur, "width": v.get("width"), "height": v.get("height"),
            "fps": round(fps, 2), "has_audio": has_audio}


# ---------------------------------------------------------------- transcript
TS = re.compile(r"(\d+):(\d{2}):(\d{2})[.,](\d{3})|(\d{1,2}):(\d{2})[.,](\d{3})")


def _ts(s):
    m = TS.search(s)
    if not m:
        return None
    if m.group(1):
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1000
    return int(m.group(5)) * 60 + int(m.group(6)) + int(m.group(7)) / 1000


def parse_subs(path: Path):
    """Parse SRT/VTT, strip tags, collapse YouTube's rolling auto-caption duplicates."""
    text = path.read_text(encoding="utf-8", errors="ignore").replace("\r", "")
    segs = []
    for block in re.split(r"\n\s*\n", text):
        lines = [l for l in block.strip().split("\n") if l.strip()]
        arrow = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if arrow is None:
            continue
        a, b = lines[arrow].split("-->")[:2]
        start, end = _ts(a), _ts(b)
        if start is None:
            continue
        body = " ".join(lines[arrow + 1:])
        body = re.sub(r"<[^>]+>", "", body)
        body = re.sub(r"\[(Music|Musique|Applause)\]", "", body, flags=re.I)
        body = re.sub(r"\s+", " ", body).strip()
        if body:
            segs.append({"start": start, "end": end or start, "text": body})
    # de-duplicate rolling captions: drop text already contained in the previous segment's tail
    out = []
    for s in segs:
        if out:
            prev = out[-1]["text"]
            if s["text"] == prev or prev.endswith(s["text"]):
                out[-1]["end"] = max(out[-1]["end"], s["end"])
                continue
            if s["text"].startswith(prev):
                s = dict(s, text=s["text"][len(prev):].strip(), start=s["start"])
                if not s["text"]:
                    continue
            else:
                # partial overlap: remove the longest prefix of s that is a suffix of prev
                for k in range(min(len(prev), len(s["text"])), 8, -1):
                    if prev.endswith(s["text"][:k]):
                        s = dict(s, text=s["text"][k:].strip())
                        break
                if not s["text"]:
                    continue
        out.append(s)
    return out


def whisper_transcribe(video, out: Path, model_name, lang, device="auto"):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        warn("faster-whisper non installé (python scripts/bootstrap.py) : pas de transcription audio.")
        return None
    wav = out / "audio.wav"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-ac", "1", "-ar", "16000", str(wav)])
    # GPU d'abord si dispo ; si CUDA/cuDNN est mal installé ça casse souvent au 1er segment → repli CPU
    devices = [device] if device == "cpu" else [device, "cpu"]
    try:
        for dev in devices:
            try:
                log(f"transcription whisper ({model_name}, {dev})… (peut prendre un moment)")
                model = WhisperModel(model_name, device=dev, compute_type="int8")
                segments, meta = model.transcribe(str(wav), language=lang or None, vad_filter=True, beam_size=5)
                segs = [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]
                log(f"langue détectée : {meta.language} ({meta.language_probability:.2f})")
                return segs
            except Exception as e:  # model download blocked, CUDA libs missing, etc.
                last = f"{type(e).__name__}: {str(e)[:200]}"
                if dev != devices[-1]:
                    log(f"échec sur {dev} ({last}) → nouvel essai sur CPU")
        warn(f"Whisper indisponible ({last}). Pas de transcription audio. Diagnostic : python scripts/bootstrap.py --check")
        return None
    finally:
        wav.unlink(missing_ok=True)


# ---------------------------------------------------------------- frames
def grab(video, t, path: Path, width=1280):
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
         "-vf", f"scale='min({width},iw)':-2", "-q:v", "3", str(path)])
    return path.exists()


TW, TH = 320, 180  # analysis thumbnail size


def iter_thumbs(video, fps):
    """Stream grayscale thumbnails at `fps` in one ffmpeg pass (cheap, works on long videos)."""
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-an",
                          "-vf", f"fps={fps},scale={TW}:{TH},format=gray", "-f", "rawvideo", "-"],
                         stdout=subprocess.PIPE)
    size, i = TW * TH, 0
    while True:
        buf = p.stdout.read(size)
        if len(buf) < size:
            break
        yield i / fps, Image.frombytes("L", (TW, TH), buf)
        i += 1
    p.wait()


def frac_changed(a, b):
    diff = ImageChops.difference(a, b).point(lambda p: 255 if p > 28 else 0)
    return diff.histogram()[255] / (TW * TH)


def detect_states(video, meta, interval, chapters):
    """
    Keep a frame when the screen (a) differs from the last kept frame and (b) has settled
    (= the next sample barely moves). That captures *completed* states — a fully typed command,
    an opened menu, a finished result — instead of mid-typing blur. A periodic fallback keeps
    coverage during continuous motion; chapter starts are always kept.
    Returns every detected state (not reduced) — the expensive pass, done once.
    2 samples/s whatever the length: anything that stays on screen ≥ 0.5 s is seen. (Decoding the video
    dominates the cost, so a denser sampling barely slows the pass.)
    """
    dur = meta["duration"]
    fps = 2
    STABLE, NEW = 0.002, 0.004  # fractions of pixels
    kept, last_kept, prev, last_t = [], None, None, -1e9
    chap_t = sorted(c["start"] for c in chapters)
    for t, img in iter_thumbs(video, fps):
        stable = prev is not None and frac_changed(prev, img) < STABLE
        if last_kept is None:
            change = 1.0
        else:
            change = frac_changed(last_kept, img)
        force_chapter = chap_t and chap_t[0] <= t
        if force_chapter:
            chap_t.pop(0)
        if (change >= NEW and (stable or t - last_t >= 2 * interval)) or force_chapter or last_kept is None:
            kept.append({"t": round(t, 2), "change": round(change, 4)})
            last_kept, last_t = img, t
        prev = img
    if dur - (kept[-1]["t"] if kept else 0) > 2:
        kept.append({"t": max(0.0, dur - 0.5), "change": 0.0})
    log(f"{len(kept)} états d'écran distincts détectés (échantillonnage {fps} img/s)")
    return kept


def with_grid(states, start, end, every, min_gap=3.0):
    """Add one frame every `every` seconds wherever no detected state is closer than min_gap:
    guarantees no blind spot longer than `every` s, even when the screen changes slowly."""
    if not every:
        return list(states)
    out = list(states)
    ts = sorted(s["t"] for s in states)
    t = start + every / 2
    import bisect
    while t < end:
        i = bisect.bisect_left(ts, t)
        near = min((abs(ts[j] - t) for j in (i - 1, i) if 0 <= j < len(ts)), default=1e9)
        if near >= min_gap:
            out.append({"t": round(t, 2), "change": 0.0, "grid": True})
        t += every
    return sorted(out, key=lambda s: s["t"])


def reduce_states(kept, max_frames, quiet=False):
    """Keep at most max_frames: half the biggest changes, half spread evenly over the rest."""
    if len(kept) > max_frames:
        if not quiet:
            warn(f"{len(kept)} images distinctes → réduit à {max_frames} (les plus gros changements + couverture "
                 "régulière). Utilise frame_at.py pour zoomer sur un passage.")
        first, last = kept[0], kept[-1]
        middle = kept[1:-1]
        budget = max_frames - 2
        # moitié = plus gros changements ; autre moitié = répartie régulièrement parmi les images RESTANTES
        # (avant, les deux listes se chevauchaient → doublons → ~76 images au lieu de 90)
        top = sorted(middle, key=lambda k: -k["change"])[: budget // 2]
        top_ids = {id(k) for k in top}
        rest = [k for k in middle if id(k) not in top_ids]
        need = budget - len(top)
        spread = [rest[int(i * len(rest) / need)] for i in range(need)] if need > 0 and rest else []
        kept = sorted([first, last] + top + spread, key=lambda k: k["t"])
    return kept


def grab_frames(video, kept, base: Path):
    """Extract full-resolution frames into base/frames/ ; paths in the result are relative to base."""
    fdir = base / "frames"
    if fdir.exists():
        shutil.rmtree(fdir)
    fdir.mkdir(parents=True)
    jobs = [(n, k, f"f_{n:04d}_t{k['t']:07.1f}.jpg") for n, k in enumerate(kept, 1)]

    def one(job):
        n, k, name = job
        try:
            return job if grab(video, k["t"], fdir / name, width=1280) else None
        except RuntimeError:
            return None
    # one ffmpeg per frame, run in parallel (hundreds of frames on long videos)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(8, max(2, (os.cpu_count() or 4) // 2))) as ex:
        done = [j for j in ex.map(one, jobs) if j]
    return [{"n": n, "t": round(k["t"], 2), "ts": fmt_ts(k["t"]), "file": f"frames/{name}",
             "change": k["change"]} for n, k, name in done]


def font(size):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
              "C:/Windows/Fonts/arialbd.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def contact_sheets(out: Path, frames, cols=3, rows=3, tile_w=640):
    sdir = out / "sheets"
    if sdir.exists():
        shutil.rmtree(sdir)
    sdir.mkdir()
    per = cols * rows
    sheets = []
    f = font(26)
    for s in range(math.ceil(len(frames) / per)):
        chunk = frames[s * per:(s + 1) * per]
        imgs = [Image.open(out / fr["file"]).convert("RGB") for fr in chunk]
        th = int(tile_w * imgs[0].height / imgs[0].width)
        cap = 38  # caption strip under each tile, so the label never hides screen content
        sheet = Image.new("RGB", (cols * tile_w + (cols + 1) * 8, rows * (th + cap) + (rows + 1) * 8), (20, 20, 20))
        d = ImageDraw.Draw(sheet)
        for i, (img, fr) in enumerate(zip(imgs, chunk)):
            x = 8 + (i % cols) * (tile_w + 8)
            y = 8 + (i // cols) * (th + cap + 8)
            sheet.paste(img.resize((tile_w, th)), (x, y))
            d.rectangle([x, y + th, x + tile_w, y + th + cap], fill=(255, 214, 0))
            d.text((x + 10, y + th + 5), f"#{fr['n']}   {fr['ts']}", fill=(0, 0, 0), font=f)
        name = f"sheet_{s + 1:02d}.jpg"
        sheet.save(sdir / name, quality=85)
        sheets.append({"file": f"sheets/{name}", "frames": [fr["n"] for fr in chunk],
                       "from": chunk[0]["ts"], "to": chunk[-1]["ts"]})
    return sheets


# ---------------------------------------------------------------- outputs
def skip_line(s):
    return f"⏭ [{fmt_ts(s['start'])}–{fmt_ts(s['end'])}] {s['label']} — passage ignoré (SponsorBlock)"


def write_transcript(path: Path, segs, skips=None, header="# Transcript"):
    """Paragraphs with timestamps. Segments inside a SponsorBlock skip are replaced by one ⏭ line."""
    skips = skips or []
    lines = [header, ""]
    if not segs:
        lines.append("_(aucune transcription disponible — se fier uniquement aux images)_")
    else:
        buf, t0, done = [], None, set()

        def flush():
            if buf:
                lines.append(f"[{fmt_ts(t0)}] {' '.join(buf)}")
            buf.clear()
        for s in segs:
            mid = (s["start"] + s["end"]) / 2
            sk = next((k for k in skips if k["start"] <= mid < k["end"]), None)
            if sk:
                if id(sk) not in done:
                    flush()
                    t0 = None
                    lines.append(skip_line(sk))
                    done.add(id(sk))
                continue
            if t0 is None:
                t0 = s["start"]
            buf.append(s["text"])
            if len(" ".join(buf)) > 400 or s["text"].endswith((".", "?", "!")) and len(" ".join(buf)) > 200:
                flush()
                t0 = None
        flush()
    path.write_text("\n\n".join(lines) + "\n", encoding="utf-8")


def write_timeline(path: Path, frames, segs, chapters, skips=None, header="# Timeline (images + narration)",
                   start=0.0):
    """Interleave: chapter headings, key frames, and what is said between two frames."""
    skips = skips or []
    events = [(c["start"], 0, f"\n## Chapitre : {c['title']}  [{fmt_ts(c['start'])}]\n") for c in chapters]
    events += [(k["start"], 0.2, skip_line(k) + "\n") for k in skips]
    keep = [s for s in segs if not in_skip((s["start"] + s["end"]) / 2, skips)]
    bounds = [fr["t"] for fr in frames] + [float("inf")]
    for i, fr in enumerate(frames):
        said = " ".join(s["text"] for s in keep if bounds[i] <= s["start"] < bounds[i + 1])
        txt = f"### [{fr['ts']}] image #{fr['n']} → `{fr['file']}`\n"
        if said:
            txt += f"> {said}\n"
        events.append((fr["t"], 1, txt))
    if keep and frames:
        pre = " ".join(s["text"] for s in keep if s["start"] < frames[0]["t"])
        if pre:
            events.append((start, 0.5, f"> {pre}\n"))
    events.sort(key=lambda e: (e[0], e[1]))
    path.write_text(header + "\n\n" + "\n".join(e[2] for e in events) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--out", default="v2s_work")
    ap.add_argument("--lang", default=None, help="langue attendue (fr, en…) ; auto si absent")
    ap.add_argument("--interval", type=float, default=None, help="1 image min. toutes les N s (auto)")
    ap.add_argument("--max-frames", type=int, default=None,
                    help="images de la vue d'ensemble (défaut : 300 pour une vidéo courte, 90 si découpée)")
    ap.add_argument("--every", type=float, default=10,
                    help="au moins une image toutes les N secondes en plus des changements d'écran (défaut 10, 0 = non)")
    ap.add_argument("--whisper-model", default="small", help="tiny, base, small, medium, large-v3, turbo…")
    ap.add_argument("--whisper-device", default="auto", choices=["auto", "cpu", "cuda"])
    ap.add_argument("--no-transcribe", action="store_true")
    ap.add_argument("--whisper", action="store_true",
                    help="ignorer les sous-titres et transcrire avec Whisper (sous-titres auto de mauvaise qualité)")
    ap.add_argument("--subs", default=None, help="fichier .srt/.vtt à utiliser")
    ap.add_argument("--cookies-from-browser", default=None, metavar="NAVIGATEUR",
                    help="pour les vidéos YouTube qui demandent une connexion (firefox, chrome, edge…)")
    ap.add_argument("--part-minutes", type=float, default=45,
                    help="au-delà, découpe en parties d'au plus N minutes (une par sous-agent). Défaut 45")
    ap.add_argument("--frames-per-part", type=int, default=300, help="plafond d'images par partie (défaut 300)")
    ap.add_argument("--no-parts", action="store_true", help="ne jamais découper")
    ap.add_argument("--no-sponsorblock", action="store_true", help="ne pas interroger SponsorBlock")
    a = ap.parse_args()

    if not all(ensure_ffmpeg()):
        sys.exit("ffmpeg/ffprobe manquant : python scripts/bootstrap.py  (ou winget/brew/apt install ffmpeg)")

    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    video, info, subs = ingest(a.source, out, a.lang, a.cookies_from_browser)
    meta = probe(video)
    if meta["duration"] <= 0:
        sys.exit("Durée illisible : fichier vidéo invalide ?")
    interval = a.interval or (8 if meta["duration"] < 600 else 15 if meta["duration"] < 2400 else 30)
    log(f"« {info['title']} » — {fmt_ts(meta['duration'])}, {meta['width']}x{meta['height']}")

    segs, tsrc = None, None
    if a.subs:
        subs = Path(a.subs)
        if not subs.exists():
            sys.exit(f"Sous-titres introuvables : {subs}")
    if a.whisper:
        subs = None
    if subs and Path(subs).exists():
        segs, tsrc = parse_subs(Path(subs)), f"sous-titres ({Path(subs).name})"
    elif not a.no_transcribe and meta["has_audio"]:
        segs = whisper_transcribe(video, out, a.whisper_model, a.lang, a.whisper_device)
        tsrc = f"whisper {a.whisper_model}" if segs else None
    if not segs:
        segs = []
        if not meta["has_audio"]:
            warn("La vidéo n'a pas de piste audio.")
        tsrc = tsrc or "aucune"

    # passages inutiles signalés par la communauté (YouTube uniquement)
    skips = []
    if info.get("video_id") and info.get("extractor") == "Youtube" and not a.no_sponsorblock:
        from download import fetch_sponsorblock
        sb = fetch_sponsorblock(info["video_id"])
        if sb is None:
            warn("SponsorBlock injoignable : aucun passage pré-filtré.")
        else:
            skips = sb
            log(f"SponsorBlock : {len(skips)} passage(s) à sauter"
                + (f" ({sum(s['end'] - s['start'] for s in skips) / 60:.1f} min)" if skips else ""))

    states = detect_states(video, meta, interval, info["chapters"])
    (out / "states.json").write_text(json.dumps(states), encoding="utf-8")
    (out / "segments.json").write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
    split = not a.no_parts and meta["duration"] > a.part_minutes * 60
    useful = [s for s in states if not in_skip(s["t"], skips)] or states
    if split:  # vue d'ensemble pour l'orchestrateur ; la couverture dense est faite partie par partie
        frames = grab_frames(video, reduce_states(useful, a.max_frames or 90), out)
    else:      # vidéo courte : Claude regarde tout lui-même → changements d'écran + 1 image / --every s
        dense = [s for s in with_grid(useful, 0, meta["duration"], a.every) if not in_skip(s["t"], skips)]
        frames = grab_frames(video, reduce_states(dense, a.max_frames or 300), out)
    log(f"{len(frames)} images extraites")
    sheets = contact_sheets(out, frames)
    write_transcript(out / "transcript.md", segs, skips)
    write_timeline(out / "timeline.md", frames, segs, info["chapters"], skips)

    manifest = {**info, **meta, "duration_hms": fmt_ts(meta["duration"]), "video": video.name,
                "transcript_source": tsrc, "transcript_segments": len(segs),
                "transcript_words": sum(len(s["text"].split()) for s in segs),
                "frame_interval_s": interval, "every_s": a.every, "skip_segments": skips, "frames": frames, "sheets": sheets,
                "parts": [], "warnings": WARNINGS}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if split:
        from parts import build_parts
        log(f"vidéo > {a.part_minutes:g} min → découpage en parties (une par sous-agent)")
        manifest["parts"] = build_parts(out, max_minutes=a.part_minutes, frames_per_part=a.frames_per_part,
                                        every=a.every)
        manifest["warnings"] = WARNINGS
        (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"out": str(out), "title": info["title"], "duration": fmt_ts(meta["duration"]),
                      "transcript": tsrc, "frames": len(frames), "sheets": len(sheets),
                      "skipped": [f"{fmt_ts(s['start'])}–{fmt_ts(s['end'])} {s['label']}" for s in skips],
                      "parts": [f"{p['dir']}  {p['from']}–{p['to']}  ({len(p['frames'])} images, "
                                f"{len(p['sheets'])} planches, {p['words']} mots)"
                                for p in manifest["parts"]],
                      "warnings": WARNINGS}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    utf8_console()
    main()
