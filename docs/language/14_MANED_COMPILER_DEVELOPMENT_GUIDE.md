# Maned Compiler Development Guide

This guide is for engineers extending Maned itself. Read the
[language guide](12_MANED_LANGUAGE_GUIDE.md) first and keep the
[project structure](01_PROJECT_STRUCTURE.md) open as a subsystem map.

## 1. The architecture in one page

**Learning objectives**

- Trace a source program into local and remote execution.
- Decide which subsystem owns a behavior.

| Stage | Core representation | Owner |
|---|---|---|
| Lexing | `Token` + source location | `parse/lexer` |
| Parsing | Owned `ast::Program` | `parse/parser`, `ast` |
| Static checks | `lint::Diagnostic` | `lint` |
| Semantic metadata | Shapes, types, operation signatures | `types`, `ops` |
| Planning | `ir::DataflowGraph` | `ir/dataflow` |
| Local execution | `interp::Value` | `interp`, `quant` |
| Remote encoding | Binary IR + MNPK | `ir/binary_ir`, `proto` |
| Transport/orchestration | Sessions, jobs, flow results | `net` |
| Compiler lowering | MLIR operations and passes | `mlir` |

A `.mnd` change normally crosses several stages. A textual syntax change ends
at the parser only if it is intentionally metadata-only. Executable behavior
must continue into a backend and its tests.

**Knowledge check:** Where should an invalid matrix shape be caught?  
Prefer the earliest layer with enough information: shape inference or MLIR
verification, with runtime validation retained as a safety boundary.

## 2. Establish a safe development loop

**Learning objectives**

- Work in a dirty repository without losing unrelated changes.
- Build and test proportionally.

Before editing:

```bash
git status --short
ctest --test-dir build --output-on-failure
```

Use C++17 and existing warning settings. Do not edit generated `*.inc` files;
change TableGen definitions and rebuild. Keep reusable logic in libraries rather
than CLI entry points. Add a focused test for the intended behavior and run the
full suite before handoff.

## 3. Adding or changing syntax

**Learning objectives**

- Keep grammar, tokens, AST, parser, linter, and editor support synchronized.
- Preserve source locations and ownership.

Recommended sequence:

1. Define the surface form and ambiguity rule in `grammar/maned.ebnf`.
2. Update `grammar/reserved_words.txt` if a word becomes reserved.
3. Add or adjust token kinds only when syntax cannot be expressed with existing tokens.
4. Add the smallest AST node/field that preserves the language meaning.
5. Parse left-to-right without introducing precedence or backtracking.
6. Preserve source ranges from the first through final token.
7. Extend visitor dispatch and lint traversal.
8. Update TextMate syntax when editor highlighting should recognize it.
9. Add valid, invalid, location, and recovery tests.

The AST uses owning smart pointers. Avoid shared ownership unless the semantic
model requires it. Parser errors should explain what was expected and point to
the token where forward progress stopped.

### Syntax test matrix

| Case | Expected evidence |
|---|---|
| Minimal valid form | Correct AST node kind and fields |
| Nested/composed form | Correct child ownership and RPN grouping |
| Missing delimiter/operand | Deterministic parse error and location |
| Reserved-word collision | Identifier is rejected or classified correctly |
| Following valid statement | Parser recovers without an infinite loop |

## 4. Adding an operation

**Learning objectives**

- Understand the difference between recognition, metadata, and execution.
- Keep arity and shape behavior consistent across backends.

An operation can exist at several support levels:

1. **Grammar/reserved:** the parser recognizes the spelling as an operation.
2. **Registry:** `OpSignature` defines arity, result count, category, target, named
   parameters, and shape inference.
3. **Local runtime:** an `OpEvaluator` or interpreter built-in computes values.
4. **Binary/remote:** an opcode and worker mnemonic encode the operation.
5. **MLIR:** TableGen defines it and one or more passes lower it.

Implement only the levels promised by the feature, but document the status.

### Registry checklist

- Choose exact operand and result counts.
- Reuse a correct shape function or implement a conservative one.
- Use dynamic dimensions when parameters prevent a concrete result.
- Choose CPU, FPGA, or Hybrid based on actual routing support.
- Add lookup, arity, shape-success, and shape-error tests.

### Interpreter checklist

- Reject wrong arity.
- Validate rank, dimensions, data length, and compatible shapes.
- Define scalar broadcasting explicitly.
- Define empty input, overflow, rounding, and division behavior.
- Return a useful error rather than a partial value.
- Add scalar, tensor, boundary, and failure tests plus a golden pipeline case.

## 5. Extending dataflow and binary IR

**Learning objectives**

- Preserve dependency order and output binding.
- Treat serialized opcodes as compatibility-sensitive.

The dataflow builder converts a parsed `LambdaFlow` into numbered nodes and named
outputs. The interpreter assumes operands are available before an operation
executes. When adding a new AST expression:

- emit nodes for all children before the consumer;
- bind every assignment target to the produced value;
- preserve declared output names;
- test repeated references, constants, clocks, and missing outputs.

Binary IR maps operation names to numeric `OpCode` values. Never renumber an
existing opcode casually: serialized requests may outlive the current process.
Add round-trip and malformed/truncated-input tests for format changes. Update
remote mnemonic mapping and the integration contract when compatibility changes.

## 6. Extending local execution and quantization

**Learning objectives**

- Keep scheduling independent from operation mathematics.
- Protect numerical claims with measurable tests.

`Interpreter` schedules graph nodes and delegates operation semantics to
evaluators. Prefer a focused evaluator for a domain such as matrix or lambda
operations. The evaluator returns “not handled” for unrelated operations and a
specific error for a recognized but invalid call.

Quantization changes must specify calibration range, scale/zero-point behavior,
saturation, rounding, and reconstruction error. Run:

- quantizer unit tests;
- quantization accuracy verification;
- simulated precision checks;
- integer-only checks;
- golden end-to-end programs.

Do not change a numerical tolerance merely to make a regression pass; explain
the algorithmic reason and resulting accuracy contract.

## 7. Adding an MLIR operation

**Learning objectives**

- Modify TableGen rather than generated output.
- Add verification and lowering coverage.

For a main-dialect operation:

1. Add the operation schema to `ManedOps.td`.
2. Declare operands, results, traits, assembly format, and constraints.
3. Add custom verification in the dialect implementation if TableGen constraints
   cannot express the invariant.
4. Rebuild `ManedOpsIncGen`.
5. Add parse/print round-trip coverage.
6. Add a lowering pattern to the intended standard or FPGA dialect.
7. Mark the source dialect illegal only when all required cases are handled.
8. Add successful and intentionally invalid FileCheck fixtures.

For hardware-facing operations, use the FPGA dialect definitions and generation
target instead. Generated declarations live under the binary include directory;
they must remain ignored.

## 8. Adding or changing a pass

**Learning objectives**

- Register a stable pass argument.
- Make conversion legality and failure visible.

A pass needs:

- a unique command-line argument and description;
- explicit dependent dialect registration;
- rewrite/conversion patterns;
- a legality target;
- a public construction or registration point where needed;
- driver registration in `maned-opt`;
- positive, negative, and composition tests.

Known pass arguments include `lower-maned-to-linalg`,
`maned-to-affine`, `lower-maned-to-fpga`, and `profile-matmul`.
Use `maned-opt` directly during iteration and compare output structurally with
FileCheck rather than depending on incidental formatting.

## 9. Protocol and networking changes

**Learning objectives**

- Keep byte layout separate from HTTP behavior.
- Normalize remote failures without hiding their source.

| Concern | Owning layer |
|---|---|
| MNPK/MNRS fields, sizes, byte order | `proto/mnpk` |
| Structured JSON errors | `proto/errors`, `json_lite` |
| HTTP parsing, timeouts, body limits | `net/http_client` |
| Authentication/capabilities/status | `net/device` |
| Request preflight and result decoding | `net/remote_run` |
| Submission/polling/fallback | `net/jobs` |
| Multi-flow dependencies/concurrency | `net/dispatch` |

Protocol parsers must reject overflow, truncation, impossible dimensions, and
payload-size mismatches. Network tests should use the local stub server and cover
success, malformed responses, worker errors, and timeouts. Dispatch changes must
test independent flows, dependent flows, partial failure, and deterministic
result association. Use the scenarios in the
[remote worker guide](15_REMOTE_WORKER_GUIDE.md) as manual integration checks.

## 10. Diagnostics and lint rules

**Learning objectives**

- Add stable, location-aware diagnostics.
- Avoid reporting downstream noise after an upstream parse failure.

Lint rules traverse a complete AST. Choose error severity when the program is
semantically unusable and warning severity for suspicious but legal code. Use a
stable diagnostic code, point to the most actionable source location, sort
deterministically, and test both presence and absence.

If a new AST node contains expressions or nested statements, update lint
traversal even when the first feature version adds no new rule.

## 11. Test selection

**Learning objectives**

- Select a minimal fast test set.
- Know when cross-subsystem verification is mandatory.

| Change | Minimum focused tests |
|---|---|
| Lexer/parser/AST | parser plus relevant decorator/literal/lint tests |
| Type/operation metadata | type and operation-registry tests |
| Dataflow/opcode | dataflow, binary IR, interpreter |
| Runtime mathematics | interpreter/matrix/golden plus numerical verification |
| MNPK/network | protocol, HTTP, device, remote execution |
| Async/dispatch | jobs, discovery, dispatch |
| MLIR operation/pass | round trip, relevant lowering, invalid verifier |
| CLI | library tests plus CLI success/failure fixture |

Then run:

```bash
ctest --test-dir build --output-on-failure
```

Use the objective harness for performance, quantization, contract, or compile-path
changes.

## 12. Review checklist

- Does the implementation match the formal grammar and public status?
- Is every new behavior owned by the lowest reusable layer?
- Are error messages actionable and source locations correct?
- Are shape, arity, bounds, overflow, and malformed-input cases handled?
- Are wire-format changes backward-compatible or explicitly versioned?
- Are generated/build artifacts excluded from the patch?
- Do focused and full tests pass?
- Are examples, editor syntax, and handbook capability labels current?

## 13. Progressive labs

### Lab 1: trace an existing operation

Trace `matmul` from grammar recognition through the operation registry, dataflow,
interpreter evaluator, binary opcode, MLIR definition, and tests. Record which
layers have real behavior versus metadata.

### Lab 2: frontend-only feature

Design a harmless no-argument decorator. List the exact grammar, registry, AST,
parser, linter-traversal, editor, and test updates without implementing backend
behavior.

### Lab 3: local unary operation

Design an integer `abs` operation for scalar/tensor local execution. Specify
arity, shape inference, overflow behavior for the minimum integer, tests, and
capability labels.

### Lab 4: MLIR pass

Read the profile pass and its fixture. Explain how its argument is registered,
which operations it inspects, what attribute/result it produces, and how
FileCheck proves the behavior.

### Lab 5: malformed protocol input

Choose one MNPK length or tensor field. Design a test proving the parser rejects
truncation without reading beyond the buffer or returning a partial request.

## 14. Solutions and review notes

### Lab 1

Start with `grammar/reserved_words.txt`, `src/ops/op_registry.cpp`,
`src/ir/dataflow.cpp`, `src/interp/matrix_ops.cpp`, the binary IR files, MLIR
TableGen/pass files, and their matching tests. `matmul` has local runtime and
compiler representations; routing metadata alone would not prove device support.

### Lab 2

Define the decorator name/schema and legal target, ensure the parser attaches it
to the intended AST node, ensure lint traversal reaches the decorated node, add
valid/invalid target and argument tests, and add highlighting if desired. Label
it **Parser** until a backend consumes it.

### Lab 3

Use arity 1 and same-shape inference. Implement elementwise behavior in a focused
evaluator or interpreter built-in. Explicitly avoid undefined signed overflow:
either reject the minimum integer or define saturating behavior. Test positive,
negative, zero, tensor, wrong arity, and the chosen minimum-value rule. Add it to
grammar/registry/runtime documentation only after each layer exists.

### Lab 4

Inspect `src/mlir/ProfileMatmul.cpp` and `tests/mlir/profile_matmul.mlir`. The
pass argument is `profile-matmul`; the fixture's `CHECK` statements are the
behavioral contract. Avoid tests tied to unrelated textual formatting.

### Lab 5

Construct a valid payload, truncate it immediately before or inside the selected
field, call the parser, and require `std::nullopt`. Include a boundary case where
the declared length exceeds remaining bytes and a valid control payload.
