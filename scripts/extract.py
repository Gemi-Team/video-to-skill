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

Usage:
  python3 extract.py <url-or-file> [--out work] [--lang fr] [--interval 15]
                     [--max-frames 90] [--whisper-model small]
                     [--no-transcribe] [--subs path.srt]

Only hard dependency: ffmpeg/ffprobe + Pillow.
Optional: yt-dlp (URLs, subtitles), faster-whisper (transcription).
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageChops
except ImportError:
    sys.exit("Pillow manquant : pip install pillow")

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


def fmt_ts(sec):
    sec = max(0, sec)
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ---------------------------------------------------------------- ingest
def is_url(s):
    return re.match(r"^https?://", s) is not None


def ingest(source, out: Path, lang):
    info = {"source": source, "title": None, "chapters": [], "description": None}
    subs_file = None
    if is_url(source):
        if not shutil.which("yt-dlp"):
            sys.exit("yt-dlp manquant : pip install yt-dlp  (ou fournis un fichier vidéo local)")
        langs = f"{lang}.*,{lang},en.*,en" if lang else "fr.*,fr,en.*,en"
        log("téléchargement (≤720p) + sous-titres…")
        r = run([
            "yt-dlp", "-f", "bv*[height<=720]+ba/b[height<=720]/b",
            "--merge-output-format", "mp4",
            "--write-info-json", "--write-subs", "--write-auto-subs",
            "--sub-langs", langs, "--sub-format", "vtt/srt/best",
            "--no-playlist", "-o", str(out / "video.%(ext)s"), source,
        ], check=False)
        if r.returncode != 0 and not list(out.glob("video.*")):
            msg = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "erreur inconnue"
            sys.exit(f"Échec du téléchargement : {msg}\n"
                     "→ Si le réseau bloque YouTube, télécharge la vidéo et donne le fichier local.")
        vids = [p for p in out.glob("video.*") if p.suffix in (".mp4", ".mkv", ".webm", ".mov")]
        if not vids:
            sys.exit("Aucune vidéo téléchargée.")
        video = vids[0]
        ij = out / "video.info.json"
        if ij.exists():
            d = json.loads(ij.read_text())
            info.update(title=d.get("title"), description=(d.get("description") or "")[:3000],
                        chapters=[{"start": c["start_time"], "title": c["title"]}
                                  for c in (d.get("chapters") or [])],
                        uploader=d.get("uploader"), upload_date=d.get("upload_date"),
                        webpage_url=d.get("webpage_url"))
        # prefer manual subs over auto, preferred lang first
        cands = sorted(out.glob("video*.vtt")) + sorted(out.glob("video*.srt"))
        if cands:
            def score(p):
                n = p.name
                return (0 if lang and f".{lang}" in n else 1, 1 if "orig" in n else 0, n)
            subs_file = sorted(cands, key=score)[0]
    else:
        src = Path(source).expanduser().resolve()
        if not src.exists():
            sys.exit(f"Fichier introuvable : {src}")
        video = out / ("video" + src.suffix.lower())
        if video.exists() or video.is_symlink():
            video.unlink()
        try:
            video.symlink_to(src)
        except OSError:
            shutil.copy2(src, video)
        info["title"] = src.stem
        for ext in (".srt", ".vtt", f".{lang}.srt", f".{lang}.vtt", ".fr.srt", ".en.srt"):
            side = src.with_name(src.stem + ext)
            if side.exists():
                subs_file = side
                break
    return video, info, subs_file


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
    text = path.read_text(errors="ignore").replace("\r", "")
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


def whisper_transcribe(video, out: Path, model_name, lang):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        warn("faster-whisper non installé (pip install faster-whisper) : pas de transcription audio.")
        return None
    wav = out / "audio.wav"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-ac", "1", "-ar", "16000", str(wav)])
    try:
        log(f"transcription whisper ({model_name})… (peut prendre un moment)")
        model = WhisperModel(model_name, device="auto", compute_type="int8")
        segments, meta = model.transcribe(str(wav), language=lang or None, vad_filter=True, beam_size=5)
        segs = [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]
        log(f"langue détectée : {meta.language} ({meta.language_probability:.2f})")
        return segs
    except Exception as e:  # model download blocked, etc.
        warn(f"Whisper indisponible ({type(e).__name__}: {str(e)[:150]}). Pas de transcription audio.")
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


def select_frames(video, meta, out: Path, interval, threshold, max_frames, chapters):
    """
    Keep a frame when the screen (a) differs from the last kept frame and (b) has settled
    (= the next sample barely moves). That captures *completed* states — a fully typed command,
    an opened menu, a finished result — instead of mid-typing blur. A periodic fallback keeps
    coverage during continuous motion; chapter starts are always kept.
    """
    dur = meta["duration"]
    fps = 2 if dur <= 1200 else 1 if dur <= 3600 else 0.5
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

    if len(kept) > max_frames:
        warn(f"{len(kept)} images distinctes → réduit à {max_frames} (les plus gros changements + couverture régulière). "
             "Utilise frame_at.py pour zoomer sur un passage.")
        first, last = kept[0], kept[-1]
        middle = kept[1:-1]
        top = sorted(middle, key=lambda k: -k["change"])[: (max_frames - 2) // 2]
        step = len(middle) / max(1, (max_frames - 2) - len(top))
        spread = [middle[int(i * step)] for i in range(int(len(middle) / step))] if step else []
        sel = {id(k): k for k in [first, last] + top + spread}
        kept = sorted(sel.values(), key=lambda k: k["t"])[:max_frames]

    fdir = out / "frames"
    if fdir.exists():
        shutil.rmtree(fdir)
    fdir.mkdir()
    frames = []
    for n, k in enumerate(kept, 1):
        name = f"f_{n:04d}_t{k['t']:07.1f}.jpg"
        if grab(video, k["t"], fdir / name, width=1280):
            frames.append({"n": n, "t": round(k["t"], 2), "ts": fmt_ts(k["t"]), "file": f"frames/{name}",
                           "change": k["change"]})
    return frames


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
def write_transcript(out: Path, segs):
    lines = ["# Transcript", ""]
    if not segs:
        lines.append("_(aucune transcription disponible — se fier uniquement aux images)_")
    else:
        buf, t0 = [], segs[0]["start"]
        for s in segs:
            buf.append(s["text"])
            if len(" ".join(buf)) > 400 or s["text"].endswith((".", "?", "!")) and len(" ".join(buf)) > 200:
                lines.append(f"[{fmt_ts(t0)}] {' '.join(buf)}")
                buf, t0 = [], None
            if t0 is None:
                t0 = s["end"]
        if buf:
            lines.append(f"[{fmt_ts(t0 or segs[-1]['start'])}] {' '.join(buf)}")
    (out / "transcript.md").write_text("\n\n".join(lines) + "\n")


def write_timeline(out: Path, frames, segs, chapters):
    """Interleave: chapter headings, key frames, and what is said between two frames."""
    events = [(c["start"], 0, f"\n## Chapitre : {c['title']}  [{fmt_ts(c['start'])}]\n") for c in chapters]
    bounds = [fr["t"] for fr in frames] + [float("inf")]
    for i, fr in enumerate(frames):
        said = " ".join(s["text"] for s in segs if bounds[i] <= s["start"] < bounds[i + 1]) if segs else ""
        txt = f"### [{fr['ts']}] image #{fr['n']} → `{fr['file']}`\n"
        if said:
            txt += f"> {said}\n"
        events.append((fr["t"], 1, txt))
    if segs and frames:
        pre = " ".join(s["text"] for s in segs if s["start"] < frames[0]["t"])
        if pre:
            events.append((0, 0.5, f"> {pre}\n"))
    events.sort(key=lambda e: (e[0], e[1]))
    (out / "timeline.md").write_text("# Timeline (images + narration)\n\n" + "\n".join(e[2] for e in events) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--out", default="v2s_work")
    ap.add_argument("--lang", default=None, help="langue attendue (fr, en…) ; auto si absent")
    ap.add_argument("--interval", type=float, default=None, help="1 image min. toutes les N s (auto)")
    ap.add_argument("--max-frames", type=int, default=90)
    ap.add_argument("--whisper-model", default="small")
    ap.add_argument("--no-transcribe", action="store_true")
    ap.add_argument("--subs", default=None, help="fichier .srt/.vtt à utiliser")
    a = ap.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"{tool} manquant : installe ffmpeg (brew/apt/winget install ffmpeg)")

    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    video, info, subs = ingest(a.source, out, a.lang)
    meta = probe(video)
    if meta["duration"] <= 0:
        sys.exit("Durée illisible : fichier vidéo invalide ?")
    interval = a.interval or (8 if meta["duration"] < 600 else 15 if meta["duration"] < 2400 else 30)
    log(f"« {info['title']} » — {fmt_ts(meta['duration'])}, {meta['width']}x{meta['height']}")

    segs, tsrc = None, None
    if a.subs:
        subs = Path(a.subs)
    if subs and Path(subs).exists():
        segs, tsrc = parse_subs(Path(subs)), f"sous-titres ({Path(subs).name})"
    elif not a.no_transcribe and meta["has_audio"]:
        segs = whisper_transcribe(video, out, a.whisper_model, a.lang)
        tsrc = f"whisper {a.whisper_model}" if segs else None
    if not segs:
        segs = []
        if not meta["has_audio"]:
            warn("La vidéo n'a pas de piste audio.")
        tsrc = tsrc or "aucune"

    frames = select_frames(video, meta, out, interval, None, a.max_frames, info["chapters"])
    sheets = contact_sheets(out, frames)
    write_transcript(out, segs)
    write_timeline(out, frames, segs, info["chapters"])

    manifest = {**info, **meta, "duration_hms": fmt_ts(meta["duration"]), "video": video.name,
                "transcript_source": tsrc, "transcript_segments": len(segs),
                "frame_interval_s": interval, "frames": frames, "sheets": sheets, "warnings": WARNINGS}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps({"out": str(out), "title": info["title"], "duration": fmt_ts(meta["duration"]),
                      "transcript": tsrc, "frames": len(frames), "sheets": len(sheets),
                      "warnings": WARNINGS}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
