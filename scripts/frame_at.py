#!/usr/bin/env python3
"""
frame_at.py — zoom into a video: full-resolution frames at given instants or over a dense window.

  python3 frame_at.py v2s_work 1:23 2:05.5          # frames at 1:23 and 2:05.5
  python3 frame_at.py v2s_work --window 1:20 1:30 --step 1   # one frame per second
  python3 frame_at.py v2s_work 1:23 --crop 0,0.5,1,0.5        # x,y,w,h as fractions (bottom half)

Writes to <work>/zoom/ and prints the file paths (read them with your image viewer / Read tool).
"""
import argparse
import subprocess
import sys
from pathlib import Path


def parse_t(s):
    parts = [float(p) for p in s.split(":")]
    t = 0.0
    for p in parts:
        t = t * 60 + p
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("times", nargs="*")
    ap.add_argument("--window", nargs=2, metavar=("START", "END"))
    ap.add_argument("--step", type=float, default=1.0)
    ap.add_argument("--crop", default=None, help="x,y,w,h en fractions de l'image")
    a = ap.parse_args()

    work = Path(a.work)
    vids = [p for p in work.glob("video.*") if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi")]
    if not vids:
        sys.exit(f"pas de video.* dans {work} — lance d'abord extract.py")
    video = vids[0]
    ts = [parse_t(t) for t in a.times]
    if a.window:
        s, e = parse_t(a.window[0]), parse_t(a.window[1])
        n = int((e - s) / a.step) + 1
        if n > 40:
            sys.exit(f"{n} images demandées : réduis la fenêtre ou augmente --step (max 40)")
        ts += [s + i * a.step for i in range(n)]
    if not ts:
        sys.exit("donne au moins un instant ou --window")

    vf = "scale='min(1920,iw)':-2"
    if a.crop:
        x, y, w, h = [float(v) for v in a.crop.split(",")]
        vf = f"crop=iw*{w}:ih*{h}:iw*{x}:ih*{y}," + vf
    zdir = work / "zoom"
    zdir.mkdir(exist_ok=True)
    for t in ts:
        out = zdir / f"z_t{t:07.2f}{'_crop' if a.crop else ''}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video),
                        "-frames:v", "1", "-vf", vf, str(out)], check=True)
        print(out)


if __name__ == "__main__":
    main()
