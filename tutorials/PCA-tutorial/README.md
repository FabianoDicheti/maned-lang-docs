# A PCA explorer, in Maned — the complete project

This folder is the project explained in the
[tutorial](https://maned-lang.com/tutorial-pca.html): a page where you upload images,
each image becomes 54 numbers, and principal component analysis reduces them to 3,
drawn as a 3D plot with the component values beside it. Everything that computes is a
`.mnd` program behind `maned-serve`; the page is plain HTML and JavaScript, and there is
no Python, no build step and no table of constants.

## Run it

1. **Maned 0.4.3 or newer** on your PATH (`maned-run`, `maned-serve`). Earlier versions
   don't have `eigendecomp`, `calc::ml::pca`, `fft2d`, `log` or `maned-serve --static`.
2. In this folder:

```sh
sh serve.sh                 # then open http://localhost:8090 (exactly "localhost")
```

Upload three or more PNG or JPEG images: each becomes a row as it arrives, and the
plot and the PCA Components card appear from the third. `sh check/check.sh` checks the
whole computation against numpy's answers.

## What is here

| file | what |
|---|---|
| `features.mnd` | one `[128,128]` grayscale image in, its `[1,54]` row out: histogram, Sobel gradient, four blocks, singular values, frequency |
| `pca.mnd` | the rows in; scores, loadings, variance, explained variance and the total out. One `calc::ml::pca` definition |
| `serve.sh` | starts both programs: `features.mnd` on :8090, which also serves `web/`, and `pca.mnd` on :8091 |
| `web/index.html` | the page: upload, the 3D plot (Plotly), the PCA Components card |
| `web/examples/` | not in the published copy. Where it exists, a **Load Example Images** button appears |
| `check/check.sh` | the check: both programs on 11 stored images, against numpy and against what any PCA must obey |
| `check/*.mnd`, `check/*.dqt` | the comparisons, and the images and numpy's answers they read |

## What runs where

| Part | Where | Why |
|---|---|---|
| The 54 features | `features.mnd`, `:8090` | |
| PCA | `pca.mnd`, `:8091` | each `maned-serve` runs one script |
| The page and its files | `maned-serve --static web`, `:8090` | |
| Grayscale, resize to 128x128 | the browser's canvas | Maned has no resize op |
| Images, labels, vectors | the browser's IndexedDB | Maned keeps nothing between requests |

So the data belongs to one browser. It is not shared, and clearing site data removes it.

## How it computes without floats

Everything is int32 matrix products plus integer-only built-ins, and the comments in
the scripts give the bound that keeps each product inside int32.

- **PCA:** `calc::ml::pca`. The exact covariance is solved by the integer eigensolver,
  and signs follow sklearn: the largest loading of each component is positive.
- **Singular values:** `AᵀA eigendecomp` gives all 128 eigenvalues, and their square
  roots are the singular values.
- **Frequency:** `fft2d` gives each bin's magnitude and `log` its logarithm. numpy's
  `fftshift` becomes two selection matrices.
- **Mean and spread:** `tensor_mean` accumulates wide, while `tensor_sum` wraps at
  int32, so the scripts rely on means.

## Limits

- **At least 3 images,** because there are 3 components. With exactly 3, PC3 correctly
  reads 0 % and its loadings mean nothing, since 3 points only span 2 dimensions.
- **Center-only PCA,** as sklearn's default, so features with large numbers dominate.
  On the examples PC1 is essentially overall brightness (the four block means), and the
  histogram and singular-value features barely count, since they sit in 0..1 beside
  values up to 255. Adding `standardize: true` to `pca.mnd` puts every feature on equal
  footing.
- **An exactly zero frequency bin has no logarithm.** It reads as 1/256, the smallest
  step, which is 20 ln(1/256) = -110.9. A flat or perfectly regular image has such bins,
  and lands far from the others.
- **The browser's resize decides the pixels,** so the same image can score slightly
  differently in another browser. On the examples, the canvas gives PC1 92.00 % and a
  `sips` resize gives 91.42 %; both are right for their own pixels.
- **No authentication.** `maned-serve` binds to 127.0.0.1 by default.

## The check

```sh
sh check/check.sh       # needs only maned-run and a shell; exit status 0 if all pass
```

It runs both programs on the 11 images stored in `check/expected.dqt` and checks three
things:

- **Against numpy:** every feature, score, loading and variance, within an allowance
  stated in `check_features.mnd` and `check_pca.mnd`. The expected values came from a
  numpy implementation of the same 54 features and of sklearn's PCA, not from Maned, so
  Maned's own bugs can't pass.
- **Parseval:** `fft2d` keeps each image's energy, which needs no reference.
- **What any PCA must obey:** the loadings are orthonormal, the scores are uncorrelated
  with the reported variances, and the explained percentages don't pass 100.

Changing a test image or a feature's definition means new expected values, from numpy
or any other independent implementation. Nothing else does: the stored values hold for
any Maned that computes the same thing.

## Measured

On the eleven example images (their gray pixels are in `check/expected.dqt`), against
numpy:

| Features | Max error | Value range |
|---|---|---|
| Histogram | 0.0005 | 0..0.69 |
| Gradient | 0.014 | 49..163 |
| Blocks | 0.008 | 16..241 |
| Singular values | 0.001 | 0.01..0.71 |
| Frequency | 0.0014 | 104..195 |

| | `\|cos\|` | Score correlation | Explained | Variance |
|---|---|---|---|---|
| PC1 | 1.00000 | 1.00000 | 91.42 % / 91.42 % | 21573.97 / 21573.99 |
| PC2 | 1.00000 | 1.00000 | 4.83 % / 4.83 % | 1139.34 / 1139.30 |
| PC3 | 1.00000 | 1.00000 | 2.65 % / 2.65 % | 625.54 / 625.57 |

The small variance gaps are the features' own rounding. Given the same features, the
variances agree on every printed digit, and explained variance did too with synthetic
data at 256 and 1000 rows.

About 40 ms per image for the features and 3 ms for PCA. `maned-run --trap-overflow` is
clean on the examples, on 10 adversarial images (all white, checkerboard, hard edges,
noise, a pure high-frequency wave) and on PCA with 3, 5 identical, 21 and 256 rows.
