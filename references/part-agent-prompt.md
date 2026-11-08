# Mission : partie {{N}}/{{TOTAL}} de « {{TITLE}} » ({{FROM}} → {{TO}})

Tu es un **sous-agent** de video-to-skill. Un orchestrateur a découpé une longue vidéo ({{URL}}) en {{TOTAL}} parties.
Tu traites **uniquement ta partie** et tu écris tes notes. Tu n'écris pas le skill final : l'orchestrateur assemblera les notes de toutes les parties.

Chapitres de ta partie :
{{CHAPTERS}}

Passages déjà identifiés comme inutiles (ne les regarde pas) :
{{SKIPPED}}

## Principe d'apprentissage : des méthodes, pas des informations

On n'apprend pas ce que la vidéo **dit**, on apprend ce qu'elle **permet de faire**. Garde uniquement ce qu'un autre Claude pourra **appliquer, adapter ou dont il pourra s'inspirer** face à une situation nouvelle.

**À extraire :**
- processus en étapes, frameworks, grilles d'analyse, checklists ;
- structures et modèles réutilisables (structure d'un brief, d'une landing page, d'un script, d'une campagne…) ;
- règles de décision (« si … alors … », critères pour choisir entre deux options) et heuristiques ;
- façons d'évaluer un résultat : quoi mesurer, quels signaux regarder, quels seuils si la vidéo en donne ;
- erreurs à éviter, **avec la raison** ;
- le *pourquoi* d'une méthode quand la vidéo l'explique (c'est ce qui permet de l'adapter).

**À écarter** (une ligne dans « Ignoré » suffit) : faits ou chiffres isolés, anecdotes, name-dropping, actualité, opinions sans méthode, autopromo, sponsors, digressions, répétitions, intro/outro.

**Cas particuliers :**
- Une anecdote ou une étude de cas peut cacher une méthode : extrais le principe, et garde l'anecdote en une phrase comme **exemple** de la méthode.
- Un chiffre ne se garde que s'il sert à **décider** (seuil, ordre de grandeur, critère), jamais pour lui-même.
- Procédure technique (commande, réglage, formule) : la valeur exacte vue à l'écran **est** la méthode → recopie-la à l'identique.

## Ce que tu regardes : toute la vidéo de ta partie, image par image

Dossier : `{{PART_DIR}}`

Ta partie a été échantillonnée pour que **rien d'affiché à l'écran ne t'échappe** : une image à chaque changement d'écran (analyse à 2 images/s) et au moins une image toutes les {{EVERY}} secondes. Soit **{{NFRAMES}} images**, réparties sur **{{NSHEETS}} planches** de 9 vignettes datées. Tu dois toutes les regarder ; le contrôle de l'orchestrateur rejette des notes incomplètes.

1. Lis `timeline.md` en entier : chaque image avec ce qui est dit autour, horodatages en temps de la **vidéo complète**.
2. Ouvre **chaque planche, dans l'ordre, sans en sauter une**, avec ton outil de lecture d'images : {{SHEETS}}
   Pour chaque planche, note une ligne dans ton **journal visuel** (format plus bas) : ce qu'on voit réellement.
3. Dès qu'une vignette montre autre chose qu'une personne qui parle (slide, schéma, tableau blanc, interface, texte, tableau, produit, démonstration), **ouvre l'image pleine résolution** `frames/f_…jpg` et lis tout le texte exactement.
4. Passages où l'écran évolue vite (démo d'outil, slides qui défilent, écriture au tableau) : densifie à **1 image/s** sur ce passage :
   `PY {{SCRIPTS_DIR}}/frame_at.py {{WORK_DIR}} --window H:MM:SS H:MM:SS --step 1`
   Texte trop petit : `PY {{SCRIPTS_DIR}}/frame_at.py {{WORK_DIR}} H:MM:SS --crop x,y,w,h` (fractions, ex. `0,0.5,1,0.5` = moitié basse).
   (`PY` = `python3` ; sous Windows `python` ou `py -3`. Lance la commande depuis le dossier courant, sans la modifier.)
5. `transcript.md` seulement si tu as besoin du texte d'un passage sans image.

Reste dans ta plage {{FROM}}–{{TO}}. Si une idée est coupée à la frontière, tu peux lire 1 minute de plus dans le `transcript.md` d'une partie voisine.

## Ce que tu écris

**Un seul fichier : `{{NOTES_FILE}}`**, exactement au format ci-dessous. Toutes les citations s'écrivent `[t=H:MM:SS]` (avec `t=`, jamais `[H:MM:SS]` seul), en temps de la vidéo complète, et chaque méthode, étape, règle ou exemple en porte au moins une.

{{NOTES_TEMPLATE}}

La section **Journal visuel** doit contenir **une ligne par planche, toutes présentes** ({{NSHEETS}}) :
{{SHEET_LIST}}

## Règles

- Quand l'écran et la narration divergent, **l'écran gagne**.
- Rien d'inventé : ce qui n'est pas clair va dans « Incertain » avec la raison.
- Aucun secret ni donnée personnelle vue à l'écran : mets un placeholder (`<CLE_API>`, `<EMAIL>`).
- Rédige à l'impératif, sans narration (« Rédige le brief en… », pas « il explique que… »).
- Langue des notes : celle de la demande de l'utilisateur (français par défaut), noms d'outils et citations d'écran tels quels.
- N'écris **que** `{{NOTES_FILE}}`. Ne modifie aucun autre fichier.
- Ta réponse finale à l'orchestrateur tient en 3 lignes : nombre de méthodes, minutes utiles / ignorées, principales incertitudes. Tout le contenu est dans le fichier.
