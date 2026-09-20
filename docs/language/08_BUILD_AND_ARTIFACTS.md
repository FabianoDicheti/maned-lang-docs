# Build and Artifacts

## Build inputs

| File | Purpose |
|---|---|
| `CMakeLists.txt` | Top-level C++17 project, MLIR discovery, targets, dependencies, warnings, and CTest registration. |
| `include/maned/mlir/CMakeLists.txt` | TableGen rules for the two Maned MLIR dialects. |
| `.gitignore` | Excludes `build/`, object/static-library outputs, compile databases, and CMake internals. |

Configuration requires an MLIR installation discoverable through CMake. The
frontend/runtime library otherwise remains MLIR-free.

## Stable target map

| Target | Kind | Principal inputs | Consumers/output |
|---|---|---|---|
| `maned_core` | Static library | AST, types, ops, parse, lint, IR, interpreter, quant, protocol, net sources | Linked by runtime CLIs and most C++ tests; normally `libmaned_core.a`. |
| `ManedOpsIncGen` | Generation target | `ManedDialect.td`, `ManedOps.td` | Four main dialect/op include fragments. |
| `ManedFPGAOpsIncGen` | Generation target | `ManedFPGADialect.td`, `ManedFPGAOps.td` | Four FPGA dialect/op include fragments. |
| `ManedMLIR` | Static library | MLIR dialects and passes | Linked by `maned-opt`; normally `libManedMLIR.a`. |
| `maned-mlir-smoke` | Executable | MLIR smoke source | Basic toolchain check. |
| `maned-opt` | Executable | Compiler driver + `ManedMLIR` | MLIR transformation CLI. |
| `maned-run` | Executable | Runtime CLI + `maned_core` | Local/remote language runner. |
| `maned-lint` | Executable | Lint CLI + `maned_core` | Static-analysis CLI. |
| `mnpk-gen` | Executable | Fixture generator + `maned_core` | Protocol fixture CLI. |
| `test_*`, `bench_*`, `verify_*` | CTest executables | Individual test sources | Unit, integration, benchmark-gate, and contract checks. |

## Generated MLIR artifacts

All generated fragments normally live below
`<binary-dir>/include/maned/mlir/`.

| Artifact | Generator mode | Consumer |
|---|---|---|
| `ManedOps.h.inc` | operation declarations | `ManedDialect.h` |
| `ManedOps.cpp.inc` | operation definitions | `ManedDialect.cpp` |
| `ManedOpsDialect.h.inc` | dialect declaration | `ManedDialect.h` |
| `ManedOpsDialect.cpp.inc` | dialect definition | `ManedDialect.cpp` |
| `ManedFPGAOps.h.inc` | FPGA operation declarations | `ManedFPGADialect.h` |
| `ManedFPGAOps.cpp.inc` | FPGA operation definitions | `ManedFPGADialect.cpp` |
| `ManedFPGAOpsDialect.h.inc` | FPGA dialect declaration | `ManedFPGADialect.h` |
| `ManedFPGAOpsDialect.cpp.inc` | FPGA dialect definition | `ManedFPGADialect.cpp` |

## Exact local build snapshot

Snapshot taken on **2026-07-23**. The current ignored `build/` tree contains:

| Path | Type | Provenance/status |
|---|---|---|
| `build/local/maned-run` | Executable system artifact | Local runtime binary; the only file currently present under `build/`. |

Current totals: two directories (`build/`, `build/local/`) and one file. There is
no configured CMake cache, generated TableGen include tree, static library, test
binary, or compile database in this snapshot. This is an inventory of the current
workspace, not a complete configured-build example.

## Expected transient configured-build artifacts

A normal out-of-source CMake configure/build can also create `CMakeCache.txt`,
`CMakeFiles/`, generated make/ninja files, `cmake_install.cmake`,
`CTestTestfile.cmake`, object/dependency files, test executables,
`compile_commands.json`, static libraries, and the MLIR include fragments above.
These are derived, machine-specific files and must not be committed.

Cleaning `build/` removes only reproducible or locally bootstrapped artifacts.
Reconfigure with the correct MLIR package path, then rebuild the requested target.
