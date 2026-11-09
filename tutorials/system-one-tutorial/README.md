# System One, in Maned — the speed-first edition

This folder is the project built step by step in the
[tutorial](https://maned-lang.com/tutorial.html): a decision layer that
answers a classification question in milliseconds from its own memory,
learns from an XLM-RoBERTa worker on your LAN, and runs inside your
Python, Kotlin or Rust app through the Maned bindings. Everything that
computes is a `.mnd` program; the rest is strings, files and processes.

It is the first of two editions of the same loop. This one pays for nothing
it does not need: one worker, a count judge, an answer in milliseconds when
the memory knows the text. The
[accuracy-first edition](../system_one_accurate/) pays time for quality: a
second teacher (an entailment model), a judge that generalises from what it
learned, and a learning rule that never writes a label the two teachers
dispute. Same memory format, same label registry, same request shape.

| | speed-first (this folder) | accuracy-first |
|---|---|---|
| known text | the count memory, ~8 ms | the same |
| unseen text | count judge → else the XLM-R worker's zero-shot label (~0.4 s) | one XLM-R embedding → a prototype judge over learned centroids; when unsure, the NLI worker decides (seconds) |
| learns | the XLM-R label when its margin ≥ 70 ‰ | the NLI label when the prototype judge agrees and the NLI margin ≥ 250 ‰; the rest waits for review |
| measured on 264 unseen texts, 240 learned | judge 0.39, final 0.45 | prototype judge 0.44; final 0.48 with half the texts answered without the second worker (agreement rule), or 0.52 with a quarter (learn every confident teacher label) |

## Deploy from zero

1. **A worker.** Tutorial parts 1 and 2: a spare x86 computer booted from
   the `maned-xlm` USB image, the model provisioned onto its disk. Its
   address and login go in `~/.config/maned/xlm.env` (mode 600):
   `XLM_USER`, `XLM_PASS`, `S1_WORKER_HOST`. The programs read all three
   with `env()`.
2. **Maned 0.4.2 or newer** on your PATH (`maned-run`, `maned-serve`), and
   the binding of your language at the same version: `manedpy` on PyPI,
   `dev.maned:maned` on Maven Central, the `maned` crate on crates.io.
3. Then, in this folder:

```sh
. ~/.config/maned/xlm.env
./00_download.sh                                   # tokenizer model, xlm-stats.dqt, the model as integers
maned-run 00_provision.mnd                         # once per worker
mkdir -p work/q/out work/ranges && maned-run 00_init_memory.mnd
python3 consumers/python/decide.py "Our servers crashed again, customers cannot log in." urgent later careful
python3 consumers/python/decide.py                 # the three demo questions
maned-serve 01_lookup.mnd --port 8787 &            # the fast lane as a service
```

## What is here

| file | what |
|---|---|
| `00_provision.mnd`, `00_embed_check.mnd` | stream the model to the worker; one sentence through it |
| `00_init_memory.mnd` | the empty memory (`counts [4096,32]`, `ntexts [1,32]`) and the index rows |
| `01_lookup.mnd` | the fast lane: text in, known / judge / tier out. One file for `maned-run`, `maned-serve` and the bindings |
| `02_label_embed.mnd`, `02_xlm_classify.mnd` | the slow lane on the worker: a description to a unit vector; the nearest description |
| `03_record.mnd` | the memory learns one text: `counts += bᵀ·y`, written in place |
| `05_eval.mnd` | every metric of the evaluation, the calibration table and the four PASS checks |
| `policy.csv` | per risk level: `t_auto`, `t_verify`, `t_dispute` (permille), `sharpen` |
| `corpus/` | three labels with descriptions; 108 messages, 36 variants, 36 unseen, in en/pt/de |
| `consumers/python/decide.py` | the loop's reference: `decide()`, serving and training modes, the verifier, a command line |
| `consumers/kotlin/`, `consumers/rust/` | the same loop, CLI and review workflow in Kotlin (Gradle) and Rust (Cargo) — feature-equal with the Python reference |
| `*.sh` | the shell runbook used to produce the tutorial's outputs: `_common.sh` and one driver per lane (`01_lookup.sh`, `02_xlm_classify.sh`, `03_record.sh`), the loop (`04_query.sh`), the evaluation (`05_eval.sh`), the rebuild (`06_rebuild.sh`). Optional: the page shows each step as plain commands |

Generated files live under `work/` and are never committed: the memory
(`memory.dqt`), the dataset (`memory.tsv`), the review queues
(`review.tsv`, `pending.tsv`), the label registry
(`labels.tsv`), the descriptions (`descs.tsv`, `labels_u.csv`), the
current request (`q/`), the downloads (the tokenizer model, the
statistics `xlm-stats.dqt`, the model).

## The apps

Each app is a complete System One: the lookup in-process through the
binding, `maned-run` for the worker and the record, the label registry
and the dataset line. They must run with the project folder as the
working directory (the programs name their files relative to it); the
Python and Rust ones change to it themselves, the Gradle `run` task is
configured for it.

```sh
python3 consumers/python/decide.py [--risk low|medium|high] [--train] "text" label[=description]...
python3 consumers/python/decide.py --yesno "text" "statement" ["negation"]
python3 consumers/python/decide.py --score "text" 1="..." 2="..." 3="..."
python3 consumers/python/decide.py --pending                  # answers held for review
python3 consumers/python/decide.py --resolve [accept]         # confirm them, then learn

# the Kotlin and Rust apps take the SAME arguments and flags (--risk --train --yesno --score --pending --resolve):
cd consumers/kotlin && gradle run --args='"Our servers crashed again." urgent later careful'
cd consumers/rust   && cargo run -- "Our servers crashed again." urgent later careful
cd consumers/kotlin && gradle run --args='--pending'      # or --resolve accept
cd consumers/rust   && cargo run -- --resolve             # confirm held answers interactively

# a browser UI (Decide + API tabs) — each app serves the same page, no extra dependencies:
python3 consumers/python/test_ui.py                       # -> http://127.0.0.1:8808 (S1_UI_PORT)
cd consumers/rust   && cargo run -- --serve 8808          # stdlib TcpListener
cd consumers/kotlin && gradle run --args='--serve 8808'   # JDK com.sun.net.httpserver
```

The Rust build links `libmaned_c` (set `MANED_LIB_DIR=/path/to/maned-capi/lib` if it is not
on the default search path). The Kotlin app needs `dev.maned:maned:0.4.3` from Maven Central (0.4.2 bundles an
engine that cannot load a host-side `spm()` initializer).

The binding needs the engine library at the same version as the tools;
each binding's README says where it looks for it (`MANEDPY_LIB`,
`-Dmaned.library.path`, `MANED_LIB_DIR`).

## When the memory asks the worker, and what it learns

The memory auto-answers only a text it has really seen: tier `auto` needs the best label to
cover at least 70 % of the text's features, not just a confident judge score. An unfamiliar
text the judge is merely sure about (for example "the house is on fire", which the raw judge
scores `later`) drops to tier `verify`, so the worker checks it and its label wins. This keeps
the Markov judge from confidently answering text it has never seen.

What the memory learns from the worker is gated too. In normal use a worker label is written
to memory only when the teacher is confident: the cosine margin between its best and
second-best candidate label must clear `S1_LEARN` (permille of cosine, default 70). A less
confident answer is still returned, then held in `work/pending.tsv` instead of learned, so one
shaky zero-shot guess cannot poison the memory. The default is calibrated on this corpus:
ungated, only 70 % of the worker's labels on novel text are correct; at `S1_LEARN=70` about
87 % of what the memory actually learns is correct (roughly half the worker's mistakes are held
for review instead of written in), and raising it to 80–90 lifts learned-label precision to
93–96 % while holding more for review. Lower it toward 40 to learn faster and review less.
Confirm held answers with `decide.py
--resolve` (Enter accepts the teacher's label, or type the right one; `--resolve accept` takes
them all). Training mode (`--train`, or `S1_XLM=always`) is the exception: you are deliberately
teaching, so every worker label is learned. The Kotlin and Rust apps are feature-equal with the
Python reference — the same confidence gate, verifier, training mode, `--pending`/`--resolve`
review queue and command line. Set `S1_LEARN` in `~/.config/maned/xlm.env` to tune it.

## Measured

288 requests over four passes on a 4-core AVX2 worker, training mode:
all 108 repeated texts and all 36 variants were answered from memory; on
36 unseen texts the memory auto-answered only the 2 it covered well (both
right) and sent the rest to the worker, so the system matched the XLM's
83 % while the judge never answered an unfamiliar text on its own; the
memory rebuilt from its text file byte for byte. The page has the whole
table and how to read it.
