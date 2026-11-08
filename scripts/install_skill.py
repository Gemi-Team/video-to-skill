#!/usr/bin/env python3
"""
install_skill.py — validate a generated skill, then install it for Claude Code (last step, automatic).

  python scripts/install_skill.py skills_out/<name>              # → ~/.claude/skills/<name>/
  python scripts/install_skill.py skills_out/<name> --project    # → ./.claude/skills/<name>/
  python scripts/install_skill.py skills_out/<name> --dest DIR   # → DIR/<name>/

- Refuses to install a skill that fails validate_skill.py.
- If a skill with the same name is already installed, it is moved to ~/.claude/skills-backup/<name>-<date>/
  (outside the skills folder, so Claude does not load it twice) before the new one is copied.
- Prints where the skill was installed and how to remove it.
"""
import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _common import PY, utf8_console  # noqa: E402


def skill_name(src: Path):
    m = re.search(r"^name:\s*(.+)$", (src / "SKILL.md").read_text(encoding="utf-8"), re.M)
    return m.group(1).strip().strip("\"'") if m else src.name


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("skill", help="folder containing the generated SKILL.md (e.g. skills_out/<name>)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--project", action="store_true", help="install into ./.claude/skills (current project)")
    g.add_argument("--dest", default=None, help="skills folder to install into")
    a = ap.parse_args()

    src = Path(a.skill).resolve()
    if not (src / "SKILL.md").exists():
        sys.exit(f"No SKILL.md in {src}")
    r = subprocess.run([PY, str(HERE / "validate_skill.py"), str(src)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print(r.stdout.strip())
    if r.returncode != 0:
        sys.exit("Not installed: fix the errors above, then run this script again.")

    name = skill_name(src)
    root = Path(a.dest).expanduser() if a.dest else (Path.cwd() / ".claude" / "skills" if a.project
                                                       else Path.home() / ".claude" / "skills")
    dest = (root / name).resolve()
    if dest == src:
        sys.exit(f"Source and destination are the same folder: {dest}")
    root.mkdir(parents=True, exist_ok=True)
    backup = None
    if dest.exists():
        backup = Path.home() / ".claude" / "skills-backup" / f"{name}-{datetime.now():%Y%m%d-%H%M%S}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dest), str(backup))
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))

    print(f"✔ Installed: {dest}")
    if backup:
        print(f"  Previous version moved to: {backup}")
    print(f"  Claude Code uses it automatically from the next request that matches its description "
          f"(or explicitly: /{name}).")
    print(f"  To remove it: delete the folder {dest}")


if __name__ == "__main__":
    main()
