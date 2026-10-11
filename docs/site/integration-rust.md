# Rust — the maned crate

*The step-by-step guide to running `.mnd` scripts from Rust, in-process.
The crates are [`maned`](https://crates.io/crates/maned) and
[`maned-sys`](https://crates.io/crates/maned-sys) on crates.io, with API
docs on [docs.rs](https://docs.rs/maned); the wrapper source lives at
[github.com/FabianoDicheti/maned-rs](https://github.com/FabianoDicheti/maned-rs).
For the contract all three bindings share, start at the
[Integration overview](bindings.html).*

## 1. Install the engine library first

Unlike the Python wheel and the Kotlin classifier jar, the Rust crate does
not bundle the engine — it **links** `libmaned_c` at build time, the way a
-sys crate should. Download `maned-capi-0.4.0-<target>.tar.gz` from the
[releases page](https://github.com/FabianoDicheti/maned/releases), unpack
it, and either copy its `lib/` and `include/` into a standard prefix
(`/usr/local`) or remember its path for the build step. Targets published:
macOS (universal), Linux x86-64, Linux arm64.

`build.rs` resolves the library through `MANED_LIB_DIR` →
`pkg-config` → the standard prefixes, and when it cannot, it refuses with
**every searched path named** — no silent miss.

## 2. A project, from zero

```sh
cargo new scoring && cd scoring
cargo add maned serde_json
```

Save the script every page in this section shares as `scoring.mnd`, in the
project directory:

```mnd
mnd::quantmax=30000;
mnd::quantmin=-30000;
mnd::quantres=0;

in::w = [[1,2],[0,1]];

calc::lambda_flow scoring(x, w) {
    w x matmul y =
} return y;

out::y = csv("y.csv");
```

## 3. First run

`src/main.rs`:

```rust
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut script = maned::load("scoring.mnd")?;
    let result = script.run(&serde_json::json!({"x": [[2, 0], [0, 2]]}))?;
    let y = result.tensor("y")?;
    println!("y = shape {:?}, data {:?}", y.shape, y.data);
    println!("engine {}", maned::version());
    Ok(())
}
```

With the tarball in a standard prefix, plain `cargo run` works; with a
custom location, name it:

```text
$ MANED_LIB_DIR=/path/to/capi/lib MANED_INCLUDE_DIR=/path/to/capi/include cargo run
y = shape [2, 2], data [2, 4, 0, 2]
engine 0.4.0
```

`load` parses and validates the script once; `run` sends one payload
through it and returns the same document `maned-serve`'s HTTP API would,
byte for byte. `result.tensor(name)` hands back exact `i64` data with its
shape.

## 4. Payloads and errors

The payload is `serde_json` JSON: one key per `in::` you want to override,
tensors as nested arrays of integers. Inputs you omit keep their script
defaults — `w` above. A key that names no input is refused with the
message the HTTP API answers 400 — never silently ignored. Failures come
back as a typed `maned::Error` carrying the status and the engine's own
message, so `?` propagates them like any other Rust error.

## 5. File routes: bytes in, file bytes back

A file-sourced input — `in::data = csv("data.csv")` — can be overridden by
name with raw bytes, and every `out::` comes back as the bytes of its
output file. With `pipeline.mnd`:

```mnd
mnd::quantmax=100000;
mnd::quantmin=-100000;
mnd::quantres=2;

in::data  = csv("data.csv");
in::scale = 100;

calc::lambda_flow gram(data, scale) {
    data transpose dT =
    dT data matmul raw =
    raw scale div g =
} return g;

out::g = csv("gram.csv");
```

```rust
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut script = maned::load("pipeline.mnd")?;
    let csv_bytes = std::fs::read("data.csv")?;

    let out = script.run_files(&[("data", csv_bytes)])?;
    println!("outputs: {:?}", out.keys().collect::<Vec<_>>());
    print!("{}", String::from_utf8_lossy(&out["g"]));
    Ok(())
}
```

```text
outputs: ["g"]
8.75,3.50
3.50,5.00
```

One caution that saves an afternoon: a script's *own* `csv("data.csv")`
sources resolve against the **process working directory** — run from the
script's directory (or `std::env::set_current_dir` first), or use absolute
paths inside the `.mnd`.

## 6. Exact decimals, with async

![A maned wolf with a crab](assets/img/wolf-rust.png)

At `quantres > 0` the integers carry a decimal scale (`1999` means
`19.99`), and `result.decimal(name)` hands back the decoded decimal **as a
string** — never a float. A non-routed script promotes to a
`SharedScript` that answers from many threads without a lock, and the
`tokio` feature adds `run_async` on the blocking pool:

```sh
cargo add maned --features tokio
cargo add tokio --features macros,rt-multi-thread
```

With `decimal.mnd`:

```mnd
mnd::quantmax=100000;
mnd::quantmin=-100000;
mnd::quantres=2;

in::prices = [1999, 2550, 999];
in::three  = 3;

calc::lambda_flow avg(prices, three) {
    prices tensor_sum total =
    total three div mean =
} return total, mean;

out::total = csv("total.csv");
out::mean  = csv("mean.csv");
```

```rust
use std::sync::Arc;

#[tokio::main(flavor = "multi_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let shared = Arc::new(maned::load("decimal.mnd")?.into_shared().expect("non-routed"));

    let result = Arc::clone(&shared).run_async(serde_json::json!({})).await?;
    println!(
        "total = {}  mean = {}",
        result.decimal("total")?,
        result.decimal("mean")?
    );

    let reference = result.body().to_vec();
    let mut tasks = Vec::new();
    for _ in 0..4 {
        let s = Arc::clone(&shared);
        tasks.push(tokio::spawn(s.run_async(serde_json::json!({}))));
    }
    let mut identical = true;
    for t in tasks {
        identical &= t.await??.body() == reference.as_slice();
    }
    println!("4 concurrent runs, byte-identical: {identical}");
    Ok(())
}
```

```text
total = [55.48]  mean = [18.49]
4 concurrent runs, byte-identical: true
```

The four concurrent responses being byte-identical is not luck — it is the
language's determinism contract, and the crate's test suite asserts it.

## 7. Routing to a Bark worker

A script with a `device::` block dispatches its `@device` flows from
inside your process — to a [Bark machine](bark-machines.html) on your
network, or with `host = "local"` to the bundled local VM (the worker's
real compute core, spawned as a child process). The local case needs the
[maned toolchain](install.html) installed, which puts `bark-vm` on your
`PATH`. With `routed.mnd`:

```mnd
mnd::quantmax=30000;
mnd::quantmin=-30000;
mnd::quantres=0;

in::a = [[1,2],[3,4]];
in::b = [[5,6],[7,8]];

device::vm1 { host = "local"; }

calc::lambda_flow mm(a, b) @device(vm1) {
    a b matmul r =
} return r;

out::r = csv("r.csv");
```

```rust
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut script = maned::load("routed.mnd")?;
    let result = script.run(&serde_json::json!({}))?;
    let r = result.tensor("r")?;
    println!("r = shape {:?}, data {:?}", r.shape, r.data);
    Ok(())
}
```

```text
r = shape [2, 2], data [19, 22, 43, 50]
```

Swap `host = "local"` for a worker's address and nothing else changes —
same code, same integers back.

## 8. The API at a glance

| Call | What it does |
|---|---|
| `maned::load(path)` | parse + validate once → a `Script` |
| `script.run(&json)` | one JSON payload through → `Result` |
| `script.run_files(&[(name, bytes)])` | multipart twin: bytes in, map of bytes back |
| `result.tensor(name)` | exact `i64` data with its shape |
| `result.decimal(name)` | the decoded decimal, as a string |
| `script.into_shared()` | non-routed scripts → lock-free `SharedScript` |
| `shared.run_async(json)` | the `tokio`-feature async variant |
| `maned::version()` | the linked engine's version |

## 9. If something refuses to run

- **`build.rs` cannot find the library** — set `MANED_LIB_DIR` (and
  `MANED_INCLUDE_DIR`) to the unpacked capi tarball's `lib/` and
  `include/`. The refusal message names every path it searched.
- **The binary builds, then dies at startup with
  `Library not loaded: @rpath/...`** — link search paths propagate through
  the dependency graph, but rpath link args do not. Either install the
  library in a standard prefix, or add to your binary crate's own
  `build.rs`:
  `println!("cargo:rustc-link-arg=-Wl,-rpath,{}", std::env::var("MANED_LIB_DIR")?);`
- **A `csv(...)` source is "not found"** — see the working-directory
  caution in section 5.
- **`cannot spawn the Bark VM ('bark-vm')`** — the routed example needs
  the [toolchain install](install.html), which provides `bark-vm` on
  `PATH`.

Runnable copies of all four programs on this page ship in the repo —
`cargo run --example scoring`, `--example files`,
`--example decimals_tokio --features tokio`, `--example routed` — in
[maned-rs/maned/examples](https://github.com/FabianoDicheti/maned-rs/tree/master/maned/examples).

## Next

- [Integration overview](bindings.html) — the contract shared with Python
  and Kotlin, and the platform matrix.
- [Language guide](guides/language.html) — the `.mnd` you are calling.
- [Remote workers](guides/remote-workers.html) — the routing these scripts
  inherit.
