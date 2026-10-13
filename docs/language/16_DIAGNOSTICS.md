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
| `E023` | A float literal in a value position (`in::x = 0.5;`, a float tensor-literal element, a float RPN operand). Values are integers at quantres, and these literals used to fall into `strtoll` and silently truncate to their integer part (`0.5` → `0`) — the exact class of loss the language exists to refuse. Write the scaled integer, or route the value through a quantized input file. Decorator params and scalar object params are exempt: `paramInt`'s toward-zero truncation there is separately documented. (lang_090; the `calc::ml::` float refusal is E022.) |
| `E024` | `mnd::quantres` (or its `decimal_places` alias) outside `0..9`. Nine is `CACT_MAX_QRES`, the bound the generated fixed-point activation tables enforce via `cact_pow10`'s sentinel and the `calc::ml::` validator enforces independently — but neither is reached by a program with no transcendental and no `calc::ml::`, so a larger value used to parse, run and encode at a scale nothing downstream could consume. The ceiling is checked where the value is declared. (gap_063) |
| `E025` | A **scale-squared** value reaching a consumer that decodes at the program scale, at `quantres > 0`. The language has two scale mechanisms and they meet here: plain `matmul` (and elementwise `mul`) multiply two scale-`q` operands raw, so the result encodes the real product at `10^-2q`, while every quantres-decoded consumer — `sigmoid`, `tanh`, `softmax`, `exp`, `sqrt`, `isqrt`, `layernorm`, the `calc::ml::` kernels — reads a register element `i` as `i / 10^q` (`maned_activation.h` is normative). Feeding one to the other reads `10^q` times too large, and before lang_097 it did so **silently**: at `q=3`, `0.5 . 2.0` gives register `1000000`, which `sigmoid` decoded as `1000.0`. Fix it by interposing the rescale — divide by a tensor of `10^q` — or by switching to `packed_matmul`, whose output is already at the program scale. **Known limit:** the tag is three-state (`preserved` / `squared` / `unknown`) and only `squared` refuses, so a division degrades it to `unknown` and passes. That is deliberate — it keeps the existing `matmul -> ÷10^q -> sigmoid` convention legal without a scale-inference pass — but it also means a *stale* `÷10^q` left behind after porting a flow to `packed_matmul` is **not** caught, and is wrong by `10^-q`. When switching to `packed_matmul`, delete the manual rescale. At `quantres = 0` squaring is the identity and this diagnostic can never fire. (lang_097) |

| `E026` | A `.dqt` file refused at the `in::dqt` boundary (lang_111). Carries the dqtensor refusal verbatim — `DQT_E01`..`DQT_E24` per the dqtensor SPEC §7 catalogue (bad magic, hostile tile geometry, crc32/sha256 mismatch, …) — plus the unknown-tensor-key case, which lists the available names (the safetensors rule). `.dqt` files are always read in **verify mode**: this boundary is exactly where bit-identity is worth one sha256 pass. Also minted when the file cannot be opened. |
| `E027` | An `in::dqt` rescale that cannot be represented (lang_111). A `.dqt` tensor arrives at its own `scale_pow10`; the reader shifts it EXACTLY to the program quantres (`d = quantres − scale_pow10`): `d > 0` multiplies by `10^d` in 128-bit and refuses any product outside int64 — the mod-2^32 wrap is the compute tier's contract, not the ingest boundary's; `|d| > 18` is refused outright (`kPow10`'s domain). Downshifts (`d < 0`) never mint this code — they divide half-even with every inexact division counted in notes. Fix by lowering the program quantres or re-converting the file at a scale within ±18 of it. |

| `E028` | An `out::dqt` collection that cannot form one canonical file (lang_112). All `out::dqt` directives naming the same path are collected into ONE write-once canonical `.dqt` (name-sorted, single header) — so two directives exporting the same **tensor name** into one path refuse (each name exists once in a canonical file), as does a tensor name outside the dqt charset `[A-Za-z0-9_.+-]` (1..256 bytes). Same-path collection is why `W009`'s later-write-wins warning deliberately exempts dqt. Exports are written at `scale_pow10` = the program quantres, logical width 64. |

| `E031` | An ambiguous `out::tokens` decode (lang_124). The one-string form (`out::words = tokens("out.txt");`) decodes through the run's vocab registry **iff the program has exactly one `tokens()` source**; zero sources or two-plus distinct id spaces refuse naming the count and the fix — the two-string form (`tokens("out.txt", "which.mnv")`), which also works when the ids arrived via `--in` or a request body. Under maned-serve the sidecar form is the ONLY decode source (request vocabs die with their request), so a one-string `out::tokens` refuses at load. Decode itself never clamps: pad (0) is skipped, `<unk>` (1) renders literally with a counting note, and an id outside the vocab refuses naming index and id — printing wrong words silently is the failure the refusal exists for. |

| `E030` | A `.mnv` vocab sidecar refused at the `tokens()` boundary (lang_123). Names the failed check: cannot open, too short/truncated, bad magic (`MNVFILE1`), checksum mismatch (the **canonical** fnv1a over everything after the tag — a new format uses the correct constant, lang_121), unsupported version, unimplemented delimiter class (1 = ASCII whitespace is the only one; the byte is the non-whitespace extension point), word count beyond the 32767-id cap, corrupt length field, stray trailing bytes. A loaded vocab is **frozen**: words absent from it intern as `<unk>` with a counting note — stable ids are the sidecar's entire point, so growth is a refusal of a different kind (build the vocab from the union document instead). |

| `E029` | A string literal in a value position inside a flow (`"hello" x =`, a string RPN operand, a string argument to a called flow). Strings have no runtime value — they exist as file paths and tensor names in `in::`/`out::`/`device::` position only. Before lang_119 this lowered to a placeholder constant whose `strtoll` parse made it **scalar 0, silently** — the same loss class as `E023`'s float truncation — while the remote path refused the identical node loudly, so local and remote semantics disagreed on the same program. The `return("...")` print form is unaffected: print statements are not lowered. (lang_119) |

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
| `W014` | Two or more `tokens()` sources with distinct id spaces (lang_124). Each document frequency-ranks its own vocabulary, so the same word gets different ids in each source — comparing or concatenating the streams is meaningless, and the one-string `out::tokens` decode refuses on the ambiguity (E031). Suppressed only when every source names the SAME `.mnv` sidecar, the one arrangement where the id spaces provably agree. |

## Allocating a new code

1. Take the next free number **in this file**. Do not scan the source for the
   highest code in use; two tickets did that concurrently and both picked the
   same number.
2. Never reuse a retired code (`W008`), even though its number looks free.
3. Add the row here in the same commit as the emitter. The drift suite fails
   the build otherwise, which is the point.
