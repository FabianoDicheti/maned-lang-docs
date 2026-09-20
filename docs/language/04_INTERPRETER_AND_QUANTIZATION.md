# Interpreter and Quantization

The MLIR-free runtime executes dataflow graphs locally and supplies the reference
behavior used by CLI runs, benchmarks, remote verification, and numerical tests.

## Runtime files

| File | Responsibility | Dependencies and consumers |
|---|---|---|
| `include/maned/interp/value.h` | Runtime scalar/tensor storage, shape, dtype, and quantization metadata. | Shared by interpreter, quantizer, protocol, and networking. |
| `include/maned/interp/interpreter.h` | Errors/results, pluggable `OpEvaluator`, and `Interpreter` interface. | Consumes dataflow IR; used by CLIs and dispatcher. |
| `src/interp/interpreter.cpp` | Dependency resolution, execution, and output/error collection. | Invokes the configured evaluator for operation nodes. |
| `include/maned/interp/matrix_ops.h` | Factory for the tensor/matrix operation evaluator. | Plugs into `Interpreter`. |
| `src/interp/matrix_ops.cpp` | Elementwise, reduction, transpose, and matrix operation behavior. | Provides normal numeric execution. |
| `include/maned/interp/lambda.h` | Lambda terms, constructors, combinators, evaluator result, and primitive adapter. | Supports lambda semantics and interpreter operations. |
| `src/interp/lambda.cpp` | Closure/application evaluation and built-in combinators. | Used independently in lambda tests and through evaluator composition. |
| `include/maned/interp/int8_emulation.h` | Precision ranges, saturation, and value-transform helpers. | Models constrained integer execution. |
| `src/interp/int8_emulation.cpp` | Range computation and recursive/clamped value transforms. | Used by precision verification. |
| `include/maned/interp/parallel.h`, `src/interp/parallel.cpp` | Deterministic row-band threading for the integer kernels (gap_024). | Used by the matrix evaluator; configured once from `--threads`. |
| `include/maned/interp/activation.h`, `norm.h`, `shape.h`, `spatial.h` | Activations, layernorm/batchnorm, reshape/split/concat, conv/pool. | Additional evaluators composed into the same `OpEvaluator` boundary. |
| `include/maned/interp/generators.h` | `ones`/`zeros`/`full`/`random` operand generators. | Lets a script build its own operands without an input file. |

An interpreter instance receives a `DataflowGraph`, input values, and an evaluator.
The evaluator boundary keeps scheduling/error handling separate from concrete
operation mathematics. Matrix and lambda evaluators supply those semantics.

## Quantization files

| File | Responsibility | Dependencies and consumers |
|---|---|---|
| `include/maned/quant/quantizer.h` | Quantizer configuration and calibration/quantize/dequantize API. | Operates on runtime `Value` using type quantization metadata. |
| `src/quant/quantizer.cpp` | Range calibration, scale/zero-point selection, integer conversion, and reconstruction. | Validated by accuracy, simulation, and integer-only checks. |

## Execution and numerical flow

| Phase | Input | Output |
|---|---|---|
| Graph preparation | Parsed lambda flow | Dataflow graph |
| Optional calibration | Floating-point values | Quantization parameters |
| Optional quantization | Values + parameters | Integer-representable values |
| Interpretation | Graph + input map + evaluator | Named output values |
| Optional emulation | Runtime values + precision range | Saturated constrained values |
| Optional reconstruction | Quantized values | Approximate floating-point values |

## Two things that must not change the numbers

Both were added as pure performance work, and both were accepted only after
sweeping the corpus twice and diffing the output byte for byte. That is the
standard either has to meet again if it is touched.

**Threading (`--threads N`, gap_024).** Work is split into contiguous bands of
output rows. The partition is a fixed function of the output shape and the
configured thread count — never of thread timing, scheduling, or completion
order. Bands write disjoint rows, so no thread reads another's elements. No
accumulator is ever split: the whole k-loop of each output element runs in its
original order on one thread, so reassociation does not merely stay safe under
mod-2³² wrap, it never happens. Below a fixed shape-derived threshold the band
runs inline. `--threads 1` is therefore an exact A/B switch, not a different
program.

**Buffer reuse (`--no-buffer-reuse` to disable, gap_022).** `src/ir/liveness.cpp`
computes each value's live range; once a value is dead its buffer can back a
later one. Reuse changes which allocation holds a value, never the value — so
the flag exists to bisect a suspected reuse bug, and a difference across it is
by definition a bug in reuse.

If you change either, the gate is the workspace `tools/ab_corpus.sh` against
`priority/gap_2026-09/AB_BASELINE.txt`: bit-exact, or it does not land.

## Extension rules

Add new runtime operations behind `OpEvaluator` and test scalar, tensor, shape-error,
and unsupported-operation behavior. Quantized implementations must establish an
acceptable error bound and preserve integer-only invariants where claimed.
