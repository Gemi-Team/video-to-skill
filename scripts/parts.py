#!/usr/bin/env python3
"""
parts.py — découpe une vidéo longue (déjà passée dans extract.py) en parties autonomes,
une par sous-agent. Rapide : réutilise states.json / segments.json, ne ré-analyse pas la vidéo.

  python scripts/parts.py v2s_work --plan                        # montre le découpage, n'écrit rien
  python scripts/parts.py v2s_work                               # auto : chapitres regroupés, ≤ 45 min/partie
  python scripts/parts.py v2s_work --max-minutes 30
  python scripts/parts.py v2s_work --at 38:00,1:18:00,2:02:00    # bornes choisies par l'orchestrateur
  python scripts/parts.py v2s_work --only 2,3                    # ne (re)générer que ces parties
  python scripts/parts.py v2s_work --every 5                     # couverture encore plus dense (1 image / 5 s)

Images d'une partie = chaque changement d'écran détecté (analyse à 2 img/s) + au moins 1 image toutes
les --every secondes (10 par défaut), plafonnées à --frames-per-part (300).
Chaque partie part_NN/ contient : transcript.md, timeline.md, frames/, sheets/, part.json et
AGENT_PROMPT.md (la consigne complète du sous-agent, qui écrit ses notes dans v2s_work/notes/part_NN.md).
Les horodatages restent ceux de la vidéo complète (les citations [t=…] restent justes).
"""
import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _common import ensure_ffmpeg, fmt_ts, utf8_console  # noqa: E402
from extract import (contact_sheets, grab_frames, in_skip, log, reduce_states,  # noqa: E402
                     with_grid, write_timeline, write_transcript)

PROMPT_TEMPLATE = HERE.parent / "references" / "part-agent-prompt.md"
NOTES_TEMPLATE = HERE.parent / "references" / "part-notes-template.md"


def parse_t(s):
    t = 0.0
    for p in s.strip().split(":"):
        t = t * 60 + float(p)
    return t


def snap_to_pause(t, segs, window=60):
    """Move a cut to the longest silence between two subtitle segments near t (no cut mid-sentence)."""
    best, best_gap = t, -1.0
    for prev, cur in zip(segs, segs[1:]):
        if abs(cur["start"] - t) <= window:
            gap = cur["start"] - prev["end"]
            if gap > best_gap:
                best, best_gap = cur["start"], gap
    return round(best, 2)


def auto_cuts(duration, chapters, segs, max_s):
    """Cut points (excluding 0 and the end). Chapters are grouped, never split unless longer than max."""
    cuts = []
    chaps = sorted(chapters, key=lambda c: c["start"])
    if len(chaps) >= 2:
        spans = [(c["start"], (chaps[i + 1]["start"] if i + 1 < len(chaps) else duration))
                 for i, c in enumerate(chaps)]
        if spans[0][0] > 1:
            spans.insert(0, (0.0, spans[0][0]))
        cur = 0.0
        for cs, ce in spans:
            if ce - cur <= max_s:
                continue
            if cs > cur:  # close the current part at this chapter's start
                cuts.append(cs)
                cur = cs
            if ce - cur > max_s:  # a single chapter longer than the max → split it evenly, at pauses
                k = math.ceil((ce - cur) / max_s)
                for i in range(1, k):
                    cuts.append(snap_to_pause(cur + i * (ce - cur) / k, segs))
                cur = cuts[-1]
        # a tiny last part is merged into the previous one if that stays reasonable
        if cuts and duration - cuts[-1] < max_s / 4 and duration - (cuts[-2] if len(cuts) > 1 else 0) <= max_s * 1.25:
            cuts.pop()
    else:
        n = math.ceil(duration / max_s)
        cuts = [snap_to_pause(i * duration / n, segs) for i in range(1, n)]
    return sorted(set(c for c in cuts if 0 < c < duration))


def fill(template, values):
    for k, v in values.items():
        template = template.replace("{{" + k + "}}", str(v))
    return template


def rel(p):
    """Shell-ready path, relative to the current directory when possible (matches the repo's permission rules)."""
    try:
        r = os.path.relpath(p)
        out = Path(r if not r.startswith("..") else p).as_posix()
    except ValueError:  # other drive on Windows
        out = Path(p).as_posix()
    return f'"{out}"' if " " in out else out


def build_parts(work, max_minutes=45, frames_per_part=300, at=None, only=None, plan_only=False, every=None):
    work = Path(work).resolve()
    man = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    states = json.loads((work / "states.json").read_text(encoding="utf-8"))
    segs = json.loads((work / "segments.json").read_text(encoding="utf-8"))
    dur, chapters, skips = man["duration"], man.get("chapters") or [], man.get("skip_segments") or []
    video = work / man["video"]
    every = man.get("every_s", 10) if every is None else every

    cuts = sorted(parse_t(x) for x in at.split(",") if x.strip()) if at else \
        auto_cuts(dur, chapters, segs, max_minutes * 60)
    bounds = [0.0] + [c for c in cuts if 0 < c < dur] + [dur]
    total = len(bounds) - 1
    parts = []
    for i in range(total):
        start, end = bounds[i], bounds[i + 1]
        n = i + 1
        pchap = [c for c in chapters if start <= c["start"] < end]
        before = [c for c in chapters if c["start"] < start]
        if before and not any(abs(c["start"] - start) < 1 for c in pchap):
            pchap.insert(0, {"start": start, "title": before[-1]["title"] + " (suite)"})
        psegs = [s for s in segs if start <= s["start"] < end]
        pskips = [k for k in skips if k["end"] > start and k["start"] < end]
        skipped = sum(min(k["end"], end) - max(k["start"], start) for k in pskips)
        parts.append({"n": n, "dir": f"part_{n:02d}", "start": round(start, 2), "end": round(end, 2),
                      "from": fmt_ts(start), "to": fmt_ts(end), "minutes": round((end - start) / 60, 1),
                      "chapters": [c["title"] for c in pchap], "_chapters": pchap, "_segs": psegs,
                      "_skips": pskips, "skipped_minutes": round(skipped / 60, 1),
                      "words": sum(len(s["text"].split()) for s in psegs if not in_skip(s["start"], pskips)),
                      "notes": f"notes/part_{n:02d}.md", "frames": [], "sheets": []})
    if plan_only:
        return [{k: v for k, v in p.items() if not k.startswith("_")} for p in parts]

    if not all(ensure_ffmpeg()):
        sys.exit("ffmpeg manquant : python scripts/bootstrap.py")
    if not PROMPT_TEMPLATE.exists():
        sys.exit(f"modèle introuvable : {PROMPT_TEMPLATE} (réinstalle le skill avec scripts/bootstrap.py)")
    prompt_tpl = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    notes_tpl = NOTES_TEMPLATE.read_text(encoding="utf-8") if NOTES_TEMPLATE.exists() else ""
    (work / "notes").mkdir(exist_ok=True)
    if not only:
        for old in work.glob("part_*"):
            if old.is_dir():
                shutil.rmtree(old)

    for p in parts:
        if only and p["n"] not in only:
            continue
        pdir = work / p["dir"]
        if pdir.exists():
            shutil.rmtree(pdir)
        pdir.mkdir()
        start, end, pskips = p["start"], p["end"], p.pop("_skips")
        pstates = [s for s in states if start <= s["t"] < end]
        if not pstates or pstates[0]["t"] - start > 2:
            pstates.insert(0, {"t": round(start + 0.5, 2), "change": 1.0})
        pstates = [s for s in with_grid(pstates, start, end, every) if not in_skip(s["t"], pskips)]
        if len(pstates) > frames_per_part:
            log(f"{p['dir']} : {len(pstates)} images → plafonnées à {frames_per_part} (--frames-per-part)")
        log(f"{p['dir']} : {p['from']}–{p['to']} ({p['minutes']} min, {p['words']} mots)")
        frames = grab_frames(video, reduce_states(pstates, frames_per_part, quiet=True), pdir)
        sheets = contact_sheets(pdir, frames)
        psegs, pchap = p.pop("_segs"), p.pop("_chapters")
        head = f"partie {p['n']}/{total} — {p['from']} → {p['to']} — « {man.get('title')} »"
        write_transcript(pdir / "transcript.md", psegs, pskips, header=f"# Transcript — {head}")
        write_timeline(pdir / "timeline.md", frames, psegs, pchap, pskips,
                       header=f"# Timeline — {head}\n\nHorodatages = temps de la vidéo complète.", start=start)
        p.update(frames=[f["file"] for f in frames], sheets=[s["file"] for s in sheets],
                 skipped=[f"{fmt_ts(k['start'])}–{fmt_ts(k['end'])} {k['label']}" for k in pskips])
        (pdir / "part.json").write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
        (pdir / "AGENT_PROMPT.md").write_text(fill(prompt_tpl, {
            "N": p["n"], "TOTAL": total, "FROM": p["from"], "TO": p["to"], "TITLE": man.get("title") or "?",
            "URL": man.get("webpage_url") or man.get("source") or "?",
            "PART_DIR": pdir, "WORK_DIR": rel(work), "SCRIPTS_DIR": rel(HERE), "NOTES_FILE": work / p["notes"],
            "NSHEETS": len(p["sheets"]), "NFRAMES": len(p["frames"]), "EVERY": f"{every:g}",
            "SHEET_LIST": "\n".join(f"- {Path(s).stem}" for s in p["sheets"]),
            "CHAPTERS": "\n".join(f"- {c}" for c in p["chapters"]) or "- (pas de chapitre)",
            "SHEETS": ", ".join(f"`{s}`" for s in p["sheets"]),
            "SKIPPED": "\n".join(f"- ⏭ {s}" for s in p["skipped"]) or "- (aucun passage pré-filtré)",
            "NOTES_TEMPLATE": notes_tpl}), encoding="utf-8")
        p["prompt"] = f"{p['dir']}/AGENT_PROMPT.md"

    for p in parts:  # clean helper keys for parts not regenerated (--only)
        for k in [k for k in p if k.startswith("_")]:
            p.pop(k)
        if not p.get("prompt"):
            old = work / p["dir"] / "part.json"
            if old.exists():
                p.update({k: v for k, v in json.loads(old.read_text(encoding="utf-8")).items()
                          if k in ("frames", "sheets", "skipped")}, prompt=f"{p['dir']}/AGENT_PROMPT.md")
    (work / "parts.json").write_text(json.dumps(parts, ensure_ascii=False, indent=2), encoding="utf-8")
    return parts


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work")
    ap.add_argument("--max-minutes", type=float, default=45)
    ap.add_argument("--at", default=None, help="bornes explicites, ex. 38:00,1:18:00,2:02:00")
    ap.add_argument("--frames-per-part", type=int, default=300)
    ap.add_argument("--every", type=float, default=None, help="1 image min. toutes les N s (défaut : celui d'extract.py)")
    ap.add_argument("--only", default=None, help="numéros de parties à régénérer, ex. 2,3")
    ap.add_argument("--plan", action="store_true", help="afficher le découpage sans rien générer")
    a = ap.parse_args()
    only = {int(x) for x in a.only.split(",")} if a.only else None
    parts = build_parts(a.work, a.max_minutes, a.frames_per_part, a.at, only, a.plan, a.every)
    for p in parts:
        print(f"  {p['dir']}  {p['from']:>8} → {p['to']:>8}  {p['minutes']:5.1f} min  {p['words']:6d} mots"
              + (f"  ⏭ {p['skipped_minutes']} min" if p["skipped_minutes"] else "")
              + (f"  {len(p['frames'])} img / {len(p['sheets'])} planches" if p.get("sheets") else "")
              + f"  | {' · '.join(p['chapters'])[:90]}", file=sys.stderr)
    print(json.dumps(parts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
