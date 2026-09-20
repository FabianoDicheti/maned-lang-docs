# Testing

> **Role:** descriptive of the suites as built. (gap_017 refresh, 2026-09-15)

**There is no cmake/ctest gate without an MLIR install.** The gate is
`../tools/run_tests.sh` (the test scripts live beside the repo in the
workspace `tools/` tree): every hermetic suite is a plain-compiler build
(CORE = parse/lint sources, FULL = everything) listed in the table inside
that script; any new `src/*.cpp` must be added to THREE source lists —
`../tools/run_tests.sh`, `scripts/build-tools.sh`, and the inlined copy of
the gate in `.github/workflows/release.yml` (CI sees only the repo, so the
release workflow carries its own copy of the suite table). Companion
scripts: `scripts/build-tools.sh` (the three shipped tools),
`../tools/test_barkvm_e2e.sh` (end-to-end against the Bark VM),
`../tools/verify_objectives.sh`.

**Three similarly-named things — keep them apart** (counts re-measured
2026-09-16; they grow, so trust the command, not the number):

1. maned_lang's gate: `../tools/run_tests.sh` (workspace tree, beside the
   repo), **36 suites**.
2. `tools/run_suites.sh` is the BARK repo's runner, **92 suites** — it globs
   `tests/*.sh`, so the count moves whenever a script lands. `BARK_STRICT=1`
   is its pre-trip gate.
3. The script corpus is `../mnd_scripts/`, **111 `.mnd` files**. Two
   different runners cover it, and they cover different subsets:
   - `../tools/ab_corpus.sh` is the **bit-exact A/B gate**. It is deliberately
     narrow: `examples/`, `benchmarks/` and `benchmarks/generated_cases/`
     only, minus anything naming a `192.168.` worker — **38 selected, 34
     hashed** (the four remote-naming scripts drop out). Those
     are the ones whose output is reproducible on any machine with no network,
     so a hash diff means a real numeric change. Lint and run output are
     hashed separately, because honesty tickets legitimately add diagnostics.
   - `../tools/run_campaign.sh` runs **everything** and classifies the outcome
     (PASS / REFUSED / NEEDS-INPUTS / REMOTE / TIMEOUT) rather than hashing it.
     Use it to answer "does the corpus still run", not "did the numbers move".

The 88 that older revisions of this file quoted for both (2) and (3) was a
coincidence of two different counts at one moment, and both have since moved.

## Frontend and type tests

| File | Covers |
|---|---|
| `tests/types/test_type.cpp` | Dtypes, shapes, broadcasting, inference, and quant metadata. |
| `tests/ops/test_op_registry.cpp` | Built-in operation signatures and lookup. |
| `tests/parse/test_parser.cpp` | Valid/invalid syntax and AST construction. |
| `tests/parse/test_decorator.cpp` | Decorator recognition, targets, and validation. |
| `tests/parse/test_literal_shape.cpp` | Rectangularity and tensor shape inference. |
| `tests/lint/test_linter.cpp` | AST lint rules, severities, locations, and messages. |

## IR, interpreter, and quantization tests

| File | Covers |
|---|---|
| `tests/ir/test_dataflow.cpp` | AST flow conversion, dependencies, and graph outputs. |
| `tests/ir/test_binary_ir.cpp` | Opcode mapping, ABI v1/v2 round trips, version negotiation, and malformed binary input. |
| `tests/ir/test_inline_calls.cpp` | Helper-flow inlining: the graph that actually ships is the inlined one. |
| `tests/ir/test_liveness.cpp` | Value live ranges and buffer-reuse statistics (gap_022). |
| `tests/ir/test_param_ops.cpp` | Parameterised ops: immediates, the 5th-operand encoding, multi-output `nout`. |
| `tests/interp/test_interpreter.cpp` | Scheduling, inputs/outputs, and runtime errors. |
| `tests/interp/test_lambda.cpp` | Lambda application, primitives, and combinators. |
| `tests/interp/test_matrix_ops.cpp` | Tensor/matrix operation semantics and shape failures. |
| `tests/interp/test_activation.cpp` | Activation-function semantics across the integer range. |
| `tests/interp/test_spatial_coverage.cpp` | Conv/pool spatial coverage — every element visited exactly once. |
| `tests/interp/test_int8_emulation.cpp` | Precision ranges and saturation. |
| `tests/interp/test_golden_suite.cpp` | End-to-end expected results across representative programs. |
| `tests/quant/test_quantizer.cpp` | Calibration, quantization, dequantization, and edge cases. |

## Serve, frame, and file-I/O tests (lang_061-080 arcs)

| File | Covers |
|---|---|
| `tests/serve/test_serve.cpp` | HTTP parse/render, multipart, JSON, /run + /run.json end-to-end, profile responses, override binding (gap_001 last-wins). |
| `tests/frame/test_dataframe.cpp` | Union-schema columnar tables, presence mask, projections. |
| `tests/frame/test_json_stream.cpp` | Streaming JSONL document splitter/scanner. |
| `tests/io/test_fileio.cpp` | csv/text reads+writes across the quant boundary. |
| `tests/io/test_parquet.cpp` | Parquet reader (read-only contract). |

## Honesty-wave suites (gap_2026-09)

| File | Covers |
|---|---|
| `tests/parse/test_reserved_words.cpp` | reserved_words.txt vs parser sets drift gate (gap_004). |
| `tests/parse/test_grammar_snippets.cpp` | One parse-clean snippet per EBNF production (gap_015 drift brake). |
| `tests/cli/test_cli_docs_drift.cpp` | Every tool flag documented in 07_CLI_AND_SCRIPTS.md (gap_016; skips on a standalone clone). |
| `tests/cli/test_docs_coverage_drift.cpp` | Every diagnostic code the tools emit has a row in 16_DIAGNOSTICS.md, and every registry op appears in the guide's op table (gap_016/gap_017; skips on a standalone clone). |
| `tests/ir/test_limits.cpp` + cli fixtures | Post-inline worker-contract limits, shared by run and lint (gap_014). |

## Analysis and packaging tests

| File | Covers |
|---|---|
| `tests/analysis/test_matrix_profile.cpp` | Matrix profiling: shape/density statistics the planner reads. |
| `tests/analysis/test_matrix_synth.cpp` | Matrix synthesis used to build test operands deterministically. |
| `tests/run/test_bundle.cpp` | `--bundle`: the sh-stub + ustar archive, MANIFEST hashes, and `--bundle-verify` (gap_012). |

## Protocol and networking tests

| File | Covers |
|---|---|
| `tests/stub_server.h` | Reusable local HTTP test server used by networking tests. |
| `tests/test_mnpk.cpp` | MNPK/MNRS serialization, parsing, conversion, and malformed payloads. |
| `tests/test_http_client.cpp` | Requests, responses, limits, timeouts, and transport errors. |
| `tests/test_device.cpp` | Configuration, status, capabilities, and structured errors. |
| `tests/test_device_syntax.cpp` | Parser/device-block integration. |
| `tests/test_remote_execute.cpp` | Remote preflight, payloads, responses, and local verification. |
| `tests/test_async_jobs.cpp` | Job submission/polling and sync fallback. |
| `tests/test_async_dispatch.cpp` | Concurrent flow planning/execution and aggregation. |
| `tests/test_discovery.cpp` | Discovery reply parsing and network discovery behavior. |
| `tests/test_local_vm.cpp` | The Bark VM stdio binding (PROTOCOL_SPEC Section 12): framing, HELO/MNPK/MNRS/ERRJ, unreachable-device fallback. |

## MLIR tests

**These run only on an MLIR-equipped host** (full MLIR toolchain +
`maned-opt`; this workspace's laptops do not carry one - gap_020 item 8).
Command on such a host: build `maned-opt` with MLIR available, then run
the FileCheck files below through it. Do not report these as covered by
`../tools/run_tests.sh` - they are not in its table by design.

| File | Covers |
|---|---|
| `tests/mlir/maned_ops.mlir` | Dialect parse/print round trip. |
| `tests/mlir/lower_to_linalg.mlir` | Main-to-Linalg conversion. |
| `tests/mlir/lower_to_affine.mlir` | Lowering toward affine-compatible forms. |
| `tests/mlir/lower_to_fpga.mlir` | Main-to-FPGA conversion. |
| `tests/mlir/fpga_verifier_invalid.mlir` | Expected FPGA verifier rejection. |
| `tests/mlir/profile_matmul.mlir` | Matrix-profile annotations/decisions. |

## CLI fixtures

| File | Covers |
|---|---|
| `tests/cli/maned_run.check` | Successful `maned-run` output. |
| `tests/cli/maned_run_bad_input.check` | Runner parse/input failure. |
| `tests/cli/maned_lint_valid.mnd` | Clean lint input. |
| `tests/cli/maned_lint_invalid.mnd` | Expected lint diagnostics. |

## Objective and performance verification

| File | Covers |
|---|---|
| `tests/verify/bench_compile.cpp` | Compile/build performance gate. |
| `tests/verify/bench_parse_scaling.cpp` | Parser scaling behavior. |
| `tests/verify/verify_contract.cpp` | External integration contract assumptions. |
| `tests/verify/verify_integer_only.cpp` | Integer-only quantized execution invariant. |
| `tests/verify/verify_quant_accuracy.cpp` | Quantization error bounds. |
| `tests/verify/verify_sim_precision.cpp` | Simulated constrained-precision behavior. |
| `tests/verify/verify_zero_overhead.cpp` | Claimed abstraction-overhead constraints. |

The harness that builds and runs these is `../tools/verify_objectives.sh`;
it writes the scorecard to `../docs/scripts/OBJECTIVES_VERIFICATION.md`
(needs an MLIR install, since it also gates on `ctest` + `maned-opt`).

## Change-to-test mapping

Frontend changes require parser/type/lint tests. Runtime operations require
interpreter, matrix, and golden tests. Wire-format changes require binary IR,
MNPK, remote, and contract tests. Network changes require stub-server success and
failure cases. MLIR changes require round-trip, relevant lowering, and invalid
verifier coverage. Numerical changes require accuracy and integer-only gates.
