# Packed weights

*Requires Maned 0.2.0 or newer. `maned-run --version` tells you what you have;
[Install](install.html) covers upgrading.*

Maned is integer-only, and the weight files the ML world ships are float —
safetensors full of BF16, F16, F32. One global decimal scale cannot bridge
that gap: real models hold values spanning thirty orders of magnitude, and a
single scale that fits the largest value rounds almost everything else to
zero. **Packed weights** solve this the way quantized inference formats do:
values are grouped into blocks of 64, and *each block* carries its own decimal
exponent. A weight is stored as a small integer `q` plus its block's exponent
`s`, and its value is exactly `q · 10⁻ˢ` — still pure decimal fixed point,
still integers everywhere.

Three promises hold throughout this page:

- **Deterministic.** Packing the same shard produces the same bytes on every
  platform — the exponent fit and the rounding are pure integer arithmetic,
  with no dependence on the host's math library. (This is verified by
  byte-comparison across macOS/arm64 and Linux/x86-64 on every release gate.)
- **Lossy once, and counted.** Conversion loss can only happen at pack time,
  never during compute, and every collapsed, clamped or non-finite value is
  counted in the notes. Compute on packed weights is bit-exact everywhere.
- **Honest refusals.** Anything the format cannot represent is refused with
  the reason and the fix — never silently approximated.

## Getting weights in

Three surfaces, all coordinator-side batch actions (they run before your
flows; `maned-serve` refuses them at load):

```mnd
in::w = safetensors("shard.safetensors", "tensor.name");   # one tensor, through the quantizer
tensor::profile("weights/");                               # statistics, writes nothing
tensor::ingestion("weights/", "weights_i64/", quantres=3); # whole tree -> I64 at one scale
tensor::pack("weights/", "weights_p/", bits=auto);         # -> the block-scaled compute format
```

`tensor::profile` is where to start: it prints the ranges, the decimal places
the data actually needs, and — since the per-width preview below — what each
pack width would do to *your* values before you commit to one.

## The pack format, and choosing a width

`tensor::pack` converts every float tensor to integer payloads plus one signed
byte of decimal exponent per 64-value block (stored as a companion
`<name>.pack_scale` tensor). Four payload widths exist, and every one of them
uses an odd saturation limit so rounding ties behave identically everywhere:

| `bits=` | payload | limit | precision per block | typical use |
|---|---|---|---|---|
| `8` | I8 | ±127 | ~2 digits | maximum compression |
| `16` | I16 | ±32767 | ~4.5 digits | the default |
| `32` | I32 | ±2147483647 | ~9.3 digits | **lossless for most real weight blocks** |
| `64` | I64 | ±(10¹⁸−1) | 18 digits | exact for anything a float file can express |
| `auto` | per tensor | — | — | smallest *lossless* width per tensor, else 64 |

You do not have to guess. Profile first:

```text
  pack preview (per-64-block scales, tensor::pack semantics):
    bits=8   collapsed 0            clamped 0            max err 0.05
    bits=16  collapsed 0            clamped 0            max err 0 (lossless)
    bits=32  collapsed 0            clamped 0            max err 0 (lossless)
    bits=64  collapsed 0            clamped 0            max err 0 (lossless)
    recommended: bits=16 (lossless)  - or bits=auto to pick per tensor
```

The preview is not an estimate — it runs the writer's own fit and rounding
over your data, so "lossless" is a promise. `bits=auto` simply applies that
recommendation per tensor and records each tensor's width in the file, so
mixed-width shards describe themselves. And if you pick a fixed width that
loses precision, the pack notes tell you what a wider one would have bought:

```text
note: pack: hint: bits=32 would be lossless for 41 of 43 packed tensor(s) (bits=16: 12)
```

Two more things the writer does for precision without being asked:

- **Rank-0/1 float tensors are exempt.** Biases and norm weights — a
  negligible fraction of bytes, a large fraction of numerical sensitivity —
  are not block-packed at all: they are stored as exact I64 at a per-tensor
  decimal scale, and the reader restores the same reals. `pack_all=1` turns
  this off.
- **Integer tensors are copied verbatim.** They were never at risk.

A real run, with `bits=auto` on a shard holding one weight matrix and one
bias:

```text
note: pack: 1 float tensor(s) -> auto(I16x1) blocks of 64, 0 integer tensor(s) copied, max reconstruction error 0
note: pack wrote 'weights_p.safetensors'
note: pack: exempt: 1 rank<2 float tensor(s) stored exact I64 (0 value(s) inexact); pack_all=1 packs them like the rest
```

Reading a packed shard back with `in:: safetensors(...)` dequantizes through
`q · 10⁻ˢ` and your program sees the same reals whether the shard was raw,
ingested, or packed — the format is invisible to a script that does not opt
into it.

## Multiplying without dequantizing

The point of the format is that the matmul kernel consumes it directly. Pack
with `transpose=1` (the kernel wants the weight stored as W^T so it walks
contiguous memory), load it with `packed()`, and multiply:

```mnd
mnd::quantmax=1000;
mnd::quantmin=-1000;
mnd::quantres=2;

in::w = packed("weights_p.safetensors", "w");   # loaded packed - never dequantized
in::x = [[100, 200]];                            # [1.00, 2.00] at quantres 2

calc::lambda_flow proj(x, w) {
    x pack_rows xp =
    xp w packed_matmul y =
} return y;
```

```text
note: packed 'w': 3x2 I16 descriptor (18 slots), W^T
flow 'proj' outputs:
y : [1x3] = [200, 575, 175]
```

That is `y = x · W` for `W = [[0.5, -1.25, 2.0], [0.75, 3.5, -0.125]]` —
`[2.00, 5.75, 1.75]` at quantres 2, exactly the real-arithmetic answer,
computed without ever materializing a float. A weight costs one or two bytes
end to end; your program's `quantres` cancels out of the algebra, so the
result lands at your scale with no conversion step.

Orientation matters: pack expects the weight in the mathematical `y = x · W`
layout — `[in_features, out_features]` — and `transpose=1` stores W^T from
it. (A file in the `[out, in]` layer convention is the transpose of this;
row *n* of the stored W^T must be column *n* of W.)

Why the answer is bit-identical on every machine and any loop order: the
kernel rescales **per block partial** — each 64-term integer dot product is
divided by its block's `10ˢ`, rounding half to even, *before* accumulation.
Integer addition is associative, division is pinned to one rule, so there is
nothing left to vary.

## Packing activations too

`pack_rows` applies the same treatment to a tensor your flow computed —
activations, which are already integers at your `quantres`. Its fit *is* the
kernel's own rescale rule, so it involves no float arithmetic at all. Two
reasons to use it:

- **The size guard disappears.** `packed_matmul` with a raw integer left
  operand must bound the activation magnitude (a huge activation times a
  block of weights can overflow the accumulator, and this kernel divides, so
  overflow would not be the documented wrap — it would just be wrong; the
  kernel refuses instead). With *both* sides packed, 8/16-bit payloads make
  the partial small by construction, and no bound exists on that path at all.
- **Pack once, use three times.** In a transformer the same activation feeds
  the Q, K and V projections. A packed activation is a value like any other —
  reuse it.

When both sides are packed, each block pair rescales by the *sum* of its two
exponents in a single half-even rounding (never two chained divisions, which
would round twice and drift by one).

## The constraints, honestly

- **Local only, for now.** `packed_matmul` and `pack_rows` run on the
  coordinator and the hosted VM; remote Bark workers refuse them honestly
  (the wire encoding is designed but not yet built).
- **Blocks are 64 values** along the last dimension and never cross rows.
  Block exponents live in `[-18, +18]` — a block whose largest value needs
  more than 18 decimal places of shift quantizes to zero, and the collapse
  is counted.
- **Packing is lossy once.** The notes carry the exact accounting: collapsed,
  clamped, non-finite counts and the maximum reconstruction error — itself
  tracked in exact integers, so even the note is platform-fixed.
- **What gets quantized is the value's shortest decimal form** — pack `12.7`
  and the format faithfully stores 12.7, not the float artifact
  12.6875-and-change the file encoded it as. This is deliberate: it is the
  same decimal contract the rest of the language keeps.
- **`transpose=1` needs the tensor's bytes in memory** and refuses above
  4 GiB per tensor, with the message naming the fix.
- **Raw-activation limits** (only when the left operand is *not* packed):
  at 16-bit payloads `|x|` may not exceed ~4.4·10¹²; at 8-bit, ~1.1·10¹⁵;
  at 64-bit, ~2.6·10¹⁸. At 32-bit payloads no bound is needed, and with
  `pack_rows` none exists at any width.
- **`tensor::` methods are batch actions** — `maned-run` executes them before
  flows; `maned-serve` refuses them at load. Packed and safetensors inputs
  read from their declared paths and cannot be overridden per request.
- Little-endian hosts only (the payload rides byte lanes by design).

## Next

- [Linear algebra](linear-algebra.html) — the scale arithmetic these formats
  plug into, and the matmul idioms.
- [Language guide](guides/language.html) — the full operation table,
  including where `packed_matmul` and `pack_rows` sit.
- [How Maned runs your program](under-the-hood.html) — why bit-exactness is
  the load-bearing property everywhere, not just here.
