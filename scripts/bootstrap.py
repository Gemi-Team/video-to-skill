#!/usr/bin/env python3
"""
bootstrap.py — installe ET vérifie tout ce dont video-to-skill a besoin (Windows, macOS, Linux).
Aucun droit admin requis, jamais de sudo. Idempotent : on peut le relancer sans risque.

  python scripts/bootstrap.py                      # tout : paquets, ffmpeg, runtime JS, Whisper (small),
                                                   #        autotest, installation du skill Claude Code
  python scripts/bootstrap.py --check              # diagnostic seul, n'installe rien
  python scripts/bootstrap.py --minimal            # pillow + ffmpeg (pas d'URL, pas de transcription)
  python scripts/bootstrap.py --whisper-model medium   # tiny | base | small | medium | large-v3 | turbo
  python scripts/bootstrap.py --skip-model         # ne pas pré-télécharger le modèle Whisper
  python scripts/bootstrap.py --no-skill           # ne pas copier le skill dans ~/.claude/skills
  python scripts/bootstrap.py --project            # copier le skill dans ./.claude/skills (projet courant)
  python scripts/bootstrap.py --test-url URL       # tester aussi un vrai téléchargement YouTube
  python scripts/bootstrap.py --json               # rapport JSON sur stdout (pour un LLM / la CI)

Code retour : 0 = tout ce qui est requis fonctionne ; 1 = au moins un ✗ (voir la colonne « fix »).
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

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # bruit inutile sous Windows
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
        return 127, f"introuvable : {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"délai dépassé ({timeout}s)"


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
        add("python", "fail", detail, "Python 3.9+ requis (3.11+ recommandé) : https://www.python.org/downloads/")
        return False
    if v < (3, 11):
        add("python", "warn", detail, "fonctionne, mais yt-dlp abandonne Python 3.10 : passe à 3.11+ quand possible")
    else:
        add("python", "ok", detail)
    return True


def step_pip(check):
    code, out = sh([PY, "-m", "pip", "--version"], 60)
    if code != 0 and not check:
        log("pip absent → python -m ensurepip")
        sh([PY, "-m", "ensurepip", "--upgrade"], 300)
        code, out = sh([PY, "-m", "pip", "--version"], 60)
    if code != 0:
        add("pip", "fail", "pip indisponible",
            "Debian/Ubuntu : sudo apt install python3-pip python3-venv ; sinon réinstaller Python avec pip")
        return False
    add("pip", "ok", out.split(" from ")[0].strip())
    return True


def step_package(label, module, spec, check, upgrade=False, required=True):
    present = importable(module)
    if check or (present and not upgrade):
        if present:
            add(label, "ok", version_of(module))
        else:
            add(label, "fail" if required else "warn", "non installé", f'"{PY}" -m pip install -U "{spec}"')
        return present
    log(f"pip install {'-U ' if upgrade else ''}{spec} …")
    ok, msg = pip_install([spec], upgrade=upgrade)
    if ok and importable(module):
        add(label, "ok", version_of(module))
        return True
    add(label, "fail" if required else "warn", f"installation impossible : {msg[-300:]}",
        f'"{PY}" -m pip install -U "{spec}"  (ou dans un venv : python -m venv .venv)')
    return False


def version_of(module):
    try:
        from importlib.metadata import version
        dist = {"PIL": "pillow", "yt_dlp": "yt-dlp", "yt_dlp_ejs": "yt-dlp-ejs",
                "faster_whisper": "faster-whisper", "curl_cffi": "curl_cffi"}.get(module, module)
        return version(dist)
    except Exception:
        return "installé"


def step_ffmpeg(check, allow_system):
    ff, fp = ensure_ffmpeg(fetch=True)
    if not ff and not check:
        sysname = platform.system()
        tried = None
        if allow_system and sysname == "Windows" and which("winget"):
            tried = "winget install Gyan.FFmpeg"
            log(f"{tried} … (peut prendre quelques minutes)")
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
        if not ff:  # repli universel, sans droits : binaires portables via pip
            log("repli : pip install static-ffmpeg (binaires portables)")
            pip_install(["static-ffmpeg"])
            ff, fp = ensure_ffmpeg(fetch=True)
    if ff and fp:
        _, out = sh([ff, "-version"], 30)
        add("ffmpeg", "ok", (out.splitlines() or ["?"])[0][:80] + f" ({ff})")
        return True
    add("ffmpeg", "fail", "ffmpeg/ffprobe introuvables",
        "Windows : winget install Gyan.FFmpeg | macOS : brew install ffmpeg | Linux : sudo apt install ffmpeg "
        "| sans droits : pip install static-ffmpeg")
    return False


def step_js(check):
    name, path = find_js_runtime()
    if not name and not check:
        log("aucun runtime JS → pip install deno (requis par yt-dlp pour YouTube)")
        pip_install(["deno"])
        name, path = find_js_runtime()
    if name:
        add("runtime JS (yt-dlp)", "ok", f"{name} ({path})")
        return True
    add("runtime JS (yt-dlp)", "warn", "ni deno, ni node, ni bun",
        "pip install deno (ou winget install DenoLand.Deno / brew install deno) ; sans lui YouTube peut refuser des formats")
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
    add("GPU CUDA", "ok" if gpu else "skip", f"{gpu} GPU détecté(s)" if gpu else "aucun → Whisper tournera sur CPU (plus lent)")
    if check or skip_model:
        add(f"modèle whisper {model}", "skip", "non testé (--check / --skip-model)")
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
            log(f"téléchargement / chargement du modèle Whisper « {model} » ({dev})… (1re fois : de 75 Mo à 3 Go)")
            m = WhisperModel(model, device=dev, compute_type="int8")
            if wav.exists():
                list(m.transcribe(str(wav), vad_filter=False)[0])
            add(f"modèle whisper {model}", "ok", f"prêt sur {'GPU' if dev == 'auto' and gpu else 'CPU'}"
                + ("" if dev == "auto" or not gpu else " (GPU présent mais inutilisable : libs CUDA/cuDNN manquantes)"))
            shutil.rmtree(tmp, ignore_errors=True)
            return True
        except Exception as e:
            errors.append(f"{dev}: {type(e).__name__}: {str(e)[:200]}")
    shutil.rmtree(tmp, ignore_errors=True)
    add(f"modèle whisper {model}", "fail", " | ".join(errors),
        "téléchargement HuggingFace bloqué ? proxy : HTTPS_PROXY=… ; miroir : HF_ENDPOINT=https://hf-mirror.com ; "
        "ou --whisper-model tiny pour tester")
    return False


def step_skill(dest):
    if dest is None:
        add("skill Claude Code", "skip", "--no-skill")
        return True
    dest = Path(dest).expanduser().resolve()
    if dest == ROOT:
        add("skill Claude Code", "ok", f"déjà en place ({dest})")
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
    add("skill Claude Code", "ok", f"copié dans {dest}  (Claude Code : /video-to-skill <URL>)")
    return True


def step_selftest():
    gen = ROOT / "tests" / "make_test_video.py"
    if not gen.exists():
        add("autotest", "skip", "tests/ absent (skill installé sans le repo)")
        return True
    tmp = Path(tempfile.mkdtemp(prefix="v2s_selftest_"))
    try:
        code, out = sh([PY, str(gen), str(tmp / "src")], 300)
        if code != 0:
            add("autotest", "fail", f"génération vidéo : {out.strip()[-300:]}", "voir l'étape ffmpeg")
            return False
        code, out = sh([PY, str(HERE / "extract.py"), str(tmp / "src" / "tuto_venv.mp4"), "--out", str(tmp / "work"),
                        "--no-transcribe"], 600)
        man = tmp / "work" / "manifest.json"
        if code != 0 or not man.exists():
            add("autotest", "fail", f"extract.py : {out.strip()[-400:]}", "relancer avec --check et lire l'erreur")
            return False
        m = json.loads(man.read_text(encoding="utf-8"))
        ok = len(m["frames"]) >= 5 and m["sheets"] and str(m["transcript_source"]).startswith("sous-titres")
        code2, out2 = sh([PY, str(HERE / "validate_skill.py"), str(ROOT / "examples" / "python-venv-requests")], 60)
        # découpage « vidéo longue » simulé : parties de 20 s sur la vidéo de test
        code3, out3 = sh([PY, str(HERE / "parts.py"), str(tmp / "work"), "--max-minutes", "0.34"], 300)
        try:  # sh() renvoie stdout (le JSON) suivi de stderr (les logs)
            nparts = len(json.JSONDecoder().raw_decode(out3.lstrip())[0]) if code3 == 0 else 0
        except ValueError:
            nparts = 0
        prompt_ok = (tmp / "work" / "part_01" / "AGENT_PROMPT.md").exists()
        detail = (f"vidéo test → {len(m['frames'])} images, {len(m['sheets'])} planches, "
                  f"transcription : {m['transcript_source']} ; validate_skill : {'OK' if code2 == 0 else 'ÉCHEC'} ; "
                  f"découpage : {nparts} parties{'' if prompt_ok else ' (AGENT_PROMPT.md manquant)'}")
        ok = ok and code2 == 0 and nparts >= 2 and prompt_ok
        add("autotest", "ok" if ok else "fail", detail,
            "" if ok else "sortie inattendue : relancer l'étape en échec à la main et lire l'erreur")
        return ok
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def step_test_url(url):
    from download import download_one
    tmp = Path(tempfile.mkdtemp(prefix="v2s_dl_"))
    try:
        r = download_one(url, tmp, progress=False)
        if r["ok"]:
            add("téléchargement YouTube", "ok",
                f"« {r['title']} » ({r['duration']} s), {len(r['subtitles'])} fichier(s) de sous-titres")
        else:
            add("téléchargement YouTube", "fail", (r["error"] or "")[-300:], r["hint"] or "")
        return r["ok"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- main
def main():
    global JSON_MODE
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="diagnostic seul, aucune installation")
    ap.add_argument("--minimal", action="store_true", help="pillow + ffmpeg seulement")
    ap.add_argument("--whisper-model", default="small")
    ap.add_argument("--skip-model", action="store_true")
    ap.add_argument("--no-system", action="store_true", help="ne pas utiliser winget/brew/apt (pip uniquement)")
    ap.add_argument("--no-skill", action="store_true")
    ap.add_argument("--project", action="store_true", help="skill dans ./.claude/skills/video-to-skill")
    ap.add_argument("--skill-dir", default=None, help="dossier de destination du skill")
    ap.add_argument("--no-selftest", action="store_true")
    ap.add_argument("--test-url", default=None, help="URL courte à télécharger pour tester yt-dlp")
    ap.add_argument("--json", action="store_true", help="rapport JSON sur stdout")
    a = ap.parse_args()
    JSON_MODE = a.json

    log(f"{platform.system()} {platform.release()} — {'diagnostic' if a.check else 'installation'}")
    if step_python() and step_pip(a.check):
        step_package("pillow", "PIL", "pillow>=10", a.check)
        step_ffmpeg(a.check, not a.no_system)
        if not a.minimal:
            # yt-dlp casse souvent quand YouTube change → toujours la dernière version
            step_package("yt-dlp", "yt_dlp", "yt-dlp[default]", a.check, upgrade=True)
            step_package("yt-dlp-ejs (défis JS YouTube)", "yt_dlp_ejs", "yt-dlp-ejs", a.check, required=False)
            # via l'extra de yt-dlp : il impose une version de curl_cffi compatible (sinon « no impersonate target »)
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
                        f'"{PY}" scripts/extract.py <URL ou fichier> --out v2s_work']}
    if a.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("\n" + ("✔ Tout est prêt." if not fails else f"✗ {len(fails)} problème(s) à corriger :"))
        for r in fails:
            print(f"  - {r['name']} : {r['detail'][:200]}\n    fix : {r['fix']}")
        warns = [r for r in REPORT if r["status"] == "warn"]
        for r in warns:
            print(f"  ⚠ {r['name']} : {r['fix']}")
        print(f"\nPython à utiliser : {PY}")
        print(f'  "{PY}" scripts/download.py "https://www.youtube.com/watch?v=…"')
        print(f'  "{PY}" scripts/extract.py "<URL ou fichier>" --out v2s_work')
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
