---
name: setup-system-one
description: Deploy a System One from zero in the user's chosen language (Python, Rust, or Kotlin). Two paths - the quick path (a seeded memory, no hardware, about ten minutes) and the full path (an XLM-RoBERTa worker on the LAN, credentials, provisioning). Use when the user wants to set up, deploy, install, run, or try System One or maned.
---

# Set up System One

You are walking a person who may never have opened a terminal through a working System One.
Read the rules, then work the steps in order. Every command block says who runs it: **you**
(after the person approves it) or **the person** (you print it and wait).

## Rules

- **One step at a time.** Show the exact command, say in one plain sentence what it does, run it,
  read the output, and say whether it worked before moving on. After a step that produces
  something, add one sentence on what the person just got. A kid should be able to follow.
- Say this once at the start: *"Claude Code asks before each command. Press Enter to allow it,
  or Esc to stop. Nothing runs without your yes."*
- **Never run a destructive or hardware command yourself.** Flashing the USB stick (`dd`),
  installing the worker to its disk, and streaming the 1.85 GB model (`00_provision.mnd`) are
  **printed for the person to run**. Explain, print, wait.
- **Never put a password in a command, a file you show, or a reply.** The person writes the
  credentials file in their own editor (step 8). You only check that it exists and is complete.
- **Shell state does not survive between your commands.** Begin every command with
  `cd <edition folder>` and, when the worker is involved, `. ~/.config/maned/xlm.env`.
- **Resumable.** Before each step, check whether it is already done (edition present, maned
  installed, binding importable, memory present, env file present, worker reachable) and skip
  it. Say what you skipped.
- **When a command fails,** quote the error, find it in the table at the end, fix the cause, then
  retry. Never retry the same command unchanged.
- Keep replies short: one command block per reply, no walls of text.
- If the person asks *why* or *what is a ...*, answer in two plain sentences, then continue. For
  a longer explanation point them to `/explain`.

## 0. What you are building

System One answers a classification question ("is this message urgent, can it wait, or does it
need care?") in milliseconds from its own **memory**, and learns from an XLM-RoBERTa **worker**
(the teacher) on the LAN. Two paths:

- **Quick path** (steps 1-6, about ten minutes, no hardware): a memory already seeded with 147
  texts, the demo, a browser UI. It answers text it knows; new text needs a teacher.
- **Full path** (steps 7-11): a spare x86 computer becomes the worker, and the system learns
  anything you ask it.

Start everyone on the quick path, even people who own a worker: it proves the install before
the hardware gets involved.

## 1. Three questions (one message)

Ask, in one message:
1. **Language**: python, rust, or kotlin. If they do not know: python.
2. **Computer**: macOS, Linux, or Windows.
3. **A worker?** "Do you have a spare 64-bit x86 computer with a wired Ethernet port you can
   erase?" Yes, no, or later.

Then apply:
- **Windows**: native Windows is not supported. It works inside **WSL** (Ubuntu 22.04 or newer);
  everything below then runs in the WSL terminal as Linux. If they do not have WSL, stop here and
  point them at Microsoft's WSL install page.
- **kotlin**: this edition needs `dev.maned:maned:0.4.3` (released 2026-11-02) and Gradle 8+. Check
  `which gradle`; the build in step 5 resolves the artifact from Maven Central (or from `~/.m2`
  if it was published locally). If the build cannot find 0.4.3, say so plainly and offer
  python (same project, same programs, same browser UI).
- **No worker**: quick path now; the full path can come any time later.

## 2. The edition folder

The three editions sit next to this folder in the `maned-lang-docs` repo:
`../system-one-python`, `../system-one-rust`, `../system-one-kotlin`.

**you**
```sh
ls .. | grep system-one
```
If the edition is missing (this folder was copied on its own), clone the repo and use the
edition inside it:
```sh
git clone https://github.com/FabianoDicheti/maned-lang-docs
```
From here on **every command starts with `cd` into the edition folder** (give the absolute
path). The `.mnd` programs name their files relative to it; running them elsewhere fails with
"cannot open work/...".

## 3. Preflight

**you**
```sh
uname -sm; git --version
```
Then the toolchain for the chosen language:
```sh
python3 --version            # python: 3.9 or newer
cargo --version              # rust
java -version; gradle --version | head -3     # kotlin: JDK 17+, Gradle 8+
```

If something is missing, install it this way (and nothing else):

| missing | macOS | Linux (Debian/Ubuntu) |
|---|---|---|
| `git` | `xcode-select --install` (a dialog opens; wait for it) | `sudo apt install git` |
| `python3` | `brew install python` (or python.org installer) | `sudo apt install python3 python3-venv python3-pip` |
| `cargo` | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh`, then open a new terminal | same |
| `java` 17+ | `brew install openjdk@21` and follow brew's PATH note | `sudo apt install openjdk-21-jdk` |
| `gradle` | `brew install gradle` | SDKMAN: `curl -s https://get.sdkman.io \| bash`, new terminal, `sdk install gradle` (apt's gradle is too old) |
| `brew` itself | https://brew.sh (one command, shown there) | - |

`curl` is present on every supported system.

## 4. Install maned (0.4.2 or newer)

**you**
```sh
curl -fsSL https://fabianodicheti.github.io/maned/install.sh | sh
maned-run --version          # expect 0.4.2 or newer
```
Homebrew users may prefer `brew install fabianodicheti/maned/maned`. If `maned-run` is "command
not found" afterwards, the installer printed the folder it used; add it to the PATH
(`export PATH="$HOME/.local/bin:$PATH"` in `~/.zshrc` or `~/.bashrc`), open a new terminal, and
check again.

## 5. The language binding

**python** - use a virtual environment inside the edition folder; it avoids the
"externally-managed-environment" refusal of system pythons and keeps everything in one place.
The wheel bundles the engine library; no extra download.

**you**
```sh
python3 -m venv .venv && .venv/bin/pip install -q manedpy && .venv/bin/python -c "import manedpy; print('manedpy ok')"
```
From now on run python as `.venv/bin/python` (tell the person: "the dot-venv folder is the
project's own Python; nothing else on the computer changed").

**rust** - the `maned` crate links the engine library `libmaned_c`, which neither the installer
nor Homebrew provides. Fetch the capi tarball at the **same version as the tools**, unpack it
under `work/` (ignored by git), and record the paths in `work/rust.env`:

**you**
```sh
V=$(maned-run --version | awk 'NR==1{print $2}')
case "$(uname -sm)" in
  Darwin*)        T=universal-apple-darwin ;;
  "Linux x86_64") T=x86_64-unknown-linux-gnu ;;
  "Linux aarch64") T=aarch64-unknown-linux-gnu ;;
esac
mkdir -p work && cd work && curl -fsSLO "https://github.com/FabianoDicheti/maned/releases/download/v$V/maned-capi-$V-$T.tar.gz" && tar xzf "maned-capi-$V-$T.tar.gz" && cd ..
L="$PWD/work/maned-capi-$V-$T/lib"
printf 'export MANED_LIB_DIR=%s\nexport DYLD_LIBRARY_PATH=%s\nexport LD_LIBRARY_PATH=%s\n' "$L" "$L" "$L" > work/rust.env
. work/rust.env && (cd consumers/rust && cargo build 2>&1 | tail -2)
```
Every later Rust command starts with `. work/rust.env` (build and run both need it).

**kotlin** - the build file picks the jar with the engine library for this OS and CPU itself, so
there is nothing to download or edit:

**you**
```sh
cd consumers/kotlin && gradle build -q 2>&1 | tail -3
```

## 6. Quick path: the first answers (no worker)

**you** - the small downloads (the tokenizer model, 5 MB, and the centering statistics, 153 KB),
each checked against its published sha256:
```sh
./00_download.sh
```
**you** - the empty memory and its index rows, then the seed (147 texts the worker already
taught: the tutorial corpus in English, Portuguese and German, plus the three demo questions):
```sh
mkdir -p work/q/out work/ranges && maned-run 00_init_memory.mnd > work/00_init_memory.log && for f in memory.dqt memory.tsv labels.tsv descs.tsv labels_u.csv; do cp ../system-one-setup-agent/seed/$f work/; done && wc -l work/memory.tsv
```
(If the setup-agent folder is elsewhere, adjust the `seed/` path. If the person wants an
**empty** memory to teach from scratch, skip the `cp` and go to the full path.)

**you** - the three demo questions (a choice, a yes/no, a score), then one text of your own:

python
```sh
.venv/bin/python consumers/python/decide.py
.venv/bin/python consumers/python/decide.py "Attention: the production server is down and customers cannot log in, please restart it now." urgent later careful
```
rust
```sh
. work/rust.env && cd consumers/rust && cargo run -q && cargo run -q -- "Attention: the production server is down and customers cannot log in, please restart it now." urgent later careful
```
kotlin
```sh
cd consumers/kotlin && gradle run -q && gradle run -q --args='"Attention: the production server is down and customers cannot log in, please restart it now." urgent later careful'
```
Expected: three lines ending in `via memory:known` with times of a few milliseconds, then
`ANSWER  urgent  via memory:known`. Explain: *"known" means the memory has seen this exact text;
it answered without any model or network.* Good texts to try next (all seeded):
- `Our monthly newsletter is out, with team photos from the summer picnic.` -> later
- `Please review the attached contract amendment, clause 7 changes the liability cap.` -> careful
- `Atenção: o servidor de produção caiu e os clientes não conseguem entrar, reinicie agora.` -> urgent

A text the memory has **not** seen stops with
`02_xlm_classify.mnd failed: error: device::worker has no host field` - that is the system asking
for its teacher, which the full path provides. Say so before the person tries one.

**you** - the browser UI (same decide function, a form, the transcript):
```sh
.venv/bin/python test_ui.py                     # python  -> http://127.0.0.1:8808
. work/rust.env && cd consumers/rust && cargo run -q -- --serve 8808      # rust
cd consumers/kotlin && gradle run -q --args='--serve 8808'                 # kotlin
```
Run it in the background (`run_in_background`) or tell the person to open a second terminal;
then tell them to open http://127.0.0.1:8808 and paste one of the seeded texts. Port busy:
`S1_UI_PORT=8809` (python) or `--serve 8809`.

**Quick path done.** Say what they have: a System One that answers from memory, and what is
missing: a teacher for new text. If they have no worker, end here and point at `/explain`.

## 7. The worker (full path, the person runs the hardware steps)

A spare **64-bit x86** computer booted from the `maned-xlm` USB image. Needs: AVX2 (any CPU from
about 2013 on; about 10x faster), **8 GB RAM**, a SATA or NVMe disk with 2 GB free that may be
erased, **wired Ethernet** (Wi-Fi never works), Secure Boot off, a keyboard plugged in before
power-on.

**the person** - on their own computer, in a folder of their choice:
```sh
curl -fLO https://github.com/FabianoDicheti/maned/releases/latest/download/maned-xlm-usb.img
curl -fLO https://github.com/FabianoDicheti/maned/releases/latest/download/SHA256SUMS
grep ' maned-xlm-usb.img$' SHA256SUMS | shasum -a 256 -c      # must print: maned-xlm-usb.img: OK
```
(The plain `bark-usb.img` on the same page is a different product; it cannot run this tutorial.)

**the person** - write the stick. This erases the stick; the wrong device letter erases a disk.
```sh
# macOS: find the stick, unmount it, write it
diskutil list                                   # the stick is the small "external, physical" disk, e.g. /dev/disk4
diskutil unmountDisk /dev/diskN
sudo dd if=maned-xlm-usb.img of=/dev/rdiskN bs=4m
# Linux:
lsblk                                           # the stick, e.g. /dev/sdb (NOT the disk with /)
sudo dd if=maned-xlm-usb.img of=/dev/sdX bs=4M conv=fsync status=progress
```
Then, on the spare computer: plug the stick and the Ethernet cable, power on, open the one-time
boot menu (F12, F8, F11, Esc, or Del on PCs; hold Option on an Intel Mac), choose the USB
device. The screen shows the worker's name, its **IP address** (write it down), and
`NOT READY: weights`. That last line is correct: the model is not on it yet.

The stick identity is user `worker`, password `12345`. Tell the person to change it with the
`P` key on the worker's screen before leaving it running, and to install to the disk with `I`
so the model and the password survive a reboot. Full guide, with a troubleshooting table:
https://maned-lang.com/bark-machines.html

Common failures to mention before they boot:
- no boot menu or the stick is ignored -> Secure Boot is on, or the BIOS is set to UEFI-only
  with CSM off; turn Secure Boot off, enable legacy/CSM boot.
- no IP on the screen -> the cable is not in, or the router gives no DHCP; wait 30 s, replug.
- `[P]` shows `locked` -> three wrong passwords; wait 60 s.

**you** - once they have the IP, check it answers (no login needed for status):
```sh
curl -s --max-time 5 http://WORKER_IP:4780/api/status; echo
```

## 8. Credentials (the person writes the file)

**you** - create the file with placeholders, mode 600:
```sh
mkdir -p ~/.config/maned && [ -f ~/.config/maned/xlm.env ] || printf 'XLM_USER=worker\nXLM_PASS=CHANGE_ME\nS1_WORKER_HOST=192.168.1.50\n' > ~/.config/maned/xlm.env; chmod 600 ~/.config/maned/xlm.env; echo written
```
**the person** - edit it: `nano ~/.config/maned/xlm.env` (change the three values, Ctrl+O, Enter,
Ctrl+X), or on macOS `open -e ~/.config/maned/xlm.env`. `S1_WORKER_HOST` is the IP from the
screen; the user and password are the ones on the worker now.

**you** - verify without printing any value:
```sh
. ~/.config/maned/xlm.env; for v in XLM_USER XLM_PASS S1_WORKER_HOST; do eval "x=\$$v"; { [ -n "$x" ] && [ "$x" != CHANGE_ME ]; } && echo "$v: set" || echo "$v: MISSING"; done; ls -l ~/.config/maned/xlm.env | cut -c1-10
```
Expect three `set` lines and `-rw-------`.

## 9. Provision the worker and check it

**you** - the model as exact integers, 1.85 GB, sha256-checked (several minutes; tell them):
```sh
WITH_WEIGHTS=1 ./00_download.sh
```
**the person** - stream it to the worker (once per worker, about 15 minutes; the worker checks
the sha256 itself and reboots `READY`):
```sh
cd <edition folder> && . ~/.config/maned/xlm.env && maned-run 00_provision.mnd
```
**you** - one sentence through the model; the log ends with the model name and the time:
```sh
. ~/.config/maned/xlm.env && maned-run 00_embed_check.mnd > work/00_embed_check.log 2>&1 && tail -3 work/00_embed_check.log
```

## 10. Teach it something

**you** - a text the memory has never seen (same commands as step 6, your own sentence):
```sh
. ~/.config/maned/xlm.env && .venv/bin/python consumers/python/decide.py "The building alarm is going off and smoke is coming from the server room." urgent later careful
```
Expected: `xlm  urgent  <N> ms` in the transcript, `via xlm` or `via memory:verified` (the memory
guessed, the worker confirmed), and `(recorded as urgent)`, in a few hundred ms. Run the **same**
text again: `via memory:known`, a few ms. Explain: *the worker answered once and the memory wrote
it down; from now on this text needs no worker.* If the line says `HELD ... not learned`, the teacher was
not sure enough (the gate `S1_LEARN`, default 70); `--pending` lists those and
`--resolve` confirms them. Rust and Kotlin take the same arguments after `--` / `--args=`.

## 11. Verify (optional, full path only)

`./05_eval.sh` runs 288 requests (about 4 minutes) and prints four PASS checks. **It erases the
memory first** (that is how it measures a cold start). Offer it only if the person wants the
numbers, and back the memory up first:
```sh
. ~/.config/maned/xlm.env && mkdir -p work/backup && cp work/memory.* work/labels.tsv work/descs.tsv work/labels_u.csv work/backup/ && ./05_eval.sh
```
Afterwards `cp work/backup/* work/` restores the seeded memory.

## Done

Tell the person what they have, in three lines. Point them at the edition's `README.md` for the
architecture, `policy.csv` for the risk tiers, `S1_LEARN` for the learning gate, and `/explain`
for a plain-words tour. The browser UI from step 6 is the easiest way to keep exploring.

## When something fails

| you see | cause | do |
|---|---|---|
| `maned-run: command not found` | install folder not on PATH | step 4's PATH note, new terminal |
| `error: maned-run not found on PATH (install Maned 0.4.2 ...)` | same, from a `.sh` step | same |
| `ModuleNotFoundError: No module named 'manedpy'` | wrong python | use `.venv/bin/python` |
| `externally-managed-environment` | pip into the system python | use the venv of step 5 |
| `cannot open 'work/q/req.csv'` or `work/...` | wrong folder, or an edition from before 2026-11-02 | `cd` into the edition; or `git pull` (the consumers now create the two request files) |
| `device::worker has no host field` | credentials not loaded in this command | prefix `. ~/.config/maned/xlm.env` (quick path: expected for unseen text) |
| `E035 ... model not ready` | worker not provisioned yet | step 9 |
| `E035 ... HTTP 401` or auth refused | user/password differ from the worker's | fix the env file; `[P]` on the worker shows the user |
| `E035 ... transport` / connection refused | wrong IP, cable, or worker off | the `curl .../api/status` check of step 7 |
| ten `No such file` lines from `shasum -c` | checked the whole SHA256SUMS | the `grep ... \| shasum` line of step 7 |
| `NOT READY: weights` on the worker | expected before provisioning | step 9 |
| `dyld: Library not loaded ... libmaned_c` / `error while loading shared libraries` | rust loader path | prefix `. work/rust.env` |
| cargo: `libmaned_c` not found, paths tried ... | capi tarball missing | step 5 rust |
| gradle: `Could not find dev.maned:maned:0.4.3` | no network, or a Central sync still pending | retry later; step 1's kotlin note; offer python |
| `Address already in use` on 8808 | another UI running | `S1_UI_PORT=8809` or `--serve 8809` |
| `HELD low teacher confidence` | not an error | `--pending`, `--resolve` |
