# Maned Technical Documentation

This folder explains the code, scripts, build outputs, tests, examples, and editor
integration that make up Maned. It is written for contributors who need to find
an entry point, follow a value through the system, or decide where a change belongs.

## Reading order

1. [Project structure](01_PROJECT_STRUCTURE.md) — repository map and end-to-end flows.
2. [Language frontend](02_LANGUAGE_FRONTEND.md) — source text, parsing, AST, types, and linting.
3. [IR and protocols](03_IR_AND_PROTOCOLS.md) — dataflow, binary IR, and wire formats.
4. [Interpreter and quantization](04_INTERPRETER_AND_QUANTIZATION.md) — local execution.
5. [MLIR compiler](05_MLIR_COMPILER.md) — compiler dialects and lowering passes.
6. [Network and dispatch](06_NETWORK_AND_DISPATCH.md) — remote and concurrent execution.
7. [CLI and scripts](07_CLI_AND_SCRIPTS.md) — user-facing executables and automation.
8. [Build and artifacts](08_BUILD_AND_ARTIFACTS.md) — targets and generated files.
9. [Testing](09_TESTING.md) — test ownership and verification strategy.
10. [Benchmarks and examples](10_BENCHMARKS_AND_EXAMPLES.md) — runnable workloads.
11. [Editor integration](11_EDITOR_INTEGRATION.md) — VS Code language support.
12. [Maned language guide](12_MANED_LANGUAGE_GUIDE.md) — learn the language and its RPN model.
13. [Maned usage guide](13_MANED_USAGE_GUIDE.md) — install, build, run, lint, and debug programs.
14. [Compiler development guide](14_MANED_COMPILER_DEVELOPMENT_GUIDE.md) — extend the frontend, runtime, protocols, and MLIR compiler.
15. [Remote worker guide](15_REMOTE_WORKER_GUIDE.md) — offload flows, mix local and remote work, and coordinate workers.
16. [Diagnostics reference](16_DIAGNOSTICS.md) — every E0xx/W0xx code the toolchain emits, and how to allocate a new one.

## Scope

These pages cover implementation-bearing files and the artifacts they produce.
The repository itself (`maned_lang/`) is kept dry — code, build, tests,
packaging, one README; this folder (workspace `docs/language/`) is the full
technical reference for it. Historical agent-process material was archived to
the workspace `_attic_maned_lang/` tree (2026-09-15) and is not source of
truth for the current code.

## Plan and report documents (same folder)

- [NESTED_FLOWS_REQUIREMENTS](NESTED_FLOWS_REQUIREMENTS.md) / [NESTED_FLOWS_PLAN](NESTED_FLOWS_PLAN.md) — lang_048–060 arc (landed).
- [FILE_IO_PLAN](FILE_IO_PLAN.md) — lang_061–065 (landed).
- [SERVE_PLAN](SERVE_PLAN.md) — lang_066–069 (landed).
- [DATAFRAME_PLAN](DATAFRAME_PLAN.md) — lang_074–078 (landed).
- [LANGUAGE_IMPROVEMENTS_2026-09-14](LANGUAGE_IMPROVEMENTS_2026-09-14.md) — 14-item improvement matrix from the ML campaign.
- [AULA_MANED](AULA_MANED.md) — guided lesson (Portuguese).

## Documentation conventions

- “Public interface” means a declaration under `include/maned/`.
- Paths are repository-relative.
- A producer creates or populates a structure/artifact; a consumer reads or runs it.
- The build snapshot in [Build and artifacts](08_BUILD_AND_ARTIFACTS.md) describes the
  local tree on 2026-07-23 and is not a promise that ignored build files stay present.
