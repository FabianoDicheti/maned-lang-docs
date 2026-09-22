# Linear algebra

Maned is a dataflow language whose values are **integer tensors** and whose
verbs are mostly linear algebra. A program is a graph of matrix products,
transposes, elementwise arithmetic and reductions, evaluated left to right with
no operator precedence to argue about.

What makes it different from every other array language is what it refuses to
do: there is **no floating point anywhere in the runtime**. Accumulation happens
in int64, results truncate to 32-bit two's complement, and the scale that turns
those integers back into real numbers is metadata you declare rather than an
artifact of the hardware. That is what makes a laptop run, a Bark worker run and
an FPGA run bit-identical instead of merely close.

This page is about using that on purpose: the op set, the fixed-point scale
arithmetic you have to carry yourself, the exact-integer solvers, and the
matmul idioms that replace loops the language does not have.

Every code block below was run to produce the output shown next to it.

## The value: a shape and some integers

A Maned tensor is a shape plus row-major `int64` data. Literals are nested
lists, and eleven **constructors** build the structured matrices you would
otherwise type out by hand. They run in `in::` initializer position, at load
time, and never enter the dataflow graph:

```mnd
in::z = 3 3 zeros;                 # 3x3 zeros
in::o = 2 2 ones;                  # 2x2 ones
in::f = 2 2 7 full;                # 2x2 filled with 7
in::i = 4 eye;                     # 4x4 identity
in::d = [2,3,5] diag;              # diagonal from a vector
in::r = 6 range;                   # [0,1,2,3,4,5]
in::b = 8 1 0 1 band;              # banded: n, lower, upper, fill
in::t = 5 1 2 1 tridiag;           # tridiagonal: n, sub, diag, super
in::s = [2,3,5,7,11,13] from_spectrum;   # a matrix with that spectrum
in::y = { rows: 4, cols: 4, symmetric: true } synth;   # by properties
in::n = 3 3 random;                # deterministic pseudo-random fill
```

```text
i : [4x4] = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
d : [3x3] = [2, 0, 0, 0, 3, 0, 0, 0, 5]
t : [5x5] = [2, 1, 0, 0, 0, 1, 2, 1, 0, 0, 0, 1, 2, 1, 0, 0, 0, 1, 2, 1, 0, 0, 0, 1, 2]
r : [6] = [0, 1, 2, 3, 4, 5]
```

`random` is seeded and reproducible — the same program prints the same matrix
on every machine, which is the only kind of random this language is willing to
have.

The last two are a different idea entirely. `from_spectrum` takes the
*eigenvalues* you want and builds a matrix that has them; `synth` takes a set
of **algebraic properties** — symmetric, tridiagonal, positive definite,
defective, a demanded spectrum — and derives a matrix that provably satisfies
all of them, or refuses and names the property it could not meet. That half of
the language, together with `profile::` reading the properties back out of any
matrix, has [its own page](properties.html).

## The core operations

| Group | Ops | Runs on a worker |
|---|---|---|
| Matrix | `matmul`, `transpose`, `scalar_mul` | yes |
| Arithmetic | `add`, `sub`, `mul`, `div` and the explicit `elemwise_*` spellings | yes |
| Reductions | `tensor_sum`, `tensor_mean`, `tensor_max`, `tensor_min` | yes |
| Comparison | `>` `<` `==` `>=` `<=` `!=` (mnemonics `gt` `lt` `eq` `ge` `le` `ne`) | yes |
| Logic | `and`, `or`, `not`, `xor` — elementwise 0/1 | yes |
| Shape | `concat`, `reshape`, `split` | yes |
| Activations | `relu`, `sigmoid`, `tanh`, `softmax` — integer LUTs decoded at `quantres` | yes |
| Spatial | `conv2d`, `maxpool2d`, `avgpool2d` | yes |
| Normalization | `layernorm`, `batchnorm` (inference) | yes |
| Exact integer algebra | `determinant`, `adjugate` | **no — local only** |
| Scalar math | `exp`, `sqrt`, `isqrt`, `abs`, `clip`, `argmax`, `argmin` | **no — local only** |
| Layout | `slice` — one index off an axis, the inverse of `concat` | **no — local only** |

`matmul` takes two operands and requires the inner dimensions to agree.
`transpose` swaps the last two axes. Broadcasting is deliberately narrow:
scalar-scalar, same-shape, or scalar-against-tensor, and nothing else.

Here is the core in one flow — a matrix product, the transpose identity
`(AB)ᵀ = BᵀAᵀ` checked *in the language*, and a Gram matrix:

```mnd
in::a = [[1,2,3],[4,5,6]];      # 2x3
in::b = [[1,0],[0,1],[1,1]];    # 3x2

calc::lambda_flow linalg(a, b) {
    a b matmul       product =
    a transpose      a_t =
    product transpose lhs =
    b transpose      b_t =
    b_t a_t matmul   rhs =
    lhs rhs ==       identity_holds =
    a_t a matmul     gram =          # A^T A: square, symmetric, PSD
} return product, a_t, identity_holds, gram;
```

```text
product        : [2x2] = [4, 5, 10, 11]
a_t            : [3x2] = [1, 4, 2, 5, 3, 6]
identity_holds : [2x2] = [1, 1, 1, 1]
gram           : [3x3] = [17, 22, 27, 22, 29, 36, 27, 36, 45]
```

A comparison returns a 0/1 tensor, so `identity_holds` being all ones *is* the
proof. That pattern — assert by computing — is worth acquiring: it survives
into the tests, over the wire, and onto hardware.

## Integer semantics you have to know

Four rules, none of them surprising once stated, all of them silent if you do
not know them:

| Rule | Consequence |
|---|---|
| **Division truncates toward zero** | `7 div 2` is 3, and `-7 div 2` is −3. Truncation is not rounding: repeated division drifts **downwards**. |
| **Division by zero yields 0** | It does not trap. A zero divisor produces a zero, and your graph keeps going. |
| **`tensor_mean` is an integer mean** | The mean of `[1..6]` is 3, not 3.5. |
| **Everything wraps mod 2³²** | No saturation, no error by default. This is what lets a worker reorder a tiled matmul and stay bit-exact. |

## The rule that catches everyone: scale arithmetic

At `quantres = q`, the integer `n` means the real number `n / 10^q`. Addition
and subtraction preserve that. **Multiplication does not.** A product of two
q-scaled integers is **2q-scaled**, and `matmul` is full of products:

```mnd
mnd::quantres=2;

in::a    = [[100,200],[300,100]];   # [[1.00, 2.00],[3.00, 1.00]]
in::b    = [[100,0],[0,100]];       # the IDENTITY, at scale 2
in::unit = [[100,100],[100,100]];   # 10^q, as a tensor

calc::lambda_flow scales(a, b, unit) {
    a b matmul       raw =          # scale 2q = 4
    raw unit elemwise_div back =    # back to scale q
} return raw, back;
```

```text
raw  : [2x2] = [10000, 20000, 30000, 10000]
back : [2x2] = [100, 200, 300, 100]
```

Multiplying by the **identity** made every number a hundred times bigger,
because the identity's `1.00` is the integer `100`. Nothing went wrong — the
result is correct at scale 4. But if you feed it into another matmul without
rescaling, the scale climbs again, and int32 is not far away.

So: **track the exponent yourself, and rescale where it suits you.** Dividing by
a `10^q` tensor after each product is the usual place.

**Why a tensor, and not the literal `100`?** Because a scalar constant does not
survive the wire. `x 100 div` runs locally and then fails on a worker:

```text
error: flow 'bad': input tensor shapes are inconsistent with the flow
(SHAPE_MISMATCH) [worker: tensor dims inconsistent with IR]
```

A worker's constants are rank-1 `[1]` and it does not broadcast them. The
exception is `scalar_mul`, which takes its scalar in the instruction itself and
routes fine. If a flow might ever be routed, make your divisors full-shape
tensors — that is also exactly what `calc::ml::` generates for its own
gradient-descent rounds.

## Per-axis reductions

The bare reductions collapse the whole tensor to a rank-1 `[1]`. With
`{axis: k}` they keep the rank and set that dimension to 1 — axis 0 of a 2×3
gives 1×3 column statistics, axis 1 gives 2×1 row statistics:

```mnd
in::scores = [[1,2,3],[4,5,6]];

calc::lambda_flow stats(scores) {
    scores {axis: 0} tensor_sum  per_col =
    scores {axis: 1} tensor_sum  per_row =
    scores {axis: 0} tensor_mean col_mean =
    scores {axis: 1} tensor_max  row_max =
    scores tensor_sum            grand =
} return per_col, per_row, col_mean, row_max, grand;
```

```text
per_col  : [1x3] = [5, 7, 9]
per_row  : [2x1] = [6, 15]
col_mean : [1x3] = [2, 3, 4]
row_max  : [2x1] = [3, 6]
grand    : [1]   = [21]
```

> ⚠ **Keep per-axis reductions local for now.** A routed `{axis: k}` reduction is currently *ignored by the worker*, which returns the whole-tensor reduction instead — with no error and no warning.

`--verify` is what catches it:

```text
verify: MISMATCH in flow 'rows': output 'rsum' differs:
  local [2x1] [6, 15] vs remote [1] [21]
```

Until the worker decodes the axis, either leave a flow containing one unrouted,
or run `--verify` on it every time. `softmax {axis: k}` is unaffected, and so
are the bare whole-tensor reductions.

## Exact integer linear algebra

`determinant` is an exact integer Bareiss elimination for `n ≤ 8` (above that it
refuses, with the number). `adjugate` gives the classical adjugate. Together
they are the exact inverse — and `inverse` itself deliberately **refuses**,
naming that recipe instead of guessing at an integer division:

> `A⁻¹ = adj(A) / det(A)`

Which means you never actually form the inverse. You solve. Here is
`A x = b` solved exactly, with the scale bookkeeping written out:

```mnd
mnd::quantres=2;

in::A   = [[600,200],[100,400]];   # [[6.00, 2.00],[1.00, 4.00]]
in::b   = [[800],[900]];           # [8.00, 9.00]
in::oc2 = [[1],[1]];               # 2x1 ones, to broadcast a scalar

calc::lambda_flow solve(A, b, oc2) {
    A determinant det =                       # scale 2q
    det { rows: 1, cols: 1 } reshape det11 =
    oc2 det11 matmul D =                      # 2x1, every entry = det
    A adjugate      adj =                     # scale q
    adj b matmul    num =                      # scale 2q
    num 100 scalar_mul numq =                  # x 10^q -> scale 3q
    numq D elemwise_div x =                    # / scale 2q -> scale q
    A x matmul      check =                    # == b, at scale 2q
} return det, adj, x, check;
```

```text
det   : [1]   = [220000]            # 22.00 at scale 2q
adj   : [2x2] = [400, -200, -100, 600]
x     : [2x1] = [63, 209]           # [0.63, 2.09]
check : [2x1] = [79600, 89900]      # [7.96, 8.99] — b, within truncation
```

Two techniques in there worth stealing:

- **Multiply up before you divide.** `num 100 scalar_mul` buys back the digits that the division by `det` is about to truncate away. Do it in the other order and `x` comes out `[0, 200]` — that is `[0.00, 2.00]`, with the first component truncated away entirely.
- **Broadcast a scalar by matmul against ones.** A rank-1 `[1]` will not divide a `[2x1]`; reshape it to `1×1` and multiply a ones column by it. (Careful: a 1×1 tensor *collapses* to a scalar under `scalar_mul`/`add`, and the next `matmul` then complains about needing 2-D operands. Broadcast with ones, not with arithmetic.)

## Idioms that replace the loops you do not have

There is no indexing, no `for`, and no mutable state. Those are not gaps to work
around — the replacements are matmuls, and they are usually faster and always
routable.

### Comparisons as matrices: the outer-equality trick

Build the M×N matrix of `u[i] == v[j]` from two matmuls against ones. One matmul
against *that* performs a gather, a permutation, a histogram or a shift —
without a single index:

```mnd
in::u   = [[0],[1],[2],[3]];     # 4x1 column
in::v   = [[0,1,2,3]];           # 1x4 row
in::or4 = [[1,1,1,1]];
in::oc4 = [[1],[1],[1],[1]];
in::x   = [[10,20,30,40]];

calc::lambda_flow gather(u, v, or4, oc4, x) {
    u or4 matmul U =             # U[i][j] = u[i]
    oc4 v matmul V =             # V[i][j] = v[j]
    U V ==       E =             # the outer-equality matrix
    x E matmul   same =
} return E, same;
```

```text
E    : [4x4] = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
same : [1x4] = [10, 20, 30, 40]
```

Now **shift the left operand by one** — `u = [1,2,3,4]` against `v = [0,1,2,3]`
— and the same construction gives a shift matrix. Squaring it doubles the
shift:

```text
S        : [4x4] = [0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0]
shifted  : [1x4] = [0, 10, 20, 30]      # x . S
shifted2 : [1x4] = [0, 0, 10, 20]       # x . S^2
```

That is the whole trick behind gathers, histograms, prefix scans by doubling,
and the "a split *is* a matmul" formulation the
[`xgboost` construct](guides/machine-learning.html#xgboost) is built on.

### Bounded iteration, and where the loop body lives

`repeat(n)` unrolls at compile time, with `n` a literal in 1..256:

```mnd
repeat(4):
  P unit square P =
end
```

**Every name a repeat body assigns is loop-carried**: it reads the *previous*
iteration's value. There are no body-locals, so a temporary inside the loop
fails on the first pass with `missing input value`. The escape hatch is that a
flow call is a single statement — put the body in a helper flow, which does
have locals:

```mnd
# One squaring, at constant scale. This is the loop body.
calc::lambda_flow square(M, unit) {
    M M matmul raw =
    raw unit elemwise_div out =
} return out;

calc::lambda_flow powers(P, unit) {
    repeat(4):
      P unit square P =
    end
} return P;
```

Four squarings is `P^16`. On a 3-state chain whose rows sum to `1.00`:

```text
P : [3x3] = [42, 28, 19, 42, 28, 19, 42, 28, 19]
```

Every row is the same — the chain has converged to its stationary
distribution, and the identical rows are how you can see that it has.

**And the rows sum to 0.89, not 1.00.** Each renormalizing division truncated,
sixteen products deep, and about 11% of the mass leaked away. The *ratios* are
intact — normalized, `[0.472, 0.315, 0.213]` against the exact
`[0.463, 0.317, 0.220]` — but the total is not. If the total matters, divide by
the row sum rather than by a constant, and know that truncation always drifts
one way.

## What runs where

Everything in the first block of the [operations table](#the-core-operations)
executes on a Bark worker as well as locally. The rest is coordinator-only, and
the split is not arbitrary — the worker's instruction set is the part that had
to be small:

- **Local only, no worker opcode**: `determinant`, `adjugate`, `slice`, `exp`, `sqrt`, `isqrt`, `abs`, `clip`, `argmax`, `argmin`, and [`profile_vector`](properties.html#properties-as-values). A flow using one of these simply stays on the coordinator.
- **`clip` has a routable spelling** if you need it on a worker: `min(x,hi) = hi − relu(hi−x)` and `max(x,lo) = lo + relu(x−lo)`.
- **Registered but not executable**: `cholesky`, `lu`, `qr`, `svd`, `eigendecomp`, `inverse`, `fft`, `fft2d`, `conv1d`, `conv3d`, `multihead_attention` and others parse and shape-infer, then refuse at run time — and `maned-lint` warns (`W011`) before you ever run them. They are named so the shapes and the grammar are settled; none of them silently returns a wrong answer.

Three constraints that only appear once a flow is routed:

- **A routed flow cannot read `in::` globals.** Inputs map onto job parameter slots positionally, so everything the flow touches must be a parameter. Local flows may use globals freely.
- **At most 16 input tensors and 16 outputs** per job.
- **A register budget of 4096 values** post-inline (256 on an older ABI v1 worker), plus the payload ceiling the worker advertises in `/api/status`. All three are checked *before* dispatch, so an oversized flow is refused with the numbers of the machine it was headed for.

## Making it fast

- **`--threads N`** splits local matmul into fixed row bands. Results are identical at every `N` by construction — no split accumulators — so `--threads 1` is an exact A/B switch and this only ever moves wall time.
- **`@device(alias)`** moves a flow to a worker. Whether that is faster depends on the shape of the work: see [the economics](guides/ml-parallel.html#the-economics-when-routing-pays) — a chain of small dependent products loses to the round-trips, while independent flows across several workers win.
- **`--verify`** re-runs a routed plan locally and compares exactly. On integer semantics that is a *proof*, not a tolerance check. Use it whenever you change routing.

## Next

- [Packed weights](packed-weights.html) — importing float weight files as per-block scaled integers, and multiplying them without ever dequantizing.
- [Language guide](guides/language.html) — the RPN model, the full op table, flows, clocks and file I/O.
- [Machine learning](guides/machine-learning.html) — where these primitives are assembled into trainable models.
- [Remote workers](guides/remote-workers.html) — worked numerical examples over the wire: Markov chain evolution, an HMM forward pass, a Kalman prediction step.
