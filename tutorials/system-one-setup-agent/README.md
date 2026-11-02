# System One — setup agent

A Claude Code assistant that puts a working **System One** on your computer and explains it to
you in plain words. System One is a decision layer: it sorts a message into labels you choose
("urgent / later / careful", yes-or-no, a score) in milliseconds from its own memory, and learns
new text from an XLM-RoBERTa worker on your LAN. Editions in Python, Rust and Kotlin.

## Use it

```sh
git clone https://github.com/FabianoDicheti/maned-lang-docs
cd maned-lang-docs/tutorials/system-one-setup-agent
claude
```
Then, inside Claude Code:

| type | what happens |
|---|---|
| `/setup` | asks three questions (language, your OS, do you have a spare computer), then walks you through it one command at a time. **Quick path first**: in about ten minutes you have a System One answering from a seeded memory, no hardware. **Full path** after that, if you have a worker: credentials, provisioning, and it learns anything you ask. |
| `/explain` | the plain-words tour: what it is, the words (worker, teacher, memory, tier...), what happens when you ask it something, how it learns, things to try, a short quiz. `/explain known` explains one word; `/explain` alone asks what you want. |
| "what is my status?" | the read-only `system-one-doctor` check-up: what is installed, what is missing, and which step to resume. |

Claude Code asks before every command it runs. Press Enter to allow, Esc to stop. Nothing runs
without your yes. The assistant loads automatically when `claude` starts in this folder: the two
skills (`setup-system-one`, `learn-system-one`), the two commands, and the doctor subagent.

## What you need

- **Claude Code** and a Claude account. Install: https://claude.com/claude-code
- **macOS 11+ or Linux** (glibc 2.35+: Ubuntu 22.04, Debian 12, Fedora 36 or newer). Windows
  only through WSL.
- About 10 minutes and 50 MB for the quick path.
- For the full path, a **worker**: a spare 64-bit x86 computer (AVX2, 8 GB RAM, a disk with 2 GB
  free that may be erased, **wired Ethernet**), a USB stick of 2 GB or more, and about an hour.
  See https://maned-lang.com/bark-machines.html

The assistant installs **maned 0.4.2+** and the binding for your language.

## The languages today

| edition | status |
|---|---|
| Python | complete. A virtual environment in the edition folder; the wheel bundles the engine. |
| Rust | complete. The assistant fetches the `maned-capi` tarball the `maned` crate links against. |
| Kotlin | complete with `dev.maned:maned:0.4.3` (its jar carries the engine library; the build picks the one for your OS and CPU). Needs JDK 17+ and Gradle 8+. |

## What it will and won't do for you

- **Does:** check prerequisites and tell you how to install what is missing; install maned and
  the binding; download the small assets (sha256-checked); initialize and seed the memory; run
  the demo and the browser UI; check that the worker answers; verify the credentials file
  without reading its values; provision-check the worker; teach it a first text.
- **Won't (prints for you to run):** writing the USB stick (`dd`), installing the worker to its
  disk, streaming the 1.85 GB model to the worker. Destructive or long: you run them.
- **Never** puts a password in a command, a file it shows, or a reply. You write
  `~/.config/maned/xlm.env` (mode 600) in your own editor.

## Files

```
.claude/skills/setup-system-one/SKILL.md   the runbook: 11 steps, who runs what, a failure table
.claude/skills/learn-system-one/SKILL.md   the tour: words, what happens, how it learns, try this
.claude/commands/setup.md                  /setup
.claude/commands/explain.md                /explain
.claude/agents/system-one-doctor.md        the read-only check-up
seed/                                      a memory of 147 taught texts (54 KB) for the quick path; see seed/README.md
```

The editions live next to this folder: `../system-one-python`, `../system-one-rust`,
`../system-one-kotlin`. Each is the complete project of the tutorial at
https://maned-lang.com/tutorial.html; the worker is the teacher / slow lane, and once the memory
holds a text the fast lane answers it with no worker at all.
