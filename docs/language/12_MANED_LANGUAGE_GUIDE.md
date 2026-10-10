# Maned Language Guide

> **Role:** primary reading entry — complete but DESCRIPTIVE. On conflict the normative spec (docs/spec/RPN_SYNTAX_SPECIFICATION.md) wins; see docs/README.md ("Which document wins"). (gap_018)

Welcome to Maned. This guide teaches the language from the perspective of an
engineer who needs to read, write, and reason about `.mnd` programs. It covers
the complete surface grammar while making backend support visible.

Use this guide together with the [usage guide](13_MANED_USAGE_GUIDE.md) when
running examples and the [compiler development guide](14_MANED_COMPILER_DEVELOPMENT_GUIDE.md)
when changing the implementation.

## 1. How to read feature status

Maned's grammar is broader than any single execution backend. Each feature in
this guide uses one or more status labels:

| Label | Meaning |
|---|---|
| **Local runtime** | The current `maned-run` interpreter executes it. |
| **Parser** | The lexer/parser represent it in the AST, but local execution may not exist. |
| **MLIR** | The Maned MLIR dialect or passes represent/transform it. |
| **Device** | It participates in remote/FPGA orchestration and requires a compatible worker. |

“Parser” is not the same as “runnable.” When learning, begin with examples marked
**Local runtime**, then use broader features when working on their backend.
Short flow-only snippets below assume the required quantization header shown in
the complete examples.

## 2. The central idea: postfix computation

**Learning objectives**

- Read Reverse Polish Notation (RPN) from left to right.
- Predict the operand stack after every token.
- Recognize the assignment target at the end of an expression.

Most languages write addition as `a + b`. Maned writes:

```mnd
a b add result =
```

Read it as: push `a`, push `b`, apply `add`, bind the result to `result`.

| Token | Stack after the token |
|---|---|
| `a` | `a` |
| `b` | `a, b` |
| `add` | `add(a, b)` |
| `result =` | empty; the value is bound to `result` |

There is no operator precedence. This:

```mnd
a b add c mul result =
```

means `(a + b) * c`. The stack makes grouping explicit:

1. `a b add` produces one value.
2. `c` pushes another value.
3. `mul` consumes both.

The local runtime executes far more than the four arithmetic ops — see the
operations table in section 6 for the full locally-executable set (it
includes conv2d, both pools, layernorm, sigmoid/tanh/softmax, comparisons,
logic, concat and slice). Division by zero currently produces zero, and
tensor means use integer division.

**Knowledge check:** What does `a b mul c add out =` compute?  
Answer after reasoning with the stack: `(a * b) + c`.

## 3. A complete minimal program

**Learning objectives**

- Recognize required program directives.
- Define a flow with parameters and outputs.
- Follow intermediate values.

```mnd
mnd::quantmax=1000;
mnd::quantmin=-1000;
mnd::quantres=0;

calc::lambda_flow add_and_scale(a, b, scale) {
    a b add sum =
    sum scale scalar_mul result =
} return result;
```

Status: **Local runtime**.

Every program begins with quantization declarations. A named `lambda_flow`
declares its inputs, body, and returned bindings. Statements end with a newline
or semicolon. Comments start with `#`.

Run it after building:

```bash
./maned-run program.mnd \
  --flow add_and_scale \
  --in a=3 --in b=4 --in scale=2
```

Expected value: `14`.

## 4. Directives and program configuration

**Learning objectives**

- Separate compile-time directives from runtime values.
- Recognize the consumed quantization keys, and the refused legacy keys.

Directives use the `mnd::key=value;` form. Since the gap_003/gap_002
honesty pass (2026-09-15), a key the toolchain does not consume REFUSES
with a numbered error instead of being silently accepted:

| Family | Keys | Status |
|---|---|---|
| Quantization | `quantmax`, `quantmin`, `quantres` (alias `decimal_places`) | **Consumed** — they feed the local quantizer, dispatch and the MNPK envelope; the preamble requires quantres + quantmax + quantmin |
| Checkpointing | `checkpoint_every` | **Refused (E020)** — tunes a backward pass; there is no autodiff phase |
| Refused (numbered) | `quantrange` (E010 — it silently yielded a 0/0 quantizer), legacy `quant` and every `_fwd`/`_grad` variant (E011), `register_backward(...)` (E011), `routing_policy { ... }` (E012), `backpropagation` (E015), legacy `device::{fpga\|cpu}` blocks (E016) | Each errors with a location and, where one exists, a migration hint |
| Unknown key | anything else | Lint error E007 with a nearest-name suggestion |

The common header is:

```mnd
mnd::quantmax=1000;
mnd::quantmin=-1000;
mnd::quantres=0;
```

These are configuration declarations; they do not push values onto the RPN
stack. Keep them together at the top of a file.

## 5. Values, literals, references, and types

**Learning objectives**

- Write scalar, string, and tensor literals.
- Understand shape requirements.
- Recognize namespaced, indexed, and property references.

### Literals

```mnd
42
-7
3.25
"double-quoted text"
'single-quoted text'
[[1, 2], [3, 4]]
```

Tensor literals must be rectangular. `[[1, 2], [3]]` is rejected because its
rows have different lengths. The local interpreter stores integer data; floating
values belong to the wider syntax/quantization model and are not general-purpose
local floating-point runtime values.

### References

| Form | Example | Purpose/status |
|---|---|---|
| Variable | `weights` | Local binding; local runtime |
| Qualified | `port::0`, `receiver::matrix_a`, `memory::W1`, `responser::output` | External/device binding; parser/device |
| Indexed | `A[0]`, `A[0:32]`, `A[1][2]` | Indexed/sliced value; parser |
| Property | `decomp.eigenvalues` | Structured-result property; parser |

### Type annotations

An assignment can place a type annotation before `=`:

```mnd
a b matmul product oc::tensor =
```

Namespaces are `oc`, `ot`, and `os`; built-in type names include `number`,
`tensor`, `string`, `text`, and `dictionary`. Modifiers such as `trunc` follow
another `::`. Type annotations are represented in the AST; do not assume every
annotation changes local interpreter behavior.

## 6. Operations

**Learning objectives**

- Select operations by arity.
- Distinguish registry support from backend execution support.

This table is generated from the toolchain's own executability sets — the
same truth lint's W011 rule reads, test-pinned against the evaluator modules and
the binary-IR opcode table. Three states: **local** (the interpreter
executes it), **remote** (a bark worker / the Bark VM executes it),
**registry-only** (parses and shape-infers, refuses at run time; lint
warns W011 up front).

| Group | Ops | Local | Worker |
|---|---|---|---|
| Arithmetic | `add`, `sub`, `mul`, `div` — and the explicit spellings `elemwise_add`, `elemwise_sub`, `elemwise_mul`, `elemwise_div` | yes | yes |
| Activations | `relu`, `sigmoid`, `tanh`, `softmax` (integer LUT, decoded at `quantres`) | yes | yes |
| Matrix | `matmul`, `transpose`, `scalar_mul` | yes | yes |
| Reductions | `tensor_sum`, `tensor_mean`, `tensor_max`, `tensor_min` | yes | yes |
| Comparison | `>` `<` `==` `>=` `<=` `!=` (and the `gt`/`lt`/`eq`/`ge`/`le`/`ne` mnemonics) | yes | yes |
| Logic | `and`, `or`, `not`, `xor` (elementwise 0/1) | yes | yes |
| Spatial | `conv2d`, `maxpool2d`, `avgpool2d` | yes | yes |
| Normalization | `layernorm`; `batchnorm` (inference mode) | yes | yes |
| Layout | `reshape`, `split` (single-section select) — dispatchable since gap_058: the target shape and the split selector ride the instruction fields a unary op leaves free. A dimension above 65534 is refused with numbers. | yes | yes |
| Shape | `concat`, `reshape`, `split` | yes | yes |
| Quantization | `quantize`, `dequantize` | — | yes |
| Shape, local only | `slice` (one index off an axis — the inverse of `concat`) | yes | **no** |
| Math, local only | `exp` (domain −16..7.616; refuses above it, see "Table domains" below), `sqrt`, `isqrt`, `abs`, `clip`, `argmax`, `argmin` (the argmax mirror; same tie rule, lowest index) | yes | **no** |
| Linear algebra | `packed_matmul` (multiplies a tensor by a lang_085 packed weight descriptor loaded with `in:: packed()`, without dequantizing — rescale per block partial, division half to even, so the result is bit-identical on every device and loop order; lang_092 payload widths are 8/16/32/64 — wide partials accumulate in 128-bit — and `tensor::pack` takes `bits=8\|16\|32\|64\|auto` (default 16, `auto` = smallest lossless width per tensor), `pack_all=0\|1` (rank-1 floats are otherwise stored exact I64 at a per-tensor scale), with `tensor::profile` printing the per-width pack preview and recommendation). **lang_089 put it on the wire as opcode `0x44`**, two operands — a plain activation and the descriptor, which needs no new MNPK dtype because since lang_094 a descriptor slot *is* one int32 element, so the whole thing travels as one ordinary rank-1 i32 tensor. One packed operand per instruction: a **packed** left operand stays local-only and refuses by name when routed (follow-on lang_100) | yes | yes |
| Linear algebra, local only | `determinant`, `adjugate`; `pack_rows` (lang_087: packs an int64 activation tensor `[M, K]` into the same descriptor form, `{bits: 8\|16}`, default 8 — the fit is the pinned `rescale_half_even` itself, so it is bit-identical everywhere with no decimal extraction; a packed left operand takes the packed×packed `packed_matmul` path, whose 8/16-bit partials fit int64 by construction — the activation-magnitude refusal does not exist there, and the combined block exponent rescales in ONE half-even rounding through a 128-bit power table, never two chained divisions. That path has no wire form: see lang_089 above) | yes | **no** |
| Profiling, local only | `profile_vector` | yes | **no** |
| ML, local only | `ml_predict` (runs a fitted model descriptor over new rows), `ml_fit` (the Tier-B native training kernel `calc::ml::` desugars to) — coordinator-only by design: inference is cheap, the parallelism that matters is in training, which the gradient-descent family reaches by desugaring to worker-legal primitives instead | yes | **no** |
| Constructors, host-side | `zeros` `ones` `full` `eye` `diag` `range` `random` `band` `tridiag` `from_spectrum` `synth` | `in::` initializer position | n/a |
| **Registered, not executable** | `tensor.init` `txt.read` `adaptive_avgpool2d` `cholesky` `clip_gradient` `conv1d` `conv3d` `cross_entropy` `eigendecomp` `embedding_lookup` `fft` `fft2d` `gelu` `get_timestamp` `groupnorm` `ifft` `instancenorm` `inverse` `lu` `multihead_attention` `qr` `s4_layer` `scaled_dot_attention` `selective_scan` `silu` `softplus` `svd` | no — lint warns **W011**, run refuses | no |

As of 2026-09-29 that is 84 registry ops: 32 run both places, 25 run locally
only, and 27 parse and shape-infer but refuse to execute. The counts are not
decoration — the table is generated from the sets and checked by a drift
suite, so if an op is added to the registry and nowhere else, this table is
what fails.

Two of those rows changed recently and older notes still say otherwise:

- `reshape`, `split` and `batchnorm` used to be described as wire-blocked on
  reserved opcodes. The ABI v2 bump (gap_009) unblocked them; they run on
  workers now.
- `exp`, `sqrt`, `abs`, `clip`, `isqrt`, `argmax`, `determinant`, `adjugate`
  and `profile_vector` used to be registry-only. They execute locally now
  (gap_008), but they have no worker opcode, so a flow using them will not
  offload.

`tensor.init` and `txt.read` are in that bottom row too. They are leftover
host-op registry entries with no evaluator behind them; the working spellings
are the tensor constructors below and `in::x = text(...)`.

`inverse` is deliberately still in the bottom row. It does not silently fail —
it refuses with the `adjugate` + `determinant` recipe, because an integer-only
inverse has to be spelled out rather than guessed at.

Operation arity matters. `matmul` consumes two values; `relu` consumes one.
Object parameters carry named configuration, and conv2d genuinely executes
locally and remotely:

```mnd
x kernel {stride: 1, padding: 0} conv2d result =
```

### Tensor constructors

Eleven host-side constructors build tensors in `in::` initializer position
(RPN postfix, evaluated at load time — they never enter the dataflow graph):

```mnd
in::z  = 4 4 zeros;            # rows cols -> zero matrix
in::o  = 2 3 ones;             # rows cols
in::f  = 2 2 7 full;           # rows cols value
in::i  = 3 eye;                # n -> identity
in::d  = [1, 2, 3] diag;       # vector -> diagonal matrix
in::r  = 5 range;              # 0..n-1 vector
in::rd = 4 4 random;           # deterministic fill, [0, 100); see below
in::b  = 5 1 1 9 band;         # n lower upper fill
in::t  = 5 1 2 3 tridiag;      # n sub diag super
in::sp = [4, 1] from_spectrum; # eigenvalues -> matrix with that spectrum
in::sy = { rows: 4, cols: 4, symmetric: true } synth;  # properties -> matrix
```

**`random` is deterministic, and each call site is its own stream.** There is
no entropy anywhere: the same program produces the same tensors on every
machine and every run, which is what `--verify` equality requires. What varies
is the *call site*.

```maned
in::w1 = 4 4 random;      # w1 and w2 are DIFFERENT tensors
in::w2 = 4 4 random;
```

Before gap_074 they were not. The generator was re-seeded inside the op, so
`random` was a pure function of shape and every draw of a given shape returned
the same tensor — `w1 w2 elemwise_sub` was all zeros. If you have scripts that
initialised weights this way, they were symmetric, and a model built on them
could not break that symmetry.

Two consequences worth knowing before they surprise you:

- **Renaming changes the draw.** A draw is keyed on where it appears — the
  input name in `in::` position, the statement's position in the dataflow
  graph inside a flow, and the flow's own name. Renaming an input or a flow
  gives you different numbers. That is the price of not carrying state between
  draws, and not carrying state is what keeps `random` reproducible when flows
  run concurrently.
- **There is no global sequence.** Inserting a `random` statement does not
  shift the draws of the ones after it, because nothing counts calls. Each
  site is independent.


### Worker-contract limits (the real numbers)

Enforced identically by `maned-run` and `maned-lint` (`ELIMIT`), so a
flow that will not fit a worker is refused before it is sent:

- **Register-file slots — 256 or 4096, depending on the worker.** A flow may
  compile to at most that many values post-inline (params + consts + ops).
  ABI v1 used 8-bit value ids, capping the file at 256; ABI v2 widened them
  to 16-bit, raising it to 4096. The budget checked is the one the *target*
  worker advertises, so an oversized flow refuses with the numbers of the
  machine it was actually headed for. Locally and in lint the v2 budget is
  used, on the principle that what runs here should also ship.
- **`kMnpkMaxTensors` = 16** — a MNPK job carries at most 16 input tensors
  and a MNRS reply at most 16 outputs (applies to local flows too).
- Worker-advertised at pre-flight (live numbers, not constants): payload ≤
  `GET /api/status max_payload` (the 1 MiB default caps square matmul at
  N≤362), and the arena estimate against bark's boot formula.

## 7. Tensors and a linear layer

**Learning objectives**

- Track matrix dimensions through a pipeline.
- Understand row-major CLI inputs.

```mnd
mnd::quantmax=1000;
mnd::quantmin=-1000;
mnd::quantres=0;

calc::lambda_flow layer(x, w, bias) {
    x w matmul product =
    product bias elemwise_add shifted =
    shifted relu result =
} return result;
```

Status: **Local runtime**. For `x` and `w` shaped `2x2`:

```bash
./maned-run layer.mnd \
  --flow layer \
  --in x=2x2:1,2,3,4 \
  --in w=2x2:5,6,7,8 \
  --in bias=2x2:0,0,-100,0
```

The values move through these shapes:

| Binding | Computation | Shape/value |
|---|---|---|
| `product` | `matmul(x, w)` | `[[19,22],[43,50]]` |
| `shifted` | `product + bias` | `[[19,22],[-57,50]]` |
| `result` | `relu(shifted)` | `[[19,22],[0,50]]` |

## 8. Stack operations

**Learning objectives**

- Manipulate stack values without introducing bindings.
- Use stack operations only when they clarify data reuse.

Maned defines `dup`, `swap`, `drop`, `over`, `rot`, and `-rot`.

```mnd
x dup matmul x_squared =
```

`dup` turns stack `[x]` into `[x, x]`; `matmul` then consumes both. Stack
operations are parsed into dedicated AST nodes. Prefer named intermediate
bindings when a longer stack sequence would be difficult to review.

## 9. Flows and clocks

**Learning objectives**

- Know that the flow is the only executable top-level definition.
- Read clock-partitioned work.

| Construct | Purpose | Status |
|---|---|---|
| `calc::lambda_flow` | Named inputs, computations, and returned values | **The** program unit — local runtime, dispatch, serve |
| `calc::lambda_symphony` | (historical) | **Rejected** (gap_002, E013) — it never executed; the definition errors at parse time |
| `calc::lambda_calculator(channels=N)` | (historical) | **Rejected** (gap_002, E014) — parsed for the location, nothing executes a calculator; use a flow |

Clock sections make logical stages explicit:

```mnd
calc::lambda_flow staged(a, b, c, d) {
    @clock(1):
    a b add left =
    c d mul right =
    @clock(2):
    left right add result =
} return result;
```

Status: **Local runtime** for this operation set. Clock 2 depends on values
created in clock 1. Clocks describe phases in the AST/dataflow model; they are not
a license to ignore data dependencies.

### Calling flows from flows (lang_051 semantics)

A flow calls another flow like any op — operands first, then the name; arity is
the callee's param count, and definition order does not matter (the flow table
is pre-scanned):

```mnd
calc::lambda_flow helper(a, b) {
    a b elemwise_add s =
} return s;

calc::lambda_flow top(x, y) {
    x y helper r =
} return r;
```

The decided v1 semantics (see RPN_SYNTAX_SPECIFICATION §11 for the full text):

- **Calls inline at compile time.** The callee's graph is spliced into the
  caller — zero runtime cost, identical local and remote.
- **A called flow is a helper**: it is not scheduled top-level (its params are
  bound at the call sites), and its `@device` decorator is ignored (lint
  W007). `--flow NAME` still runs a helper directly.
- **Recursion**: top-level stays a DAG; mutual recursion is always an error.
  A direct self-call needs `@unroll(n)`: bounded macro expansion, exactly `n`
  copies execute, and the innermost self-call passes its arguments through
  positionally (`returns[i] = args[i]`) — so put the recursion state in the
  returned positions:

  ```mnd
  @unroll(5)
  calc::lambda_flow power_step(h, w) {
      w h matmul h2 =
      h2 w power_step out =
  } return out;
  ```

  computes `W⁵·h`. The compiler warns if a returned position threads a param
  through unchanged (that output would equal the initial input).
- **One namespace, shadowing is an error**: a param or assignment target named
  like a flow, or any name matching a reserved word, is a redefinition error.

Status: **Working end to end** (lang_052): calls are inlined before the
dataflow graph is built, so they run locally and remotely today. Multi-return
calls must be the entire right-hand side of an assignment with one target per
return. Diagnostics: parse errors for unknown names, arity mismatch and
recursion; lint W007 for an ignored `@device`.

### Bounded iteration: `repeat(n)` (gap_023)

A loop whose trip count is known at compile time, expanded by the parser:

```mnd
calc::lambda_flow train(w) {
    repeat(5):
      w 2 mul w =
    end
} return w;
```

- `n` is a literal in **1..256** — the macro-expansion bound `@unroll`
  carries. It is deliberately a *different* limit from the IR value budget
  (4096 since gap_009); an over-budget expansion refuses with a message
  that names the repeat and both numbers.
- A name the body rebinds is **loop-carried** (last-wins): each iteration
  reads the previous iteration's value. Internally each iteration writes a
  fresh SSA name, so the expansion never trips W002.
- No dynamic counts, no `break`, no early exit — bounded and total, like
  the rest of the language. `repeat` is sugar over the same machinery
  `@unroll(n)` bounded recursion uses; both forms produce identical
  results.

### 9.4 `calc::ml::` — supervised learning as a first-class construct

Training a model by hand means writing the gradient-descent loop out of
`matmul`/`transpose`/`div` and managing the fixed-point scale at every step.
`calc::ml::<algorithm>` does that for you — and produces a **saveable
model**:

```mnd
calc::ml::linear_regression fit(X, y) {
    iters: 200,
    lr: 50,
    features: 3,
    fit_intercept: true,
    standardize: true
} return model, loss;

out::model = model("house.mnm");
```

The braces hold **hyperparameters**, not RPN statements. Values are
integers in the scaled domain (`lr: 50` at `quantres=3` means 0.05 — a
float here is refused, E022), `true`/`false`, or a flat list `[1, 10, 100]`
— a **sweep**: one configuration per value, round-robined across the
`@device(a, b, c)` aliases, returning one output set per configuration.
Only the numeric tuning knobs sweep (`lr`, `l2`, `iters`, `k`,
`max_depth`, `trees`, `seed`, and for the 2026-09-20 pair: `rounds`,
`eta`, `min_child_hess`); `features`, `fit_intercept`, `standardize`,
`budget`, `depth`, `bins`, `states`, `symbols`, `steps` and `rows` shape
the shared expansion and are refused as lists.

#### Reading the fit loss

The return list decides how much the fit reports back. One name per
configuration gives you the model; each further name adds a number:

| Returns | You get |
|---|---|
| `model` | the fitted model only |
| `model, loss` | …plus the final loss |
| `model, loss, loss_scale` | …plus the scale the loss is reported at |
| `model, loss, loss_scale, loss_before` | …plus the loss **before** fitting |

**The loss is reported at scale `2 × quantres`, not `quantres`.** A loss is a
residual, so it is small by construction and the better the fit the less room
it has: reported at `quantres = 2` every loss under 0.005 printed as `0`, and
three different fits were indistinguishable. `2 × quantres` is the loss's
natural scale rather than headroom invented for the purpose — the squared
error is already computed there, and was being divided back down only to match
the data's scale.

Name a third return and that scale arrives as a value, so nothing has to
assume the rule:

```mnd
calc::ml::linear_regression fit(X, y) {
    iters: 400, lr: 5, features: 2
} return model, loss, loss_scale, loss_before;
# at quantres=2:  loss = 16, loss_scale = 4, loss_before = 393750
#                 i.e. 0.0016, reported at 10^4, down from 39.375
```

**`loss_before` is how you tell a converged fit from a stalled one.** Only the
final loss is otherwise visible, so a fit that stopped improving immediately
and one that converged after 400 iterations look identical. If `loss` equals
`loss_before`, the fit moved nothing.

It also disambiguates a zero. A hinge loss of `0` on separable data is the
correct answer, not lost resolution — and a non-zero `loss_before` is what
tells you which of the two you are looking at.

When you sweep, the names repeat per configuration in the same order:
`return m0, l0, s0, b0, m1, l1, s1, b1;` for two configurations.

The eleven algorithm names are closed (E021 otherwise) and split in two
tiers:

- **Tier A — desugars to wire-legal primitives**: `linear_regression`,
  `logistic_regression` (integer-LUT `sigmoid`, bit-exact with workers),
  `svm` (hinge). The definition rewrites into a local init flow
  (standardization + the intercept column), a chain of gradient-descent
  *round* flows sized to the register budget, and a local epilogue that
  packs the model and reports the final `loss` (watch it: a stalled fit is
  visible there, not silent). `loss` is scale-q mean squared error — for
  `logistic_regression` the squared error of the *probabilities* (there is
  no `log` op, so it is not log-loss) — and mean hinge for `svm`. Route the rounds with `@device(alias)`;
  `--verify` proves the expansion bit-for-bit against the worker. The
  `features: <d>` hyperparameter is **required** — shapes are dynamic at
  compile time and β₀, the divisor tensors and the int32-overflow refusal
  all need the feature count. `budget: <slots>` sizes rounds for an ABI v1
  worker (256) instead of the v2 default (4096).
- **Tier A, the matmul-form pair (ML_PLAN_XGB_HMM)**: `xgboost` and
  `hmm` also desugar to wire-legal primitives — no native training
  kernels. `xgboost` (supervised, `fit(X, y)`, y ∈ {0, 10^q}) is
  09_xgboost.mnd's algebra generalized: a split *is* a matmul (the CUM
  "goes-left" matrix, the `(M∘G)ᵀ·CUM` histogram pair, gain elementwise,
  per-node argmax as a split-halving row-max fold with
  `max(a,b) = a + relu(b−a)` plus the U-triangle prefix-scan lowest-index
  tie-break). Hypers: `rounds: 8`, `depth: 3` (1..6), `bins: 8` (2..16),
  `eta: 0.3·10^q`, `l2: 10^q`, `min_child_hess: 0.75·10^q`, `features:`
  (required), `rows:` (optional — enables the exact `(10^q·rows/8)²`
  int32 refusal; ≈370 rows at q=3), `budget:`. `hmm` (unsupervised,
  `fit(O)` with O the `[sequences, steps]` symbol matrix, values
  `0..V−1` at scale q) is 10_hmm.mnd's scaled forward-backward: batch
  the sequences as rows and every Baum-Welch quantity is a matmul — the
  3-D ξ table never exists (`uᵀ·w` contracts it). Hypers: `states: 2`
  (2..16), `symbols:` and `steps:` (required, they shape the unrolled
  body), `iters: 4`, `seed: 0` (0 = the canonical asymmetric start —
  sticky A₀, 0.9-uniform B₀ rows with the leftover placed
  asymmetrically; a nonzero seed perturbs B₀ ±5% via splitmix64, and
  since EM converges to a fixed point of its start, the seed is part of
  the model's provenance), `rows:`, `budget:`. Requires `quantres` 2..3
  (the α/β renormalization scale 10^(q+1) must square inside int32).
  Both chunk **one flow per boosting round / EM iteration** sized to the
  register budget and chained through wire values, so `rounds:` and
  `iters:` are unbounded by the register file — the exact cap that
  stopped the hand script at 4 EM iterations. Every full-shape constant
  is derived in-flow by the `ones_like` idiom (`x x ==` then
  `scalar_mul`), which is also what fits an EM iteration in **5** MNPK
  params. Second return: `xgboost` = scale-q MSE of the final
  probabilities; `hmm` = `score`, the final mean scale factor c̄
  (monotone non-decreasing under EM — a fit-quality trace, one `log` op
  short of the true log-likelihood, so not one). Routing economics,
  measured on the live 2-worker fleet: a routed chain LOSES (~40× for
  xgboost — boosting rounds are hard sequential barriers; no crossover
  for hmm at any batch size — bark is ~6× slower per unit work), so
  train local-first and use `@device` + `--verify` for correctness
  proofs or to free the coordinator; the parallelism that pays today is
  the **sweep**. Labels: `hmm` fits unsupervised and does NOT align
  state labels — EM is identifiable only up to a permutation, and
  `ml_predict` returns the fitted labeling.
- **Tier B — native, coordinator-only**: `kmeans` (+`k`, `iters`), `knn`
  (+`k`), `naive_bayes`, `decision_tree` (+`max_depth`, `min_samples`),
  `isolation_forest` (+`trees`, `max_depth`, `seed` — a private seedable
  splitmix64, bit-identical everywhere). These train through the `ml_fit` op, which has
  no wire opcode, so `@device` on them is refused honestly. `kmeans`,
  `knn` and `naive_bayes` accept `standardize` too, but here it defaults
  to **false** (Tier A defaults to true — the GD numerics need it; a
  distance or count model merely benefits). `pca` is reserved and
  refuses: `eigendecomp` has no evaluator yet.

A fitted model is one rank-1 integer descriptor vector (magic, version,
algorithm, `quantres`, feature count, flags, payload) — it prints, ships
over MNPK, and persists via the `model("path.mnm")` file format (raw
little-endian int64 slots + checksum, never quantizer-encoded). Inference
is the `ml_predict` op:

```mnd
in::model = model("house.mnm");
in::Xn    = csv("new.csv");

calc::lambda_flow run(model, Xn) {
    model Xn ml_predict yhat =
} return yhat;
```

`ml_predict` applies the model's recorded standardization, refuses a
`quantres` mismatch, and returns: scale-q predictions (linear), scale-q
probabilities (logistic), ±1·10^q classes (svm), cluster indices (kmeans),
the stored labels (knn / naive_bayes / decision_tree), scale-q expected
path lengths, lower = more anomalous (isolation_forest), scale-q
probabilities from the native tree walk (xgboost — descend `depth` levels
on `x ≤ threshold`, sum the eta-shrunk leaf logits, sigmoid), or the
posterior-decoded state indices `[sequences, steps]`, raw `0..K−1`
(hmm — a native scaled forward-backward whose truncating arithmetic
mirrors the fit flows step for step, so decoding the training data
reproduces the in-graph decode exactly; the step count is free at predict
time).

Defaults, when a key is omitted: `iters: 200`, `lr: 10^quantres / 20`
(0.05 real, floored at 1), `l2: 0`, `fit_intercept: true`,
`standardize: true` (Tier A) / `false` (Tier B), `k: 3`, `iters: 20`
(kmeans), `max_depth: 8` and `min_samples: 2` (tree), `trees: 50`,
`max_depth: 10` and `seed: 42` (forest); `rounds: 8`, `depth: 3`,
`bins: 8`, `eta: 0.3·10^q`, `l2: 10^q`, `min_child_hess: 0.75·10^q`
(xgboost); `states: 2`, `iters: 4`, `seed: 0` (hmm). `{}` is a legal
block — all defaults (except the required keys: `features` for the GD
family and xgboost; `symbols` and `steps` for hmm).

Two integer-GD facts worth internalizing: `lr` scales the **summed**
gradient (there is no 1/n), so larger datasets want a smaller `lr`; and
below ~`10^-quantres` of gradient resolution the update rounds to zero and
training stalls — `standardize: true` (the default) plus the reported
`loss` are the guard rails.

## 10. Decorators and object parameters

**Learning objectives**

- Attach metadata to supported targets.
- Keep compile-time options separate from runtime operands.

The DecoratorRegistry is the single decorator truth (gap_021); each entry
carries an honest `implemented` flag. There is **no `checkpoint` decorator**
— it never existed (the old table here was wrong).

| Decorator | Target | Args | Status |
|---|---|---|---|
| `@clock(n)` | block | required | **Working** — scheduling phases (clock sections) |
| `@device(alias)` | any | required | **Working** — routes the statement/flow to a declared worker |
| `@unroll(n)` | definition | required bound 1..256 | **Working** — bounded self-recursion, macro-expanded |
| `@quantize{...}` | statement | required | Recognized, **no effect yet** — lint W012 |
| `@tile{...}` | statement | required | Recognized, **no effect yet** — lint W012 |
| `@autodiff` | definition | optional | Recognized, **no effect yet** — lint W012 |
| `@prefetch{...}` | statement | optional | Recognized, **no effect yet** — lint W012 |

An unknown decorator name is lint **error E008** with a nearest-name
suggestion (the old "unknown names are accepted as user decorators"
loophole is closed — gap_003).

```mnd
@autodiff
calc::lambda_flow network(x, weights) {
    @tile {tile_m: 2, tile_n: 2, tile_k: 2}
    x weights matmul output =
} return output;
```

This parses and runs; the two inert decorators each draw a W012 note so the
no-op is visible.

Object parameters use `{key: value}` and may contain literals, identifiers,
tuples, tensors, and lists. Duplicate keys produce lint warnings.

## 11. Combinators (and the retracted lambda forms)

**Learning objectives**

- Know which combinators exist, and in which contexts.
- Know that anonymous lambda syntax is retracted.

The anonymous lambda forms (`x => body` and `lambda x => ... end`) are
**RETRACTED** (gap_002, parse error E017): the grammar and spec claimed
them but the parser never constructed a lambda node, so programs using
them silently degraded. Define a `calc::lambda_flow` instead. `lambda`
and `end` stay reserved words.

Bird combinators — the per-name truth (gap_028 decision: the implemented
four stay an **evaluator implementation detail**; no surface exposure
until a campaign needs it):

| Combinator | State |
|---|---|
| `identity`, `kestrel`, `kite`, `compose` | **Internal-only** — implemented as evaluator terms, reachable from `.mnd` only where the lambda evaluator is engaged; statement-context use errors "not reachable from this context" |
| `mockingbird`, `bluebird`, `cardinal`, `starling`, `thrush`, `warbler`, `owl`, `bluebird_prime`, `blackbird`, `psi`, `phoenix`, `vireo` | **Reserved** — no implementation anywhere; statement use errors "reserved but has no implementation" (lang_058) |
| `ycombinator` | **Reserved, and cannot become a term** under the strict evaluator — it would diverge; it needs call-by-name or a fuel-bounded fixpoint first. Do not file "implement ycombinator" as a small ticket. |

## 12. Printing, memory, devices, and backpropagation

**Learning objectives**

- Recognize side-effecting and device-oriented statements.
- Avoid confusing printed `return(...)` with a flow return clause.

| Form | Meaning/status |
|---|---|
| `return(value);` | Print statement (top level); in a flow body it is not executed — lint W010 |
| `} return result;` | Flow output clause |
| `value memory::write` | Memory write; top level. In a flow body: parsed, not executed (W010, with a real location since gap_019) |
| `device::alias { host = ...; }` | **The** worker declaration (lang_044) — see below and the usage guide |
| `mnd::device::fpga { ... }` | **Rejected** (gap_002, E016) — legacy form; the error carries a migration hint to `device::alias` |
| `loss mnd::backpropagation { ... } ... =` | **Rejected** (gap_002, E015) — reserved for a future autodiff phase, not implemented |

`status::alias;` is a host-side query that prints a declared worker's
`GET /api/status` metadata (uptime, op set, max payload) — not a dataflow
op; it runs in the CLI driver. If the alias did not resolve, the error is
targeted at that alias (gap_019).

Script device declarations and flow routing interact with remote discovery and
dispatch. See the [usage guide](13_MANED_USAGE_GUIDE.md) before attempting
device execution, then work through the
[remote worker guide](15_REMOTE_WORKER_GUIDE.md) for complete programs.

### The local Bark VM (`host = "local"`)

A device block may name the reserved host `local` to route its flows to the
Bark VM — a hosted build of the real bark worker executor — with no network
and no credentials:

```maned
device::rex { host = "local"; }

calc::lambda_flow multiply(a, b) @device(rex) {
    a b matmul result =
} return result;
```

Everything else is unchanged: dependency chaining, `--verify`, pre-flight
refusals. A running `maned-bark-here` terminal instance serves the jobs
(and shows them on its console); otherwise a headless `bark-vm` is spawned.
An unreachable network device also falls back to the VM automatically, with
a notice (`--no-vm-fallback` disables this). See the
[remote worker guide](15_REMOTE_WORKER_GUIDE.md), Section 14.

### The execution model is int32 wrap-around

Every op result — locally, on the Bark VM, and on hardware workers — is
truncated to a 32-bit two's-complement integer: values wrap mod 2^32, they
never saturate and never error by default (with one exception, below). This is
a deliberate contract, not an artifact: wrapping addition is associative and commutative (sum mod
2^32 is an abelian group), which is what lets workers reorder tiled and
sliced matmuls while staying bit-exact, and what makes `--verify` an exact
equality check on every machine.

The practical consequence: a matmul over large values can silently wrap
(the classic symptom is an impossible number, e.g. a negative eigenvalue
from a PSD matrix). Bound your operands from the declared quant range
before deep chains, and rescale an operand when an intermediate can exceed
±2^31.

**The one exception: `packed_matmul` refuses instead of wrapping.** Every
other op wraps because wrapping addition is associative — the answer stays
correct mod 2^32 no matter how the work is reordered. `packed_matmul`'s
rescale **divides**, and division does not commute with wrapping: a wrapped
partial divided by 10^s is not congruent to the truth mod 2^32, it is simply a
different number. So the kernel bounds `max|X| · |Q|max · block` up front and
**refuses** past it, rather than returning a value that would be silently
unrelated to the answer:

```
packed_matmul: activation magnitude ... is too large for a block partial to
hold ...; rescale x before the multiply
```

That refusal is the contract working, not a limitation of it — it is the one
place where wrapping would break the property the contract exists to provide.
It is also coordinator-only today: the packed tier has no binary-IR opcode, so
a worker refuses `packed_matmul` outright.

To find a wrap instead of diagnosing its symptoms, run locally with
`maned-run script.mnd --trap-overflow`: the first op whose raw result
leaves int32 fails the run, attributed to the op and the name it binds
(`overflow trap: op 'mul' (value v1 -> 'big') element 0 is
10000000000...`). The flag is a local debug instrument only — workers and
the Bark VM always wrap, so it is refused together with `--device` or
`@device` routing, and it never changes values: a run that passes under
the trap is bit-identical to one without it.

### Rounding: four rules, plus one narrowing

Integer division appears all over the interpreter, and it does **not** round
the same way everywhere. The last row below is a narrowing rather than a
rounding, and is listed because it decides the final value just as the other
four do. The differences are each defensible, none of them is
inferable from the op name, and until gap_067 only one of them was documented
anywhere — inside a single cell of the operations table. All are pinned by
tests; the point of this table is that you should not have to read the source
to know which one an op uses.

| Rule | Where | Why that rule |
|---|---|---|
| **Truncate toward zero** | elementwise `div`; `tensor_mean` (whole-tensor and per-axis) | C++ `/` on integers. The accumulator is i64 and the divide happens *before* the narrowing to i32 — narrowing first would diverge on any sum exceeding int32. |
| **Half to even** | `packed_matmul`'s rescale, `P / 10^s` | The rescale point of the packed contract: it runs once per block partial, and half-to-even is the only rule that does not accumulate a bias over many blocks. **Every device must do exactly this**, which is why it is the one rounding rule the ops table already named. |
| **Half away from zero** | `sqrt` | The result is a scaled fixed-point value the caller reads as a decimal, so it rounds the way a person expects a decimal to round. |
| **Floor** | `isqrt`, and `cnrm_isqrt` in the normalization kernels | `isqrt` is the *integer* square root — floor is its definition, not a rounding choice. It is a different op from `sqrt` on purpose. |
| **Truncate mod 2⁶⁴** *(narrowing, not rounding)* | the return of `div_pow10_half_even`, the 128-bit widened divide in the packed path | The divide itself rounds half to even, bit-identical to `rescale_half_even` (a test pins the two against each other over a remainder-boundary corpus). What this row names is the `__int128 → int64` return: callers that need the quotient to fit must bound their inputs first. |

Two consequences worth stating outright:

- **`sqrt` and `isqrt` round differently.** They are adjacent ops running the
  same Newton iteration, and they disagree on the last digit by design: `sqrt`
  rounds half away from zero, `isqrt` floors. If you want the integer square
  root, ask for `isqrt`; do not round `sqrt` yourself.
- **Elementwise `div` by zero yields `0`**, it does not error. That is the
  interpreter's behaviour today and it is deliberate — a zero divisor in a
  tensor lane is data, not a program fault, and trapping would make every
  masked expression unusable. Mask before dividing if zero is meaningful.

### Table domains: where saturation is the answer, and where it is a lie

`sigmoid`, `tanh`, `exp` and `softmax` are evaluated through sampled
fixed-point lookup tables, each defined on a finite domain. Outside it the
lookup **saturates to the end entry**. For three of the four that is correct;
for one it was a silently wrong number until gap_068.

| Op | Domain | Outside it |
|---|---|---|
| `sigmoid` | [−16, 16] | saturates — and that **is** the answer: `sigmoid(16)` and `sigmoid(100)` differ by less than one unit of the output scale at every `quantres`. |
| `tanh` | [−8, 8] | saturates, same argument. |
| `softmax` | [−16, 0] | unreachable: the kernel subtracts the row max first, so its input is ≤ 0 by construction. |
| **`exp`** | **[−16, 7.616]** | **above: refuses.** Below: saturates to `0`, which is correct — `exp(−16)` rounds to zero at the table's scale, so saturation converges on the true limit. |

`exp` is the one op in the family whose true value leaves the domain and keeps
growing, so saturating returns a number that is not merely imprecise but
unboundedly wrong: before gap_068, `exp(8)`, `exp(20)` and `exp(100)` all
returned `exp(7.616)`, with no error and no note. It now refuses, naming the
offending element and the bound — the same choice `sqrt` makes on negative
input.

**The bound belongs to the table, not to your `quantres`.** The domain stops
where `exp(r) × 10⁶` stops fitting the `int32` the table is stored in, so it is
7.616 regardless of the scale you declared. One consequence is worth knowing
before it surprises you: at `quantres = 0`, `exp 8` refuses even though 2981
would have fit the register comfortably. A refusal naming the bound was judged
better than a wrong number; widening the domain by range reduction is recorded
as a follow-on, not a promise.

### Reading and writing files (lang_061-064)

Programs read data files as inputs and write results back out — all on the
coordinator (workers never see a file). Format keywords are contextual to the
`in::`/`out::` value position:

```maned
mnd::quantmax=30000; mnd::quantmin=-30000; mnd::quantres=2;

in::x = csv("data/train.csv");      # numbers -> quantized [rows, cols]
in::im = image("photo.png");        # 8-bit PNG/JPEG/BMP -> [H,W] / [H,W,C]

calc::lambda_flow score(x, im) {
    x transpose xt =
} return xt;

out::xt = csv("results.csv");       # decoded via quantres; round-trips
out::im = image("copy.png");        # values clamped 0..255, with a note
```

`csv`/`parquet` numbers cross the quant boundary like literals
(`quantres=2` turns `3.14` into `314` and back on write); `text`/`image`
are raw bytes 0..255, never scaled. `parquet(...)` reads flat numeric
columns (Snappy or uncompressed). An `out::` name must be a flow return, an
`in::` input, or a `frame::` — writing an input back out is the idiom for
format conversion. `--in name=...` overrides a file-sourced input,
`--out name=PATH` overrides where an `out::` writes; lint W009
flags two `out::` writing the same path.

**Tensor files (`.dqt`).** A dqtensor file (lang_111/112) is the integer-
native tensor container: every payload value is already a decimal-scaled
integer at a per-tensor `scale_pow10`, verified end to end (crc32 per tile,
sha256 per tensor). Both directions take the two-argument shape — a shard
holds many tensors, so the name is not optional:

```maned
in::w  = dqt("weights.dqt", "model.layers.0.w");  # exact integer rescale
out::t = dqt("results.dqt", "model.t");           # written at the program
out::u = dqt("results.dqt", "model.u");           # quantres, ONE file
```

Reading never crosses the FP quant boundary: the file's integers are shifted
EXACTLY to the program `quantres` (multiplying up refuses on int64 overflow,
E027; dividing down rounds half-even with every inexact division counted in
a note; a shift beyond ±18 refuses). A refused file — bad magic, corrupt
tile, checksum mismatch — surfaces as E026 carrying the dqtensor code
verbatim. On `out::`, every `dqt(...)` directive naming the same path is
collected into ONE canonical multi-tensor file (so W009 does not apply to
dqt); two directives exporting the same tensor name refuse with E028.
`safetensors(...)`/`packed(...)` remain the read-only shard loaders; `.dqt`
is the export format, and the same file round-trips bit-identically.

**Converting model weights (`tensor::ingestion`).** Ingestion converts a
file — or a folder tree, recursively — of model weights into maned's
integer world, at one folder-wide decimal scale (full-precision places +
`quantres` headroom zeros):

```maned
tensor::ingestion("llama_f16/", "llama_dqt/", quantres=2, format="dqt");
```

The named arguments are order-free. `format` picks the output container:
`"safetensors"` (default — the I64 twin, 2× the float source) or `"dqt"`
(typically **smaller than the float source**; the notes print a compression
receipt: source vs I64-equivalent vs `.dqt` bytes, plus the peak in-memory
payload). Inputs are detected by magic bytes, never extension trust:

- **safetensors** — any float dtype through the exact decimal scan; integer
  dtypes pass through (scale 0 in dqt output, natural logical width).
- **`.npy`** — NumPy v1–v3, C-order little-endian numeric dtypes; the one
  tensor is named after the file's basename. Fortran order, big-endian and
  object dtypes refuse by name; `.npz` is skipped with the unzip
  workaround named.
- **`.gguf`** — llama.cpp models, v2/v3: unquantized tensors
  (F32/F16/BF16/F64, I8..I64) plus dequantized Q4_0/Q4_1/Q5_0/Q5_1/Q8_0
  and the Q4_K/Q6_K pair (the `Q4_K_M` family). Dequantization is
  bit-identical to llama.cpp's own (fixture-pinned against the real ggml
  code); every dequantized value is an exact binary rational, so the
  decimal scan loses nothing. Other quant types refuse by name with the
  `llama-quantize` re-quantize workaround.

Tensor names are mangled to the dqt charset (`[A-Za-z0-9_.+-]`, invalid
bytes → `_`); a post-mangle collision refuses the file rather than silently
merging tensors.

**Selecting columns at ingest.** A second string on `csv(...)` reads only the
columns you name, which is the difference between loading a working set and
loading a file — and it happens before quantization, so an unselected column
never occupies a register.

```maned
in::xy = csv("big.csv", "alpha,gamma");   # by name, needs a header row
in::ab = csv("big.csv", "1,3");           # by 1-based position
in::r  = csv("big.csv", "gamma,alpha");   # the SELECTOR's order, not the file's
```

A selector is a **position** if it is all digits and a **name** otherwise.
That is the only rule that serves both kinds of file: names need a header row,
and a headerless file can be addressed no other way. The cost is that a column
literally named `2` is reached by its position rather than its name.

Anything that cannot be resolved is **refused, naming what was available** —
an unknown column, a name against a headerless file, or a position past the
last column. A narrower frame is never produced silently. Omit the second
string and every column is read, exactly as before.

Column *types* are deliberately not selectable: the language has one global
integer scale (`mnd::quantres`), so a per-column dtype would have nowhere to
live.

**What each `out::` format can write depends on what the name refers to**, and
the two sets are different (gap_010):

| `out::` names a | Can be written as | Notes |
|---|---|---|
| a tensor (flow return or `in::`) | `csv`, `text`, `image` | `parquet` is refused by name |
| a `frame::` | `jsonl`, `parquet`, `csv` | anything else is refused by name |

```maned
frame::f  = jsonl("docs.jsonl");
out::f    = parquet("table.parquet");   # the whole table, presence preserved
out::f    = jsonl("table.jsonl");       # round-trips absence exactly
out::xt   = csv("tensor.csv");          # a flow return
```

The presence mask survives the round trip where the format can express it:
`jsonl` simply omits an absent field, and `parquet` carries `.present`
columns. **`csv` cannot** — it renders an absent cell as an empty field, which
is the one lossy writer here, so prefer jsonl or parquet when absence matters.

Asking for the wrong pairing is an error naming the mismatch, not a silent
no-op — `out::xt = parquet(...)` on a tensor says *"parquet(...) writes a
FRAME, and 'xt' names no frame:: declared in this script"* and the run exits
non-zero.

### Serving flows as an API (lang_066-068)

`maned-serve` turns the same `in::`/`out::` contract into a live HTTP API —
the FastAPI role, dependency-free, on exactly maned-run's engine (local
flows and `@device`-routed plans alike):

```
$ maned-serve model.mnd --port 8080        # --host 0.0.0.0 to expose
routes: GET /health, POST /run, POST /run.json  (inputs: h0 w? | outputs: a t)

$ curl localhost:8080/health                  # the contract, as JSON
$ curl -X POST localhost:8080/run -F h0=@batch.csv -o result.csv
$ curl -X POST localhost:8080/run.json -d '{"h0": [[3,1],[2,4]]}'
{"outputs":{"a":[[7,9],[2,4]]},"notes":[]}
```

The script is parsed and validated once at startup; a request only supplies
data. Script `in::` literals and files are defaults a request may override
(the `--in` rule); a `?` in the routes line marks an input with a default.
When the data always comes from the request — an API's image is never a file
on the server — declare the wire format alone with empty parens:
`in::img = image();`.

### Answering with a profile instead of a tensor

A `profile::name;` directive puts the matrix *descriptor* in the response
rather than the values, so a script can answer "what is this matrix". This
decomposes an uploaded image into its colour channels and profiles each:

```maned
in::img = image();                        # arrives with the request

calc::lambda_flow decompose(img) {
    img { axis: 2, index: 0 } slice red =     # [H,W,C] -> [H,W]
    img { axis: 2, index: 1 } slice green =
    img { axis: 2, index: 2 } slice blue =
} return red, green, blue;

profile::red;
profile::green;
profile::blue;
```

```
$ curl -X POST localhost:8080/run -F img=@photo.png
{"red":{...},"green":{...},"blue":{...}}
```

`slice` takes one index off an axis and drops that axis (the inverse of
`concat`), which is what turns a channel-last image into plain matrices.
The profiles travel as one JSON document — a descriptor set is a single
answer — so a profile-only script replies `application/json` on both routes,
and a script with `out::` too gets a `profiles` part beside its tensor parts.
Each descriptor is the same document `maned-run --profile-json` prints.
Tier 2 (rank, eigenvalues, definiteness) is O(n³) and is skipped above
256×256, so large photos still answer, with the structural tier only.
In serve mode `out::` values travel to the client instead of disk: one
`out::` is the raw response body (text/csv, text/plain, or image/*), several
come back as multipart parts named after their `out::`. JSON numbers cross
the quant boundary like csv; text/image bytes stay raw. Errors keep the
honesty rules — 400 carries the reader's own refusal ("in 'h0': line 3 ..."),
unknown inputs get a did-you-mean, execution failures are a 500 with the
engine's message, and clamp/header notes arrive in the `X-Maned-Notes`
header (or the JSON `notes` array). Requests are handled one at a time by
design: the workers underneath are single-context machines.

### Dataframes: many JSON documents, one table (lang_074-078)

`frame::` builds a columnar table from JSON documents that need not share a
shape. The column set is the **union** of every document's fields, and a
document that lacks a field contributes an *absent* cell rather than a zero:

```maned
frame::f = jsonl("docs.jsonl");   # or jsonl() to take them from the request
                                  # or profiles() for this run's descriptors
in::x = f.values;                 # [rows, cols] integers
in::m = f.present;                # [rows, cols] of 0/1 - which cells are real
```

```
{"potato": 5, "rank": 2}          values        present
{"rank": 3, "trace": 41}     ->   [[5, 2,  0],  [[1, 1, 0],
                                   [0, 3, 41]]   [0, 1, 1]]
```

Nested objects flatten to dotted paths (`dimensions.rows`) and arrays to
indexed ones (`shape.0`). Booleans become 0/1, strings are dictionary-encoded
to integer codes, and numbers cross the same quantiser boundary as CSV — so
every field lands in one integer matrix a flow can consume. Projections are
`f.values`, `f.present`, `f.shape` and `f.missing`; column names and string
dictionaries are text, so they live in the frame's schema JSON instead.

**The presence mask is not optional bookkeeping.** Integer tensors have no
NaN, and every sentinel you might pick collides with real data — `trace` is
legitimately 0, `is_sparse` is legitimately false. `f.values` holds 0 where a
cell is absent, and that 0 means nothing without `f.present`.

A column that mixes strings and numbers is refused by name rather than
coerced. Widening is safe and automatic: bool → int → double.

### An image dataset as a frame: `images()` (gap_026)

`images("glob")` reads a whole directory of images coordinator-side and lays
them out as one row per file:

```maned
frame::ds = images("data/*.png");
in::x  = ds.values;               # one row per image
in::px = ds cols("px0", "px1");   # or project individual pixels
```

Columns are `path` (string-coded), `width`, `height`, `channels`, then `px0`,
`px1`, … one per pixel of the decoded image. Files are decoded through the
same reader a single `in::x = image(...)` uses, so the pixel semantics are
identical — raw bytes 0..255, never scaled.

Two refusals are deliberate:

- A glob that **matches no files** is an error, not an empty dataset. An empty
  training set is never what anyone meant.
- **Shapes must be uniform** across the batch. The first mismatch refuses by
  name and prints both shapes, so an accidentally-ragged dataset cannot be
  silently batched into meaningless columns. Split the glob or resize the odd
  file.

Matches are sorted into lexicographic path order before reading — the same
determinism rule `profiles("glob")` follows, so a dataset's row order does not
depend on the filesystem.

### Reshaping a frame: `filter`, `cols`, `group`, `merge`, `onehot`

A `frame::` declaration can derive a new table from frames declared above it,
rather than only from a source. Five verbs:

```maned
frame::f = jsonl("docs.jsonl");
frame::g = jsonl("labels.jsonl");

frame::warm  = f filter("temp", "gt", 30);     # select ROWS by one column
frame::small = f cols("rank", "trace");        # project columns, in this order
frame::tot   = f group("k", "sum", "v");       # one row per distinct k
frame::both  = f g merge("id");                # inner join on a shared key
frame::wide  = f onehot("category");           # string column -> indicator columns
```

- **`filter(column, comparison, value)`** keeps the rows where the comparison
  holds. `comparison` is one of `eq`, `ne`, `lt`, `le`, `gt`, `ge`. Compare a
  numeric column against a number and a string column against a quoted string
  — the mismatch is refused by name, because a dictionary code and an integer
  cell are the same type in the buffer and only you know which you meant.
  String columns accept `eq`/`ne` only: ordering them would order by
  dictionary insertion, which is not an order anyone asked for.
  A row whose filter column is **absent is dropped**, including by `ne` — an
  unknown value cannot be shown to satisfy a predicate, and it is not evidence
  of difference either. Every surviving row keeps every column and its mask;
  dropping a column is what `cols` is for.
- **`cols(...)`** selects columns by name, in the order given.
- **`group(key, agg, value)`** takes exactly three arguments. `agg` is one of
  `sum`, `mean`, `count`, `min`, `max`. Absent *key* cells skip the row;
  aggregates are computed over present cells only, and a group in which every
  cell is absent produces an **absent** output cell rather than a 0 — the
  presence mask survives aggregation, which is the whole point of having one.
- **`merge(key)`** takes two base frames and is **inner-only**: all matching
  pairs, and rows with an absent key are skipped. Duplicate non-key column
  names are refused by name rather than silently renamed.
- **`onehot(col)`** expands a string column into indicator columns. It needs a
  genuine String column and caps cardinality at 256, so a free-text field
  fails loudly instead of producing thousands of columns.

Each verb refuses with the frame's name and the specific problem
(`frame::tot: group needs (key, agg, value), ...`), so a malformed derivation
never silently yields an empty table. A `filter` that matches nothing is *not*
an error — it yields an empty frame that still carries the schema.

Over HTTP the documents can come from the request, and `profiles()` closes
the loop the arc was built for — profile many matrices, get one feature
table:

```maned
profile::red; profile::green; profile::blue;
frame::features = profiles();     # 3 rows x 132 columns of matrix properties
```

When a script declares a frame, two more routes appear — the same run as
`/run`, rendered as the table instead of the tensors:

```
$ curl -X POST localhost:8080/frame     -F img=@photo.png   # json records
[{"basic_id.name":"red","linear_algebra.trace":42, ...}, ...]

$ curl -X POST localhost:8080/frame.csv -F img=@photo.png   # header + rows
basic_id.name,dimensions.rows,linear_algebra.trace, ...
red,3,42, ...
```

Values come back **decoded** — dictionary codes as their strings, 0/1 as
booleans, doubles through the quantiser — because a caller asking for the
table wants the data, not the encoding. An absent cell is JSON `null` or an
empty CSV field. Records are rectangular and pandas-ready
(`pd.DataFrame(resp["features"])`); use `/frame.csv` for large tables, since
records repeat every column name on every row.

A value too large for `mnd::quantmax`/`quantmin` is clamped, **counted, and
reported** in `X-Maned-Notes` and the frame schema — a clamped number is a
wrong number, so it never passes silently.

Ingest streams: documents are split from a chunked reader and scanned into
leaf events without building a tree, so peak memory is one document plus one
chunk regardless of file size. Measured at 200k rows x 11 columns in 223 ms
(170 MB/s of JSON), with the table at 22.3 MB against 37.9 MB of text.

## 13. Style and debugging guidelines

- Use one operation per assignment while learning.
- Choose names that describe values (`product`, `activated`, `total`), not steps.
- Keep quantization directives together at the top.
- Make matrix shapes obvious in comments or input documentation.
- Prefer checked-in, deterministic examples.
- Run `maned-lint` before execution.
- Read an “unsupported op” error as a backend capability issue, not necessarily
  invalid language syntax.
- When debugging RPN, write the stack after every token.

## 14. Progressive labs

### Lab 1: scalar pipeline

Write a flow computing `(a + b) * c`. Predict the result for `a=2`, `b=3`, `c=4`.

### Lab 2: activation pipeline

Extend the `layer` flow above so it also returns `tensor_sum(result)` as
`total`.

### Lab 3: clocked graph

Write a two-clock flow where clock 1 independently computes `a+b` and `c*d`,
and clock 2 adds both intermediate results.

### Lab 4: capability review

Classify `relu`, `conv2d`, a device block, and `@autodiff` using this guide's
feature-status labels. Explain why parse support alone is insufficient.

## 15. Solutions

### Lab 1

```mnd
calc::lambda_flow arithmetic(a, b, c) {
    a b add sum =
    sum c mul result =
} return result;
```

The result is `20`.

### Lab 2

```mnd
shifted relu result =
result tensor_sum total =
} return result, total;
```

With the guide's sample inputs, `total` is `91`.

### Lab 3

```mnd
calc::lambda_flow staged(a, b, c, d) {
    @clock(1):
    a b add left =
    c d mul right =
    @clock(2):
    left right add result =
} return result;
```

### Lab 4

- `relu`: local + remote runtime.
- `conv2d`: local + remote runtime (the sliced/tiled kernels landed in the
  bark algebraic-op expansion; the old answer "not implemented locally" is
  itself the kind of doc drift this guide's op table now prevents).
- Device block: device/dispatch path, with Bark VM fallback.
- `@autodiff`: registered, `implemented=false` — recognized but inert
  (lint W012); no autodiff execution is implied.

For complete functional numerical programs, see the Markov-chain, Hidden Markov
Model, and Kalman examples in the
[remote worker guide](15_REMOTE_WORKER_GUIDE.md).

## Glossary

| Term | Meaning |
|---|---|
| RPN/postfix | Operands precede the operation that consumes them. |
| Flow | Named computation with inputs and returned bindings. |
| Binding | A name assigned to a computed value. |
| Dataflow graph | Dependency graph produced from a parsed flow. |
| Backend | Interpreter, MLIR transformation path, or remote device worker. |
| Quantization | Mapping values into a constrained numeric representation. |
| MNPK/MNRS | Maned remote request/response binary formats. |
