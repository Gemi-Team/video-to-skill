---
description: Turn a video (YouTube URL or file) into a Claude skill — setup, frame-by-frame extraction, sub-agents, assembly, all automatic.
argument-hint: <video URL or path> [instructions, e.g. "only 12:00–25:00"]
---
Video and instructions: $ARGUMENTS

Follow the "When the user gives a video" section of CLAUDE.md end to end, without asking the user to run anything.
If no video is given, only ask for the URL or the file path.
