# Python, Rust and Kotlin

*Bindings at 0.4.x track engine 0.4.0. Each library calls `.mnd`
scripts **in-process** — the same request→response contract as
[`maned-serve`](guides/remote-workers.html)'s REST API, minus the socket —
and each test suite proves its responses **byte-identical** to what the
HTTP server returns for the same script and body.*

One script serves all three examples below:

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

For `x = [[2,0],[0,2]]` and the script's default `w`, every language gets
`y = w·x = [[2,4],[0,2]]` — the same integers, bit for bit, as `maned-run`
and as a Bark worker.

## Python — `manedpy` on PyPI

```sh
pip install manedpy
```

The wheel bundles the Maned embedding library — nothing else to install.

```python
from manedpy import maned as mnd

script = mnd.load("scoring.mnd")
result = script.run({"x": [[2, 0], [0, 2]]})
print("y =", result.outputs["y"])
```

```text
y = [[2, 4], [0, 2]]
```

`mnd.io.scoring(payload)` is sugar over the same call for scripts on
`mnd.search_path`. A payload key with no matching `in::` is refused the
same way the HTTP API answers 400 — not silently ignored.

## Rust — the `maned` crate

```sh
cargo add maned
```

The crate links `libmaned_c` at build time: install the engine first (the
library ships in the `maned-capi-0.4.0-<target>.tar.gz` release asset), and
`build.rs` finds it via `MANED_LIB_DIR`, pkg-config, or the standard
prefixes — refusing with every searched path named when it cannot.

```rust
let mut script = maned::load("scoring.mnd")?;
let result = script.run(&serde_json::json!({"x": [[2, 0], [0, 2]]}))?;
let y = result.tensor("y")?;
println!("y = shape {:?}, data {:?}", y.shape, y.data);
```

```text
y = shape [2, 2], data [2, 4, 0, 2]
```

A non-routed script promotes to `SharedScript` and answers from many
threads without a lock — and the suite asserts the four-thread answers are
byte-identical, because that is the kind of claim this language makes.
An async wrapper rides the `tokio` feature.

## Kotlin/JVM — `dev.maned:maned` on Maven Central

```kotlin
dependencies {
    implementation("dev.maned:maned:0.4.2")
    runtimeOnly("dev.maned:maned:0.4.2:macos-universal")   // or linux-x86_64 / linux-aarch64
}
```

The platform classifier jar carries the native library; the binding
extracts and loads it itself. Two requirements, stated plainly: **JDK 22 or
newer** (the binding uses the Foreign Function & Memory API, final in 22),
and the JVM flag every FFM consumer needs:

```text
--enable-native-access=ALL-UNNAMED
```

```kotlin
import dev.maned.Maned

Maned.load("scoring.mnd").use { s ->
    val result = s.run("""{"x": [[2,0],[0,2]]}""")
    println("y = " + result.outputs["y"])
}
```

```text
y = [[2,4],[0,2]]
```

At `quantres > 0`, `result.decimal(name)` hands back exact `BigDecimal`s
instead of raw integers.

## What holds across all three

- **One contract.** Load a script, send a JSON payload, get the
  `/run.json` document back. What a binding returns is what the HTTP API
  would have sent — a test gate in each repo, not a convention.
- **Routing included.** A script with a `device::` block dispatches to Bark
  workers from inside your process; `host = "local"` spawns the bundled
  local VM exactly as `maned-run` does.
- **Exact numbers end to end.** Tensors arrive as integers plus the
  script's declared scale; the Kotlin binding hands you exact
  `BigDecimal`s, Python and Rust hand you the integers and the scale.

| | Install | Native library | Platforms |
|---|---|---|---|
| Python | `pip install manedpy` | bundled in the wheel | macOS (universal), Linux x86-64 / arm64 |
| Rust | `cargo add maned` | linked at build from the engine install | macOS, Linux x86-64 / arm64 |
| Kotlin | `dev.maned:maned:0.4.2` | bundled in the classifier jar | JDK 22+, macOS / Linux x86-64 / arm64 |

Windows is not supported, matching the [toolchain](install.html).

**Licensing, stated plainly:** the three wrapper libraries are open source
(Apache-2.0; the Rust crates Apache-2.0 OR MIT) and developed at
github.com/FabianoDicheti — `manedpy`, `maned-rs`, `maned-kotlin`. The
embedded engine library they bundle or link is not open source; it is
redistributed unmodified under the Maned licence's Redistributable
Components grant, and each artifact carries both licence texts.

## Next

- [Install](install.html) — the engine toolchain the Rust crate builds
  against.
- [Remote workers](guides/remote-workers.html) — the routing these bindings
  inherit.
- [Language guide](guides/language.html) — the `.mnd` you will be calling.
