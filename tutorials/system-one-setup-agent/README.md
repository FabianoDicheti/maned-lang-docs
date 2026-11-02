# System One — setup agent

A Claude Code assistant that deploys a **System One** (in Python, Rust, or Kotlin) on your own
machine, step by step. System One is a decision layer that answers a classification question in
milliseconds from its own memory and learns from an XLM-RoBERTa worker on your LAN.

## Use it

```sh
git clone https://github.com/FabianoDicheti/maned-lang-docs
cd maned-lang-docs/tutorials/system-one-setup-agent
claude
/setup
```

`/setup` asks which language you want and walks you through the whole deployment — the worker,
installing maned and the language binding, your credentials, the downloads, the memory, and
running the app — setting up the matching edition that lives next to this folder
(`../system-one-python`, `../system-one-rust`, or `../system-one-kotlin`).

Running `claude` in this folder loads the assistant automatically (no install step): the skill
`setup-system-one`, the `/setup` command, and a scoped `system-one-setup` subagent that is limited
to `Bash`, `Read`, `Write`, and `Edit`.

## What it will and won't do for you

- **Does:** check prerequisites, install maned and the binding, write `~/.config/maned/xlm.env`
  (mode 600), download the small assets, initialize the memory, and run the app and its browser UI.
- **Won't (prints for you to run):** flashing the worker USB stick (`dd`), installing the worker to
  its disk, and streaming the 1.85 GB model to the worker (`maned-run 00_provision.mnd`). These are
  destructive or long, so you run them yourself.
- **Never** echoes, logs, or commits your worker credentials.

## Requirements

- Claude Code.
- A **worker**: a spare 64-bit x86 machine (AVX2, 8 GB RAM, wired Ethernet) booted from the
  maned-xlm USB image — see https://maned-lang.com/bark-machines.html — or one you already run.
- **maned 0.4.2+** (the assistant installs it) and the binding for your language.

The worker is the teacher / slow lane; once the memory is seeded, the fast lane answers known text
with no worker at all.
