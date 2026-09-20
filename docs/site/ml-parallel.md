# Training across Bark devices

A `calc::ml::` definition is not a black box that happens to run somewhere. It
**desugars into ordinary Maned flows**, and a flow is the unit Maned knows how
to route. That is the whole mechanism behind distributed training here: there is
no separate "distributed mode", only flows with a `@device` decorator on them.

This page covers what parallelizes, how to say so, how to prove the answer did
not change, and — the part most documents leave out — when routing actually
makes your training *faster* rather than slower.

Read [Machine learning](guides/machine-learning.html) first if you have not
fitted a model yet, and [Remote workers](guides/remote-workers.html) for the
device block, the CDP protocol and worker setup in general.

## Three axes of parallelism

They are independent, and they are not equally useful:

| Axis | How | What it buys |
|---|---|---|
| **Local cores** | `maned-run script.mnd --threads 8` | The local kernels (matmul and friends) split into fixed row bands. Results are identical at every `N` by construction — no split accumulators — so `--threads 1` is an exact A/B switch, and this only ever moves wall time. |
| **Routed flows** | `@device(alias)` on a Tier A fit | The training rounds execute on a bark worker instead of the coordinator. Frees the coordinator; proves the expansion is wire-legal. Rarely faster today — see [The economics](#the-economics-when-routing-pays). |
| **The sweep** | a list-valued hyperparameter + `@device(a, b, ...)` | Whole configurations run concurrently on different workers. **This is the parallelism that pays**, because configurations share nothing and therefore have no barriers. |

## What routes and what does not

| Algorithm | Routes? | Why |
|---|---|---|
| `linear_regression`, `logistic_regression`, `svm` | **yes** | Desugar into a local init flow, a chain of gradient-descent *round* flows, and a local epilogue. The round flows are wire-legal. |
| `xgboost`, `hmm` | **yes** | Also desugar to wire-legal primitives — one flow per boosting round / EM iteration. A split *is* a matmul; a Baum-Welch quantity *is* a matmul. |
| `kmeans`, `knn`, `naive_bayes`, `decision_tree`, `isolation_forest` | **no** | Trained by the native `ml_fit` kernel, which has no binary-IR opcode. |
| `ml_predict` (all algorithms) | **no** | Inference is coordinator-only by design: it is cheap, and the parallelism that matters is in training. |

Tier B refuses out loud rather than silently running local:

```text
ml error [41:1] ml definition 'fit' (kmeans): is coordinator-only
  (ml_fit has no binary-IR opcode, it cannot cross the wire);
  drop the @device decorator
```

## Declaring the workers

A `device::` block resolves an alias to a worker. Nothing about it is
ML-specific — and if you do not have a worker yet,
[Set up a Bark machine](bark-machines.html) turns a spare x86 laptop into one:

```mnd
device::rex {
    host = "10.0.0.21";
    port = 4780;
    user = "fabiano";
    pass = env("MANED_REX_PASS");
}

device::bob {
    host = "10.0.0.22";
    port = 4780;
    user = "fabiano";
    pass = env("MANED_BOB_PASS");
}
```

`env("NAME")` is resolved at run time, never at parse time, and the resolved
value never appears in a diagnostic. A literal `pass = "..."` is legal and the
linter warns about it every time — which is the point.

**No hardware?** `host = "local"` routes to the Bark VM, a hosted build of the
real bark worker executor, with no network and no credentials:

```mnd
device::vm1 { host = "local"; }
device::vm2 { host = "local"; }
```

Everything below works against those two aliases exactly as it does against two
machines — dependency chaining, `--verify`, the pre-flight refusals. It is the
right way to develop a routed script before a worker exists.

## Routing one fit

Put the decorator on the `calc::ml::` definition, between the signature and the
hyperparameter block:

```mnd
calc::ml::logistic_regression fit(X, y) @device(rex) {
    iters: 300,
    lr: 10,
    features: 2
} return model, loss;
```

Every gradient-descent round now executes on `rex`. The init flow and the
epilogue that packs the model stay local — they are bookkeeping, not
arithmetic.

The generated flows are visible in diagnostics under the names
`fit#c0#r0`, `fit#c0#r1`, … — *configuration 0, round 0, round 1*. When a
routed run fails, that is the name you will see, and it tells you which
configuration and which round could not be placed.

## Fanning a sweep across workers

This is the interesting one. A sweep produces N independent configurations;
`@device` with N aliases spreads them:

```mnd
calc::ml::linear_regression fit(X, y) @device(rex, bob) {
    iters: 400,
    lr: [2, 5, 10],       # three configurations
    features: 2
} return m0, l0, m1, l1, m2, l2;
```

Configuration *i* runs its whole round chain on alias *i* mod N: `lr: 0.02` on
`rex`, `lr: 0.05` on `bob`, `lr: 0.10` back on `rex`. Multiple aliases are legal
**only** on a sweep. On a plain flow they are refused, because one flow runs on
exactly one worker:

```text
error: flow 'mm' names 2 @device aliases; a flow runs on one worker -
  use one alias, or a calc::ml:: sweep to fan a hyperparameter list
  across workers
```

That refusal exists because the old behaviour silently kept the first alias and
dropped the rest — a decorator that lied about where the work ran.

## How the scheduler overlaps the work

Flows are executed **event-driven**: each one launches the moment *its*
dependencies are available, not when its level finishes. Two constraints shape
what overlaps:

- **One job in flight per remote device.** The bark listener is single-connection, so a device is a serialization domain: its queued flows run one at a time, in a deterministic order (dependency level, then script order).
- **Local flows have no serialization constraint.** They run as they become ready.

Put those together and the sweep's behaviour follows: three configurations
across two workers means `rex` works through its two chains serially while `bob`
works through its one — two chains in flight at all times, no barrier between
configurations, and the coordinator free to pack models as they land. Adding a
third worker adds a third in-flight chain.

Within one configuration there is nothing to overlap: round *r+1* consumes
round *r*'s weights. Boosting rounds and EM iterations are the same story. **The
chain is the serial unit; the sweep is the parallel one.**

## Proving the routed answer

`--verify` re-runs the plan on the local interpreter and compares every decoded
remote output, exactly:

```text
$ maned-run ml_sweep.mnd --verify
flow 'fit' outputs:
m0 : [15] = [1296974925, 1, 1, 2, 2, 1, 3, 7, 370, -244, 508, 287, 362, 189, 254]
l0 : [1] = [1]
m1 : [15] = [1296974925, 1, 1, 2, 2, 1, 3, 7, 377, -251, 512, 287, 362, 189, 254]
l1 : [1] = [0]
m2 : [15] = [1296974925, 1, 1, 2, 2, 1, 3, 7, 379, -253, 513, 287, 362, 189, 254]
l2 : [1] = [0]
verify: PASS (compared local interpreter vs routed targets)
```

Those are the same three models, slot for slot, that the unrouted script
produces. All five Tier A algorithms were re-checked this way on 2026-09-20
against the Bark VM — `linear_regression`, `logistic_regression`, `svm`,
`xgboost` and `hmm`, each `verify: PASS` with bit-identical descriptors.

This is not a tolerance comparison. Every op result — locally, on the VM, and on
hardware — is truncated to 32-bit two's complement and wraps rather than
saturating, which makes wrapping addition associative and commutative. That is
exactly what lets a worker reorder a tiled matmul and still return the same
integers, and what makes `--verify` an exact test instead of an approximate one.

Use it whenever you change routing. A routed fit that verifies is a fit you can
stop thinking about.

## The economics: when routing pays

Be honest with yourself about the numbers before you distribute anything.

Measured on the live two-worker fleet: a **routed chain loses**. For `xgboost`
the routed training ran roughly 40× slower than local, because boosting rounds
are hard sequential barriers — each round is one round-trip, and the round-trips
dominate. For `hmm` there was no crossover at any batch size tested: a bark
worker is around 6× slower per unit of work than the coordinator, and EM
iterations are barriers for the same reason.

So the guidance, in order:

1. **Train local first.** `--threads N` is the cheap win, and it is exact.
2. **Use the sweep for parallelism.** Independent configurations, no barriers, linear in the number of workers. This is the one that gets faster.
3. **Route a chain when you want something other than speed** — a correctness proof (`@device` + `--verify` shows the expansion is wire-legal), a coordinator you need to keep free, or data that has to stay on the machine that holds it.

The picture changes as workers get faster or datasets get large enough that
per-round compute dominates the round-trip. It has not changed yet, and the
documentation says so rather than implying a speedup you will not measure.

## Sizing the work for a worker

A routed round has to fit the worker's register file. Tier A chunks the rounds
to the register budget automatically, which is why `iters:`, `rounds:` and EM
`iters:` are unbounded by the register file — the exact limit that capped the
hand-written HMM script at four EM iterations before the construct existed.

| Knob | When you need it |
|---|---|
| `budget: 256` | Targeting an ABI v1 worker; the default assumes v2 (4096 register slots). Too large a budget means a flow the worker refuses at pre-flight. |
| `rows: <n>` | `xgboost` and `hmm`: turns the int32 overflow guard into an exact refusal computed from your actual row count, before any training happens. |
| `features: <d>` | Always, for the GD family and xgboost. Shapes are dynamic at compile time. |

Maned queries `/api/status` before sending work and checks protocol
compatibility, payload limits and the required op mnemonics, so a worker that
cannot run your flow says so in the pre-flight rather than half way through a
sweep. Requests under 64 KiB go synchronously; larger ones submit as a job and
poll.

## A complete routed sweep

Runs as written, with no hardware, on any machine with `bark-vm` on `PATH`:

```mnd
mnd::quantmax=100;
mnd::quantmin=-100;
mnd::quantres=2;

in::X = [[100,200],[200,100],[300,500],[400,200],[500,800],[600,300],[0,100],[200,700]];
in::y = [[300],[600],[400],[900],[500],[1200],[200],[0]];

device::vm1 { host = "local"; }
device::vm2 { host = "local"; }

calc::ml::linear_regression fit(X, y) @device(vm1, vm2) {
    iters: 400,
    lr: [2, 5, 10],
    features: 2
} return m0, l0, m1, l1, m2, l2;
```

```sh
maned-run sweep.mnd --verify
```

Swap the two `host = "local"` lines for real addresses and the script is a
two-machine training job, unchanged in every other respect. That substitution —
VM for hardware, hardware for VM — is the intended development path.

## Troubleshooting

| Symptom | What it means |
|---|---|
| `is coordinator-only (ml_fit has no binary-IR opcode)` | Tier B algorithm with `@device`. Drop the decorator, or pick a Tier A algorithm. |
| `names 2 @device aliases; a flow runs on one worker` | Multiple aliases outside a sweep. Use one alias, or make the hyperparameter a list. |
| `no local Bark VM: socket ... spawning 'bark-vm' failed` | `host = "local"` with no VM available. Put `bark-vm` on `PATH`, set `$MANED_BARK_VM`, or set the device's `vm` field. |
| `connect_failed` during status | Worker offline, service stopped, host changed, or no LAN access. Probe it with `maned-run devices --probe HOST:PORT` before touching the script. |
| `not run (inputs poisoned)` | An upstream flow failed; the outputs downstream of it were never attempted. The first error in the list is the real one. |
| Unsupported operation | The worker's `/api/status` is the final capability check. Split the pipeline, keep that flow local, or update the worker. |
| Verification mismatch | Compare `quantres`, dtypes, op semantics and output ordering — not the computation logic, which `--verify` has just told you differs. |

Do **not** edit computation logic in response to a `connect_failed`: rerun a
known-good routed script first, to tell a worker outage apart from a script
regression.

## Next

- [Machine learning](guides/machine-learning.html) — the ten algorithms, their hyperparameters and what their outputs mean.
- [Remote workers](guides/remote-workers.html) — device blocks, async slots, discovery, and the Bark VM in full.
- [How Maned runs your program](under-the-hood.html) — what the toolchain does between `maned-run` and a result.
