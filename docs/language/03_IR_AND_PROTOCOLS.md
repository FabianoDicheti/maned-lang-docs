# IR and Protocols

Maned uses an in-memory dataflow graph for local planning, a compact binary IR
for transport, and MNPK/MNRS envelopes for remote inputs and outputs.

## Dataflow and binary IR

| File | Responsibility | Interactions |
|---|---|---|
| `include/maned/ir/dataflow.h` | Value IDs, graph node kinds, `DataflowNode`, `DataflowGraph`, and AST-to-graph builder. | Consumes `ast::LambdaFlow`; used by interpreter, serializer, and dispatch. |
| `src/ir/dataflow.cpp` | Builds dependencies and outputs from a lambda flow. | Defines execution order independent of local or remote backend. |
| `include/maned/ir/binary_ir.h` | Stable opcodes, binary instructions/modules, serialize/deserialize API. | Consumes a dataflow graph; supplies remote job payloads. |
| `src/ir/binary_ir.cpp` | Opcode mapping, binary encoding, bounds checking, and decoding. | Used by CLIs, MNPK generator, dispatcher, and protocol tests. |

The dataflow graph is semantic and uses strings/structured nodes. Binary IR assigns
compact opcodes and serializes graph content for transport. Deserialization rejects
invalid/truncated data rather than returning a partial module.

## Graph optimization (item 5)

`buildDataflow` ends with `ir::optimizeDataflow`: duplicate literal
constants collapse to one node (constant CSE) and Const/Op values no
output reaches are eliminated, with ids renumbered densely in topological
order. Param/Operand nodes always survive - they are the input contract,
and dropping one would renumber the worker's PARAM binding. The pass only
removes values nothing reads, so results are bit-exact; `--verify` against
a worker or the Bark VM is the regression gate. The practical effect is
headroom under the 256-value register budget (repeated literals used to
count once per use).

## MNPK/MNRS wire format

| File | Responsibility | Interactions |
|---|---|---|
| `include/maned/proto/mnpk.h` | Protocol constants, quant blocks, tensor entries, request/response models, serialization, parsing, and `Value` conversion. | Wraps binary IR and runtime values for device communication. |
| `src/proto/mnpk.cpp` | Little-endian MNPK/MNRS encoding/decoding and validation. | Called by remote execution and `mnpk-gen`. |
| `include/maned/proto/errors.h` | Structured protocol error model and JSON error-body parsing. | Used by device, jobs, and remote execution layers. |
| `include/maned/proto/json_lite.h` | Header-only, bounded JSON-object parser and escaping helper. | Parses discovery/status/error payloads without an external JSON library. |

## Data relationships

| Source value | Transformation | Result |
|---|---|---|
| `ast::LambdaFlow` | `buildDataflow` | `DataflowGraph` |
| `DataflowGraph` | `ir::serialize` | Binary instruction bytes |
| `interp::Value` | `tensorFromValue` | Typed/quantized `TensorEntry` |
| Binary IR + tensors | `serializeMnpk` | Device request bytes |
| Device response bytes | `parseMnrs` | Status plus tensor entries |
| `TensorEntry` | `valueFromTensor` | Local runtime value |

## Compatibility rules

- Treat numeric opcode and wire-format changes as protocol changes, not refactors.
- Keep serializer and parser validation symmetric and add malformed-input tests.
- Quantization metadata must remain consistent with tensor dtype and payload size.
- Network code owns transport concerns; protocol code owns byte layout.
- Update `mnpk-gen`, remote tests, and integration contract checks when the wire
  representation changes.

## Stdio binding (Bark VM)

The binary envelopes also travel over a local byte stream: the **Bark VM**
(`bark/tools/barkvm`, a hosted build of the worker's real executor) speaks
length-prefixed frames — `4-byte ASCII type` + `u32 LE length` + payload —
over stdin/stdout pipes (spawned) or the unix socket `~/.maned/bark-vm.sock`
(a running `maned-bark-here` instance). Frame types: `HELO` (a Section 6.1
status body, parsed by the same `parseDeviceStatusJson`), `MNPK`, `MNRS`,
`ERRJ` (Section 7 error JSON). Strict half-duplex, one job in flight. The
normative spec is PROTOCOL_SPEC.md Section 12; the client is
`src/net/local_vm.cpp`, reusing `encodeJobMnpk`/`decodeMnrsOutputs`
verbatim — the envelope bytes are identical to the HTTP path.

Note: `ir::kArenaFixedBytes` is `64 + 256*32`, matching bark's
`IR_EXEC_ARENA_FIXED` (a cache line of alignment slack plus the register
file). An earlier mirror said `8 + 256*32`; the 56-byte drift is fixed.

## Binary IR: two ABI versions (gap_009)

The instruction encoding is versioned. `ir::serialize(graph, version)` emits
either; `ir::deserialize` reads both and tells them apart from the header.

| | ABI v1 | ABI v2 |
|---|---|---|
| Instruction size | 8 bytes | 16 bytes |
| Value ids | u8 — `kRfSlots` = 256 slots | u16 — `kRfSlotsV2` = 4096 slots |
| Operands | 2, plus `aux0`/`aux1` doubling as operands 3–4 | 4 (`src0..src3`), plus a 5th via `flags` bit 0 |
| Immediate | opcode-defined 24-bit, in `aux0`/`aux1`/`flags`, mutually exclusive with >2 operands | dedicated 16-bit `imm` field |
| Dataflow level | u8 (caps a flow at 255 levels) | u16 |
| Outputs per instruction | 1 | 1 + `flags >> 4` extra consecutive registers (≤15), for multi-output ops like SPLIT |
| Output table entries | u8 | u16 little-endian |
| CONST literals | **refused** if nonzero | carried in `imm` |

Two consequences worth stating plainly:

- **The v2 register file is 16× larger**, which lifts the 96×96 campaign
  ceiling. A worker's fixed arena grows to `64 + 4096*32` = 131,136 bytes
  (~128 KiB) — deliberately not the ~2 MiB a full 65,536-slot file would pin
  on every worker. Note `kArenaFixedBytes` above still mirrors bark's v1
  constant; the v2 figure is computed from `kRfSlotsV2`, not a second mirror.
- **v1 now refuses a nonzero CONST literal rather than shipping it.** It has
  to: the coordinator never encoded CONST literals, so every nonzero constant
  silently executed as **0** on every worker. `--verify` caught it. An honest
  refusal is the only safe v1 behavior; v2 carries the literal.

Version is negotiated per worker, not assumed. `/api/status` advertises `ir`
and `rf_slots` (see PROTOCOL_SPEC.md Section 6.1); a worker advertising
neither is v1 with 256 slots. `checkWorkerLimits` is then checked against
*that worker's* negotiated budget, so an oversized flow refuses with the
numbers of the machine it was actually headed for. Locally, and in lint, the
default budget is the v2 one — the gate is "what runs here also ships".
