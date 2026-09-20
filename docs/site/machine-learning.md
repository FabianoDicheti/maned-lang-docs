# Machine learning

Maned ships eleven named learning algorithms as a **language construct**, not a
library. You write the algorithm name, the data it learns from, and its
hyperparameters; the compiler writes the training program — the standardization,
the intercept column, the gradient-descent rounds, the fixed-point scale
management — and hands you back a **model** you can print, save, ship over the
wire, and predict with.

```mnd
calc::ml::linear_regression fit(X, y) {
    iters: 400,
    lr: 5,
    features: 2
} return model, loss;
```

That is the whole training program. Ten of the eleven algorithms run today; the
eleventh (`pca`) is reserved and refuses honestly — see
[`pca` is reserved](#pca-is-reserved).

Every example on this page is taken from `mnd_scripts/tutorials/`, one
self-contained teaching script per algorithm, and every output block was
captured by running it. Nothing here needs a network, a dataset, or a worker:
the fixtures are inline literals.

When you are ready to spread the training across machines, continue to
[Training across Bark devices](guides/ml-parallel.html).

## The shape of every ML program

Three parts, and only the first is new:

1. a `calc::ml::` **definition** — the algorithm, the data, the hyperparameter block, the returns;
2. a normal `calc::lambda_flow` that calls the **`ml_predict`** op on the fitted model;
3. optionally, `out::model = model("file.mnm");` to persist it.

Here is a complete program — the linear-regression tutorial, stripped to its
code:

```mnd
mnd::quantmax=100;
mnd::quantmin=-100;
mnd::quantres=2;

# 8 samples of y = 2*x1 - x2 + 3, pre-scaled (100 == 1.00).
in::X = [[100,200],[200,100],[300,500],[400,200],[500,800],[600,300],[0,100],[200,700]];
in::y = [[300],[600],[400],[900],[500],[1200],[200],[0]];

# New rows: (1,1) -> 4.00, (3,1) -> 8.00, (0,5) -> -2.00.
in::Xnew = [[100,100],[300,100],[0,500]];

calc::ml::linear_regression fit(X, y) {
    iters: 400,
    lr: 5,
    features: 2
} return model, loss;

calc::lambda_flow infer(model, Xnew) {
    model Xnew ml_predict yhat =
} return yhat;
```

```text
$ maned-run ml_01_linear_regression.mnd
flow 'fit' outputs:
model : [15] = [1296974925, 1, 1, 2, 2, 1, 3, 7, 377, -251, 512, 287, 362, 189, 254]
loss : [1] = [0]
flow 'infer' outputs:
yhat : [3x1] = [401, 793, -192]
```

`yhat` is `[4.01, 7.93, -1.92]` at `quantres=2` — the model recovered
`y = 2·x₁ − x₂ + 3` to within a hundredth, in integers, with no float anywhere
in the runtime.

The braces hold **hyperparameters**, not RPN statements: `key: value` pairs,
where a value is an integer in the scaled domain, `true`/`false`, or a flat
list (a [sweep](#sweeps-many-configurations-from-one-definition)). A float
literal there is refused (`E022`) rather than silently truncated to zero.

## Everything is a scaled integer

Maned has no floating point. `mnd::quantres=2` means every value in the program
is *real × 100*: the literal `300` means 3.00, and `lr: 5` means a learning rate
of 0.05. This is the first thing your file says, so "what does the integer 500
mean?" is never an implementation detail discovered later.

Three consequences worth internalizing before you fit anything:

| Fact | What follows from it |
|---|---|
| **Labels are scaled too** | For logistic and xgboost, class 1 is `10^q` (`100` at q=2) and class 0 is `0`. For `svm` they are `−10^q` and `+10^q`. For knn, naive Bayes and decision tree, labels pass through verbatim — whatever integers `y` holds are what comes back. |
| **`lr` scales the summed gradient** | There is no `1/n`. A larger dataset wants a smaller `lr`. |
| **Gradients can round to zero** | Below roughly `10^−quantres` of gradient resolution the update truncates to nothing and training stalls. `standardize: true` (the Tier A default) plus the reported `loss` are the guard rails — a stalled fit is visible in the loss, not silent. |

`features: <d>` is **required** for the gradient-descent family and for
xgboost: shapes are dynamic at compile time, and β₀, the divisor tensors and
the int32-overflow refusal all need the feature count.

## Choosing an algorithm

| Algorithm | Learns from | `ml_predict` returns | Tier |
|---|---|---|---|
| `linear_regression` | `fit(X, y)`, continuous `y` | scale-q predictions | A — routable |
| `logistic_regression` | `fit(X, y)`, `y ∈ {0, 10^q}` | scale-q probabilities | A — routable |
| `svm` | `fit(X, y)`, `y ∈ {−10^q, +10^q}` | the class, `±10^q` | A — routable |
| `kmeans` | `fit(X)` — unsupervised | cluster index `0..k−1`, raw | B — local only |
| `knn` | `fit(X, y)` | the stored labels, verbatim | B — local only |
| `naive_bayes` | `fit(X, y)` | the stored labels, verbatim | B — local only |
| `decision_tree` | `fit(X, y)` | the stored labels, verbatim | B — local only |
| `isolation_forest` | `fit(X)` — unsupervised | scale-q path length, **lower = anomalous** | B — local only |
| `xgboost` | `fit(X, y)`, `y ∈ {0, 10^q}` | scale-q probabilities | A — routable |
| `hmm` | `fit(O)` — unsupervised sequences | state ids `0..K−1`, `[sequences, steps]` | A — routable |
| `pca` | — | — | reserved, refuses |

**Tier A** desugars into ordinary Maned flows built from wire-legal
primitives, so the training itself can be routed to a Bark worker with
`@device(alias)` and proved bit-for-bit with `--verify`. **Tier B** trains
through the native `ml_fit` kernel, which has no wire opcode; `@device` on one
is refused with a reason rather than silently ignored. That distinction, and
what to do with it, is the subject of
[Training across Bark devices](guides/ml-parallel.html).

## The ten algorithms

### Linear regression

**Purpose.** Fit `y = w·x + b` by integer gradient descent. The workhorse for
continuous targets: demand, price, sensor calibration, any place a straight
line through scaled data is the honest model.

**Reach for it when** the relationship is roughly linear and you want a model
small enough to read: the descriptor holds the weights themselves, so you can
see what it learned.

```mnd
calc::ml::linear_regression fit(X, y) {
    iters: 400,           # gradient steps, chunked to the register budget
    lr: 5,                # 0.05 at quantres=2
    features: 2,          # required
    fit_intercept: true,  # default
    standardize: true     # default - integer GD stalls on raw scales
} return model, loss;
```

`loss` is the scale-q mean squared error. Watch it: `0` means the fit reached
under 0.01 MSE, a large number means the learning rate never bit.

### Logistic regression

**Purpose.** Binary classification, through the bit-exact integer sigmoid LUT —
the same table a bark worker uses, which is why the desugared rounds route and
`--verify` holds.

**Reach for it when** you want a *probability*, not just a side of a line, and
you want the decision boundary to be a linear function of the features.

```mnd
in::y = [[0],[0],[0],[0],[100],[100],[100],[100]];   # 0 / 10^q

calc::ml::logistic_regression fit(X, y) {
    iters: 300,
    lr: 10,               # 0.10 - classification tolerates a hotter rate
    features: 2
} return model, loss;

calc::lambda_flow infer(model, Xnew) {
    model Xnew ml_predict prob =    # scale-q probabilities
} return prob;
```

```text
prob : [4x1] = [1, 99, 33, 50]
```

`100` is certainty, `50` is the decision boundary, so "predicted class 1" is
`prob > 50`. The probe at exactly the midpoint returns `50` — it is on the line.

**The loss is not log-loss.** There is no `log` op on the tensor path, so what
is reported is the scale-q mean squared error of the probabilities: same
minimum, different units.

### Support vector machine

**Purpose.** A linear maximum-margin classifier — hinge loss, optional L2,
integer subgradient descent.

**Reach for it when** you want the boundary itself rather than a calibrated
probability, and you want regularization you can dial.

```mnd
in::y = [[-100],[-100],[-100],[-100],[100],[100],[100],[100]];   # signed!

calc::ml::svm fit(X, y) {
    iters: 200,
    lr: 5,                # 0.05
    l2: 10,               # 0.10 - the soft margin
    features: 2
} return model, loss;
```

```text
cls     : [8x1] = [-100, -100, -100, -100, 100, 100, 100, 100]
cls_new : [3x1] = [-100, 100, -100]
```

**Labels are signed** here, unlike logistic: `−10^q` and `+10^q`. `ml_predict`
returns exactly those two values — the class, because a margin machine has no
probabilities to give.

**`l2` matters.** The hinge subgradient is zero for well-classified points, so
without it the weights only ever grow. The third probe above sits exactly on
the midline: `z = 0`, and `z > 0` is false, so the tie resolves to `−100` — the
boundary belongs to the negative class, spelled rather than left to chance.

### k-means

**Purpose.** Unsupervised clustering by Lloyd's algorithm, with deterministic
everything: the `k` initial centroids are rows spread evenly through the data
(no RNG), assignment ties break to the lowest centroid index, and centroid
updates are truncating integer means. Same data, same hypers → byte-identical
model on every platform.

**Reach for it when** you have no labels and want a small number of compact
groups — segmentation, vector quantization, a cheap codebook.

```mnd
calc::ml::kmeans fit(X) {
    k: 2,
    iters: 10,
    standardize: true
} return model;
```

```text
assign     : [8x1] = [0, 0, 0, 0, 1, 1, 1, 1]
assign_new : [2x1] = [0, 1]
```

**One input.** `fit(X)`, no `y`. `ml_predict` returns the nearest **centroid
index**, raw `0..k−1`, not scaled — an index is an index. Which cluster gets
which id depends on data order, so treat the ids as labels to compare, never as
meanings.

### k-nearest neighbours

**Purpose.** Classification with no training to speak of: the model *memorizes*
the standardized training rows and their labels, and `ml_predict` does the work
— exact integer squared distances, the `k` nearest by a total `(distance,
index)` order, then a majority vote with ties broken to the **smallest label**.

**Reach for it when** the decision boundary is irregular, the dataset is small,
and you would rather spend at predict time than at fit time.

```mnd
calc::ml::knn fit(X, y) {
    k: 3                  # pick k ODD for binary problems
} return model;
```

```text
model : [34] = [1296974925, 1, 5, 2, 2, 2, 0, 26, 3, 8, 100, 100, ...]
cls   : [8x1] = [0, 0, 0, 0, 100, 100, 100, 100]
```

Look at the descriptor length compared with the gradient-descent models (15
slots): knn is the one whose model grows with the data, because the data *is*
the model. Labels pass through verbatim — knn never does arithmetic on them
beyond counting.

### Naive Bayes

**Purpose.** Gaussian naive Bayes — per class, per feature, a mean and a
variance; prediction is the argmax of an integer log-space score. The language
has no `log` op on the tensor path, but the kernel is native, so it uses a
hand-rolled fixed-point `ln` internally: integer in, integer out, deterministic,
without a float ever entering the runtime.

**Reach for it when** you want a calibrated-ish multi-class classifier in one
pass over the data, with nothing to tune.

```mnd
calc::ml::naive_bayes fit(X, y) {} return model;
```

The empty block is legitimate: features are treated as independent given the
class, so fitting is a single pass of counts, means and variances — no
iterations, no learning rate. Only `standardize` exists as a knob, defaulting to
`false`.

**Variance smoothing** is the entire regularization story: each variance gets
`+1` raw integer unit, so a constant feature cannot divide by zero or take
`ln(0)`.

### Decision tree

**Purpose.** CART classification — greedy binary splits maximizing a Gini-style
purity score, integer thresholds at value midpoints, majority leaves.

**Reach for it when** you need to *explain* the classifier. The fitted model is
the node table itself: `(feature, threshold, left, right, label)` per node, and
`ml_predict` just walks it — `x[feature] <= threshold` goes left.

```mnd
calc::ml::decision_tree fit(X, y) {
    max_depth: 3,
    min_samples: 2
} return model;
```

Determinism is spelled into every rule: candidate splits are scanned
lowest-feature-then-lowest-threshold first, only a *strictly* better score
replaces the incumbent, leaf ties break to the smallest label, and the purity
comparison runs in a 2²⁰ fixed-point scale so no float enters the comparison.

Thresholds compare in **raw feature units**, which makes the decision tree the
one classifier here that does not care about standardization at all.

### Isolation forest

**Purpose.** Anomaly detection by isolation. Grow random binary trees (random
feature, random threshold inside its range); points that are easy to isolate —
few cuts suffice — are anomalous. No labels anywhere: the signal is structural.

**Reach for it when** you have unlabelled data and want a ranking of "how odd
is this row" — fraud triage, sensor faults, log outliers.

```mnd
in::X = [[100,100],[100,200],[200,100],[200,200],[700,700],[700,800],[800,700],[800,800],[1500,100]];

calc::ml::isolation_forest fit(X) {
    trees: 50,
    max_depth: 8,
    seed: 7
} return model;

calc::lambda_flow infer(model, X) {
    model X ml_predict score =     # expected path length
} return score;
```

```text
score : [9x1] = [366, 354, 380, 370, 382, 366, 382, 368, 196]
```

**Read the output carefully.** `ml_predict` returns the expected **path
length** at scale q (tree depth plus the `c(m)` correction for the leaf's
population, averaged over the forest). **Lower means more anomalous.** The
ninth row — the intruder at (15.00, 1.00) — scores `196` against a cluster
floor of `354`. It is a ranking statistic: compare rows against each other, or
threshold it yourself; there is no built-in cutoff.

**"Random", deterministically.** The randomness is a private splitmix64 stream
under *your* seed — bit-identical on every platform, and the same seed always
grows the same forest. Sweep `seed:` to check your anomalies are not one
forest's opinion.

### XGBoost

**Purpose.** Gradient-boosted trees with the logistic objective — real XGBoost
math (second-order gradients, the exact split gain, `lambda` and
`min_child_hess` regularization, shrinkage) expressed as dense integer linear
algebra, because that is the shape Maned runs: a split *is* a matmul.

**Reach for it when** the relationship is non-linear and interacting, and a
single tree underfits. This is the strongest tabular classifier in the set.

```mnd
calc::ml::xgboost fit(X, y) {
    rounds: 4,            # one tree each, fit to the current residual
    depth: 2,             # 1..6, perfect binary trees
    bins: 4,              # 2..16 equal-width thresholds per feature
    eta: 30,              # shrinkage 0.30 - each tree's say
    l2: 100,              # lambda 1.00 in the gain denominator
    min_child_hess: 75,   # 0.75 - both children must carry this much hessian
    features: 2,          # required
    rows: 8               # optional - makes the int32 guard an exact refusal
} return model, loss;
```

```text
loss     : [1]   = [7]
prob     : [8x1] = [27, 27, 27, 27, 73, 73, 73, 73]
prob_new : [2x1] = [27, 73]
```

Labels are `0 / 10^q` like logistic; predictions are scale-q probabilities
(walk every tree, sum the leaf logits, sigmoid), so class 1 is `prob > 50`.

**Where is the boundary?** Wherever the *tree* put it — not the midline. On the
fixture above all four bin thresholds between the clusters (2.40, 3.80, 5.20,
6.60) produce the identical perfect split, so the gain ties, and Maned's exact
integers break the tie to the lowest candidate index: the learned boundary is
`x ≤ 2.40`. That is the same documented tie-break real XGBoost uses — visible
here because integer gains tie *exactly* where float ones differ by rounding
noise.

**Rounds are chunked**: one flow per boosting round, chained through wire
values, so `rounds:` is unbounded by the register file.

### Hidden Markov model

**Purpose.** Unsupervised sequence modelling — Baum-Welch (EM) training by
scaled integer forward-backward, then posterior decoding of the hidden states.
The whole algorithm is matmuls over a *batch* of sequences: batch them as rows
and the three-dimensional ξ table never has to exist, because `uᵀ·w` contracts
it.

**Reach for it when** your data is sequences over a small symbol alphabet and
you believe an unobserved regime drives them — activity segmentation, regime
detection, tokenized telemetry.

```mnd
# [6, 8]: regime A emits symbols 0/1, regime B emits symbol 2 (with noise).
in::O = [[0,100,0,100,200,200,200,200],
         [100,0,100,0,200,200,100,200],
         [0,0,100,200,200,200,200,200],
         [100,100,0,0,0,200,200,200],
         [0,100,100,0,200,100,200,200],
         [100,0,0,100,200,200,200,0]];

calc::ml::hmm fit(O) {
    states: 2,            # K, the hidden alphabet
    symbols: 3,           # V - required, shapes the emission matrix
    steps: 8,             # T - required, the time axis unrolls at compile time
    iters: 3              # EM iterations, one chunked flow each
} return model, score;

calc::lambda_flow infer(model, O) {
    model O ml_predict states =    # [sequences, steps], raw 0..K-1
} return states;
```

```text
score  : [1x1] = [355]
states : [6x8] = [0, 0, 0, 0, 1, 1, 1, 1,
                  0, 0, 0, 0, 1, 1, 1, 1,
                  0, 0, 0, 1, 1, 1, 1, 1,
                  0, 0, 0, 0, 0, 1, 1, 1,
                  0, 0, 0, 0, 1, 1, 1, 1,
                  0, 0, 0, 0, 1, 1, 1, 1]
```

Each decoded row switches state once, roughly where its symbols shift from
{0,1} to {2} — EM found the regime change without ever being told there was one.

**The input shape** is one matrix `O` of `[sequences, steps]`: each row is an
observation sequence, each cell a symbol id `0..symbols−1` at scale q (at
quantres=2 the literal `200` means symbol 2 — the same convention a `csv()`
column arrives in).

**`score`** is the final mean scale factor: monotone non-decreasing over EM
iterations, so raising `iters` and watching it climb is a fit-quality trace. It
is one `log` op short of the true log-likelihood, so it is reported as what it
is rather than mislabelled.

**Labels are identifiable only up to a permutation** — which hidden state got
called "0" is the fit's choice, not a meaning. And since EM converges to a fixed
point *of its start*, `seed:` is part of the model's provenance: sweep
`seed: [1, 2, 3]` to see how stable your fit really is.

`hmm` needs `quantres` 2..3 — the α/β renormalization scale `10^(q+1)` must
square inside int32, and the construct refuses otherwise, with your numbers.

## What a fitted model is

One rank-1 integer vector. Eight header slots, then the payload:

| Slot | Meaning |
|---|---|
| 0 | magic `1296974925` = `0x4D4E444D` ("MNDM") |
| 1 | format version (`1`) |
| 2 | algorithm id |
| 3 | `quantres` the model was fitted at |
| 4 | feature count |
| 5 | output count |
| 6 | flags — bit 0 `fit_intercept`, bit 1 `standardized` |
| 7 | payload length |
| 8.. | the payload: weights, centroids, node tables, transition matrices |

Algorithm ids: `1` linear, `2` logistic, `3` svm, `4` kmeans, `5` knn, `6`
naive Bayes, `7` decision tree, `8` isolation forest, `10` xgboost, `11` hmm.

So the linear-regression model above —

```text
model : [15] = [1296974925, 1, 1, 2, 2, 1, 3, 7, 377, -251, 512, 287, 362, 189, 254]
```

— reads as: MNDM, v1, linear regression, quantres 2, 2 features, 1 output,
flags 3 (intercept + standardized), 7 payload slots, then the standardized
weights, the intercept, and the standardization statistics the model carries so
`ml_predict` can reproduce them.

It prints, it ships over MNPK, and `ml_predict` refuses a `quantres` mismatch
rather than quietly predicting nonsense.

## Saving and loading a model

Write it with `out::`, read it back with `in::`:

```mnd
out::model = model("linear_fit.mnm");
```

```mnd
in::m    = model("linear_fit.mnm");
in::Xnew = [[100,100],[300,100],[0,500]];

calc::lambda_flow infer(m, Xnew) {
    m Xnew ml_predict yhat =
} return yhat;
```

```text
$ maned-run fit.mnd
out::m1 -> linear_fit.mnm
$ maned-run predict.mnd
yhat : [3x1] = [401, 793, -192]
```

Same three numbers as the in-memory run. The `.mnm` format is raw
little-endian int64 slots plus a checksum — never quantizer-encoded, so a model
file means the same thing whatever the reading program's `quantres` is, and
`ml_predict` checks. Writing validates the descriptor first, so a non-model
tensor cannot be saved under the model format by accident.

## Sweeps: many configurations from one definition

A list-valued hyperparameter trains **one configuration per value**:

```mnd
calc::ml::linear_regression fit(X, y) {
    iters: 400,
    lr: [2, 5, 10],       # three configurations: 0.02, 0.05, 0.10
    features: 2
} return m0, l0, m1, l1, m2, l2;
```

```text
m0 : [15] = [..., 370, -244, 508, ...]
l0 : [1] = [1]
m1 : [15] = [..., 377, -251, 512, ...]
l1 : [1] = [0]
m2 : [15] = [..., 379, -253, 513, ...]
l2 : [1] = [0]
```

The return list takes one output set per configuration, in value order, so
comparing the losses is reading down the page: `lr: 0.02` stalled at loss 1,
the other two converged.

Only the numeric tuning knobs sweep — `lr`, `l2`, `iters`, `k`, `max_depth`,
`trees`, `seed`, `rounds`, `eta`, `min_child_hess`. The keys that shape the
generated program — `features`, `fit_intercept`, `standardize`, `budget`,
`depth`, `bins`, `states`, `symbols`, `steps`, `rows` — are refused as lists.

Configurations share nothing, which makes the sweep the parallelism that
actually pays: see
[Fanning a sweep across workers](guides/ml-parallel.html#fanning-a-sweep-across-workers).

## Hyperparameters at a glance

| Key | Applies to | Default | Sweeps |
|---|---|---|---|
| `features` | GD family, xgboost | **required** | no |
| `iters` | GD family, kmeans, hmm | `200` (GD), `20` (kmeans), `4` (hmm) | yes |
| `lr` | GD family | `10^quantres / 20` (0.05 real, floored at 1) | yes |
| `l2` | GD family, xgboost | `0` (GD), `10^q` (xgboost) | yes |
| `fit_intercept` | GD family | `true` | no |
| `standardize` | GD family / kmeans, knn, naive_bayes | `true` / `false` | no |
| `k` | kmeans, knn | `3` | yes |
| `max_depth` | decision_tree, isolation_forest | `8` / `10` | yes |
| `min_samples` | decision_tree | `2` | yes |
| `trees` | isolation_forest | `50` | yes |
| `seed` | isolation_forest, hmm | `42` / `0` | yes |
| `rounds` | xgboost | `8` | yes |
| `depth` | xgboost | `3` (1..6) | no |
| `bins` | xgboost | `8` (2..16) | no |
| `eta` | xgboost | `0.3·10^q` | yes |
| `min_child_hess` | xgboost | `0.75·10^q` | yes |
| `rows` | xgboost, hmm | optional — exact overflow refusal | no |
| `states` | hmm | `2` (2..16) | no |
| `symbols`, `steps` | hmm | **required** | no |
| `budget` | Tier A | worker register budget (4096; `256` for ABI v1) | no |

`{}` is a legal block — everything defaults, except the required keys.

## `pca` is reserved

`pca` is the eleventh name in the closed set and it does not run. It refuses at
desugar time: *deferred behind a symmetric eigensolver — `eigendecomp` is
registered but has no evaluator*. That is deliberate. The name is claimed so
that a future release can add it without changing the closed set, and refusing
loudly beats shipping an approximation nobody asked for. When the eigensolver
lands, `pca` starts working and gets a tutorial like the rest.

## When Maned refuses

| Situation | What you see |
|---|---|
| Unknown algorithm name | `E021` — the set is closed; the eleven names are listed in the message |
| Float in a hyperparameter, or a missing return clause | `E022` — floats would silently truncate, so they are refused |
| `@device` on a Tier B algorithm | *is coordinator-only (`ml_fit` has no binary-IR opcode, it cannot cross the wire); drop the `@device` decorator* |
| `ml_predict` with a model fitted at another `quantres` | refused — the scale is part of the model's contract |
| A fit too large for int32 at this `quantres` | refused **before** training, with your numbers, when you supply `rows:` |
| `hmm` outside `quantres` 2..3 | refused, with the scale arithmetic spelled out |

Every code is in the [Diagnostics reference](guides/diagnostics.html).

## Next

- [Training across Bark devices](guides/ml-parallel.html) — routing fits to workers, fanning sweeps, and what actually gets faster.
- [Language guide](guides/language.html) — the RPN model, the op set, and `calc::ml::` in its full reference form.
- [Remote workers](guides/remote-workers.html) — declaring devices, the CDP wire protocol, and the Bark VM.
