---
description: Walk me through deploying a System One (Python, Rust, or Kotlin) from zero - quick path first, worker later.
---

Use the `setup-system-one` skill and follow its rules and steps exactly, one step at a time.

Start by asking three things in one message: the language (python / rust / kotlin), my computer
(macOS / Linux / Windows), and whether I have a spare x86 computer for a worker (yes / no /
later). Then take me down the quick path (seeded memory, no hardware) in the matching edition
(`../system-one-<lang>`, cloning the repo if it is not a sibling), and only then the full path
if I have a worker.

Show each command before running it, verify each step, explain in one plain sentence what each
step produced, and print (never run) the stick-flashing, disk-install and provisioning commands.
Never put a password in a command or a reply; I write the credentials file myself.
