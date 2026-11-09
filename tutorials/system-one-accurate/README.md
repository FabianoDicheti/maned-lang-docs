# System One, in Maned — the accuracy-first edition

This folder is the project built step by step in the
[tutorial](https://maned-lang.com/tutorial-accurate.html): a decision layer
that answers a classification question from its own memory, learns from TWO
teachers on your LAN — an XLM-RoBERTa worker and an entailment (NLI) worker —
and runs inside your Python app through the Maned binding. Everything that
computes is a `.mnd` program; the rest is strings, files and processes.

It is the second of two editions of the same loop. The
[speed-first edition](../system_one/) pays for nothing it does not need: one
worker, a count judge, an answer in milliseconds when the memory knows the
text. This one pays time for quality: a second worker that is right more
often, a judge that generalises from what it learned, and a learning rule
that never writes a label the two teachers dispute.

| | speed-first | accuracy-first (this folder) |
|---|---|---|
| known text | the count memory, ~8 ms | the same, ~8 ms |
| unseen text | count judge → else the XLM-R worker's zero-shot label (~0.4 s) | one XLM-R embedding → the **prototype judge** (learned centroids); when it is not sure, the **NLI worker** decides (~0.25 s per candidate on bare metal) |
| learns | the XLM-R label when its margin ≥ 70 ‰ | the NLI label when the XLM-R zero-shot verdict **agrees** and the NLI margin ≥ 250 ‰; the rest waits in `work/pending.tsv` for you |
| memories | `memory.dqt` (counts) | `memory.dqt` + `protos.dqt` (one centroid per label) |
| apps | Python, Kotlin, Rust | Python (Kotlin and Rust follow once Maned has a native `nli()` call) |

## Deploy from zero

1. **Two workers.** Tutorial parts 1 and 2 of the speed edition: a spare x86
   computer booted from the `maned-xlm` USB image, the XLM-R model provisioned
   onto its disk; its address and login go in `~/.config/maned/xlm.env` (mode
   600): `XLM_USER`, `XLM_PASS`, `S1_WORKER_HOST`. A second computer (or the
   same stick family) serving the NLI model `maned-nli-bark`; its address goes
   in `~/.config/maned/nli.env` as `S1_NLI_HOST`, with `NLI_USER` / `NLI_PASS`
   when its login differs. The programs read the XLM login with `env()`;
   `nli/nli_lane.py` reads the NLI one.
2. **Maned 0.4.2 or newer** on your PATH (`maned-run`, `maned-serve`), the
   `manedpy` binding at the same version, and `pip install sentencepiece`
   (the NLI worker's tokenizer runs on your side).
3. Then, in this folder:

```sh
. ~/.config/maned/xlm.env; . ~/.config/maned/nli.env
./00_download.sh                                   # tokenizer models, xlm-stats.dqt, the model as integers
maned-run 00_provision.mnd                         # once per XLM-R worker
./00_setup.sh                                      # both memories, empty
./04_query.sh "Our servers crashed again, customers cannot log in." urgent later careful
python3 consumers/python/decide.py                 # the three demo questions
python3 consumers/python/decide.py --pending       # what the loop held back for you
python3 consumers/python/decide.py --resolve       # confirm it, and the memories learn
maned-serve 01_lookup.mnd --port 8787 &            # the known-text cache as a service
```

## What is here

| file | what |
|---|---|
| `00_provision.mnd`, `00_embed_check.mnd` | stream the XLM-R model to the worker; one sentence through it |
| `00_init_memory.mnd`, `00_init_protos.mnd`, `00_setup.sh` | the two empty memories: `counts [4096,32]` + `ntexts [1,32]`, and `sum [32,256]` + `n [1,32]` |
| `01_lookup.mnd` | the fast lane: is this text KNOWN? One file for `maned-run`, `maned-serve` and the bindings |
| `02_label_embed.mnd` | a label description to its 256-d unit vector, once, on the worker |
| `02_proto_classify.mnd` | the judge: ONE embedding of the text; the cosine to every label anchor (the zero-shot verdict) and to every learned centroid (the prototype verdict), its margin and tier, and the vector itself for the record |
| `02_nli_classify.mnd`, `nli/nli_lane.py`, `nli/model_nli.sha256` | the teacher: every candidate hypothesis against the text on the NLI worker, softmax over the entailment logits, argmax |
| `03_record.mnd`, `03_record_proto.mnd` | both memories learn one text: `counts += bᵀ·y` and `sum += yᵀ·u`, written in place |
| `05_eval.mnd` | every metric of the evaluation, the calibration table and the four PASS checks (shared with the speed edition) |
| `policy.csv` | the count judge's thresholds per risk level (it reports; it no longer decides) |
| `proto_policy.csv` | the prototype judge's, per risk level: `t_auto`, `t_verify` (cosine margin, permille), `warm` (texts the anchor is worth), `min_n` (texts a label needs before the judge answers alone) |
| `corpus/` | three labels with descriptions and hypotheses; 108 messages, 36 variants, 36 unseen, in en/pt/de |
| `consumers/python/decide.py` | the loop's reference: `decide()`, training mode, `--pending` / `--resolve` |
| `*.sh` | the shell runbook: `_common.sh`, the loop (`04_query.sh`), the evaluation (`05_eval.sh`), the rebuild (`06_rebuild.sh`) |

Generated files live under `work/` and are never committed: the memories
(`memory.dqt`, `protos.dqt`), the dataset (`memory.tsv`) and its vectors
(`vectors.csv`, row-aligned), the review queue (`pending.tsv`), the label
registry (`labels.tsv`), the descriptions (`descs.tsv`, `labels_u.csv`) and
hypotheses (`descs_nli.tsv`), the current request (`q/`), the downloads.

## The loop

1. **Known?** `01_lookup.mnd` hashes the text's SentencePiece features into
   the count memory. A text the memory has seen, or a close variant, is
   answered from it in about 8 ms. Nothing else about the count judge is
   used here: measured on nine public datasets it does not generalise to
   unseen text (0.35 → 0.40 accuracy from 40 to 240 learned texts), so it
   keeps the job it is good at, the cache.
2. **The prototype judge.** `02_proto_classify.mnd` embeds the text once on
   the XLM-R worker, whitens it to a 256-d unit vector `u`, and scores it
   against one centroid per label: the mean of the label's recorded vectors,
   warm-started with `warm` copies of the label's anchor (its description's
   vector) so an empty label is judged by its anchor and the anchor fades as
   texts arrive. The cosine margin between the best and second-best candidate
   is its confidence. It answers alone when the margin clears `t_auto` for the
   request's risk AND it has learned at least `min_n` texts of that label.
   The same program also reports the nearest anchor, the speed edition's
   zero-shot verdict.
3. **The teacher.** Otherwise `nli/nli_lane.py` asks the NLI worker whether
   the text entails each candidate's hypothesis (`descs_nli.tsv`, from
   `corpus/hypotheses.tsv` or the description itself) and
   `02_nli_classify.mnd` takes the softmax over the entailment logits; the
   most entailed label is the answer and the gap to the runner-up its margin.
4. **Learning.** Whenever the teacher ran, its label is written to both
   memories (`03_record.mnd`, `03_record_proto.mnd` from the `u` of step 2,
   no second worker call) when `S1_LEARN_RULE` holds. The default, `agree`,
   requires the XLM-R zero-shot verdict — the anchor the judge was computed
   alongside, fixed — to agree with the teacher and the NLI margin to clear
   `S1_LEARN` (250 ‰). Not the judge's own verdict: gating on that was
   measured to feed the judge its own answers (63 % label precision, no growth). Everything else — a disagreement, a shaky
   teacher — is appended to `work/pending.tsv` with both verdicts and the
   text's vector; `decide.py --resolve` shows you each one and the memories
   learn what you confirm. The judge never learns its own answers
   (`S1_SELF_LEARN=1` opts in). `S1_LEARN_RULE=nli` learns every teacher
   label above the margin; `all` learns everything (the speed edition's
   training mode).

`06_rebuild.sh` replays `memory.tsv` and `vectors.csv` from empty memories
and compares the bytes: both files are pure functions of what was recorded.

## Measured

See the tutorial page's "Measured" section and `work/eval_suite/README.md`
of the speed edition (the benchmark harness, shared). Headline numbers on the
same 264 unseen texts of 8 public datasets, 240 texts learned per dataset:

| configuration (240 texts learned per dataset) | judge on unseen text | final answer | answered without the second worker |
|---|---|---|---|
| speed-first: count judge, XLM-R teacher | 0.39 | 0.45 | — (one worker) |
| NLI teacher alone, no judge | — | 0.48 | 0 % |
| accuracy-first, `S1_LEARN_RULE=agree`: prototype judge, NLI teacher | 0.44 | 0.48 (medium risk; 0.48 with the threshold chosen on the other datasets) | 48 % |
| accuracy-first, `S1_LEARN_RULE=nli`: prototype judge, NLI teacher | 0.44 | 0.52 (medium risk; 0.48 with the threshold chosen on the other datasets) | 26 % |

The prototype judge by texts learned (40 → 80 → 160 → 240): `agree`: 0.42 → 0.40 → 0.42 → 0.44; `nli`: 0.39 → 0.41 → 0.45 → 0.44. The count judge of the speed edition on the same texts: 0.35 → 0.38 → 0.39 → 0.40.

What `agree` wrote while learning 1920 texts: 479 (25 %) at 75 % label precision; 1441 held at 47 %; the two lanes agreed on 38 % of texts.

What `nli` wrote while learning 1920 texts: 1023 (53 %) at 64 % label precision; 897 held at 43 %; the two lanes agreed on 38 % of texts.
