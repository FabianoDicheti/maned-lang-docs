# Objectives

The numeric targets the project set itself, what they were measured at, and who
owns the ones `maned_lang` cannot close.

This document exists because those targets nearly went missing. Until gap_032
they survived only in `tools/verify_objectives.sh`'s report template — which
cited four sources (`README.md:441`, `LANGUAGE_SPEC_RPN.md`, `DECISIONS.md`,
`ROADMAP M2`) that were all evicted to `_attic_maned_lang/` in the 2026-09-15
reorganization — plus the attic itself and git history. A target with no living
home is a target nobody is accountable for.

**This file is the citation target.** `tools/verify_objectives.sh` measures
against it and writes its scorecard to
[`docs/scripts/OBJECTIVES_VERIFICATION.md`](../scripts/OBJECTIVES_VERIFICATION.md).
The seven objective suites also run in the ordinary unit gate (`bench_compile`,
`bench_parse`, `vf_contract`, `vf_integer`, `vf_quant`, `vf_precision`,
`vf_overhead`), so a regression shows up without anyone remembering to ask.

## In scope for maned_lang

| # | Objective | Target | Last measured | Verdict |
|---|---|---|---|---|
| O1 | Compile speed | < 1 s per 1000 LOC | 3.287 ms / 1000 LOC | **Met** |
| O2 | Parse scaling | linear (≈2× per input doubling) | 2.08× worst doubling | **Met** |
| O3 | Quantization accuracy | < 5 % loss | 0.002 % relative error (best, at `quantres=4`) | **Met** |
| O4 | Simulation matches worker precision | integer, wrap-exact | exact — `--verify` is equality | **Met** |
| O5 | Deterministic execution | same in → same out | identical across runs | **Met** |
| O6 | Integer-only runtime | no floating point at run time | int64 values throughout | **Met** |
| O7 | Zero-overhead abstractions | stack ops and object params cost nothing at run time | 0 stack nodes in the dataflow; `conv2d` object params resolve to 2 positional operands | **Met** |
| O8 | Binary IR well-formed | fixed-width instructions + magic | yes (16-byte instructions under ABI v2) | **Met** |
| O9 | Compile-time quantization of in-source FP literals | scale literals by 10^quantres | host-boundary `Quantizer` scales at the boundary; the interpreter constant path does not auto-scale | **Partial** |

Measurements are from the 2026-09-17 gate run on Apple arm64. They are recorded
here as the most recent reading, not as a contract — the suites are the contract.

O9 is the one in-scope objective not fully met, and the suite says so itself
(`vf_integer` emits `NOTE … (PARTIAL)`). It is reported rather than rounded up.

## Cross-workstream — not maned_lang's to close

The full Maned vision is four workstreams. These targets belong to the other
three, and a `maned_lang` scorecard must not imply otherwise:

| Target | Owner |
|---|---|
| 38.4 GOPS (INT8) peak, ~30 GOPS sustained, 150–200 MHz, < 25 W | `maned_board` |
| Memory bandwidth 10 GB/s at 75–85 % utilization | `maned_board` |
| Multi-FPGA scaling ≥ 90 % linear | `maned_board` |
| < 1 µs syscall / context switch / IPC, < 100 KB kernel, < 100 ms boot | `maned_os` |

## The three language goals

- **Elegant** — RPN with no precedence rules, integer-only semantics, a formal
  grammar, and combinators in the evaluator. Met for the implemented surface.
  The Y-combinator and lambda *expressions* are retracted (E017), not pending:
  bounded recursion is `@unroll` on a named flow.
- **Performative** — linear front end (O2), zero-overhead abstractions (O7),
  constant CSE and dead-value elimination, buffer liveness and reuse, threaded
  local kernels, and lowering to linalg → affine plus an FPGA dialect. Met at
  the compiler level; runtime GOPS is `maned_board`'s.
- **Portable** — the same `.mnd` runs on the local interpreter, the hosted Bark
  VM, and a real x86 worker, and `--verify` asserts the three agree bit for bit.
  Met.

## What this page is not

It is not a roadmap and not a status report. It holds the *targets* and the
*most recent measurement*. Open work lives in `priority/`; the current gap
backlog is `docs/GAP_ANALYSIS_2026-09-16.md` and
`docs/GAP_VERIFICATION_2026-09-17.md`.
