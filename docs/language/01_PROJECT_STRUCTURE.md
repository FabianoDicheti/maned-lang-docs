# Project Structure

## High-level map

| Path | Purpose | Main relationships |
|---|---|---|
| `include/maned/` | Public C++ interfaces and MLIR TableGen definitions. | Implemented by `src/`; consumed by tools and tests. |
| `src/` | Core frontend, runtime, protocol, networking, and compiler implementations. | Built into `maned_core` or `ManedMLIR`. |
| `tools/` | Executable entry points plus build/code-generation/testing tool notes. | Links libraries declared in `CMakeLists.txt`. |
| `tests/` | C++ unit/integration tests, MLIR FileCheck inputs, and CLI fixtures. | Registered with CTest by `CMakeLists.txt`. |
| `grammar/` | Human-readable language grammar and reserved-word list. | Defines the intended syntax implemented by the lexer/parser. |
| `scripts/` | The build entry point (`build-tools.sh`). | Invoked verbatim by CI; test gates live beside the repo in `../tools/`. |
| `syntaxes/`, `images/` | VS Code grammar and icon asset. | Referenced by `package.json` and theme configuration. |
| `CMakeLists.txt` | Canonical C++/MLIR build and test graph. | Produces libraries, CLIs, generated includes, and tests. |
| `package.json`, `language-configuration.json`, `maned-icon-theme.json` | VS Code extension manifest and behavior. | Connect `.mnd` files to syntax and icons. |
| `build/` | Ignored, machine-local compiled/generated output. | Produced by CMake or local bootstrap work. |

Example programs and benchmarks are not in the repo: they live beside it in
`../mnd_scripts/`, documentation in `../docs/`, and the test/campaign
scripts (`run_tests.sh`, `test_barkvm_e2e.sh`, `verify_objectives.sh`,
`run_campaign.sh`, `ab_corpus.sh`) in `../tools/`.

## Code subsystem map

| Subsystem | Header/source directories | Responsibility |
|---|---|---|
| AST | `include/maned/ast`, `src/ast` | Owned syntax tree and source ranges. |
| Types and operations | `include/maned/types`, `include/maned/ops`, matching `src/` | Shapes, dtypes, inference, and operation metadata. |
| Parsing and linting | `include/maned/parse`, `include/maned/lint`, matching `src/` | Text-to-AST conversion and static diagnostics. |
| IR | `include/maned/ir`, `src/ir` | Executable dataflow graphs and compact binary instructions. |
| Interpreter | `include/maned/interp`, `src/interp` | Local scalar/tensor/lambda execution. |
| Quantization | `include/maned/quant`, `src/quant` | Value calibration and quantize/dequantize transforms. |
| Protocol | `include/maned/proto`, `src/proto` | MNPK requests, MNRS responses, JSON, and structured errors. |
| Networking | `include/maned/net`, `src/net` | HTTP, devices, discovery, jobs, and dispatch. |
| Analysis | `include/maned/analysis`, `src/analysis` | Matrix profiling and deterministic operand synthesis. |
| File I/O | `include/maned/io`, `src/io` | `in::`/`out::` sources and sinks: csv, text, image, parquet. |
| Dataframes | `include/maned/frame`, `src/frame` | Streaming JSONL scanning and union-schema columnar tables. |
| Serving | `include/maned/serve`, `src/serve` | `maned-serve`: HTTP, multipart, JSON, one script as an API. |
| Run packaging | `include/maned/run`, `src/run` | `--bundle`: the self-contained sh + ustar replay archive. |
| MLIR | `include/maned/mlir`, `src/mlir` | Dialects, generated operations, lowering, and profiling. |

Three files inside those directories are worth naming, because each is the
single place a rule lives and a second copy would be a bug:

| File | Why it is the only copy |
|---|---|
| `src/ops/executable_ops.cpp` | Partitions the op registry into locally- vs remotely-executable sets. Tests pin it against the registry and `opcodeFor`, so an op cannot be added to one side only. |
| `src/ir/liveness.cpp` | Value live ranges (`computeLiveness`, `diesAt`) behind buffer reuse. Reuse must be bit-exact, so the range rule cannot be re-derived ad hoc. |
| `src/interp/parallel.cpp` | Row-band threading. Bands are a fixed function of shape, never of thread timing — that is what makes `--threads` change wall time and nothing else. |

## Main execution flows

### Local interpreter

| Step | Producer | Output | Consumer |
|---|---|---|---|
| 1 | `Lexer` | Tokens with source locations | `Parser` |
| 2 | `Parser` | `ast::Program` | Linter, CLI, dataflow builder |
| 3 | `buildDataflow` | `ir::DataflowGraph` | Interpreter, binary serializer, dispatcher |
| 4 | `Interpreter` with operation evaluator | `interp::Value` outputs or `InterpError` | CLI, verification, remote comparison |

### Remote execution

| Step | Producer | Output | Consumer |
|---|---|---|---|
| 1 | Parser/device collector | AST flows and device declarations | Dispatcher |
| 2 | Dispatcher/dataflow builder | Planned graphs and input values | Remote job encoder |
| 3 | Binary IR and MNPK serializers | Request bytes | `DeviceSession`/HTTP client |
| 4 | Worker response | MNRS bytes or JSON error | Protocol decoder |
| 5 | Dispatcher | Per-flow outputs and diagnostics | `maned-run` |

### MLIR compiler

| Step | Producer | Output | Consumer |
|---|---|---|---|
| 1 | TableGen from `*.td` | Generated dialect/op `*.inc` files | Dialect C++ implementations |
| 2 | MLIR parser | Maned MLIR module | `maned-opt` pass manager |
| 3 | Lowering/profile passes | Linalg, affine, FPGA, or annotated MLIR | Downstream MLIR tooling |

## Where to make common changes

| Goal | Start here | Usually update too |
|---|---|---|
| Add language syntax | `grammar/maned.ebnf`, lexer/parser headers and sources | AST, parser tests, editor grammar |
| Add an operation | `include/maned/ops/op_signature.h`, registry source | parser, interpreter evaluator, IR opcode, tests |
| Change runtime semantics | interpreter source | golden suite, examples, verification checks |
| Add remote capability | networking/protocol headers | stub-server tests and `maned-run` |
| Add an MLIR operation | `ManedOps.td` or `ManedFPGAOps.td` | dialect implementation, passes, MLIR tests |
| Add a CLI | a new `tools/<name>` entry point | CMake target, CLI tests, this documentation |
