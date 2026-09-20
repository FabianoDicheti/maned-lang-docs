# Maned workspace documentation

Central documentation for the maned language. The repository itself
(`../maned_lang/`) is kept dry (code, build, tests, packaging, one README);
everything explanatory lives here. Runnable scripts live in
`../mnd_scripts/` (see its README for the catalog).

## Map

| Where | What |
|---|---|
| [language/](language/00_README.md) | The full technical reference (01–16: structure, frontend, IR, interpreter, MLIR, network, CLI, build, testing, benchmarks, editor, language guide, usage guide, compiler-dev guide, remote-worker guide, diagnostics) plus the plan/report docs and the compiled PDF (`render_pdf.py` rebuilds it). |
| [spec/RPN_SYNTAX_SPECIFICATION.md](spec/RPN_SYNTAX_SPECIFICATION.md) | Normative prose specification of the surface language. |
| [spec/GRAMMAR_NOTES.md](spec/GRAMMAR_NOTES.md) | Conventions for the grammar artifacts (`maned_lang/grammar/`). |
| [contracts/INTEGRATION_CONTRACT.md](contracts/INTEGRATION_CONTRACT.md) | Cross-repo binary-IR / protocol contract (referenced by `binary_ir.h` and `verify_contract.cpp`). |
| [scripts/EXAMPLES_VERIFICATION.md](scripts/EXAMPLES_VERIFICATION.md) | "Maned by Example" — per-flow reference tables for the example scripts. |
| [scripts/RUN_LOG.md](scripts/RUN_LOG.md) | 2026-09-15 run campaign: every script executed, fixed, or classified. |
| [CAPABILITY_REVIEW.md](CAPABILITY_REVIEW.md) | Item-by-item review of the language's full capability surface. |
| [GAP_ANALYSIS.md](GAP_ANALYSIS.md) | Prioritized gap matrix merging the improvement report, the run campaign, and the capability review. |
| [GAP_ANALYSIS_2026-09-16.md](GAP_ANALYSIS_2026-09-16.md) | The current gap matrix — post-reorganization review at `maned_lang@dbb66db` (code surface, living docs, build/CI). |
| [capability/](capability/) | The three detailed capability-review working documents (ops/execution, language surface, tooling/IO/distribution). |
| [history/](history/) | Historical inputs: `review.md` (2026-07 four-repo review), `todo.md` (idea backlog), `task_14_sep.md` (the 7-item demo request), and the two 2026-07-21 session handoffs archived from the repo root on 2026-09-16. |

## Which document wins (precedence — gap_018, 2026-09-15)

Three overlapping references describe the language. When they disagree,
the precedence is:

1. **The implementation and its tests are the ground truth.** On conflict
   with every document, the docs carry the bug — file it against the doc.
2. **`spec/RPN_SYNTAX_SPECIFICATION.md` is normative.** Among documents,
   it wins on conflict.
3. **`language/12_MANED_LANGUAGE_GUIDE.md` is the primary reading
   entry** — complete but descriptive; it teaches, it does not rule.
4. **`scripts/EXAMPLES_VERIFICATION.md` and the `capability/` documents
   are illustrative** — evidence of verified behavior at a stated commit,
   never a specification.

Three references are **drift-checked by tests, in both directions** (the code
must be documented, *and* the docs must not invent flags, codes or counts that
do not exist — gap_044), which makes them the ones to trust when a detail
matters: `language/07_CLI_AND_SCRIPTS.md` (every tool
flag), `language/16_DIAGNOSTICS.md` (every diagnostic code), and the
operations table in `language/12_MANED_LANGUAGE_GUIDE.md` (every registry op
is listed, and its three summary counts match the registry — the per-op
executability *column* is not pinned; gap_044 records why). The suites are
`maned_lang/tests/cli/test_cli_docs_drift.cpp` and
`test_docs_coverage_drift.cpp`; adding a flag, a code, or an op without
documenting it fails the build.

`GAP_ANALYSIS.md` and `CAPABILITY_REVIEW.md` are **closed history** as of
2026-09-16 — snapshots of what was wrong at commit `8f77f1b`, each now
carrying a resolution header. Their counts are deliberately not updated; read
them for how something was found, never for how it is now. The current gap
matrix is [GAP_ANALYSIS_2026-09-16.md](GAP_ANALYSIS_2026-09-16.md).

The EBNF (`maned_lang/grammar/maned.ebnf`) is descriptive of the
parser as built. Each document carries a one-line role header pointing
back here.

Deeper archive: `../_attic_maned_lang/` holds the agent-era scaffolding
(knowledge base, session logs, sprint specs) evicted from the repo on
2026-09-15. The wire-protocol spec remains at `../PROTOCOL_SPEC.md` (CDP,
shared with the bark repo).
