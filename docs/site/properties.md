# Properties and profiles

In most array languages a matrix is a bag of numbers, and everything you know
about it you had to ask for one question at a time: `rank()`, `det()`, `eig()`,
`issymmetric()`, `cond()`, and then you stitch the answers together yourself.

Maned turns that around in both directions:

```text
PROPERTIES  ──synth──▶  MATRIX  ──operate──▶  MATRIX  ──profile──▶  PROPERTIES
```

**`synth`** builds a matrix from a list of properties you name, and verifies
that the matrix it built actually has them. **`profile::`** reads the whole
property dictionary back out of any matrix — structure, spectrum, definiteness,
which decompositions are legal, what it inherits and what it forbids — in one
statement. In between, ordinary flows do ordinary algebra, and a synthesized
matrix is indistinguishable from one you typed by hand.

This page is that round trip. Everything below was run to produce the output
shown with it.

## Reading a matrix: `profile::`

One statement, and the matrix tells you what it is:

```mnd
in::spd = [[2,1],[1,2]];

profile::spd;
```

Nothing in that program says "symmetric", "positive definite" or
"tridiagonal". All three are conclusions:

```text
Matrix Profile: spd
------------------------------------------------
[dimensions]  exact
  shape                     2 x 2
  is_square                 true
[structure]  exact
  is_tridiagonal            true
  bandwidth_lower           1
  bandwidth_upper           1
  is_sparse                 false
  non_zero_elements         4
[symmetry]  exact
  is_symmetric              true
  is_hermitian              true
  is_normal                 true
[linear_algebra]
  trace                     4
  determinant               3
  rank                      2
  is_invertible             true
[spectral]  exact (integer spectrum certified)
  eigenvalues               1, 3
  multiplicity              1 (alg 1, geo 1), 3 (alg 1, geo 1)
  spectral_radius           3
  is_diagonalizable         true
  is_defective              false
  jordan_blocks             1^1, 3^1
[numerical]  approximate
  condition_number          3
  condition_status          well_conditioned
[positivity]
  is_positive_definite      true
[decompositions]
  supports_cholesky         true
  supports_lu               true
  supports_qr               true
[computational]  rule
  storage_format            dense_row_major
  linear_solver             cholesky
  eigen_solver              jacobi, symmetric_qr
  fpga_friendly             false
  cache_friendly            true
[geometric_interpretation]  rule
  represents_scaling        true
  represents_shear          true
[dynamic_interpretation]  rule
  has_coupled_modes         false
  dynamic_modes             all modes independent
[taxonomy]
  inherits   square_matrix, tridiagonal_matrix, dense_matrix, symmetric_matrix,
             full_rank_matrix, invertible_matrix, diagonalizable_matrix,
             positive_definite_matrix
  implies    full_rank, invertible, real_spectrum, normal
  forbids    diagonal, orthogonal, singular, defective
```

(Trimmed — the real report carries every field in each section.)

The last three sections are the ones with no equivalent elsewhere. The profiler
does not stop at measuring: it tells you **which solver to reach for**, how the
matrix will behave as a dynamical system, and what the properties it found
*imply* and *forbid* about properties it did not measure.

### Exactness is reported, never assumed

Each section carries a confidence tag, and they mean different things:

| Tag | Meaning |
|---|---|
| `exact` | Computed in integer arithmetic. `[spectral] exact (integer spectrum certified)` means each eigenvalue is an integer λ for which `det(A − λI) == 0` was confirmed exactly, with a geometric multiplicity from an exact integer rank. |
| `approximate` | A numeric result — condition number, a complex or irrational spectrum from the QR/Jacobi path. Never labelled exact. |
| `rule` | A recommendation derived from the facts above it, not a measurement: storage format, solver choice, hardware hints, the geometric reading. |

The analysis is **tiered**. Tier 1 always runs: exact O(n²) integer structure,
symmetry, sparsity, trace, and an exact determinant by fraction-free Bareiss
elimination over 128-bit integers. Tier 2 is the O(n³) work — rank,
eigenvalues, definiteness, diagonalizability, decomposition support — and it is
**skipped above 256×256**, so profiling a large matrix still answers, with the
structural tier only.

And the whole profiler is **Tier B**: it runs host-side, off the integer
execution path, so it may use double or wide-integer math internally without
ever putting a float into the runtime. The values your flows compute with stay
integers.

## Properties as values

A report is for reading. For *computing*, there are two machine-readable forms.

**A dotted path** projects one field of the dictionary into an ordinary value:

```mnd
in::A    = [2,2,3,3,5,7,11,13] from_spectrum;
in::det  = A.linear_algebra.determinant;
in::tr   = A.linear_algebra.trace;
in::rank = A.linear_algebra.rank;
in::sym  = A.symmetry.is_symmetric;
```

```text
det  : scalar = 180180
tr   : scalar = 46
rank : scalar = 8
sym  : scalar = 1
```

Booleans arrive as 0/1, so a property can drive arithmetic directly.

**`profile_vector`** is the in-graph form: an op that turns a matrix into a
rank-1 `[33]` integer descriptor a flow can compute with.

```mnd
in::spd  = [[2,1],[1,2]];
in::sing = [[1,2],[2,4]];

calc::lambda_flow inspect(spd, sing) {
    spd  profile_vector p =
    sing profile_vector q =
} return p, q;
```

```text
p : [33] = [2, 2, 1, 0, 0, 0, 0, 0, 1, 0, 1, 1, 2, 0, 4, 0, 1, 0, 0, 1, 4, 1, 3, 1, 2, 1, 0, 1, 1, 1, 0, 0, 0]
q : [33] = [2, 2, 1, 0, 0, 0, 0, 0, 1, 0, 1, 1, 2, 0, 4, 0, 1, 0, 0, 1, 5, 1, 0, 1, 1, 0, 1, 0, 0, 1, 0, 0, 0]
```

Slot 21 is `determinant_exact` and slot 22 the determinant itself: `1, 3` for
the first matrix, `1, 0` for the singular one. Slots 24–27 read `2, 1, 0, 1`
versus `1, 0, 1, 0` — rank 2, full rank, not singular, invertible, against rank
1, not full rank, singular, not invertible.

The positions are a **frozen contract** — programs depend on them, so the table
is extended by appending and never by reordering:

| Slot | Field | Slot | Field |
|---|---|---|---|
| 0–1 | `rows`, `cols` | 17–19 | `is_skew_symmetric`, `is_orthogonal`, `is_normal` |
| 2 | `is_square` | 20 | `trace` |
| 3–5 | `is_diagonal`, `is_identity`, `is_zero` | 21–22 | `determinant_exact`, `determinant` (valid when 21 is 1) |
| 6–9 | `is_upper_triangular`, `is_lower_triangular`, `is_tridiagonal`, `is_band` | 23–25 | `has_rank`, `rank`, `is_full_rank` |
| 10–12 | `bandwidth_upper`, `bandwidth_lower`, `total_bandwidth` | 26–27 | `is_singular`, `is_invertible` |
| 13–15 | `is_sparse`, `non_zero`, `zero_count` | 28–29 | `is_positive_definite`, `is_positive_semidefinite` |
| 16 | `is_symmetric` | 30–32 | `is_nilpotent`, `is_idempotent`, `is_involutory` |

Booleans are 0/1; trace and determinant are the exact integers. Spectral radius
and condition number are **deliberately excluded** — they are doubles, and this
vector is integer-honest.

`profile_vector` has no worker opcode, so a flow using it stays on the
coordinator.

## Building a matrix from properties: `synth`

The other direction. State what you want; the engine derives a canonical
witness and then **profiles it to check**:

```mnd
in::cube = { depth:4,
             order:8,
             is_symmetric:true,
             is_tridiagonal:true,
             is_positive_definite:true,
             is_sparse:true,
             is_diagonalizable:true } synth;

profile::cube;
```

Nothing there says "2 on the diagonal, −1 beside it". That second-difference
stencil is what the engine *derives* as the canonical 8×8 witness of those five
properties. `depth: 4` stacks four identical slices into a 4×8×8 tensor, and
since the profiler is defined on matrices, a 3-D value is profiled slice by
slice — identical slices collapse into one report:

```text
Matrix Profile: cube[0..3]  (all 4 slices identical)
  shape                     8 x 8
  is_tridiagonal            true
  is_band_matrix            true
  bandwidth_lower           1
  bandwidth_upper           1
  is_sparse                 true
```

### A spec that names its own spectrum

Properties can be harder than structure. Ask for a demanded **spectrum**, a
triangular shape, *and* defectiveness at once:

```mnd
in::A = { eigenvalues:[2,2,3,3,5,7,11,13],
          is_lower_triangular:true,
          is_defective:true,
          is_band_matrix:true,
          bandwidth_lower:1,
          is_sparse:true } synth;
```

"Defective" means the repeated eigenvalues do **not** get their own
eigenvectors — so the witness cannot be the diagonal matrix carrying that
spectrum. It has to couple each repeated pair into a 2×2 Jordan block, and
coupling *below* the diagonal is what satisfies `is_lower_triangular` at the
same time. The result is the canonical lower-bidiagonal Jordan form:

```text
  bandwidth_lower           1
  bandwidth_upper           0
  non_zero_elements         10
  trace                     46
  determinant               180180
[spectral]  exact (triangular diagonal)
  eigenvalues               2, 2, 3, 3, 5, 7, 11, 13
  multiplicity              2 (alg 2, geo 1), 3 (alg 2, geo 1), 5 (alg 1, geo 1), ...
  is_diagonalizable         false
  is_defective              true
  jordan_blocks             2^2, 3^2, 5^1, 7^1, 11^1, 13^1
[computational]  rule
  storage_format            CSR, CSC, COO
  linear_solver             forward_substitution, sparse_lu
```

Two eigenvalues repeated, each with algebraic multiplicity 2 and geometric
multiplicity 1 — exactly what "defective" asked for — and the profiler now
recommends sparse storage and forward substitution, because the matrix it was
handed is triangular and sparse.

### A spec that cannot be met is refused, by name

`synth` never returns a matrix that quietly misses what you asked for. Ask for
the same symmetric tridiagonal positive-definite 8×8, but `is_dense` instead of
`is_sparse`:

```text
error: in::impossible: synth: no canonical witness for this spec -
  is_dense was requested true but the matrix built from the other
  properties has it false
```

It names the property that failed and what the witness had instead. That is the
verification half of the round trip: `synth` builds a witness and then profiles
it, so the contradiction surfaces as a refusal rather than as a matrix you would
have trusted.

### The vocabulary

A spec key is either a **shape key** or any property the profiler reports. Keys
marked † *steer* the construction; the rest are pure **constraints** — the
witness is checked against them and the spec is rejected if it misses one.

| Group | Keys |
|---|---|
| Shape / construction (synth only) | `order` †, `rows` †, `cols` †, `depth` †, `diagonal_value` †, `off_diagonal_value` † |
| Dimensions | `rows`, `cols`, `order`, `is_square`, `is_rectangular`, `is_row_matrix`, `is_column_matrix`, `shape` |
| Structure | `is_diagonal` †, `is_scalar_matrix` †, `is_identity` †, `is_zero` †, `is_upper_triangular` †, `is_lower_triangular` †, `is_bidiagonal` †, `is_lower_bidiagonal` †, `is_upper_bidiagonal` †, `is_tridiagonal` †, `is_band_matrix` †, `bandwidth_upper` †, `bandwidth_lower` †, `is_sparse`, `is_dense`, `total_bandwidth`, `non_zero_elements`, `zero_elements`, `sparsity_num`, `sparsity_den` |
| Symmetry | `is_symmetric` †, `is_orthogonal` †, `is_skew_symmetric`, `is_hermitian`, `is_normal` |
| Linear algebra | `rank` †, `trace`, `determinant`, `determinant_exact`, `rank_exact`, `is_full_rank`, `is_singular`, `is_invertible` |
| Spectral | `eigenvalues` †, `is_diagonalizable` †, `is_defective` †, `distinct_eigenvalues`, `algebraic_multiplicities`, `geometric_multiplicities`, `jordan_block_sizes`, `jordan_block_count`, `spectral_radius`, `all_eigenvalues_positive`, `eigenvalues_exact`, `spectrum_determined` |
| Positivity | `is_positive_definite` †, `is_positive_semidefinite`, `is_negative_definite`, `is_negative_semidefinite`, `is_indefinite` |
| Special | `is_nilpotent` †, `is_idempotent` †, `is_involutory` † |
| Decompositions | `supports_lu`, `supports_qr`, `supports_svd`, `supports_cholesky`, `supports_eigendecomposition`, `supports_jordan_decomposition` |
| Numerical / computational | `is_numerically_stable`, `fpga_friendly`, `cache_friendly`, `gpu_friendly`, `tensor_core_friendly` |
| Interpretation | `represents_scaling`, `represents_shear`, `represents_rotation`, `represents_projection`, `has_coupled_modes` |

Booleans are `true`/`false`, sizes are integers, and `eigenvalues` takes a
bracketed list.

### The named shortcuts

For the common specs there are direct constructors, and they are cheaper to
read than a property block:

```mnd
in::id      = 4 eye;                      # the identity: orthogonal, spectrum {1}
in::spec    = [2,3,5] diag;               # a diagonal matrix whose spectrum IS the list
in::stencil = 5 1 2 1 tridiag;            # n sub diag super
in::banded  = 6 2 0 1 band;               # n lower upper fill
in::jordan  = [1,2,2,5] from_spectrum;    # a matrix with exactly that spectrum
```

Each of these profiles as what its name claims — `from_spectrum` is the round
trip in miniature: ask for eigenvalues 1, 2, 2, 5 and the profile reports
exactly those back.

## Profiling what your algebra produced

`profile::` names any value, including one a flow computed. That closes the
loop — and it is where the feature earns its keep, because the profile of a
*result* tells you what the operation did to the properties:

```mnd
calc::lambda_flow algebra(cube, A) {
    cube cube add cube_doubled =     # 2A on every slice of the 3-D stack
    A A matmul A_squared =           # a genuine matrix product
} return cube_doubled, A_squared;

profile::cube_doubled;
profile::A_squared;
```

- **`cube_doubled`** is still symmetric, still tridiagonal, still positive definite — and its spectrum is doubled, so the determinant is `2⁸ · 9 = 2304` rather than 9.
- **`A_squared`** has spectrum `[4,4,9,9,25,49,121,169]` — squaring a matrix squares its spectrum — and determinant `180180² = 32464832400`, exact, in 128-bit integer arithmetic. It is **still defective**: a Jordan block stays coupled under multiplication. Still lower triangular, still of lower bandwidth 1 — squaring turned each subdiagonal 1 into the sum of the two eigenvalues it joins, and only a Jordan block larger than 2×2 could have widened the band.

Those are the kind of statements you would otherwise verify by hand on paper.
Here they are a line of output.

## JSON, and profiles over HTTP

`--profile-json` prints the same dictionaries as canonical JSON — keys in a
fixed order, no incidental whitespace, so two runs of the same matrix are
byte-identical and the output diffs cleanly between runs:

```sh
maned-run matrices.mnd --profile-json
```

```json
{"quant_mode":"wrap","ok":true,
 "basic_id":{"name":"spd","type":"matrix","field":"real","dtype":"int"},
 "dimensions":{"_confidence":"exact","shape":[2,2],"rows":2,"cols":2,
   "order":2,"is_square":true,"is_rectangular":false, ...},
 "structure":{"_confidence":"exact","is_tridiagonal":true,
   "bandwidth_upper":1,"bandwidth_lower":1,"is_sparse":false, ...}, ...}
```

Confidence travels *in the payload* as a `_confidence` sibling key, so a
consumer never has to guess whether a number was measured or inferred.

The same directive works under `maned-serve`, where it makes a script answer
"what is this matrix" instead of returning the values:

```mnd
in::img = image();                            # arrives with the request

calc::lambda_flow decompose(img) {
    img { axis: 2, index: 0 } slice red =     # [H,W,C] -> [H,W]
    img { axis: 2, index: 1 } slice green =
    img { axis: 2, index: 2 } slice blue =
} return red, green, blue;

profile::red;
profile::green;
profile::blue;
```

```text
$ curl -X POST localhost:8080/run -F img=@photo.png
{"red":{...},"green":{...},"blue":{...}}
```

A descriptor set is one answer, so the profiles travel as a single JSON
document. A profile-only script replies `application/json`; a script with
`out::` as well gets a `profiles` part beside its tensor parts. And the 256×256
tier-2 cutoff is why a large photo still answers — with the structural tier
only.

## Limits worth knowing

- **The profiler is defined on matrices.** A rank-3 value is profiled slice by slice; identical slices collapse into one report.
- **Tier 2 is skipped above 256×256.** Structure, symmetry, sparsity, trace and the exact determinant still come back; rank, spectrum and definiteness do not.
- **`profile::`, `synth` and dotted paths are host-side**, evaluated at load or report time. They never enter a dataflow graph, which is what lets them use wide math honestly.
- **`profile_vector` is the in-graph form, and it is coordinator-only** — no worker opcode. It excludes every non-integer field by design.
- **The in-graph `determinant` op caps at n ≤ 8** (and refuses above it, with the number). The profiler's determinant has no such cap — it is Bareiss over 128-bit integers.

## Next

- [Linear algebra](linear-algebra.html) — the ops these matrices flow through, the scale rule, and the exact solvers.
- [Language guide](guides/language.html) — the full op table, flows, and serving scripts as an HTTP API.
- [Machine learning](guides/machine-learning.html) — where the same primitives become trainable models.
