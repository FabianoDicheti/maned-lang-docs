# System One, in Maned — the complete project

This folder is the project built step by step in the
[tutorial](https://maned-lang.com/tutorial.html): a decision layer that
answers a classification question in milliseconds from its own memory,
learns from an XLM-RoBERTa worker on your LAN, and runs inside your
Python, Kotlin or Rust app through the Maned bindings. Everything that
computes is a `.mnd` program; the rest is strings, files and processes.

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
./00_download.sh                                   # tokenizer model, statistics, the model as integers
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
| `consumers/kotlin/`, `consumers/rust/` | the serving loop in Kotlin (Gradle) and Rust (Cargo) |
| `*.sh` | the shell runbook used to produce the tutorial's outputs: `_common.sh` and one driver per lane (`01_lookup.sh`, `02_xlm_classify.sh`, `03_record.sh`), the loop (`04_query.sh`), the evaluation (`05_eval.sh`), the rebuild (`06_rebuild.sh`). Optional: the page shows each step as plain commands |

Generated files live under `work/` and are never committed: the memory
(`memory.dqt`), the dataset (`memory.tsv`), the label registry
(`labels.tsv`), the descriptions (`descs.tsv`, `labels_u.csv`), the
current request (`q/`), the downloads.

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
cd consumers/kotlin && gradle run
cd consumers/rust && cargo run
```

The binding needs the engine library at the same version as the tools;
each binding's README says where it looks for it (`MANEDPY_LIB`,
`-Dmaned.library.path`, `MANED_LIB_DIR`).

## Measured

288 requests over four passes on a 4-core AVX2 worker, training mode:
105 of 108 repeated texts answered from memory; on 36 unseen texts the
judge alone was right 69 % of the time (the XLM 83 %) and all 8 of its
confident answers were right; the verifier disputed 11 of the XLM's
labels and was right 8 times; the memory rebuilt from its text file byte
for byte. The page has the whole table and how to read it.
