---
name: setup-system-one
description: Deploy this System One (kotlin) edition from zero — provision the worker, install maned and the kotlin binding, write the credentials file, download assets, initialize the memory, and run the app. Use when the user wants to set up, deploy, or install System One or maned here.
---

# Set up System One (kotlin edition)

Guide the user through deploying this System One, one step at a time. **Read these rules first,
then work the steps in order.**

Rules:
- Do one step at a time. Show the exact command, say what it does, then run it (the user approves
  each command in their normal permission prompt) and confirm it worked before moving on.
- **Never run a destructive or hardware command yourself.** Flashing the USB stick (`dd`),
  installing the worker to its disk, and provisioning the 1.85 GB model are **printed for the user
  to run**. Explain, print, and wait.
- **Never echo, log, or commit credentials.** The worker password goes only into
  `~/.config/maned/xlm.env` at mode 600.
- This is resumable: if something is already done (maned installed, env file present, memory
  initialized), detect it and skip ahead.

## 0. What you are building
System One answers a classification question in milliseconds from its own memory, and learns from
an XLM-RoBERTa **worker** on the LAN. The worker is the teacher / slow lane: the fast lane runs
with no worker once the memory is seeded, but to learn or classify novel text you need a worker.

## 1. Preflight
```sh
uname -sm                 # macOS 11+ or Linux glibc 2.35+, on x86-64 or ARM64 (no native Windows)
git --version
gradle --version && java -version    # JDK 17+
```

## 2. The worker (bare metal)
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

> No spare x86 machine? A local `bark-vm` fallback is planned but not yet wired into this edition;
> for now this step needs a real worker (or one you already run).

## 3. Install maned (0.4.2 or newer)
```sh
curl -fsSL https://fabianodicheti.github.io/maned/install.sh | sh     # or: brew install fabianodicheti/maned/maned
maned-run --version                                                   # expect 0.4.2 or newer
```

### 4. Install the Kotlin binding

This edition needs `dev.maned:maned:0.4.3` (0.4.2 cannot load a host-side `spm()` initializer).
Until it is published to Maven Central, publish it to your local Maven repo once, from a clone of
the `maned-kotlin` binding repo:

```sh
./gradlew publishToMavenLocal
```
`consumers/kotlin/build.gradle.kts` already resolves it from `mavenLocal()`.

## 5. Credentials
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
Everything below runs after `. ~/.config/maned/xlm.env`.

## 6. Download the assets
```sh
. ~/.config/maned/xlm.env
./00_download.sh                      # tokenizer model + xlm-stats.dqt (small); sha256-verified
```
The 1.85 GB integer model is skipped by default and is only needed to provision a worker. Fetch it
only when you are about to provision:
```sh
WITH_WEIGHTS=1 ./00_download.sh       # ~1.85 GB — print this and let the user decide
```

## 7. Provision the worker, then initialize the memory
Provisioning streams the 1.85 GB model to a fresh worker (idempotent — an already-provisioned
worker writes nothing). **Print it; the user runs it** (it is a long, large transfer):
```sh
maned-run 00_provision.mnd            # once per worker; the worker verifies the sha256
```
Then create the empty memory (safe to run yourself):
```sh
mkdir -p work/q/out work/ranges
maned-run 00_init_memory.mnd
```

## 8. Run it
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
Point the user at `README.md` for the architecture, `policy.csv` for the risk tiers, and
`S1_LEARN` (default 70) for the learning gate. The browser UI from step 8 is the easiest way to
explore.
