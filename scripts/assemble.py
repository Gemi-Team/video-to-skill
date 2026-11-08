#!/usr/bin/env python3
"""
assemble.py — dernière étape du mode vidéo longue : contrôle les notes des sous-agents,
puis range leurs méthodes dans les fichiers de référence du skill final.

  python scripts/assemble.py v2s_work --check                  # notes complètes ? journal visuel ? citations ?
  python scripts/assemble.py v2s_work --list                   # toutes les méthodes : id (P2.M7) + titre
  python scripts/assemble.py v2s_work --plan-template          # brouillon de plan (JSON) à réorganiser par thème
  python scripts/assemble.py v2s_work --plan v2s_work/plan.json --out skills_out/<nom>

Plan (JSON écrit par l'orchestrateur, dans l'ordre logique d'application, pas l'ordre de la vidéo) :
  {
    "name": "<nom-du-skill>",
    "files": [
      {"file": "01-positionnement", "title": "Positionnement et message",
       "purpose": "Choisir ce pour quoi la marque est connue…", "methods": ["P1.M2", "P1.M4"]}
    ],
    "drop": {"P3.M3": "doublon de P2.M12 : fusionné à la main dans 04, section 4.7"}
  }
Chaque méthode est placée une seule fois, ou listée dans "drop" avec une raison (fusion, hors sujet).
Sortie : <out>/references/NN-*.md (méthodes renumérotées N.k, horodatages normalisés)
         + <out>/references/99-incertitudes-et-ignore.md.
Restent à faire par l'orchestrateur : les fusions annoncées dans "drop", puis SKILL.md (voir SKILL.md du repo).
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import utf8_console  # noqa: E402

REQUIRED = ["## Méthodes", "## Ignoré", "## Incertain", "## Journal visuel"]
CITE = re.compile(r"\[t=(\d+(?::\d{2}){1,2})")


def secs(ts):
    t = 0
    for p in ts.split(":"):
        t = t * 60 + int(p)
    return t


def norm(text):
    """[2:00:05] → [t=2:00:05] (format oublié par certains agents) ; [t=0:02:50] → [t=2:50]."""
    text = re.sub(r"\[(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[–-]\s*\d{1,2}:\d{2}(?::\d{2})?)?)\]", r"[t=\1]", text)
    return re.sub(r"(?<=[=–-])0:(\d{2}):(\d{2})", lambda m: f"{int(m.group(1))}:{m.group(2)}", text)


def load(work):
    work = Path(work).resolve()
    pj = work / "parts.json"
    if not pj.exists():
        sys.exit(f"{pj} introuvable : lance d'abord extract.py (vidéo longue) ou parts.py")
    parts = json.loads(pj.read_text(encoding="utf-8"))
    out = []
    for p in parts:
        f = work / p["notes"]
        text = norm(f.read_text(encoding="utf-8")) if f.exists() else ""
        methods = [{"id": f"P{p['n']}.M{m.group(1)}", "title": m.group(2).strip(), "body": m.group(3).rstrip()}
                   for m in re.finditer(r"^### M(\d+)\. (.+?)\n(.*?)(?=^### |^## |\Z)", text, re.S | re.M)]
        out.append({**p, "path": f, "text": text, "methods": methods})
    return work, out


def section(text, head):
    m = re.search(rf"^{re.escape(head)}\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else None


def check(parts):
    errors, warns = [], []
    for p in parts:
        tag = p["dir"]
        if not p["text"].strip():
            errors.append(f"{tag} : notes absentes ({p['notes']}) → relancer son sous-agent")
            continue
        for h in REQUIRED:
            if section(p["text"], h) is None:
                errors.append(f"{tag} : section « {h} » manquante")
        if not p["methods"]:
            warns.append(f"{tag} : aucune méthode (partie non instructive ? vérifier « Ignoré »)")
        for m in p["methods"]:
            if not CITE.search(m["body"]):
                errors.append(f"{tag} : {m['id']} « {m['title'][:50]} » sans citation [t=…]")
        # citations hors de la plage de la partie (±90 s) → probable erreur d'horodatage
        out = [c for c in CITE.findall(section(p["text"], "## Méthodes") or "")
               if not (p["start"] - 90 <= secs(c) <= p["end"] + 90)]
        if out:
            warns.append(f"{tag} : {len(out)} citation(s) hors de {p['from']}–{p['to']} (ex. {out[0]})")
        # couverture visuelle : chaque planche doit apparaître dans le journal
        journal = section(p["text"], "## Journal visuel") or ""
        sheets = [Path(s).stem for s in p.get("sheets", [])]
        missing = [s for s in sheets if not re.search(rf"\b{s}\b", journal)]
        if missing:
            errors.append(f"{tag} : journal visuel incomplet — {len(missing)}/{len(sheets)} planche(s) non décrite(s) "
                          f"({', '.join(missing[:6])}{'…' if len(missing) > 6 else ''}) → relancer le sous-agent")
        cov = re.search(r"Couverture visuelle\s*:\s*(\d+)\s*/\s*(\d+)", p["text"])
        if not cov:
            warns.append(f"{tag} : ligne « Couverture visuelle : x/y » absente")
        elif int(cov.group(1)) < int(cov.group(2)):
            errors.append(f"{tag} : couverture visuelle déclarée {cov.group(1)}/{cov.group(2)} planches")
    return errors, warns


def build(work, parts, plan_path, out):
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    by_id = {m["id"]: (p, m) for p in parts for m in p["methods"]}
    placed = [mid for f in plan["files"] for mid in f["methods"]]
    unknown = [m for m in placed + list(plan.get("drop", {})) if m not in by_id]
    dup = sorted({m for m in placed if placed.count(m) > 1})
    missing = [m for m in by_id if m not in placed and m not in plan.get("drop", {})]
    if unknown or dup or missing:
        sys.exit("Plan invalide :"
                 + (f"\n  ids inconnus : {unknown}" if unknown else "")
                 + (f"\n  placés deux fois : {dup}" if dup else "")
                 + (f"\n  non placés (ajoute-les ou mets-les dans \"drop\" avec une raison) : {missing}" if missing else ""))
    refs = Path(out) / "references"
    refs.mkdir(parents=True, exist_ok=True)
    written = []
    for i, f in enumerate(plan["files"], 1):
        n = int(re.match(r"\d+", f["file"]).group(0)) if re.match(r"\d+", f["file"]) else i
        srcs = sorted({by_id[m][0]["n"] for m in f["methods"]})
        lines = [f"# {f['title']}", "", f.get("purpose", ""), "",
                 f"Source : partie(s) {', '.join(map(str, srcs))} de la vidéo — citations `[t=…]` en temps de la vidéo complète.", ""]
        for k, mid in enumerate(f["methods"], 1):
            p, m = by_id[mid]
            lines += [f"## {n}.{k} {m['title']}", f"<!-- src: {mid} -->", m["body"].strip(), ""]
        name = f["file"] if f["file"].endswith(".md") else f["file"] + ".md"
        (refs / name).write_text("\n".join(lines), encoding="utf-8")
        written.append((name, len(f["methods"])))
    extra = ["# Incertitudes et passages ignorés", "",
             "Relevés par les sous-agents. L'écran a primé sur la narration quand ils divergeaient.", "",
             "## Incertitudes", ""]
    for p in parts:
        extra += [f"### Partie {p['n']} ({p['from']}–{p['to']})", section(p["text"], "## Incertain") or "_(rien)_", ""]
    extra += ["## Passages ignorés (sans méthode)", ""]
    for p in parts:
        extra += [f"### Partie {p['n']} ({p['from']}–{p['to']})", section(p["text"], "## Ignoré") or "_(rien)_", ""]
    (refs / "99-incertitudes-et-ignore.md").write_text("\n".join(extra), encoding="utf-8")
    return written, plan.get("drop", {})


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--plan-template", action="store_true")
    ap.add_argument("--plan")
    ap.add_argument("--out")
    a = ap.parse_args()
    work, parts = load(a.work)

    if a.check or not (a.list or a.plan_template or a.plan):
        errors, warns = check(parts)
        for p in parts:
            print(f"  {p['dir']}  {p['from']}–{p['to']}  {len(p['methods'])} méthode(s)  {len(p.get('sheets', []))} planches")
        for w in warns:
            print(f"  ⚠  {w}")
        for e in errors:
            print(f"  ✗  {e}")
        print("ÉCHEC : corrige ou relance les sous-agents concernés" if errors else "OK : notes prêtes à assembler")
        sys.exit(1 if errors else 0)
    if a.list:
        for p in parts:
            print(f"\n{p['dir']}  {p['from']}–{p['to']}  ({', '.join(p.get('chapters', []))[:100]})")
            for m in p["methods"]:
                print(f"  {m['id']:<7} {m['title']}")
    if a.plan_template:
        tpl = {"name": "<nom-du-skill>",
               "files": [{"file": f"{p['n']:02d}-<theme>", "title": "<titre du thème>", "purpose": "<à quoi ça sert>",
                          "methods": [m["id"] for m in p["methods"]]} for p in parts],
               "drop": {}}
        print(json.dumps(tpl, ensure_ascii=False, indent=2))
    if a.plan:
        if not a.out:
            sys.exit("--out requis avec --plan")
        errors, _ = check(parts)
        if errors:
            sys.exit("Notes incomplètes : lance --check et corrige d'abord.\n" + "\n".join(errors))
        written, drop = build(work, parts, a.plan, a.out)
        for name, n in written:
            print(f"  ✔ references/{name}  ({n} méthodes)")
        print("  ✔ references/99-incertitudes-et-ignore.md")
        if drop:
            print("À faire à la main (fusions / exclusions annoncées dans le plan) :")
            for k, v in drop.items():
                print(f"  - {k} : {v}")
        print(f"Puis écris {Path(a.out) / 'SKILL.md'} (carte des méthodes, méthodes centrales, principes, source) "
              f"et valide : python scripts/validate_skill.py {a.out}")


if __name__ == "__main__":
    main()
