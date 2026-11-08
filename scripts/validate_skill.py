#!/usr/bin/env python3
"""
validate_skill.py — lint a generated skill folder before installing it.

  python validate_skill.py path/to/skill-dir

Errors (exit 1): missing/invalid frontmatter, bad name, description too long, secrets,
broken relative links. Warnings: no timestamp citations, video narration left in,
body too long, unverified steps not flagged.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import utf8_console  # noqa: E402

SECRET_PATTERNS = [
    (r"sk-[A-Za-z0-9_-]{20,}", "clé API style OpenAI/Anthropic"),
    (r"ghp_[A-Za-z0-9]{30,}", "token GitHub"),
    (r"AKIA[0-9A-Z]{16}", "clé AWS"),
    (r"xox[baprs]-[A-Za-z0-9-]{10,}", "token Slack"),
    (r"(?i)(password|passwd|mot de passe|secret|api[_-]?key)\s*[:=]\s*['\"]?[^\s'\"<>{}]{6,}", "mot de passe / secret en clair"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "clé privée"),
]
NARRATION = [
    r"(?i)\bin this video\b", r"(?i)\bdans cette vid[ée]o\b", r"(?i)\bsubscribe\b", r"(?i)\babonnez\b",
    r"(?i)\bsmash (that|the) like\b", r"(?i)\blike and subscribe\b", r"(?i)\bso what we'?re gonna do\b",
    r"(?i)\balors ce qu'on va faire\b", r"(?i)\bas you can see\b", r"(?i)\bcomme vous pouvez (le )?voir\b",
]


def parse_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None, text
    fm = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if mm:
            fm[mm.group(1)] = mm.group(2).strip().strip('"').strip("'")
    return fm, text[m.end():]


def main():
    utf8_console()
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = Path(sys.argv[1])
    skill = root / "SKILL.md" if root.is_dir() else root
    root = skill.parent
    errors, warns = [], []
    if not skill.exists():
        sys.exit(f"ERREUR: {skill} introuvable")
    text = skill.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)

    if fm is None:
        errors.append("frontmatter YAML absent (--- name/description --- en tête du fichier)")
        fm = {}
    name, desc = fm.get("name", ""), fm.get("description", "")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name or ""):
        errors.append(f"name invalide « {name} » : kebab-case minuscules attendu")
    if len(name) > 64:
        errors.append("name > 64 caractères")
    if re.search(r"claude|anthropic", name):
        errors.append("name ne doit pas contenir 'claude' ou 'anthropic'")
    if name and root.name != name and root.name not in ("", "."):
        warns.append(f"le dossier « {root.name} » ne correspond pas au name « {name} »")
    if not desc:
        errors.append("description vide")
    elif len(desc) > 1024:
        errors.append(f"description trop longue ({len(desc)} > 1024)")
    elif len(desc) < 60:
        warns.append("description très courte : dis QUAND utiliser le skill (déclencheurs)")
    if "<" in desc or ">" in desc:
        errors.append("description ne doit pas contenir < ou >")

    files = [skill] + [p for p in root.rglob("*") if p.is_file() and p != skill and p.suffix in (".md", ".txt", ".py", ".sh", ".json", ".yaml", ".yml")]
    for f in files:
        t = f.read_text(encoding="utf-8", errors="ignore")
        for pat, label in SECRET_PATTERNS:
            for m in re.finditer(pat, t):
                frag = m.group(0)
                if re.search(r"(?i)<[^>]+>|\$\{?[A-Z_]+|your[_-]|votre|xxx|\*\*\*|example|exemple|placeholder|changeme", frag):
                    continue
                errors.append(f"{f.relative_to(root)}: possible {label} : « {frag[:24]}… » → remplace par un placeholder")

    for link in re.findall(r"\]\(([^)#\s]+)\)", body):
        if not re.match(r"^[a-z]+://", link) and not (root / link).exists():
            errors.append(f"lien relatif cassé : {link}")

    n_lines = body.count("\n")
    if n_lines > 500:
        warns.append(f"SKILL.md fait {n_lines} lignes : déplace la théorie dans references/ (cible < 500)")
    cites = re.findall(r"\[t=\d+:\d{2}(?::\d{2})?\]", text)
    if not cites:
        warns.append("aucune citation [t=MM:SS] : impossible de retracer les étapes vers la vidéo")
    for pat in NARRATION:
        m = re.search(pat, body)
        if m:
            warns.append(f"narration de vidéo restée dans le texte (« {m.group(0)} ») → réécris en instruction")
    if not re.search(r"(?i)source|provenance", text):
        warns.append("pas de section Source (URL/titre de la vidéo)")

    print(f"Skill : {name or '?'}  |  {n_lines} lignes  |  {len(cites)} citations temporelles  |  {len(files)} fichiers")
    for w in warns:
        print(f"  ⚠  {w}")
    for e in errors:
        print(f"  ✗  {e}")
    if errors:
        print("ÉCHEC")
        sys.exit(1)
    print("OK" + (" (avec avertissements)" if warns else ""))


if __name__ == "__main__":
    main()
