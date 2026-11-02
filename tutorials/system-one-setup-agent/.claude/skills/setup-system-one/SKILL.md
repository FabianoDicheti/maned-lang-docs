---
name: setup-system-one
description: Deploy a System One from zero in the user's chosen language (Python, Rust, or Kotlin) — provision the worker, install maned and the binding, write the credentials file, download assets, initialize the memory, and run the app. Use when the user wants to set up, deploy, or install System One or maned.
---

# Set up System One (any language)

Guide the user through deploying a System One, one step at a time. **Read these rules first, then
work the steps in order.**

Rules:
- Do one step at a time. Show the exact command, say what it does, then run it (the user approves
  each command in their normal permission prompt) and confirm it worked before moving on.
- **Never run a destructive or hardware command yourself.** Flashing the USB stick (`dd`),
  installing the worker to its disk, and provisioning the 1.85 GB model are **printed for the user
  to run**. Explain, print, wait.
- **Never echo, log, or commit credentials.** The worker password goes only into
  `~/.config/maned/xlm.env` at mode 600.
- This is resumable: if something is already done (edition cloned, maned installed, env file
  present, memory initialized), detect it and skip ahead.

## 0. What you are building
System One answers a classification question in milliseconds from its own memory, and learns from
an XLM-RoBERTa **worker** on the LAN. The worker is the teacher / slow lane: the fast lane runs
with no worker once the memory is seeded, but to learn or classify novel text you need a worker.

## 1. Choose the language and locate the edition
Ask the user which language they want: **python**, **rust**, or **kotlin**. Each lives in its own
edition folder next to this one in the repo.

- If this folder was cloned as part of the whole `maned-lang-docs` repo, the edition is a sibling:
  `../system-one-<lang>` (e.g. `../system-one-python`). Check with `ls ..`.
- Otherwise, clone it:
  ```sh
  git clone https://github.com/FabianoDicheti/maned-lang-docs
  cd maned-lang-docs/tutorials/system-one-<lang>
  ```

**All remaining steps run with the edition folder as the working directory.** `cd` into
`../system-one-<lang>` (or the clone) now and stay there; the `.mnd` programs name their files
relative to it.

## 2. Preflight
```sh
uname -sm                 # macOS 11+ or Linux glibc 2.35+, on x86-64 or ARM64 (no native Windows)
git --version
# then the chosen language's toolchain:
#   python:  python3 --version        # 3.9+
#   rust:    cargo --version
#   kotlin:  gradle --version && java -version    # JDK 17+
```

## 3. The worker (bare metal)
A dedicated 64-bit x86 machine booted from the maned-xlm USB image serves embeddings over HTTP on
port 4780. Needs AVX2 (≈10× faster), **8 GB RAM**, a SATA/NVMe disk with ~2 GB free, **wired
Ethernet** (Wi-Fi never works), Secure Boot off, a keyboard attached before power-on.

Walk the user through it — **print these, do not run them**:
```sh
# on your own computer: fetch and verify the image
curl -fLO https://github.com/FabianoDicheti/maned/releases/latest/download/bark-usb.img
curl -fLO https://github.com/FabianoDicheti/maned/releases/latest/download/SHA256SUMS
shasum -a 256 -c SHA256SUMS            # must say: bark-usb.img: OK

# write the stick (REPLACE /dev/diskN — this ERASES it; the user runs this, not you)
#   macOS:  sudo dd if=bark-usb.img of=/dev/rdiskN bs=4m    (diskutil list to find N, then unmount)
#   Linux:  sudo dd if=bark-usb.img of=/dev/sdX  bs=4M status=progress && sync
```
Then: boot the machine from the stick (one-time boot menu — F12/F8/F11/Esc/Option), read the node
screen for its DHCP IP, and note it shows `NOT READY: weights` until provisioned. Full guide:
https://maned-lang.com/bark-machines.html . The default stick identity is user `worker` /
password `12345` — tell the user to change it (screen key `P`) before leaving it running.
Provisioning happens in step 7.

> No spare x86 machine? A local `bark-vm` fallback is planned but not yet wired in; for now this
> step needs a real worker (or one you already run).

## 4. Install maned (0.4.2 or newer)
```sh
curl -fsSL https://fabianodicheti.github.io/maned/install.sh | sh     # or: brew install fabianodicheti/maned/maned
maned-run --version                                                   # expect 0.4.2 or newer
```

## 5. Install the language binding
Use the block for the chosen language.

**python**
```sh
pip install manedpy            # the same 0.4.x line as the tools
python3 -c "import manedpy; print('manedpy ok')"
```
The binding finds the engine library through `MANEDPY_LIB`; point it at your maned capi
`lib/libmaned_c.*` if it is not found automatically.

**rust**
```sh
cd consumers/rust
MANED_LIB_DIR=/path/to/maned-capi/lib cargo build     # the `maned` crate is already in Cargo.toml
cd ../..
```
At run time keep that directory on `DYLD_LIBRARY_PATH` (macOS) or `LD_LIBRARY_PATH` (Linux).

**kotlin**
```sh
# this edition needs dev.maned:maned:0.4.3 (0.4.2 cannot load a host-side spm() initializer).
# until it is on Maven Central, publish it once from a clone of the maned-kotlin binding repo:
./gradlew publishToMavenLocal
```
`consumers/kotlin/build.gradle.kts` already resolves it from `mavenLocal()`.

## 6. Credentials
Ask the user for the worker host (its LAN IP) and the login, then write them to a mode-600 file —
**do not print the password back**:
```sh
mkdir -p ~/.config/maned
umask 177
cat > ~/.config/maned/xlm.env <<'ENV'
XLM_USER=worker
XLM_PASS=CHANGE_ME
S1_WORKER_HOST=192.0.2.10
ENV
chmod 600 ~/.config/maned/xlm.env
```
Replace the values with the user's own (prompt for them; a missing one is maned error E035).
Everything below runs after `. ~/.config/maned/xlm.env`, from the edition folder.

## 7. Download assets, provision, initialize
```sh
. ~/.config/maned/xlm.env
./00_download.sh                      # tokenizer model + xlm-stats.dqt (small); sha256-verified
```
The 1.85 GB integer model is skipped by default and is only needed to provision a worker — fetch
it only when about to provision, and **print** the provision command for the user to run:
```sh
WITH_WEIGHTS=1 ./00_download.sh       # ~1.85 GB
maned-run 00_provision.mnd            # once per worker; the worker verifies the sha256 (user runs this)
```
Then create the empty memory (safe to run yourself):
```sh
mkdir -p work/q/out work/ranges
maned-run 00_init_memory.mnd
```

## 8. Run it
Use the block for the chosen language.

**python**
```sh
python3 consumers/python/decide.py "Our servers crashed again, customers cannot log in." urgent later careful
python3 consumers/python/decide.py            # the three demo questions (choice / yes-no / score)
python3 consumers/python/test_ui.py           # the browser UI -> http://127.0.0.1:8808 (S1_UI_PORT)
```

**rust**
```sh
cd consumers/rust
cargo run -- "Our servers crashed again, customers cannot log in." urgent later careful
cargo run                                     # the three demo questions
cargo run -- --serve 8808                     # the browser UI -> http://127.0.0.1:8808
cd ../..
```

**kotlin**
```sh
cd consumers/kotlin
gradle run --args='"Our servers crashed again, customers cannot log in." urgent later careful'
gradle run                                    # the three demo questions
gradle run --args='--serve 8808'              # the browser UI -> http://127.0.0.1:8808
cd ../..
```
A novel text escalates to the worker and is learned; ask the same text again and it comes back
`memory:known` in milliseconds.

## 9. Verify
```sh
. ~/.config/maned/xlm.env
./05_eval.sh                          # optional: the four PASS checks over 288 requests (~4 min)
```

## Done
Point the user at the edition's `README.md` for the architecture, `policy.csv` for the risk tiers,
and `S1_LEARN` (default 70) for the learning gate. The browser UI from step 8 is the easiest way
to explore.
