# Generated skill template

Copy this skeleton into `<name>/SKILL.md` and adapt it. Remove sections that do not apply (e.g. "Methods" for a pure CLI tutorial).

~~~markdown
---
name: <short-kebab-case>
description: <What the skill lets you do, in one sentence.> Use when <situations / trigger phrases: "…", "…">.
---

# <Action-oriented title>

> Verification: <N/M steps executed successfully on YYYY-MM-DD | not verified by execution>;
> <what could not be verified and why>.

<1–2 sentences: what you get at the end, for whom.>

## Prerequisites
- <tool> <version seen on screen> [t=0:42]
- <account / access / file needed>

## Steps   ← for a procedure

### 1. <Verb + object>
<imperative instruction>
```bash
<exact command copied from the screen>
```
✔ Success: <what should be displayed / exist> [t=1:05]

### 2. …
⚠ uncertain: <what is unclear and why> [t=3:12]
➕ added: <step missing from the video but needed> (source: <official docs URL>)

## Method map   ← for a course / know-how (especially long videos)
| Problem / situation | Method | Details |
|---|---|---|
| <what the user wants to do> | <method name> | [references/01-<theme>.md](references/01-<theme>.md) |

## Methods
### <Actionable name: verb + object>
- When to use it: <situation>
- Steps: 1. … [t=…]  2. … [t=…]
- Decision rules: if … → … [t=…]
- Why it works: … [t=…]
- Example from the video: … [t=…]
- Mistakes to avoid: … — <reason> [t=…]

## Worked example
<an example from the video, redone step by step> [t=…]

## Variants
- <alternative case shown or mentioned> [t=…]

## Troubleshooting
- <symptom> → <cause> → <fix> [t=…]

## Going further
- [Concepts](references/concepts.md) — theory explained in the video

## Source
- Video: "<title>" — <channel/author>, <date> — <URL>
- Transcript: <manual subtitles | auto-captions | whisper small | none>
- Extracted on <YYYY-MM-DD> with video-to-skill
~~~

## Good and bad examples

| ❌ Narration | ✅ Instruction |
|---|---|
| "So what we're gonna do now is install the thing" | "Install the package: `pip install requests` [t=0:31]" |
| "He types something like sum" (audio) | "Enter `=SUM(B3:B10)` in B11 [t=2:14]" (screen) |
| "And there you go, it works!" | "✔ Success: the terminal prints `200`" |
| Step invented to fill a gap | `⚠ uncertain: the video cuts between [t=4:01] and [t=4:20]` |
