# System One — kotlin edition

This folder is a complete System One: a decision layer that answers a classification question in
milliseconds from its own memory and learns from an XLM-RoBERTa **worker** on the LAN. Everything
that computes is a `.mnd` program; the rest is strings, files and processes.

To deploy it, run `/setup` (the `setup-system-one` skill) — it walks through the worker, maned, the
binding, credentials, the downloads, the memory, and running the app.

Key facts for working here:
- A **worker** is the teacher / slow lane. The fast lane (`01_lookup.mnd`) runs with **no worker**
  once the memory is seeded; learning or classifying novel text needs the worker.
- Requires **maned 0.4.2+** (`maned-run`, `maned-serve`) on PATH.
- Worker credentials live only in `~/.config/maned/xlm.env` (mode 600): `XLM_USER`, `XLM_PASS`,
  `S1_WORKER_HOST`. Never put them in a repo or a URL. A missing one is maned error E035.
- Binding: `dev.maned:maned:0.4.3` via `mavenLocal()` (run `./gradlew publishToMavenLocal` in the maned-kotlin repo) until it reaches Maven Central.
- Generated state lives under `work/` (gitignored): the memory, the dataset, the review queues,
  the downloads. `./06_rebuild.sh` rebuilds the memory from its text file.
- Safety: flashing the USB stick, installing the worker to disk, and provisioning the 1.85 GB model
  are run by the user, never automatically.
