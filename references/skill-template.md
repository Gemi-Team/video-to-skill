# Modèle de skill généré

Copie ce squelette dans `<name>/SKILL.md` et adapte. Supprime les sections inutiles (ex. « Méthode » pour un pur tuto CLI).

~~~markdown
---
name: <kebab-case-court>
description: <Ce que le skill permet de faire, en une phrase.> À utiliser quand <situations / phrases déclencheuses : « … », « … »>.
---

# <Titre orienté action>

> Vérification : <N/M étapes exécutées avec succès le AAAA-MM-JJ | non vérifié par exécution> ;
> <ce qui n'a pas pu être vérifié et pourquoi>.

<1–2 phrases : ce qu'on obtient à la fin, pour qui.>

## Prérequis
- <outil> <version vue à l'écran> [t=0:42]
- <compte / accès / fichier nécessaire>

## Étapes   ← pour une procédure

### 1. <Verbe + objet>
<instruction impérative>
```bash
<commande exacte recopiée de l'écran>
```
✔ Réussite : <ce qui doit s'afficher / exister> [t=1:05]

### 2. …
⚠ incertain : <ce qui n'est pas clair et pourquoi> [t=3:12]
➕ ajouté : <étape absente de la vidéo mais nécessaire> (source : <doc officielle URL>)

## Carte des méthodes   ← pour un cours / savoir-faire (surtout vidéo longue)
| Problème / situation | Méthode | Détail |
|---|---|---|
| <ce que l'utilisateur veut faire> | <nom de la méthode> | [references/01-<theme>.md](references/01-<theme>.md) |

## Méthodes
### <Nom actionnable : verbe + objet>
- Quand l'utiliser : <situation>
- Étapes : 1. … [t=…]  2. … [t=…]
- Règles de décision : si … → … [t=…]
- Pourquoi ça marche : … [t=…]
- Exemple de la vidéo : … [t=…]
- Erreurs à éviter : … — <raison> [t=…]

## Exemple travaillé
<un exemple de la vidéo, refait pas à pas> [t=…]

## Variantes
- <cas alternatif montré ou mentionné> [t=…]

## Dépannage
- <symptôme> → <cause> → <correctif> [t=…]

## Pour aller plus loin
- [Concepts](references/concepts.md) — théorie expliquée dans la vidéo

## Source
- Vidéo : « <titre> » — <chaîne/auteur>, <date> — <URL>
- Transcription : <sous-titres manuels | auto | whisper small | aucune>
- Extrait le <AAAA-MM-JJ> avec video-to-skill
~~~

## Bons et mauvais exemples

| ❌ Narration | ✅ Instruction |
|---|---|
| « Alors là ce qu'on va faire c'est installer le truc » | « Installe le paquet : `pip install requests` [t=0:31] » |
| « Il tape un truc genre sum » (audio) | « Saisis `=SUM(B3:B10)` dans B11 [t=2:14] » (écran) |
| « Et voilà, ça marche ! » | « ✔ Réussite : le terminal affiche `200` » |
| Étape inventée pour combler | `⚠ incertain : la vidéo coupe entre [t=4:01] et [t=4:20]` |
