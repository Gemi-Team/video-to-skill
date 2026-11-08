# video-to-skill — instructions pour Claude

Ce repo transforme une vidéo (URL YouTube ou fichier) en **skill Claude** réutilisable.
L'utilisateur n'a rien à préparer ni à lancer : **c'est toi qui installes, extrais, orchestres et assembles.** Ne lui demande jamais d'exécuter une commande.

## Quand l'utilisateur donne une vidéo

Déclencheurs : une URL ou un fichier vidéo, « transforme cette vidéo en skill », « apprends de cette vidéo », « lis le repo et fais-le », `/video-to-skill <URL>`.

1. **Python** — `PY` = `python` ou `py -3` sous Windows (jamais `python3`, souvent un faux raccourci du Microsoft Store) ; `python3` sur macOS/Linux.
2. **Prérequis** — `PY scripts/bootstrap.py --check --json` (quelques secondes).
   Si `"ok": false` : annonce-le en une phrase, puis `PY scripts/bootstrap.py --json --no-skill` (2 à 10 min : donne-lui 15 min de délai ou lance-le en arrière-plan, ne l'interromps pas). En cas d'échec seulement, suis [LLM_SETUP.md](LLM_SETUP.md).
3. **Méthode** — suis [SKILL.md](SKILL.md) avec `SKILL_DIR` = la racine de ce repo. Lance toujours les scripts en **chemin relatif** depuis la racine (`PY scripts/extract.py …`) : ce sont ces commandes que les permissions du repo autorisent.
   Dossier de travail : `v2s_work/<identifiant-court>/` (ex. l'id YouTube).
4. **Vidéo de plus de 45 min** — mode vidéo longue de SKILL.md :
   - un sous-agent `general-purpose` **par partie, tous lancés en parallèle**, consigne : « Lis et exécute `<chemin absolu>/part_NN/AGENT_PROMPT.md`. N'écris que le fichier de notes indiqué. Réponds en 3 lignes. » ;
   - puis `PY scripts/assemble.py v2s_work/<id> --check` : une partie en échec (journal visuel incomplet, notes absentes) → relance **son** sous-agent avec la raison ;
   - puis plan → `assemble.py --plan … --out skills_out/<nom>` → fusions → `SKILL.md` du skill.
5. **Livraison** — le skill final va dans `skills_out/<nom>/` et doit passer `PY scripts/validate_skill.py skills_out/<nom>`. Ensuite seulement, demande si l'utilisateur veut l'installer dans `~/.claude/skills/<nom>/`. C'est la seule question à poser, avec celle des cookies si YouTube l'exige.
6. **Message final**, court : nom et emplacement du skill, nombre de méthodes, couverture (parties, planches regardées, passages densifiés), incertitudes principales.

## Autres demandes

- **Juste télécharger** : `PY scripts/download.py <URL> [--out downloads]` (JSON sur stdout ; en cas d'échec, lis `hint`).
- **Installer / réparer l'environnement** : [LLM_SETUP.md](LLM_SETUP.md).
- **Modifier le tool lui-même** : les scripts sont dans `scripts/`, les modèles des sous-agents dans `references/`. Après une modification, lance `PY scripts/bootstrap.py --no-skill --skip-model` (son autotest couvre extraction, découpage et validation).
