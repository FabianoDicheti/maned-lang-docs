# Benchmarks and Examples

Every `.mnd` script in the workspace — benchmarks, examples, demos, probes and
the ml_14sep pipeline — lives in `mnd_scripts/`, and
[`mnd_scripts/README.md`](../../mnd_scripts/README.md) is its catalog: one
row per script, with tags (`local`, `needs-inputs`, `serve-only`,
`device-remote`, `vm-ok`, …) and the data each one needs. **That catalog is the
index; this page covers only the benchmark harness**, which is not a script
collection and has nowhere else to be described.

Run everything from the workspace root, where `build-tools.sh` puts the CLIs:

```bash
./maned-run mnd_scripts/benchmarks/matmul_relu_sum.mnd
```

## Benchmark drivers

| File | Purpose |
|---|---|
| `mnd_scripts/benchmarks/run_benchmark.py` | The focused Maned/Python comparison. Invokes the runner and the Python baseline on one workload. |
| `mnd_scripts/benchmarks/run_extensive_benchmark.py` | Broader/repeated scenarios; aggregates timing across workloads. |
| `mnd_scripts/benchmarks/run_suite_benchmark.py` | Discovers `generated_cases/`, executes them, validates results, summarizes metrics. |
| `mnd_scripts/benchmarks/python_matmul_relu_sum.py` | Python reference for matmul → ReLU → reduction. |
| `mnd_scripts/benchmarks/python_deep_pipeline.py` | Python reference for the deeper operation pipeline. |

## Primary workloads

| File | Purpose |
|---|---|
| `mnd_scripts/benchmarks/matmul_relu_sum.mnd` | Matrix multiplication, activation, reduction. |
| `mnd_scripts/benchmarks/deep_pipeline.mnd` | Multi-stage interpreter/dataflow workload. |

## Generated benchmark cases

`mnd_scripts/benchmarks/generated_cases/` holds ten cases, each isolating one
feature: `01_scalar_chain`, `02_elementwise_add_sum`,
`03_elementwise_mul_add_relu_sum`, `04_scalar_mul_mean`, `05_transpose_add_sum`,
`06_comparison_mask_sum`, `07_matmul_sum`, `08_rectangular_matmul_relu_sum`,
`09_two_layer_pipeline`, `10_three_layer_pipeline`.

They are checked-in deterministic inputs, not build artifacts — and they are
also part of the bit-exact A/B corpus (`tools/ab_corpus.sh`), so their output
hashes are frozen in `priority/gap_2026-09/AB_BASELINE.txt`. A benchmark change
that alters a number is therefore a gate failure, by design.

## What benchmarks do and do not tell you

Benchmarks measure the local execution path: file read → lexer/parser →
dataflow construction → interpreter. The Python files provide semantic and
timing baselines. **Correctness is not measured here** — that is the golden
suite, the unit gate (`tools/run_tests.sh`) and `--verify` equality against a
worker. A fast wrong answer fails those, not this page.

For the project's numeric objectives (compile speed, quantization loss,
integer-only runtime) see [`17_OBJECTIVES.md`](17_OBJECTIVES.md) and the
scorecard that `tools/verify_objectives.sh` writes.
