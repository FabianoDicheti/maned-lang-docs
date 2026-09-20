# MLIR Compiler

The MLIR path is a separate compiler library from `maned_core`. It defines
Maned and FPGA dialects, lowers operations to standard dialects, and provides
profiling annotations through `maned-opt`.

## Definitions and generated interfaces

| File | Responsibility | Generated/consumed artifacts |
|---|---|---|
| `include/maned/mlir/CMakeLists.txt` | Runs MLIR TableGen and exposes generation targets. | Produces eight `*.inc` files under the binary include tree. |
| `include/maned/mlir/ManedDialect.td` | Main dialect metadata and operation base class. | Included by main operation definitions. |
| `include/maned/mlir/ManedOps.td` | Main Maned operation schemas, operands, results, and traits. | Generates op/dialect declarations and definitions. |
| `include/maned/mlir/ManedFPGADialect.td` | FPGA dialect metadata and operation base. | Included by FPGA operation definitions. |
| `include/maned/mlir/ManedFPGAOps.td` | Hardware-facing operation schemas and verification constraints. | Generates FPGA op/dialect declarations and definitions. |
| `include/maned/mlir/ManedDialect.h` | Public main dialect wrapper around generated declarations. | Included by dialect implementation, passes, and tools. |
| `include/maned/mlir/ManedFPGADialect.h` | Public FPGA dialect and pass-registration declarations. | Included by FPGA implementation and compiler driver. |
| `include/maned/mlir/ManedPasses.h` | Main lowering pass construction/registration API. | Used by `maned-opt` and tests. |

TableGen emits `ManedOps.h.inc`, `ManedOps.cpp.inc`,
`ManedOpsDialect.h.inc`, `ManedOpsDialect.cpp.inc`,
`ManedFPGAOps.h.inc`, `ManedFPGAOps.cpp.inc`,
`ManedFPGAOpsDialect.h.inc`, and `ManedFPGAOpsDialect.cpp.inc`.
Headers include declaration fragments; dialect source files include definition
fragments. `ManedOpsIncGen` and `ManedFPGAOpsIncGen` enforce generation order.

## Implementations and passes

| File | Responsibility | Interactions |
|---|---|---|
| `src/mlir/ManedDialect.cpp` | Registers and materializes the main generated dialect/operations. | Compiled into `ManedMLIR`. |
| `src/mlir/ManedFPGADialect.cpp` | Registers FPGA operations and validates hardware constraints. | Used by FPGA lowering and verifier tests. |
| `src/mlir/LowerToLinalg.cpp` | Converts supported Maned operations toward Linalg/standard dialects. | Exposed through `ManedPasses.h`. |
| `src/mlir/LowerToFPGA.cpp` | Converts eligible operations into the FPGA dialect. | Uses both dialects and hardware legality rules. |
| `src/mlir/ProfileMatmul.cpp` | Profiles/annotates matrix multiplication for target selection. | Registered with FPGA/profile passes. |
| `tools/maned-opt/maned_opt.cpp` | Registers dialects/passes and delegates CLI handling to `MlirOptMain`. | Links `ManedMLIR`, MLIR opt, transforms, and dialect libraries. |
| `tools/mlir_smoke/maned_mlir_smoke.cpp` | Minimal MLIR parser/context integration executable. | Proves the external MLIR toolchain is wired correctly. |

## Pass flow

An MLIR text file is parsed into a context with registered dialects. `maned-opt`
constructs the requested pass pipeline. A main-dialect operation can be inspected
by the profiling pass, lowered to Linalg/affine-oriented forms, or lowered to the
FPGA dialect. MLIR diagnostics report illegal types/shapes or failed conversions.

## Supporting tool notes

| File | Purpose |
|---|---|
| `tools/build_system/cmake_mlir.md` | CMake/MLIR integration reference. |
| `tools/build_system/mlir_builder.md` | MLIR build workflow guidance. |
| `tools/code_generation/mlir_tablegen.md` | TableGen generation guidance. |
| `tools/testing/mlir_filecheck.md` | FileCheck testing conventions. |

When adding an operation, update the relevant `.td`, regenerate via CMake, implement
required parsing/printing/verification or lowering behavior, register the pass or
dialect, and add round-trip plus lowering tests.
