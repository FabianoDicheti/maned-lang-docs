# System One, in Maned — the complete project

This folder is the project built step by step in the
[tutorial](https://maned-lang.com/tutorial.html): a decision layer that
answers a classification question in milliseconds from its own memory,
learns from an XLM-RoBERTa worker on your LAN, and runs inside your
Rust app through the Maned crate. Everything that
computes is a `.mnd` program; the rest is strings, files and processes.

## Deploy from zero

1. **A worker.** Tutorial parts 1 and 2: a spare x86 computer booted from
   the `maned-xlm` USB image, the model provisioned onto its disk. Its
   address and login go in `~/.config/maned/xlm.env` (mode 600):
   `XLM_USER`, `XLM_PASS`, `S1_WORKER_HOST`. The programs read all three
   with `env()`.
2. **Maned 0.4.2 or newer** on your PATH (`maned-run`, `maned-serve`), and
   the Rust binding at the same version: the `maned` crate on crates.io.
3. Then, in this folder:

```sh
. ~/.config/maned/xlm.env
./00_download.sh                                   # tokenizer model, xlm-stats.dqt, the model as integers
maned-run 00_provision.mnd                         # once per worker
mkdir -p work/q/out work/ranges && maned-run 00_init_memory.mnd
cd consumers/rust && cargo run -- "Our servers crashed again, customers cannot log in." urgent later careful
cd consumers/rust && cargo run                     # the three demo questions
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
| `consumers/rust/` | the loop in Rust (Cargo): `decide()`, training mode, the verifier, the `--pending`/`--resolve` review queue, a CLI, and a `--serve` browser UI |
| `*.sh` | the shell runbook used to produce the tutorial's outputs: `_common.sh` and one driver per lane (`01_lookup.sh`, `02_xlm_classify.sh`, `03_record.sh`), the loop (`04_query.sh`), the evaluation (`05_eval.sh`), the rebuild (`06_rebuild.sh`). Optional: the page shows each step as plain commands |

Generated files live under `work/` and are never committed: the memory
(`memory.dqt`), the dataset (`memory.tsv`), the review queues
(`review.tsv`, `pending.tsv`), the label registry
(`labels.tsv`), the descriptions (`descs.tsv`, `labels_u.csv`), the
current request (`q/`), the downloads (the tokenizer model, the
statistics `xlm-stats.dqt`, the model).

## The app

A complete System One in Rust: the lookup runs in-process through the `maned`
crate; `maned-run` drives the worker and the record. `cargo run` changes to the
project folder itself (the programs name their files relative to it).

```sh
cargo run -- [--risk low|medium|high] [--train] "text" label[=description]...
cargo run -- --yesno "text" "statement" ["negation"]
cargo run -- --score "text" 1="..." 2="..." 3="..."
cargo run -- --pending                 # answers held for review
cargo run -- --resolve [accept]        # confirm them, then learn
cargo run -- --serve 8808              # a browser UI -> http://127.0.0.1:8808 (stdlib TcpListener)
```

The build links `libmaned_c`: set `MANED_LIB_DIR=/path/to/maned-capi/lib` if it is not on the
default search path, and keep it on the loader path at runtime (`DYLD_LIBRARY_PATH` on macOS,
`LD_LIBRARY_PATH` on Linux).

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
teaching, so every worker label is learned. Set `S1_LEARN` in `~/.config/maned/xlm.env` to tune it.

## Measured

288 requests over four passes on a 4-core AVX2 worker, training mode:
all 108 repeated texts and all 36 variants were answered from memory; on
36 unseen texts the memory auto-answered only the 2 it covered well (both
right) and sent the rest to the worker, so the system matched the XLM's
83 % while the judge never answered an unfamiliar text on its own; the
memory rebuilt from its text file byte for byte. The page has the whole
table and how to read it.
