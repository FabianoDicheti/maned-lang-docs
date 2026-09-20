# Maned Usage Guide

This guide takes a new engineer from a clean machine to a repeatable daily
workflow: build, test, lint, run, benchmark, and diagnose Maned programs.

## 1. Prerequisites and supported setup

**Learning objectives**

- Build the toolchain on a clean machine.
- Know which tools need MLIR and which do not.
- Land the binaries where the rest of this guide expects them.

**The four tools you will actually use need a C++17 compiler and nothing
else** — no CMake, no Ninja, no LLVM, no MLIR. `maned-run`, `maned-serve`,
`maned-lint` and `mnpk-gen` are built by a plain compiler invocation:

```bash
sh maned_lang/scripts/build-tools.sh
```

Run that from the **workspace root** — the directory that holds `maned_lang/` —
and it writes `./maned-run`, `./maned-serve`, `./maned-lint` and `./mnpk-gen`
beside the repository, which is where every command in this guide expects them.
It finishes by printing the version and executing a smoke program, so a
successful run is its own proof:

```text
compiler: c++ (Darwin)   version: <dev default>   rev: 5cdeae3
building maned-run  -> ../maned-run
...
built:
  maned-run      arm64            0 internal symbols
  maned-serve    arm64            0 internal symbols
  maned-lint     arm64            0 internal symbols
  mnpk-gen       arm64            0 internal symbols

version:
  maned-run 0.1.0-dev
  build: 5cdeae3 (aarch64-apple-darwin)

smoke test:
  flow 'arithmetic' outputs:
  sum_then_scale : scalar = 20
```

Useful flags:

| Flag | Effect |
|---|---|
| `--out DIR` | Write the binaries somewhere else (default: the workspace root) |
| `--universal` | macOS only: one binary carrying both arm64 and x86_64 |
| `--version V`, `--rev R` | Stamp what `--version` reports (the release workflow passes the tag) |

### What has to be installed

| Platform | Requirement |
|---|---|
| macOS | Xcode command line tools — `xcode-select --install` |
| Linux | A C++17 `g++` or `clang++` and the standard library headers — `build-essential` on Debian/Ubuntu |

Set `$CXX` to pick a specific compiler. Build on the machine you run on: a
locally compiled binary is never quarantined, and you cannot get the
architecture wrong.

**Knowledge check:** you are on a fresh laptop with no LLVM. Can you run a
`.mnd` program?
Yes — `sh maned_lang/scripts/build-tools.sh` is the whole install.

### Optional: LLVM/MLIR 18, for `maned-opt` only

`maned-opt` is the single tool that needs a full LLVM/MLIR 18 toolchain, and it
is the only reason to configure CMake at all. CMake builds the MLIR path and
nothing else — the four tools above are not CMake targets. **If you do not have
MLIR you are not missing anything those four need**; skip to section 2 and come
back only if you work on the compiler passes.

The repository-verified environment is Ubuntu 24.04 with packaged LLVM/MLIR 18.
The macOS path works but is best-effort. Consult the official
[MLIR getting-started guide](https://mlir.llvm.org/getting_started/) for upstream
toolchain context and the current [Homebrew `llvm@18` formula](https://formulae.brew.sh/formula/llvm%4018)
before relying on package availability.

#### Ubuntu 24.04: verified path

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential cmake ninja-build \
  llvm-18-dev libmlir-18-dev mlir-18-tools clang-18
```

Configure and build, from inside `maned_lang/`:

```bash
cmake -S . -B build -G Ninja \
  -DMLIR_DIR=/usr/lib/llvm-18/lib/cmake/mlir \
  -DLLVM_DIR=/usr/lib/llvm-18/lib/cmake/llvm
cmake --build build
ctest --test-dir build --output-on-failure   # the six MLIR FileCheck tests
```

If Ubuntu cannot find the versioned packages, verify that the LLVM 18 package
repository appropriate for the machine is enabled rather than silently building
against a different MLIR major version.

#### macOS: best-effort Homebrew path

```bash
brew install cmake ninja llvm@18
```

Use Homebrew's keg-specific CMake packages:

```bash
LLVM18_PREFIX="$(brew --prefix llvm@18)"
cmake -S . -B build -G Ninja \
  -DLLVM_DIR="$LLVM18_PREFIX/lib/cmake/llvm" \
  -DMLIR_DIR="$LLVM18_PREFIX/lib/cmake/mlir" \
  -DCMAKE_C_COMPILER="$LLVM18_PREFIX/bin/clang" \
  -DCMAKE_CXX_COMPILER="$LLVM18_PREFIX/bin/clang++"
cmake --build build
ctest --test-dir build --output-on-failure
```

`llvm@18` is keg-only, so do not assume `/usr/local/bin` or `/opt/homebrew/bin`
contains its tools. Use `brew --prefix llvm@18` as shown. If Homebrew's package
layout lacks `lib/cmake/mlir`, stop and report the platform/toolchain mismatch;
do not substitute an unrelated LLVM major version.

**Knowledge check:** Why are both `LLVM_DIR` and `MLIR_DIR` supplied?  
They point CMake at the installed configuration packages used by this out-of-tree
MLIR project.

## 2. Know the build outputs

**Learning objectives**

- Choose the correct executable.
- Know which build system produces each one.

| Tool | Use | Built by |
|---|---|---|
| `maned-run` | Parse and execute `.mnd` locally, on the Bark VM, or on remote workers. | `build-tools.sh` |
| `maned-serve` | Serve one `.mnd` script as an HTTP API. | `build-tools.sh` |
| `maned-lint` | Report static source diagnostics. | `build-tools.sh` |
| `mnpk-gen` | Generate and mutate MNPK/MNRS protocol fixtures. | `build-tools.sh` |
| `maned-opt` | Parse Maned MLIR and run compiler passes. | CMake, needs MLIR |
| `maned-mlir-smoke` | Check basic MLIR integration. | CMake, needs MLIR |

`build-tools.sh` always builds all four of its tools; each is a few seconds, so
there is no single-target mode to learn. To iterate without touching the
workspace root, write them somewhere scratch:

```bash
sh maned_lang/scripts/build-tools.sh --out /tmp/maned-bin
/tmp/maned-bin/maned-run maned_lang/tests/cli/smoke_rpn_postfix.mnd
```

The set of source files each tool links comes from one manifest,
`maned_lang/scripts/gate_manifest.sh`, shared with the test gates and the
release workflow — adding a `src/*.cpp` is one edit, there.

For the full target and artifact map, see
[Build and artifacts](08_BUILD_AND_ARTIFACTS.md).

## 3. Editor setup

**Learning objectives**

- Associate `.mnd` files with Maned.
- Know the boundary of editor support.

Load the repository's VS Code extension by pointing VS Code at the
`maned_lang` repo root (**Developer: Install Extension from Location…**); see
`11_EDITOR_INTEGRATION.md`. It provides
syntax highlighting, comments, bracket behavior, and icons. It does not provide
a language server, completion, or live compiler diagnostics. Run the actual
linter and parser before trusting syntax color alone.

## 4. Your first run

**Learning objectives**

- Supply scalar and tensor parameters.
- Select a flow and interpret output formatting.

Run the checked-in matrix example:

```bash
./maned-run maned_lang/tests/cli/matmul_relu.mnd \
  --flow layer \
  --in x=2x2:1,2,3,4 \
  --in w=2x2:5,6,7,8 \
  --in bias=2x2:0,0,-100,0
```

Expected output includes:

```text
flow 'layer' outputs:
result : [2x2] = [19, 22, 0, 50]
```

Input forms:

| Form | Meaning |
|---|---|
| `--in count=5` | Scalar integer input. |
| `--in x=2x3:1,2,3,4,5,6` | Rank-2 tensor, row-major. |

The number of tensor values must equal the product of its dimensions. Repeating
an input name uses the last value. Every selected flow parameter needs a value
unless the script supplies a compatible input directive.

## 5. Lint before running

**Learning objectives**

- Separate parse errors from lint diagnostics.
- Use diagnostic codes to guide fixes.

```bash
./maned-lint maned_lang/tests/cli/matmul_relu.mnd
```

The linter detects issues such as duplicate callable definitions/targets,
undefined variables, reassignment, unused parameters/variables, duplicate object
keys, and malformed device declarations. A parse failure occurs earlier and
prevents AST linting.

A good loop is:

```bash
./maned-lint path/to/program.mnd
./maned-run path/to/program.mnd --flow name --in ...
```

## 6. Selecting flows and diagnosing failures

**Learning objectives**

- Select one flow from a multi-flow file.
- Classify common failure modes.

Use `--flow NAME` when a file contains multiple flows. Typical failures:

| Message class | Likely cause | Next action |
|---|---|---|
| Cannot open file | Wrong path or working directory | Resolve the path from repository root. |
| Parse error with line/column | Invalid grammar or insufficient RPN operands | Inspect the reported token and simulate the stack. |
| Missing input | Flow parameter lacks `--in` data | Add the named input. |
| Bad `--in` | Shape/value count mismatch or malformed scalar | Recalculate dimensions and use comma-separated integers. |
| Unsupported op | Parsed operation has no selected backend evaluator | Check the language capability status. |
| Incompatible shapes | Elementwise or matrix dimension mismatch | Trace shapes at each binding. |

## 7. Tests and focused development

**Learning objectives**

- Run the full regression suite.
- Narrow to one suite during iteration.

The gate is a plain-compiler runner, not CTest. It lives beside the repository
in the workspace `tools/` tree and takes optional suite-name filters:

```bash
sh tools/run_tests.sh                 # every hermetic unit suite
sh tools/run_tests.sh parse lint      # just the ones whose names match
sh tools/run_cli_tests.sh             # the built CLIs against fixture scripts
```

Two more gates matter before handing work over:

```bash
sh maned_lang/scripts/golden_vectors.sh   # cross-platform determinism
sh tools/test_barkvm_e2e.sh               # Bark VM end-to-end (needs $MANED_BARK_VM)
```

`golden_vectors.sh` re-runs a fixed corpus and compares hashes against a
checked-in manifest, which is what catches a change that makes this machine
compute something another machine does not. It is the only net under the ops
that never cross the wire.

`ctest` covers the six MLIR FileCheck tests and only exists if you did the
optional MLIR build from section 1:

```bash
ctest --test-dir build --output-on-failure
```

Use [Testing](09_TESTING.md) to map a change to the relevant suite. Run the
full suite before handing work to another engineer.

The objective harness provides broader project gates:

```bash
bash ../tools/verify_objectives.sh
```

These checks include numerical and performance expectations beyond ordinary unit
tests; the harness writes its scorecard to `../docs/scripts/OBJECTIVES_VERIFICATION.md`.

## 8. MLIR usage

**Learning objectives**

- Run a compiler pass on a checked-in MLIR fixture.
- Distinguish `.mnd` source execution from MLIR transformations.

`.mnd` programs run through `maned-run`. MLIR text runs through `maned-opt`.
This section needs the optional MLIR build from section 1; without it there is
no `maned-opt` to run, and nothing else in this guide depends on it.

```bash
./build/maned-opt \
  --lower-maned-to-linalg \
  tests/mlir/lower_to_linalg.mlir
```

Other registered project pass arguments include `--maned-to-affine`,
`--lower-maned-to-fpga`, and `--profile-matmul`. Use the matching test fixture
as a known-good starting point.

## 9. Device discovery and remote execution

**Learning objectives**

- Discover workers.
- Execute explicitly against a worker.
- Compare remote results with the local reference.

Discover by broadcast and/or explicit probes:

```bash
./maned-run devices
./maned-run devices --probe HOST:PORT --timeout 1000 --no-broadcast
```

Run one flow remotely:

```bash
./maned-run program.mnd \
  --flow flow_name \
  --in x=... \
  --device http://HOST:PORT \
  --device-user USER \
  --device-pass env:MANED_DEVICE_PASSWORD
```

A pre-issued token can replace user/password authentication:

```bash
--device-token env:MANED_DEVICE_TOKEN
```

Do not combine token authentication with user/password authentication. Credential
flags require `--device`. Use `--verify` to run locally and remotely and compare
decoded outputs:

```bash
./maned-run program.mnd ... \
  --device http://HOST:PORT \
  --device-token env:MANED_DEVICE_TOKEN \
  --verify
```

Script-driven device declarations can activate dependency-ordered dispatch when
no explicit `--device` overrides them. Remote work also requires protocol and
operation compatibility with the worker. The
[remote worker guide](15_REMOTE_WORKER_GUIDE.md) provides progressive,
self-contained examples for this mode.

## 10. File I/O, frames, serving, and the Bark VM (2026-09 arcs)

Every snippet in this chapter is a runnable file — no freehand code.

### Files in and out (lang_061-064)

`in::x = csv("path")` reads coordinator-side before any dispatch;
`out::name = csv|text|image("path")` writes after the run. See
`mnd_scripts/examples/example_inputs_and_outputs.mnd` and the file-I/O
verification scripts under `mnd_scripts/demos/`. Numbers cross the quant
boundary (`quantres=2` turns `3.14` into `314` and back); `text`/`image`
are raw bytes. Parquet is read-only.

### Frames (lang_074-078)

`frame::f = jsonl("docs.jsonl")` builds one integer table from JSON
documents of differing shapes (union schema + presence mask). Run
`mnd_scripts/demos/profile_frame.mnd` for the profiles()-to-table loop.
Under maned-run, `profiles()` as a frame source REFUSES with E018 (it
is a serve request source — gap_011); the file-list form is scheduled
work.

### Serving a script (lang_066-073)

`maned-serve model.mnd --port 8080` serves the same engine over HTTP:
`/run` (multipart), `/run.json`, `/frame` views, `/health`, `/contract`.
`--max-requests N` makes the server exit 0 after N responses (the CI
idiom). Request inputs override script defaults **last-wins**, including
in `profile::`/`out::` views (gap_001). Flag reference: 07_CLI page.

### The Bark VM and auto-fallback (gap_019 semantics)

`device::rex { host = "local"; }` routes to the hosted bark worker (no
network, no credentials). When a *declared network worker* is unreachable
at the transport level, the flow executes on the local Bark VM instead —
results are exact, and the run prints
`notice: device 'alias' (host:port) unreachable - executed on local Bark
VM (results exact)`. Under `--verify` the verdict names its comparison
target (hardware vs Bark VM) so a VM pass never masquerades as a hardware
pass. `--no-vm-fallback` turns the fallback into a hard error. A
discovery alias that does not resolve fails only the flows that target
it (gap_019); unrelated flows still run.

## 10b. Shipping, speed, and bisecting a numeric change

**Learning objectives**

- Hand a run to someone with no toolchain.
- Make a run faster without changing what it computes.
- Bisect a suspected numeric change.

Every flag here is specified in
[07_CLI_AND_SCRIPTS.md](07_CLI_AND_SCRIPTS.md); this section is about when to
reach for them.

> **The script path comes first.** `maned-run` parses flags starting *after*
> the first argument, so `maned-run script.mnd --threads 8` works and
> `maned-run --threads 8 script.mnd` does not — the flag is taken as the
> filename and you get `unknown argument: 8` (exit 2), which does not hint at
> the cause. The one exception is the bundle form, which the usage line spells
> out: `maned-run --bundle OUT.bundle script.mnd`.

### Hand the whole run to someone else (`--bundle`)

```bash
maned-run --bundle demo.bundle demo.mnd
# bundled demo.mnd + 1 data file(s) -> demo.bundle (1552252 bytes)

./demo.bundle                  # runs on the same platform, no toolchain
./demo.bundle --bundle-list    # what is inside
./demo.bundle --version        # runner version, producing commit, script hash
```

The bundle is a POSIX `sh` stub with a tar payload appended: the script, every
`in::`/`frame::` file it statically names, the `maned-run` binary, and
(unless you pass `--bundle-no-vm`) `bark-vm`. Inputs are resolved at **bundle
time**, so a missing or glob-derived source fails while you are building it,
not on the recipient's machine. The stub verifies every manifest hash before
executing, so a tampered payload refuses to run.

On macOS, a bundle *downloaded* onto another Mac picks up a quarantine
attribute that blocks the embedded binaries. Clear it once:
`xattr -d com.apple.quarantine ./demo.bundle`.

### Make it faster without changing the answer (`--threads`)

```bash
maned-run heavy.mnd --threads 8
maned-run heavy.mnd --threads 1     # same numbers, one thread
```

`--threads` splits the local kernels into fixed row bands. The partition
depends on the output shape and N only — never on timing — and no accumulator
is ever split across threads, so the result is identical at every N *by
construction*. That is what makes `--threads 1` an exact A/B switch rather
than a second implementation: if output ever moves with N, that is a bug in
the threading, not a tolerance to accept.

### Bisect a suspected numeric change

Two flags exist specifically so a "the numbers moved" report can be narrowed
without a debugger:

```bash
maned-run script.mnd --threads 1 --no-buffer-reuse   # the plainest path
```

`--no-buffer-reuse` disables the liveness-driven reuse of dead buffers. Like
threading, reuse is bit-exact by construction — it changes which allocation
holds a value, never the value — so a difference across either flag localizes
the bug immediately.

For the corpus as a whole, the gate is:

```bash
sh tools/ab_corpus.sh > /tmp/now.txt
diff priority/gap_2026-09/AB_BASELINE.txt /tmp/now.txt   # must be empty
```

Re-freeze that baseline **only** when a change legitimately adds a script to
the corpus — never to make a hash difference go away.

### Saturating arithmetic, for debugging only (`--quant-mode sat`)

```bash
maned-run script.mnd --quant-mode sat
```

The default `wrap` is the mod-2³² register wrap every worker implements, and
is the contract. `sat` clamps into the script's declared quant range instead,
which is useful when you suspect an overflow is the reason a result looks
wrong. It deliberately departs from the worker contract: it prints a note
saying so, and it is refused together with `@device` routing, because a
saturating local run is not comparable to a remote one.

### Serving on more than one thread (`--workers`)

```bash
maned-serve script.mnd --port 8080 --workers 4
```

Default is 1 — the historical single-threaded loop, with no threads created at
all. Workers are per **connection** (a keep-alive connection stays on its
worker). `--max-requests` is claimed before serving, so N workers never
over-serve, and the server drains in-flight requests before exiting. It is
refused for scripts with `@device` routing, since routed execution reaches the
single-threaded Bark VM channel — that combination errors by name rather than
racing.

## 11. Benchmarks

**Learning objectives**

- Run a representative workload.
- Separate correctness from timing.

```bash
python3 mnd_scripts/benchmarks/run_benchmark.py
python3 mnd_scripts/benchmarks/run_suite_benchmark.py
```

Use the benchmark report and Python baselines to understand comparisons. Do not
accept a faster result that fails output validation. Benchmarks are measurements;
CTest and verification suites are correctness gates.

## 12. Daily engineering workflow

1. Pull or inspect the intended change and read the relevant technical page.
2. Configure once; build the smallest affected target.
3. Add or adjust a focused test before changing semantics.
4. Run `maned-lint` on edited `.mnd` files.
5. Run the focused test, then the full CTest suite.
6. Run objective/benchmark checks when touching performance, quantization, or IR.
7. Update examples and documentation when behavior changes.
8. Review `git diff` and preserve unrelated working-tree changes.

## 13. Progressive labs

### Lab 1: environment proof

Build the toolchain on your machine and record the compiler and revision the
build script reports.

### Lab 2: input validation

Run `maned_lang/tests/cli/matmul_relu.mnd` successfully, then deliberately supply only three
values for a `2x2` input. Explain the failure.

### Lab 3: lint repair

Run the linter on `tests/cli/maned_lint_invalid.mnd`. Identify one error and
one warning, then describe the source change that would address each.

### Lab 4: focused regression

Run only the parser suite, then the complete gate. Explain when each command is
appropriate.

### Lab 5: compiler pass

Run the Linalg lowering fixture and identify the dialect of the resulting core
operation.

## 14. Solutions

### Lab 1

From the workspace root:

```bash
sh maned_lang/scripts/build-tools.sh
```

The script prints the compiler it used, the version stamp and the git
revision, then runs a smoke program — no CMake and no LLVM are involved:

```text
compiler: c++ (Darwin)   version: <dev default>   rev: 5cdeae3
built:
  maned-run      arm64            0 internal symbols
```

### Lab 2

The successful command is shown in section 4. A `2x2` tensor requires four
row-major values, so `2x2:1,2,3` is rejected as a bad `--in`.

### Lab 3

Use:

```bash
./maned-lint tests/cli/maned_lint_invalid.mnd
```

Resolve undefined names by defining/passing them before use; resolve unused
bindings by using them or removing them. Preserve warnings that intentionally
teach a lint rule only in test fixtures.

### Lab 4

```bash
sh tools/run_tests.sh parse
sh tools/run_tests.sh
```

The first shortens the edit/debug loop; the second detects cross-subsystem
regressions before handoff. The filter is a substring match on the SUITE NAME,
not on the path, so `parse` runs `parse` and `bench_parse` — the parser tests
under `tests/parse/` that are named otherwise (`reserved`, `grammar`) are not
picked up.

### Lab 5

Needs the optional MLIR build from section 1.

```bash
./build/maned-opt --lower-maned-to-linalg \
  tests/mlir/lower_to_linalg.mlir
```

The Maned matrix operation is lowered into the standard Linalg path. Compare
the output with the `CHECK` expectations in the fixture.
