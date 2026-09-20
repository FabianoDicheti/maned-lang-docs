# Diagnostics Reference

> **Role:** normative for code *allocation*, descriptive of message wording.
> Codes are a user-facing contract: someone greps a code out of a terminal and
> expects to land here. Wording may be improved; a code's **meaning** may not
> change, and a retired code is never reused. (2026-09-16)

Every code below is emitted by the parser, the linter, or `maned-run`
itself. A drift test fails the build if any tool mints a code that appears in
no ledger, so this page cannot silently fall behind the toolchain.

This page is the reference. Earlier, partial lists existed in internal
working notes; where they disagree with this one, this one is right.

## Errors

| Code | Meaning |
|---|---|
| `E001` | Duplicate function definition. |
| `E002` | Duplicate assignment target. |
| `E003` | Undefined variable. |
| `E004` | Duplicate parameter. |
| `E005` | A `return` references an undefined variable. |
| `E006` | Indexed or property reference in a flow body. These would become an opaque input and die at run time, so they are refused up front. |
| `E007` | A `mnd::` directive key the toolchain consumes nowhere. Suggests the nearest real key; the known set is `parse::directive_keys()`, a single table shared with the parser. |
| `E008` | Unknown decorator `@name`, with a nearest-name suggestion drawn from the decorator registry. |
| `E009` | An unrecognized `calc::` definition kind. Previously skipped silently; now an honest refusal pointing at `calc::lambda_flow`. |
| `E010` | `mnd::quantrange` is parsed but consumed by nothing — honoring it would silently yield a 0/0 quantizer. Declare `quantmax`/`quantmin` (and `quantres`) instead. |
| `E011` | `mnd::register_backward` is parsed but consumed by nothing: there is no autodiff phase to receive the adjoint. |
| `E012` | `mnd::routing_policy` is reserved, not implemented. Route work with `@device(alias)` on a statement or flow. |
| `E013` | `calc::lambda_symphony` is reserved and has no implementation; use `calc::lambda_flow`. Its AST and lint support were dead code and have been deleted, so the definition block is skipped after the refusal. |
| `E014` | `calc::lambda_calculator` is reserved and has no implementation — nothing executes a calculator. Use `calc::lambda_flow`. The definition is still parsed so recovery lint sees the body. |
| `E015` | `mnd::backpropagation` in statement position: reserved for a future autodiff phase, not implemented. The old diagnostic was a misleading "reserved word" error from the assignment-target check. |
| `E016` | The legacy `mnd::device::` block is not supported. Declare a worker with `device::alias { ... }`. |
| `E017` | Lambda expressions (`x => body`, `lambda ... end`) are **retracted** — the grammar claimed them but the evaluator never implemented them, so a statement using one silently degraded. Define a `calc::lambda_flow`, or use the combinator ops (`identity`/`kestrel`/`kite`/`compose`). |
| `E018` | The script's output is a profile, not a tensor: it can be served but not printed by a plain `maned-run`. Emitted by `maned-run`, not the linter. |
| `E019` | `repeat` takes one integer count: `repeat(8):`. |
| `E020` | `mnd::checkpoint_every` is parsed but consumed by nothing. Gradient checkpointing tunes a backward pass; there is no autodiff phase to checkpoint. Reserved alongside `mnd::backpropagation` (E015). |
| `E021` | `calc::ml::` names an unknown algorithm (or lacks one). The set is closed: `linear_regression`, `logistic_regression`, `svm`, `kmeans`, `knn`, `naive_bayes`, `decision_tree`, `isolation_forest`, `pca`, `xgboost`, `hmm`. |
| `E022` | A malformed `calc::ml::` definition: the hyperparameter block takes `key: value` pairs (integers in the scaled domain, `true`/`false`, or a flat `[v, v, ...]` sweep list — floats are refused, they would silently truncate), and the definition needs a return clause (`} return model;` or `} return model, loss;`). |

`WPARSE` is separate and unnumbered: a parser *warning* (as opposed to an
error), printed by `maned-lint`.
It carries the parser's own message and location rather than a fixed text, so
it has no row of its own.

`ELIMIT` is separate and unnumbered: a worker-contract limit (register-file
slots, MNPK tensor count, payload size, arena estimate) refused identically by
`maned-run` and `maned-lint`. See
[12_MANED_LANGUAGE_GUIDE.md](12_MANED_LANGUAGE_GUIDE.md).

`EPARSE` is the umbrella code for parse errors that have not been given a
number — for example an unknown identifier, which carries a nearest-name
suggestion.

## Warnings

| Code | Meaning |
|---|---|
| `W001` | Unused parameter. |
| `W002` | Variable assigned more than once. Skips compiler-generated assignments, so a `repeat` expansion does not warn about its own SSA renaming. |
| `W003` | Duplicate object parameter. |
| `W004` | Unused variable. |
| `W005` | Duplicate `device::` field. |
| `W006` | An `in::` input defined more than once. |
| `W007` | `@device` on a called (and therefore inlined) flow is ignored — the caller's placement wins. |
| `W008` | **RETIRED** (lang_052). Never reuse this number. A regression test asserts it is never emitted. |
| `W009` | Two `out::` declarations writing one path. |
| `W010` | An inert `print` or `memory::write` in a flow body. |
| `W011` | The flow uses an op with no local evaluator: it executes only on a worker (`@device` or the Bark VM), so a plain local run will refuse. The op-state table in the guide is generated from the same sets this rule reads. |
| `W012` | A decorator that is registered but not implemented — it parses and is then ignored. |
| `W013` | The mirror of `W011`: the op runs locally, but the flow is routed with `@device` and no worker implements it, so the job is refused at pre-flight before it is sent. |

## Allocating a new code

1. Take the next free number **in this file**. Do not scan the source for the
   highest code in use; two tickets did that concurrently and both picked the
   same number.
2. Never reuse a retired code (`W008`), even though its number looks free.
3. Add the row here in the same commit as the emitter. The drift suite fails
   the build otherwise, which is the point.
