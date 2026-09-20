# Network and Dispatch

The networking layer discovers devices, establishes HTTP-backed sessions, packages
jobs, chooses synchronous/asynchronous execution, and coordinates independent
flows. It depends on `maned_core`, not MLIR.

## Transport and devices

| File | Responsibility | Dependencies and consumers |
|---|---|---|
| `include/maned/net/http_client.h` | HTTP request/response/error records, options, client, and convenience request API. | Lowest transport layer; used by device sessions and tests. |
| `src/net/http_client.cpp` | URL/socket request handling, response parsing, timeouts, and limits. | Converts OS/network failures into `HttpResult`. |
| `include/maned/net/device.h` | Device configuration/status/errors and `DeviceSession`. | Builds on HTTP and is consumed by jobs/remote execution. |
| `src/net/device.cpp` | Environment expansion, capability/status calls, and device configuration. | Parses JSON/error responses via protocol helpers. |
| `include/maned/net/discovery.h` | Discovered-device model, options/results, UDP discovery and reply parsing. | Supplies sessions/targets to CLI dispatch. |
| `src/net/discovery.cpp` | Broadcast/listen lifecycle and discovery JSON parsing. | Uses lightweight JSON helpers. |

## Jobs, remote execution, and dispatch

| File | Responsibility | Dependencies and consumers |
|---|---|---|
| `include/maned/net/remote_run.h` | Remote job/output/result models, preflight, MNPK encoding, MNRS decoding, synchronous execution, and local verification. | Bridges IR/protocol/runtime values to a device session. |
| `src/net/remote_run.cpp` | Capability checks, request execution, response decoding, and error normalization. | Used by jobs, dispatcher, and CLI. |
| `include/maned/net/jobs.h` | Async/automatic execution options and entry points. | Wraps remote execution according to device support. |
| `src/net/jobs.cpp` | Job submission, polling, fallback, and timeout behavior. | Uses structured protocol errors and session requests. |
| `include/maned/net/dispatch.h` | Script device/flow plans, output/result models, AST extraction, quant settings, and `runFlows`. | Highest orchestration interface used by `maned-run`. |
| `src/net/dispatch.cpp` | Builds flows, resolves devices/dependencies, runs local/remote work, and combines results. | Uses AST, discovery, jobs, protocol, IR, and interpreter. |

## Interaction sequence

| Stage | Action | Failure surface |
|---|---|---|
| Discovery/configuration | Resolve script aliases to reachable devices and capabilities. | Invalid config, timeout, malformed reply. |
| Planning | Collect device blocks and lambda flows; build dependency plans. | Missing alias, invalid dependency, unsupported operation. |
| Encoding | Serialize dataflow and values into MNPK. | Unsupported dtype/value or size violation. |
| Execution | Submit synchronously or asynchronously over HTTP. | Transport, worker error, polling timeout. |
| Decoding | Parse MNRS outputs into runtime values. | Bad status, malformed tensor, protocol mismatch. |
| Aggregation | Publish per-flow outputs; optionally compare locally. | Numerical mismatch or upstream flow failure. |

Flow concurrency is implemented with threads in `dispatch.cpp`; consequently
`Threads::Threads` is a public dependency of `maned_core`.

### One scheduler, local runs included (gap_007)

There is no longer a separate "just run it locally" path. **Every** run goes
through `net::runFlows`, and a flow with no `@device` is simply a flow the
scheduler assigns to the in-process interpreter. The practical consequence,
which has bitten twice: anything that must affect local execution has to be
threaded through `JobsOptions`, because patching a single-flow path only
patches dead code. Both `--quant-mode sat` and the buffer-reuse metric were
written that way first and had no visible effect at all.

### How a flow gets its inputs

Each flow's input list is built on the coordinator, and the rule differs by
where the flow runs:

- **Remote flows get their declared parameters, in order, and nothing else.**
  `buildRemoteJob` maps inputs onto MNPK `PARAM` slots positionally, so an
  extra tensor would not be ignored — it would shift the table and corrupt the
  envelope.
- **Local flows additionally get the whole `in::` environment.** A flow body
  may reference a global `in::` name directly instead of declaring it a
  parameter — `calc::lambda_flow pipeline()` taking nothing and reading
  `in::one11` out of its body is the shape several corpus scripts use. Only
  the fixed CLI/`in::` values are injected; values *produced* by other flows
  are deliberately not, because a parameterless flow declares no dependency on
  the flow whose output it would be naming, and the scheduler is free to run
  both at once. The parser independently forbids that case (another flow's
  return name does not resolve inside a flow body), and
  `tests/test_async_dispatch.cpp` pins both halves.

A parameter with no value is an actionable error naming the flow and the
missing name; it fails that flow and poisons its dependents, while independent
flows keep running.

### Version negotiation (gap_009)

Each device is probed once per plan, not once per flow — an extra status probe
per flow is enough to exhaust a small worker's connection budget. The cached
answer is the worker's `ir` / `rf_slots` from `/api/status`; a worker
advertising neither is ABI v1 with 256 register slots. Worker limits are then
checked against *that* worker's budget, so an oversized flow refuses with the
numbers of the machine it was headed for.

For runnable script-driven examples, async job behavior, and multi-worker
teaching templates, continue with the [Remote worker guide](15_REMOTE_WORKER_GUIDE.md).

## The local Bark VM (`host = "local"`)

A device block whose host is the reserved name `local` routes its flows to
the **Bark VM** — the genuine bark executor compiled for the host
(`bark/tools/barkvm/build.sh`) — over process I/O, never HTTP:

```
device::rex { host = "local"; }            # optional: vm = "/path/to/bark-vm"
calc::lambda_flow f(a, b) @device(rex) { ... } return r;
```

Connection order (`src/net/local_vm.cpp`): a running `maned-bark-here`
instance on `~/.maned/bark-vm.sock` wins ("a bark machine is here" — its
console shows the jobs live); otherwise a private headless `bark-vm` child
is spawned. Binary discovery for the spawn: the device's `vm` field →
`$MANED_BARK_VM` → `bark-vm` on `$PATH`. Local devices need no
credentials (process spawn rights and socket file permissions are the trust
boundary; PROTOCOL_SPEC Section 12.2).

The dispatcher treats a VM device exactly like a remote one — its own ready
queue, one job in flight, dependency chaining, `--verify` — only the
transport differs. Pre-flight runs the same checks (proto, ops coverage,
payload cap, arena estimate) against the VM's HELO status via the shared
`preflightAgainstStatus`.

**Auto-fallback:** when a routed HTTP device fails the `GET /api/status`
probe at the *transport* level (connect refused/timeout), the flow runs on
the local Bark VM instead, with a stderr notice naming the device. Auth and
protocol errors do NOT fall back — a reachable-but-misconfigured worker
stays a hard error. The probe result is cached per device for the plan, so
a dead device costs one timeout, not one per flow. `--no-vm-fallback`
(maned-run) disables the fallback for CI runs that must exercise real
hardware.
