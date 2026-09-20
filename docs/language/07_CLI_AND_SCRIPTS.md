# CLI and Scripts

> **Role:** descriptive reference for the shipped command-line tools,
> transcribed from each tool's `--help` (the source of truth). A drift check
> in the maned_lang suite (`cli_docs` — tests/cli/test_cli_docs_drift.cpp)
> fails when a tool grows a flag this page does not name. (gap_016)

Three user-facing tools ship from `maned_lang` and build with a plain
C++17 compiler — no cmake, no ninja, no MLIR
(`scripts/build-tools.sh`; binaries land at the workspace root):

| Tool | One line |
|---|---|
| `maned-run` | Execute a `.mnd` program — locally, on a routed worker, or on the local Bark VM. |
| `maned-lint` | Static diagnostics with source positions, plus the post-inline worker-contract limit checks. |
| `maned-serve` | Serve one `.mnd` script as an HTTP API (`/health`, `/run`, `/run.json`, `/frame`, `/frame.csv`). |

Exit codes for all three: `0` success / clean, `1` diagnostics or runtime
failure, `2` usage or environment error (cannot open file, bad flag).

## maned-run

```
usage: maned-run <file.mnd> [--flow NAME] [--in name=VALUE]...
                   [--device http://HOST:PORT | --device local]
                   [--device-user USER]
                   [--device-pass PASS] [--device-token TOK] [--verify]
                   [--no-vm-fallback] [--require-vm]
                   [--trap-overflow] [--profile-json]
                   [--probe HOST[:PORT]]... [--discover-timeout MS]
       maned-run devices [--probe HOST[:PORT]]... [--timeout MS]
                           [--no-broadcast]
       maned-run --version | --help
```

| Flag | Meaning |
|---|---|
| `--flow NAME` | Run this flow instead of the first non-helper flow (helpers — called flows — are inlined, never scheduled on their own). |
| `--in name=VALUE` | Supply/override an input. `--in a=5` is a scalar; `--in m=2x2:1,2,3,4` a row-major tensor. Repeatable; the **last** binding of a name wins (same rule everywhere — gap_001). |
| `--device URL` | Execute on a CDP worker (`http://HOST:PORT`) instead of locally. `--device local` runs on the local Bark VM over the stdio binding. |
| `--device-user` / `--device-pass` | Worker login. `--device-pass` accepts `env:NAME`; falls back to `MANED_DEVICE_PASS`. |
| `--device-token` | Pre-issued session token (mutually exclusive with user/pass); accepts `env:NAME`. |
| `--verify` | Run both remotely and locally, compare outputs exactly. The verdict names its comparison target — hardware worker vs Bark VM (gap_019). |
| `--no-vm-fallback` | An unreachable routed device stays a hard error instead of silently-but-exactly executing on the local Bark VM. Fallback prints a `notice:` line either way. |
| `--require-vm` | **Nothing runs on the in-process interpreter.** Every flow without `@device` is routed to the local Bark VM; a flow that already carries `@device` keeps its declared target (it is already on a bark executor, and stealing it would make the flag lie about where the work ran). Implies `--no-vm-fallback`, so an unreachable device is a hard error rather than a silent VM substitution. A flow the wire cannot carry is refused **before** any VM is contacted, naming the ops responsible — the ~25 executable ops with no binary IR opcode (every generator plus `abs` `adjugate` `argmax` `clip` `determinant` `exp` `isqrt` `profile_vector` `slice` `sqrt`) exist only in the interpreter, so there is nothing to send. `--verify` stays legal: its local rerun is the comparison **oracle**, not the program's execution. |
| `--trap-overflow` | Fail (with the value name and element) when any op result leaves int32 instead of wrapping mod 2³². |
| `--profile-json` | Emit `profile::` descriptors as JSON instead of the text report. The JSON carries a `quant_mode` key so a recorded descriptor says which numeric contract produced it. |
| `--threads N` | Worker threads for the local kernels (matmul, conv2d) — gap_024. Default: hardware concurrency. Results are **identical at every N by construction** (fixed row bands, no split accumulators, no float), so this only moves wall time; `--threads 1` is the exact A/B switch. |
| `--no-buffer-reuse` | Disable local buffer reuse (gap_022). Reuse is on by default and bit-exact by construction — a dying operand's storage is *moved* into the op and dead registers are released — so this flag exists to keep that claim checkable (the corpus A/B runs both ways). |
| `--quant-mode wrap\|sat` | Numeric contract for op results (gap_027). `wrap` (default, unchanged) is the mod-2³² register wrap every worker implements. `sat` saturates into the script's declared quant range — a **local debug mode**: it departs from the worker contract, prints a note saying so, and is refused together with `@device` routing (a saturating run is not comparable to a remote one). |
| `--probe HOST[:PORT]` | Add a unicast discovery probe target (repeatable). |
| `--discover-timeout MS` | Discovery reply window for `discover = true` device blocks. |
| `devices` subcommand | Probe the LAN for workers; `--timeout MS`, `--no-broadcast`, `--probe` as above. |
| `--bundle OUT.bundle script.mnd` | Write a **self-contained bundle** (gap_012): the script, every `in::`/`frame::` file it statically names, and this `maned-run` binary, as one executable file. A script that can reach the Bark VM also embeds `bark-vm`. |
| `--bundle-no-vm` | Build the bundle without embedding `bark-vm` (the recipient must supply a worker). |
| `--bundle-verify DIR` | Integrity check over an extracted bundle (the stub calls this before running); recomputes every manifest hash and refuses on mismatch. |

### Bundles

```
$ maned-run --bundle demo.bundle demo.mnd
bundled demo.mnd + 1 data file(s) -> demo.bundle (1552252 bytes)

$ ./demo.bundle                 # runs anywhere on the SAME platform, no toolchain
$ ./demo.bundle --version       # runner version + producing commit + script hash
$ ./demo.bundle --bundle-list   # what is inside
$ ./demo.bundle --bundle-extract out/
```

A bundle is a POSIX `sh` stub with an appended (uncompressed) tar payload,
so `tar` can read it and the script inside stays readable. It is
**single-platform by construction** — the manifest records `uname -s`/`-m`
and the stub refuses a mismatch with a clear message. Every input is
resolved at **bundle** time, so a missing or glob-derived source fails on
your machine, never on the recipient's. Payload hashes are verified before
execution (a tampered payload refuses). A bundle always uses its own
embedded `bark-vm`, never a VM already running for another user.

**macOS note:** a bundle *downloaded* onto another Mac carries
`com.apple.quarantine` and Gatekeeper will refuse its unsigned embedded
binaries — run `xattr -d com.apple.quarantine ./demo.bundle` first, or
transfer it in a way that does not quarantine (the v1 stance: Linux-first,
macOS supported with that one documented step).

Examples (run from the workspace root; outputs are real):

```
$ ./maned-run mnd_scripts/examples/example_rpn_postfix.mnd
flow 'arithmetic' outputs:
sum_then_scale : scalar = 20
scale_then_sum : scalar = 14
nested : scalar = 33
clamped : scalar = 0

$ ./maned-run mnd_scripts/examples/example_matrix_ops.mnd
flow 'linalg' outputs:
product : [2x2] = [4, 5, 10, 11]
a_t : [3x2] = [1, 4, 2, 5, 3, 6]
...
```

Device-routed scripts (`@device(alias)` + `device::alias { ... }` blocks)
dispatch each flow to its worker with dependency ordering and concurrency;
see `mnd_scripts/examples/example_device_*.mnd`.

## maned-lint

```
usage: maned-lint <file.mnd>
       maned-lint --version | --help
```

`maned-run` and `maned-serve` **also run the linter** and refuse a script
carrying any **Error**-severity finding (gap_035) — the same contract
`--bundle` already had. Before that, E007/E008/E012 and friends were visible
only to `maned-lint`, so a typo'd `@devcie` or a `routing_policy` directive
parsed clean and was silently ignored on the paths that actually execute.
Warnings stay lint-only: they are advice, and a runner that prints them on
every run trains you to ignore all of them. `maned-serve` refuses at **load**,
so an operator finds out at startup rather than never.

No flags beyond `--version`/`--help`. Prints every diagnostic as
`file:line:col: severity[CODE]: message`. The code space: `E001`–`E020`
errors, `W001`–`W012` warnings (`W008` retired), `EPARSE`/`WPARSE` for
uncoded parse diagnostics, and `ELIMIT` for the post-inline worker-contract
limits (gap_014) — maned-lint runs the same inline → CSE/DVE →
`checkWorkerLimits` pipeline as maned-run, so a lint-clean script cannot
refuse at run time for a statically-knowable reason. Exit 1 whenever any
error fired.

```
$ ./maned-lint mnd_scripts/probes/ops/p04_unsupported.mnd
mnd_scripts/probes/ops/p04_unsupported.mnd:6:7: warning[W011]: op 'gelu' is registered but not executable on any path - it will refuse at run time
```

## maned-serve

```
usage: maned-serve <file.mnd> [--port N] [--host ADDR] [--max-requests N] [--workers N]
                     [--no-vm-fallback]
       maned-serve --version | --help
```

| Flag | Meaning |
|---|---|
| `--port N` | Listen port (default 8080). |
| `--host ADDR` | Bind address (default 127.0.0.1). |
| `--max-requests N` | Self-shutdown after serving N requests — the server exits 0 once the Nth response is written. This is the fixture/CI mechanism (start the server, make N requests, it shuts itself down; no kill required). |
| `--no-vm-fallback` | Same semantics as maned-run: unreachable routed devices are hard errors. |
| `--workers N` | Handle connections on N threads (gap_025). Default 1 = the historical single-threaded loop, with no threads created at all. One worker per **connection** (keep-alive stays put). `--max-requests` is claimed before serving, so N workers never over-serve, and the server drains in-flight requests before exiting. **Refused for scripts with `@device` routing** — routed execution reaches the single-threaded Bark VM channel, so that combination errors by name instead of racing. |

The served surface: `POST /run` (multipart), `POST /run.json`,
`POST /frame` and `POST /frame.csv` (the same execution as `/run`, rendered as
JSON records or CSV), and `GET /health` — which carries the script's
input/output contract alongside its liveness fields, so there is no separate
contract endpoint. Request-supplied inputs override script defaults last-wins,
including in `profile::`/`out::` views of the overridden input (gap_001).
See `docs/language/SERVE_PLAN.md` and `mnd_scripts/demos/` serve demos.

## MLIR and internal tools

- **`maned-opt`** runs registered Maned MLIR passes. It is the only
  MLIR-dependent tool and is **not runnable without a full MLIR
  toolchain installed** — `scripts/build-tools.sh` deliberately does not
  build it (see its header). If you don't have MLIR, you are not missing
  anything the three main tools need.
- **`mnpk-gen`** generates MNPK/MNRS protocol fixtures from `.mnd`
  values (internal, used by protocol tests).
- **`gen-activation`** (Python) regenerates the integer activation
  tables (`maned_activation.h`).
- **`mlir_smoke`** verifies MLIR context/parser integration (internal).

## Automation

`../tools/run_tests.sh` builds and runs every hermetic unit suite with a
plain compiler; `scripts/build-tools.sh` builds the three shipped tools;
`../tools/verify_objectives.sh` runs the objective verification sequence.
(The test scripts live beside the repo in the workspace `tools/` tree; the
release workflow inlines its own copy of the unit gate.) The 111-script
corpus lives in `../mnd_scripts/` with the campaign log at
`../docs/scripts/RUN_LOG.md`; `../tools/ab_corpus.sh` is the bit-exact
A/B gate over its local subset.
