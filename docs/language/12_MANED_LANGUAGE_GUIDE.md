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

This table is sourced from the executability sets in
`maned_lang/include/maned/ops/executable_ops.h` (gap_005) — the same
truth lint's W011 rule reads, test-pinned against the evaluator modules and
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
| Math, local only | `exp`, `sqrt`, `isqrt`, `abs`, `clip`, `argmax` | yes | **no** |
| Linear algebra, local only | `determinant`, `adjugate` | yes | **no** |
| Profiling, local only | `profile_vector` | yes | **no** |
| Constructors, host-side | `zeros` `ones` `full` `eye` `diag` `range` `random` `band` `tridiag` `from_spectrum` `synth` | `in::` initializer position | n/a |
| **Registered, not executable** | `tensor.init` `txt.read` `adaptive_avgpool2d` `cholesky` `clip_gradient` `conv1d` `conv3d` `cross_entropy` `eigendecomp` `embedding_lookup` `fft` `fft2d` `gelu` `get_timestamp` `groupnorm` `ifft` `instancenorm` `inverse` `lu` `multihead_attention` `qr` `s4_layer` `scaled_dot_attention` `selective_scan` `silu` `softplus` `svd` | no — lint warns **W011**, run refuses | no |

As of 2026-09-18 that is 79 registry ops: 31 run both places, 21 run locally
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
in::rd = 4 4 random;           # deterministic pseudo-random fill
in::b  = 5 1 1 9 band;         # n lower upper fill
in::t  = 5 1 2 3 tridiag;      # n sub diag super
in::sp = [4, 1] from_spectrum; # eigenvalues -> matrix with that spectrum
in::sy = { rows: 4, cols: 4, symmetric: true } synth;  # properties -> matrix
```

### Worker-contract limits (the real numbers)

Enforced identically by maned-run and maned-lint (gap_014, `ELIMIT`),
from `maned_lang/include/maned/ir/limits.h`:

- **Register-file slots — 256 or 4096, depending on the worker.** A flow may
  compile to at most that many values post-inline (params + consts + ops).
  ABI v1 used u8 value ids (`kRfSlots` = 256); ABI v2 (gap_009) widened them
  to u16 with `kRfSlotsV2` = 4096. The budget checked is the one the *target*
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
./maned-run maned_lang/tests/cli/matmul_relu.mnd \
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
| `identity`, `kestrel`, `kite`, `compose` | **Internal-only** — implemented as lang_017 evaluator terms (`src/interp/lambda.cpp`), reachable from `.mnd` only where the evaluator is engaged (see `example_lambda_birds.mnd`); statement-context use errors "not reachable from this context" |
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
never saturate and never error by default. This is a deliberate contract,
not an artifact: wrapping addition is associative and commutative (sum mod
2^32 is an abelian group), which is what lets workers reorder tiled and
sliced matmuls while staying bit-exact, and what makes `--verify` an exact
equality check on every machine.

The practical consequence: a matmul over large values can silently wrap
(the classic symptom is an impossible number, e.g. a negative eigenvalue
from a PSD matrix). Bound your operands from the declared quant range
before deep chains, and rescale an operand when an intermediate can exceed
±2^31.

To find a wrap instead of diagnosing its symptoms, run locally with
`maned-run script.mnd --trap-overflow`: the first op whose raw result
leaves int32 fails the run, attributed to the op and the name it binds
(`overflow trap: op 'mul' (value v1 -> 'big') element 0 is
10000000000...`). The flag is a local debug instrument only — workers and
the Bark VM always wrap, so it is refused together with `--device` or
`@device` routing, and it never changes values: a run that passes under
the trap is bit-identical to one without it.

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
format conversion. `--in name=...` overrides a file-sourced input; lint W009
flags two `out::` writing the same path.

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

### Reshaping a frame: `cols`, `group`, `merge`, `onehot`

A `frame::` declaration can derive a new table from frames declared above it,
rather than only from a source. Four verbs:

```maned
frame::f = jsonl("docs.jsonl");
frame::g = jsonl("labels.jsonl");

frame::small = f cols("rank", "trace");        # project columns, in this order
frame::tot   = f group("k", "sum", "v");       # one row per distinct k
frame::both  = f g merge("id");                # inner join on a shared key
frame::wide  = f onehot("category");           # string column -> indicator columns
```

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
never silently yields an empty table.

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

Extend `maned_lang/tests/cli/matmul_relu.mnd` so the flow also returns
`tensor_sum(result)` as `total`.

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
