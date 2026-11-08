#!/usr/bin/env python3
"""
assemble.py — last step of long-video mode: checks the sub-agents' notes,
then files their methods into the reference files of the final skill.

  python scripts/assemble.py v2s_work --check                  # notes complete? visual log? citations?
  python scripts/assemble.py v2s_work --list                   # every method: id (P2.M7) + title
  python scripts/assemble.py v2s_work --plan-template          # draft plan (JSON) to reorganise by theme
  python scripts/assemble.py v2s_work --plan v2s_work/plan.json --out skills_out/<name>

Plan (JSON written by the orchestrator, in the logical order of application, not the order of the video):
  {
    "name": "<skill-name>",
    "files": [
      {"file": "01-positioning", "title": "Positioning and messaging",
       "purpose": "Choose what the brand is known for…", "methods": ["P1.M2", "P1.M4"]}
    ],
    "drop": {"P3.M3": "duplicate of P2.M12: merged by hand into 04, section 4.7"}
  }
Every method is placed exactly once, or listed in "drop" with a reason (merge, off-topic).
Output: <out>/references/NN-*.md (methods renumbered N.k, timestamps normalized)
        + <out>/references/99-uncertainties-and-skipped.md.
Left to the orchestrator: the merges announced in "drop", then SKILL.md (see the repo's SKILL.md).

Section headings are read in English (template) or French (notes written with an older template).
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import utf8_console  # noqa: E402

# heading → accepted spellings (English template first, French for older notes)
SECTIONS = {
    "methods": ["## Methods", "## Méthodes"],
    "skipped": ["## Skipped", "## Ignoré"],
    "uncertain": ["## Uncertain", "## Incertain"],
    "visual_log": ["## Visual log", "## Journal visuel"],
}
COVERAGE = re.compile(r"(?:Visual coverage|Couverture visuelle)\s*:\s*(\d+)\s*/\s*(\d+)", re.I)
CITE = re.compile(r"\[t=(\d+(?::\d{2}){1,2})")


def secs(ts):
    t = 0
    for p in ts.split(":"):
        t = t * 60 + int(p)
    return t


def norm(text):
    """[2:00:05] → [t=2:00:05] (format some agents forget); [t=0:02:50] → [t=2:50]."""
    text = re.sub(r"\[(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[–-]\s*\d{1,2}:\d{2}(?::\d{2})?)?)\]", r"[t=\1]", text)
    return re.sub(r"(?<=[=–-])0:(\d{2}):(\d{2})", lambda m: f"{int(m.group(1))}:{m.group(2)}", text)


def load(work):
    work = Path(work).resolve()
    pj = work / "parts.json"
    if not pj.exists():
        sys.exit(f"{pj} not found: run extract.py (long video) or parts.py first")
    parts = json.loads(pj.read_text(encoding="utf-8"))
    out = []
    for p in parts:
        f = work / p["notes"]
        text = norm(f.read_text(encoding="utf-8")) if f.exists() else ""
        methods = [{"id": f"P{p['n']}.M{m.group(1)}", "title": m.group(2).strip(), "body": m.group(3).rstrip()}
                   for m in re.finditer(r"^### M(\d+)\. (.+?)\n(.*?)(?=^### |^## |\Z)", text, re.S | re.M)]
        out.append({**p, "path": f, "text": text, "methods": methods})
    return work, out


def section(text, key):
    """Body of a section (any accepted spelling), or None if the heading is missing."""
    for head in SECTIONS[key]:
        m = re.search(rf"^{re.escape(head)}\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
        if m:
            return m.group(1).strip()
    return None


def check(parts):
    errors, warns = [], []
    for p in parts:
        tag = p["dir"]
        if not p["text"].strip():
            errors.append(f"{tag}: notes missing ({p['notes']}) → relaunch its sub-agent")
            continue
        for key, heads in SECTIONS.items():
            if section(p["text"], key) is None:
                errors.append(f"{tag}: section \"{heads[0]}\" missing")
        if not p["methods"]:
            warns.append(f"{tag}: no method (non-instructional part? check \"Skipped\")")
        for m in p["methods"]:
            if not CITE.search(m["body"]):
                errors.append(f"{tag}: {m['id']} \"{m['title'][:50]}\" has no [t=…] citation")
        # citations outside the part's range (±90 s) → probably a wrong timestamp
        out = [c for c in CITE.findall(section(p["text"], "methods") or "")
               if not (p["start"] - 90 <= secs(c) <= p["end"] + 90)]
        if out:
            warns.append(f"{tag}: {len(out)} citation(s) outside {p['from']}–{p['to']} (e.g. {out[0]})")
        # visual coverage: every contact sheet must appear in the log
        journal = section(p["text"], "visual_log") or ""
        sheets = [Path(s).stem for s in p.get("sheets", [])]
        missing = [s for s in sheets if not re.search(rf"\b{s}\b", journal)]
        if missing:
            errors.append(f"{tag}: incomplete visual log — {len(missing)}/{len(sheets)} sheet(s) not described "
                          f"({', '.join(missing[:6])}{'…' if len(missing) > 6 else ''}) → relaunch the sub-agent")
        cov = COVERAGE.search(p["text"])
        if not cov:
            warns.append(f"{tag}: line \"Visual coverage: x/y\" missing")
        elif int(cov.group(1)) < int(cov.group(2)):
            errors.append(f"{tag}: declared visual coverage {cov.group(1)}/{cov.group(2)} sheets")
    return errors, warns


def build(work, parts, plan_path, out):
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    by_id = {m["id"]: (p, m) for p in parts for m in p["methods"]}
    placed = [mid for f in plan["files"] for mid in f["methods"]]
    unknown = [m for m in placed + list(plan.get("drop", {})) if m not in by_id]
    dup = sorted({m for m in placed if placed.count(m) > 1})
    missing = [m for m in by_id if m not in placed and m not in plan.get("drop", {})]
    if unknown or dup or missing:
        sys.exit("Invalid plan:"
                 + (f"\n  unknown ids: {unknown}" if unknown else "")
                 + (f"\n  placed twice: {dup}" if dup else "")
                 + (f"\n  not placed (add them, or put them in \"drop\" with a reason): {missing}" if missing else ""))
    refs = Path(out) / "references"
    refs.mkdir(parents=True, exist_ok=True)
    written = []
    for i, f in enumerate(plan["files"], 1):
        n = int(re.match(r"\d+", f["file"]).group(0)) if re.match(r"\d+", f["file"]) else i
        srcs = sorted({by_id[m][0]["n"] for m in f["methods"]})
        lines = [f"# {f['title']}", "", f.get("purpose", ""), "",
                 f"Source: part(s) {', '.join(map(str, srcs))} of the video — `[t=…]` citations in full-video time.", ""]
        for k, mid in enumerate(f["methods"], 1):
            p, m = by_id[mid]
            lines += [f"## {n}.{k} {m['title']}", f"<!-- src: {mid} -->", m["body"].strip(), ""]
        name = f["file"] if f["file"].endswith(".md") else f["file"] + ".md"
        (refs / name).write_text("\n".join(lines), encoding="utf-8")
        written.append((name, len(f["methods"])))
    extra = ["# Uncertainties and skipped segments", "",
             "Reported by the sub-agents. The screen took precedence over the narration when they disagreed.", "",
             "## Uncertainties", ""]
    for p in parts:
        extra += [f"### Part {p['n']} ({p['from']}–{p['to']})", section(p["text"], "uncertain") or "_(none)_", ""]
    extra += ["## Skipped segments (no method)", ""]
    for p in parts:
        extra += [f"### Part {p['n']} ({p['from']}–{p['to']})", section(p["text"], "skipped") or "_(none)_", ""]
    (refs / "99-uncertainties-and-skipped.md").write_text("\n".join(extra), encoding="utf-8")
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
            print(f"  {p['dir']}  {p['from']}–{p['to']}  {len(p['methods'])} method(s)  {len(p.get('sheets', []))} sheets")
        for w in warns:
            print(f"  ⚠  {w}")
        for e in errors:
            print(f"  ✗  {e}")
        print("FAILED: fix or relaunch the sub-agents listed above" if errors else "OK: notes ready to assemble")
        sys.exit(1 if errors else 0)
    if a.list:
        for p in parts:
            print(f"\n{p['dir']}  {p['from']}–{p['to']}  ({', '.join(p.get('chapters', []))[:100]})")
            for m in p["methods"]:
                print(f"  {m['id']:<7} {m['title']}")
    if a.plan_template:
        tpl = {"name": "<skill-name>",
               "files": [{"file": f"{p['n']:02d}-<theme>", "title": "<theme title>", "purpose": "<what it is for>",
                          "methods": [m["id"] for m in p["methods"]]} for p in parts],
               "drop": {}}
        print(json.dumps(tpl, ensure_ascii=False, indent=2))
    if a.plan:
        if not a.out:
            sys.exit("--out is required with --plan")
        errors, _ = check(parts)
        if errors:
            sys.exit("Incomplete notes: run --check and fix them first.\n" + "\n".join(errors))
        written, drop = build(work, parts, a.plan, a.out)
        for name, n in written:
            print(f"  ✔ references/{name}  ({n} methods)")
        print("  ✔ references/99-uncertainties-and-skipped.md")
        if drop:
            print("To do by hand (merges / exclusions announced in the plan):")
            for k, v in drop.items():
                print(f"  - {k}: {v}")
        print(f"Then write {Path(a.out) / 'SKILL.md'} (method map, core methods, principles, source) "
              f"and validate: python scripts/validate_skill.py {a.out}")


if __name__ == "__main__":
    main()
