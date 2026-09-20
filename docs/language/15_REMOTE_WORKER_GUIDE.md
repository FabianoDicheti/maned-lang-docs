# Remote Worker Guide

Maned programs can declare outside workers, embed their inputs, and route
complete flows without command-line connection arguments. This guide progresses
from one remote matrix multiplication to async queues and multi-worker dataflow.

The runnable demo suite lives in `/Users/fabianodicheti/Documents/maned/demos`.
Run commands below from `/Users/fabianodicheti/Documents/maned`, where the
`maned-run` executable is located.

## 1. The controller/worker model

**Learning objectives**

- Know which work stays on the controller.
- Distinguish job concurrency from physical compute parallelism.
- Understand how values move between flows.

The controller running `maned-run`:

1. parses the `.mnd` script;
2. reads `in::` values and `device::` definitions;
3. builds a dependency graph between flows;
4. serializes each remote flow into binary IR and MNPK;
5. authenticates, submits, polls when necessary, and decodes MNRS;
6. moves returned values into dependent flows;
7. executes undecorated flows locally.

Workers never communicate directly. For Bob → Alice, the controller receives
Bob's output and includes it in Alice's next request.

| Situation | What overlaps? |
|---|---|
| Independent flows sent to different workers | Network requests and physical computation can overlap. |
| Independent async jobs sent to one worker | Submission and queue occupancy overlap; compute depends on that worker's executor count. |
| Dependent flows | The consumer waits until the producer's level completes. |
| Remote flow followed by local flow | The controller decodes the remote value and runs the consumer locally. |

The current Bob demo worker advertises four job slots but one executor. Four
occupied slots therefore demonstrate queued asynchronous work, not four CPUs.

## 2. Remote script anatomy

```mnd
mnd::quantmax=1000;
mnd::quantmin=-1000;
mnd::quantres=0;

in::a = [[1,2],[3,4]];
in::b = [[5,6],[7,8]];

device::bob {
    host = "192.168.100.76";
    port = 4780;
    user = "test";
    pass = env("MANED_BOB_PASS");
}

calc::lambda_flow multiply(a, b) @device(bob) {
    a b matmul result =
} return result;
```

| Construct | Role |
|---|---|
| `in::name = literal;` | Supplies a scalar or rectangular tensor without `--in`. |
| `device::bob { ... }` | Resolves an alias to a worker and authentication method. |
| `@device(bob)` | Routes that entire flow to the named worker. |
| `@device(bob, rex)` | Legal only on a `calc::ml::` hyperparameter sweep: configuration *i* runs its round chain on alias *i* mod N. On a plain flow it is refused — a flow runs on one worker (the old behavior silently dropped every alias after the first). |
| No `@device` | Leaves the flow on the controller's local interpreter. |

An explicit CLI `--device` overrides script routing and selects the older
single-flow remote path. A matching CLI `--in` overrides an embedded input.

Every example in this guide reads its password from the environment:

```mnd
pass = env("MANED_BOB_PASS");
```

`env("NAME")` is resolved at run time, never at parse time, and the resolved
value never appears in a diagnostic. Export it in the process environment
only:

```sh
MANED_BOB_PASS=... ./maned-run demos/remote_01_offload_matmul.mnd
```

A literal `pass = "..."` is legal, and convenient on a private bench where
zero setup matters more than hygiene. It is deliberately noisy: the linter
emits a plaintext-password warning for it, which is why some of the runs
recorded further down this page report one. Do not copy that form into
anything shared.

## 3. Example 01: smallest offload

File: `demos/remote_01_offload_matmul.mnd`

```bash
./maned-run demos/remote_01_offload_matmul.mnd
./maned-run demos/remote_01_offload_matmul.mnd --verify
```

Expected result:

```text
flow 'multiply' outputs:
result : [2x2] = [19, 22, 43, 50]
verify: PASS
```

`--verify` executes the same plan locally and compares every decoded remote
output. Use it for new examples when every operation also has a local evaluator.

## 4. Example 02: offload a pipeline

File: `demos/remote_02_remote_pipeline.mnd`

```bash
./maned-run demos/remote_02_remote_pipeline.mnd --verify
```

The worker executes:

```text
matmul → elemwise_add → relu → transpose
```

Expected flattened result:

```text
result : [2x2] = [19, 0, 22, 50]
verify: PASS
```

Sending one graph avoids returning intermediate tensors after every operation.
Only the declared flow output returns in MNRS.

## 5. Example 03: remote producer, local consumer

File: `demos/remote_03_remote_to_local.mnd`

```bash
./maned-run demos/remote_03_remote_to_local.mnd --verify
```

The routed `offload` flow returns `remote_matrix`. The undecorated `postprocess`
flow has a parameter with the same name, which creates a dependency:

```text
Bob: matmul → remote_matrix
controller: decode remote_matrix → tensor_sum → total
```

Expected values:

```text
remote_matrix : [2x2] = [19, 22, 43, 50]
total : scalar = 134
verify: PASS
```

This pattern is useful when a worker accelerates a large kernel but the final
operation is cheaper or available only in the local interpreter.

## 6. Example 04: chained remote jobs

File: `demos/remote_04_remote_dependency_chain.mnd`

```bash
./maned-run demos/remote_04_remote_dependency_chain.mnd --verify
```

Both flows target Bob, but they remain separate jobs:

1. `produce` returns `intermediate`.
2. The controller decodes it.
3. `consume(intermediate, bias)` becomes ready.
4. The controller encodes `intermediate` into the second MNPK.

Expected final result:

```text
result : [2x2] = [19, 22, 0, 50]
verify: PASS
```

Use separate flows when orchestration, placement, or reuse matters. Keep a
straight-line pipeline in one flow when no such boundary is needed.

## 7. Example 05: async slots on one worker

Files:

- `demos/generate_remote_heavy_demo.py`
- `demos/remote_05_async_slots.mnd`

Regenerate the large script deterministically:

```bash
python3 demos/generate_remote_heavy_demo.py
```

Run it:

```bash
./maned-run demos/remote_05_async_slots.mnd
```

Each independent flow sends two `96x96` int32 tensors. The input payload alone is
approximately 72 KiB, above the client's 64 KiB synchronous threshold. The
client therefore submits async jobs, polls status with backoff, and fetches each
result.

The four flows are in the same dependency level, so the controller starts one
thread per flow. They can fill Bob's four job slots together. Bob's single
executor still processes actual kernels serially/time-sliced; adding slots
improves admission and observation, not physical CPU count.

The generated permutation matrices only reorder columns. Repeated matmuls
therefore keep all values bounded while producing enough work to make job state
observable.

The existing `demos/demo_parallel.mnd` is the longer stress version: four flows,
160 dense `96x96` matmuls per flow, and detailed resource reasoning.

## 8. Example 06: true two-worker overlap

File: `demos/remote_06_two_workers_parallel.mnd`

This is a template until a real Alice worker is available. Bob uses its tested
static address; Alice is resolved through discovery:

```mnd
device::alice {
    discover = true;
    user = "test";
    pass = env("MANED_ALICE_PASS");
}
```

When both workers are reachable:

```bash
./maned-run demos/remote_06_two_workers_parallel.mnd
```

`bob_job` and `alice_job` are independent and occupy the same dependency level.
The controller sends them concurrently, allowing genuine physical overlap.
Discovery matches the alias reported by the worker; it is not an arbitrary local
nickname.

## 9. Example 07: cross-worker pipeline

File: `demos/remote_07_cross_worker_pipeline.mnd`

This is also an Alice-dependent template:

```text
Bob produce(a,b) → intermediate
controller transfer
Alice consume(intermediate,bias) → result
```

Run it after Alice is discoverable:

```bash
./maned-run demos/remote_07_cross_worker_pipeline.mnd --verify
```

The two jobs do not overlap because the second depends on the first. The benefit
is placement: each stage can run on the worker best suited to it.

## 10. Functional numerical algorithms

Maned's functional character is visible when computation is expressed as
immutable bindings and composition: every step consumes values and produces a new
value, with no hidden mutation. The worker graph does not yet execute a general
recursive list fold, so finite sequences are unrolled into explicit dataflow. The
complete graph is still offloaded as one remote job.

### Example 08: Markov-chain evolution

File: `demos/remote_08_markov_chain_forecast.mnd`

```bash
./maned-run demos/remote_08_markov_chain_forecast.mnd --verify
```

The transition function is applied five times:

```text
state_(t+1) = state_t matmul transition
```

Bindings `state_1` through `state_5` are immutable snapshots: a finite explicit
fold over the transition function. The example uses integer weights rather than
normalized floating-point probabilities.

```text
state_1 : [1x3] = [10, 10, 0]
state_3 : [1x3] = [20, 30, 30]
state_5 : [1x3] = [110, 100, 110]
verify: PASS
```

### Example 09: Hidden Markov Model forward algorithm

File: `demos/remote_09_hidden_markov_forward.mnd`

```bash
./maned-run demos/remote_09_hidden_markov_forward.mnd --verify
```

For each observation:

```text
predicted_t = alpha_(t-1) matmul transition
alpha_t = predicted_t elemwise_mul emission_t
```

The initial state is multiplied by `emission_0`; three later observations apply
the transition/emission composition. Scores remain unnormalized integer weights,
preserving exact worker/local comparison without unsupported normalization.

```text
alpha_0 : [1x3] = [12, 3, 1]
alpha_1 : [1x3] = [28, 38, 17]
alpha_2 : [1x3] = [222, 121, 200]
alpha_3 : [1x3] = [765, 1328, 743]
verify: PASS
```

### Example 10: Kalman prediction

File: `demos/remote_10_kalman_prediction.mnd`

```bash
./maned-run demos/remote_10_kalman_prediction.mnd --verify
```

The example composes two pure state/covariance prediction steps:

```text
x' = x F + u
P' = F P F^T + Q
```

Every predicted state and covariance receives a new binding. Measurement
correction is intentionally omitted because Bob does not advertise matrix
inverse.

```text
x_1 : [1x2] = [1, 1]
P_1 : [2x2] = [3, 1, 1, 2]
x_2 : [1x2] = [2, 2]
P_2 : [2x2] = [8, 3, 3, 3]
verify: PASS
```

Choose algorithms whose primitives exist in both the local evaluator and target
worker, then use `--verify` as an executable equivalence check.

## 11. Sync, async, and capability checks

Before sending work, Maned queries `/api/status`, checks protocol compatibility,
payload limits, and required operation mnemonics.

| Request size | Client path |
|---|---|
| Below 64 KiB | Synchronous `/api/execute?mode=sync` |
| 64 KiB or above | Async submission, job polling, then result fetch |

The threshold is a client policy, not a language semantic. A worker can still
reject an unsupported operation or oversized payload. The current binary IR
remote set includes matrix multiplication, arithmetic, ReLU, selected
activations, convolution, transpose, and quantization opcodes, but the target
worker's `/api/status` response is the final capability check.

## 12. Discovery and troubleshooting

List workers:

```bash
./maned-run devices
./maned-run devices --probe 192.168.100.76:4780 --timeout 1000
```

| Failure | Meaning/action |
|---|---|
| `connect_failed` during status | Worker is offline, service stopped, host changed, or network is unavailable. |
| No worker with alias | Discovery received no matching `alias`; check the worker's advertised name. |
| Authentication failure | Check user/password/token and environment variables. |
| Unsupported operation | Split the pipeline, use a local flow, or deploy compatible worker support. |
| Payload too large | Reduce inputs or adapt the worker's advertised limit. |
| Poll timeout | Inspect worker job state and workload size. |
| Verification mismatch | Compare quantization, dtype, operation semantics, and output ordering. |

Do not edit computation logic in response to `connect_failed`: first rerun the
known working `demo_worker.mnd` and probe `/api/status` to distinguish a worker
outage from a script regression.

## 13. Validation record

Validation attempted on **2026-07-23** with
`/Users/fabianodicheti/Documents/maned/maned-run`.

| Example | Static validation | Live validation |
|---|---|---|
| 01 | Parses/lints; only expected plaintext-password warning | Passed remotely; `--verify` passed with `[19,22,43,50]` |
| 02 | Parses/lints; only expected warning | Passed remotely; `--verify` passed with `[19,0,22,50]` |
| 03 | Parses/lints; dependency names are valid | Remote → local flow passed; total `134`; `--verify` passed |
| 04 | Parses/lints; remote dependency is unambiguous | Both remote jobs passed; final `[19,22,0,50]`; `--verify` passed |
| 05 | Deterministically regenerated with an identical checksum; parses/lints; 106,084-byte script | All four async `96x96` jobs completed remotely |
| 06 | Parses/lints; Alice is discovery-based | Template; Alice unavailable |
| 07 | Parses/lints; Bob → Alice dependency is unambiguous | Template; Alice unavailable |
| 08 | Parses/lints; immutable five-step Markov fold | Remote run and local verification passed |
| 09 | Parses/lints; four-step HMM forward graph | Remote scores matched local execution |
| 10 | Parses/lints; two state/covariance prediction steps | Remote matrices matched local execution |

Bob reported protocol 1, four job slots, a 1 MiB payload limit, and all operations
required by examples 01–05. Initial executions from a network-isolated workspace
sandbox returned `connect_failed`; rerunning with LAN access reached the same
worker as a normal terminal and passed. This distinction is useful when diagnosing
controller connectivity: verify the execution environment before changing the
Maned script.

## 14. The Bark VM: a worker without hardware

When no bark machine is on the network, the same programs run on the
**Bark VM** — a hosted build of the worker's real compute core
(`bark/kernel/ir_exec.c` + the MNPK codec + the scalar kernels), so results
are bit-identical to hardware by construction (it byte-matches the same
golden fixtures firmware must match).

The VM ships with the bark worker distribution as a `bark-vm` binary (plus a
`maned-bark-here` alias); it is not part of the `maned-run` install. Two ways
to use it:

1. **Interactive** — run `maned-bark-here` in a terminal. You get the
   bark machine console (status faceplate, [R]eboot / [P] setup / [L]og
   action keys, live job log; identity persists to
   `~/.maned/bark-vm-identity`) and it listens on
   `~/.maned/bark-vm.sock`. Any `host = "local"` flow connects there and
   its jobs appear on the console as they execute.
2. **Headless** — do nothing: maned-run spawns a private `bark-vm` child
   per run when no instance is listening. Point it at the binary with the
   device's `vm` field, `$MANED_BARK_VM`, or `PATH`.

Routing and verification are the standard forms:

```
./maned-run demo.mnd --device local            # whole script to the VM
./maned-run demo.mnd --verify                  # script-routed + verify
```

An unreachable network worker auto-falls back to the VM with a notice
(Section 12 of PROTOCOL_SPEC.md; `--no-vm-fallback` to disable). The VM is
deliberately scalar and single-threaded: it is the reference oracle, and
`--verify` against it is an exact-equality check, the same as against
hardware.
