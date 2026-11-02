---
name: making-demo-videos
description: Use when the owner asks for a demo, walkthrough, screencast or narrated video of the CheekyMarine plotter, whether of one PR's changes, a PR with surrounding context, or the whole app
---

# Making Demo Videos

## Overview

A demo is a recording of the live plotter (n2kd replaying the Everett log, real chart packs) driven
by xdotool, with a voice-over in the owner's chosen voice (edge-tts `en-US-AndrewNeural`, +0%)
laid on the exact time each step ran. `engine.py` does launch, input, capture, narration, sync and
checks; your job is the scope and the step script.

## Scope

Ask which scope if the request doesn't say. Then build the step list from:

| Scope | Steps |
|---|---|
| **PR** | Each user-visible change in the PR, nothing else. Source: `gh pr view N`, its plan or ledger, `gh pr diff N` (works after merge). One intro line on what the PR is. |
| **PR + context** | The PR steps, each preceded by the minimum existing screens a viewer needs to reach and understand it (where the feature lives, what it replaced). Say which parts are new. |
| **Whole app** | Tour every page and sheet; `example-saved-views.py` is the model (3:56). |

Changes with nothing to see (schema, CI, removals) get one spoken sentence, not a step.

## Workflow

1. **Worktree at the commit to demo** (a merged PR: its merge commit). Reuse
   `.claude/worktrees/demo` only if `git -C` it shows that commit; otherwise
   `git worktree add --detach .claude/worktrees/demo-<slug> <sha>`. Never another session's
   worktree or build dir. Build `build/` (n2kd) and `build-plotter/` there per `plotter/README.md`.
2. **Script** in the main checkout: `mkdir -p .superpowers/demo`, then
   `.superpowers/demo/<date>-<slug>.py` (gitignored) in the shape of `example-saved-views.py`:
   `TITLE = "<date>-<slug>"` (the MP4 name: unique, or it overwrites), `LAUNCH_ARGS`,
   `STEPS = [(narration, lambda: ...)]`, optional `AFTER_RESTART`. Coordinates: `screens.md`.
   Unknown screen: `engine.py SCRIPT open --root WORKTREE` prints the app PID; poke with
   `CM_DEMO_PID=<pid> bash x.sh tap|hold|drag|shot`, then `close`.
3. **Run** from this skill's folder with absolute paths: `P=~/.cache/cheekymarine/demo-venv/bin/python`
   (missing: `python3 -m venv` it, `pip install edge-tts`), `$P engine.py SCRIPT MODE --root WORKTREE`.
   `tts` (length), then `rehearse` and Read `sheet.png`; fix and rehearse until every frame shows
   what its line says. Check the exit status every time (never pipe through `tail`/`grep` without
   `set -o pipefail`): a failed run deletes the sheet rather than leaving an old one to misread. Then `record`, then `check` and Read `check.png`. Narration-only edits: `mux`.
4. **Hand over** the MP4 path (`C:\Users\jjvel\Videos\CheekyMarine\<TITLE>.mp4`), length, the
   commit, what was left out and why. You can't hear it: say the voice is unchecked.

## Narration

Short spoken sentences, viewer is "you". Spell what must be spelled: "A I S", "S O G". `[[0.5]]`
pauses around a key point. No em dash (the engine refuses one). A step lasts the longer of its
line and its action, so long actions (typing) can run past their line.

## Rules

- One demo on the display at a time: there is one pointer, so two runs drive each other's
  windows. The engine takes a machine-wide lock and refuses while any CheekyMarine window is
  visible. If refused, wait (a background `until` loop on `xdotool search --onlyvisible --name
  '^CheekyMarine$'`); never close another session's app.
- Other sessions run the same binaries at the same window size. The engine and `x.sh` act only
  on the app this run started (by PID, on its own socket, checked to be on top under the
  pointer before each input); never `pkill`/`killall` by name, never target a window by name.
- WSLg display with `QT_QPA_PLATFORM=xcb` (the engine sets it). Offscreen crashes; GL is needed.
- Never record before a clean rehearsal sheet.
- x11grab may print `Cannot get the image data`: harmless when the frame is written.

## Common mistakes

| Mistake | Result | Fix |
|---|---|---|
| Tapping a tab after 8 s on a view | Lands on the map; next hold opens a slot sheet | Tap `MAP` first to wake the bar |
| Tapping the map to close the legend | Legend stays over every later step | Close 1117,45 |
| Reusing coordinates after the screen changed | Taps hit the wrong control | Sheets dock top for low slots; editor buttons move with the bottom banner; Home tiles shift per view: `screens.md` |
| Socket in the scratchpad | `socket path too long` | Engine uses `/run/user/<uid>/` |
| Frame-count timestamps, clock started at ffmpeg launch | Voice drifts seconds off the picture | Engine stamps wall clock and times from the first frame |
| espeak or another voice | Not the owner's voice | edge-tts Andrew only |
| `xdotool windowmove` to separate two apps | Under WSLg the moved window still draws, but clicks stop reaching it | Never move windows; one demo at a time (lock + refusal) |
