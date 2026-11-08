#!/usr/bin/env python3
"""
make_test_video.py — builds a ~50 s fake terminal tutorial + its .srt narration, to self-test the pipeline.

  python3 make_test_video.py /tmp/v2s_test      →  tuto_venv.mp4 + tuto_venv.srt

The narration deliberately mishears a command ("request 2.32" vs the screen's requests==2.32.3)
so you can check that the generated skill copies the screen, not the audio.
"""
import os
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def f(path, size):
    return ImageFont.truetype(path, size) if os.path.exists(path) else ImageFont.load_default()


def slide(title, sub):
    im = Image.new("RGB", (W, H), (24, 32, 56))
    d = ImageDraw.Draw(im)
    d.text((80, 260), title, fill=(255, 255, 255), font=f(SANS, 56))
    d.text((80, 350), sub, fill=(170, 190, 230), font=f(SANS, 30))
    return im


def term(lines):
    im = Image.new("RGB", (W, H), (30, 30, 30))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 36], fill=(60, 60, 60))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([16 + i * 26, 10, 32 + i * 26, 26], fill=c)
    d.text((W // 2 - 60, 8), "Terminal", fill=(200, 200, 200), font=f(SANS, 18))
    fm = f(MONO, 26)
    for i, l in enumerate(lines[-19:]):
        d.text((24, 56 + i * 34), l, fill=(230, 230, 230), font=fm)
    return im


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "v2s_test")
    out.mkdir(parents=True, exist_ok=True)
    fr = out / "_frames"
    fr.mkdir(exist_ok=True)
    seq = []  # (image, duration)

    seq.append((slide("Python : environnement virtuel", "Créer un venv, installer requests, figer les dépendances"), 5))
    hist = []
    prompt = "~/projet $ "

    def typed(cmd, outputs, hold=4.0):
        nonlocal prompt
        for k in list(range(0, len(cmd), 3)) + [len(cmd)]:
            seq.append((term(hist + [prompt + cmd[:k] + "█"]), 0.12))
        hist.append(prompt + cmd)
        seq.append((term(hist + [prompt + "█"] if not outputs else hist), 0.6))
        hist.extend(outputs)
        seq.append((term(hist + [prompt + "█"]), hold))

    seq.append((term([prompt + "█"]), 2))
    typed("python3 -m venv .venv", [])
    typed("source .venv/bin/activate", [])
    prompt = "(.venv) ~/projet $ "
    seq.append((term(hist + [prompt + "█"]), 2))
    typed("pip install requests==2.32.3",
          ["Collecting requests==2.32.3", "  Downloading requests-2.32.3-py3-none-any.whl (64 kB)",
           "Collecting charset-normalizer<4,>=2", "Collecting idna<4,>=2.5", "Collecting urllib3<3,>=1.21.1",
           "Collecting certifi>=2017.4.17",
           "Successfully installed certifi charset-normalizer idna requests-2.32.3 urllib3"], hold=5)
    typed("python -c \"import requests; print(requests.__version__)\"", ["2.32.3"])
    typed("pip freeze > requirements.txt", [])
    typed("grep requests requirements.txt", ["requests==2.32.3"], hold=4)
    seq.append((slide("Merci d'avoir regardé !", "Abonnez-vous pour plus de tutos"), 4))

    lst = []
    t = 0.0
    for i, (im, dur) in enumerate(seq):
        p = fr / f"{i:04d}.png"
        im.save(p)
        lst.append(f"file '{p.resolve()}'\nduration {dur}")
        t += dur
    lst.append(f"file '{(fr / f'{len(seq) - 1:04d}.png').resolve()}'")
    (out / "_list.txt").write_text("\n".join(lst) + "\n")
    video = out / "tuto_venv.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(out / "_list.txt"),
                    "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-shortest",
                    "-vf", "fps=25,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
                    str(video)], check=True)

    srt = [
        (0.5, 5, "Salut ! Dans cette vidéo on va voir comment créer un environnement virtuel Python."),
        (7, 11, "D'abord on crée le venv avec python -m venv."),
        (12, 15, "Ensuite on l'active avec source."),
        (17, 24, "Maintenant on installe request, version 2.32."),
        (25, 31, "On vérifie que ça marche en affichant la version."),
        (32, 39, "Et enfin on fige les dépendances dans un fichier requirements."),
        (t - 4, t - 0.5, "Merci d'avoir regardé, abonnez-vous !"),
    ]

    def ts(x):
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    (out / "tuto_venv.srt").write_text("\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{txt}\n" for i, (a, b, txt) in enumerate(srt, 1)))
    for p in fr.iterdir():
        p.unlink()
    fr.rmdir()
    (out / "_list.txt").unlink()
    print(video, f"{t:.1f}s")


if __name__ == "__main__":
    main()
