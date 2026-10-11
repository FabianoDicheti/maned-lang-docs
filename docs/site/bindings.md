# Integration

*Maned embeds. Three libraries — Python, Kotlin and Rust, at 0.4.x
tracking engine 0.4.0 — call `.mnd` scripts **in-process**: the same
request→response contract as [`maned-serve`](guides/remote-workers.html)'s
REST API, minus the socket. Each test suite proves its responses
**byte-identical** to what the HTTP server returns for the same script and
body. This page is the map; each language has its own step-by-step guide:
[Python](integration/python.html), [Kotlin](integration/kotlin.html),
[Rust](integration/rust.html).*

![A maned wolf having coffee with two snakes and a crab](assets/img/wolf-polyglot.png "Python, the JVM and Rust, one engine between them.")

One script serves every example in this section:

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

## Python

```sh
pip install manedpy
```

The wheel bundles the engine library — nothing else to install.

```python
from manedpy import maned as mnd

result = mnd.load("scoring.mnd").run({"x": [[2, 0], [0, 2]]})
print("y =", result.outputs["y"])
```

```text
y = [[2, 4], [0, 2]]
```

**[The full Python guide →](integration/python.html)** — project setup,
payloads and typed errors, file routes, exact decimals, routing to Bark.
Package on [PyPI](https://pypi.org/project/manedpy/); source at
[github.com/FabianoDicheti/manedpy](https://github.com/FabianoDicheti/manedpy).

## Kotlin/JVM

```kotlin
dependencies {
    implementation("dev.maned:maned:0.4.2")
    runtimeOnly("dev.maned:maned:0.4.2:macos-universal")   // or linux-x86_64 / linux-aarch64
}
```

The platform classifier jar carries the native library; the binding
extracts and loads it itself. JDK 22+, plus the
`--enable-native-access=ALL-UNNAMED` flag every FFM consumer needs.

```kotlin
import dev.maned.Maned

Maned.load("scoring.mnd").use { s ->
    println("y = " + s.run("""{"x": [[2,0],[0,2]]}""").outputs["y"])
}
```

```text
y = [[2,4],[0,2]]
```

**[The full Kotlin guide →](integration/kotlin.html)** — the Gradle setup,
exact `BigDecimal`s, coroutines, file routes, routing to Bark. Artifact on
[Maven Central](https://central.sonatype.com/artifact/dev.maned/maned);
source at
[github.com/FabianoDicheti/maned-kotlin](https://github.com/FabianoDicheti/maned-kotlin).

## Rust

```sh
cargo add maned
```

The crate links `libmaned_c` at build time: install the engine first (the
library ships in the `maned-capi-0.4.0-<target>.tar.gz` release asset),
and `build.rs` finds it via `MANED_LIB_DIR`, pkg-config, or the standard
prefixes.

```rust
let mut script = maned::load("scoring.mnd")?;
let y = script.run(&serde_json::json!({"x": [[2, 0], [0, 2]]}))?.tensor("y")?;
println!("y = shape {:?}, data {:?}", y.shape, y.data);
```

```text
y = shape [2, 2], data [2, 4, 0, 2]
```

**[The full Rust guide →](integration/rust.html)** — linking and rpath,
lock-free shared scripts, the `tokio` async feature, file routes, routing
to Bark. Crates on [crates.io](https://crates.io/crates/maned) (plus
[maned-sys](https://crates.io/crates/maned-sys)), API docs on
[docs.rs](https://docs.rs/maned); source at
[github.com/FabianoDicheti/maned-rs](https://github.com/FabianoDicheti/maned-rs).

## What holds across all three

- **One contract.** Load a script, send a JSON payload, get the
  `/run.json` document back. What a binding returns is what the HTTP API
  would have sent — a test gate in each repo, not a convention. A payload
  key with no matching `in::` is refused the same way the HTTP API answers
  400 — not silently ignored.
- **Routing included.** A script with a `device::` block dispatches to Bark
  workers from inside your process; `host = "local"` spawns the bundled
  local VM exactly as `maned-run` does.
- **Exact numbers end to end.** Tensors arrive as integers plus the
  script's declared scale; the Kotlin binding hands you exact
  `BigDecimal`s, Python and Rust hand you the integers, the scale, and the
  decoded decimal strings.

| | Install | Native library | Platforms |
|---|---|---|---|
| [Python](integration/python.html) | `pip install manedpy` | bundled in the wheel | macOS (universal), Linux x86-64 / arm64 |
| [Kotlin](integration/kotlin.html) | `dev.maned:maned:0.4.2` | bundled in the classifier jar | JDK 22+, macOS / Linux x86-64 / arm64 |
| [Rust](integration/rust.html) | `cargo add maned` | linked at build from the engine install | macOS, Linux x86-64 / arm64 |

Windows is not supported, matching the [toolchain](install.html).

**Licensing, stated plainly:** the three wrapper libraries are open source
(Apache-2.0; the Rust crates Apache-2.0 OR MIT) and developed at
github.com/FabianoDicheti — `manedpy`, `maned-rs`, `maned-kotlin`. The
embedded engine library they bundle or link is not open source; it is
redistributed unmodified under the Maned licence's Redistributable
Components grant, and each artifact carries both licence texts.

## Next

- [Python](integration/python.html), [Kotlin](integration/kotlin.html) and
  [Rust](integration/rust.html) — the step-by-step guides.
- [Remote workers](guides/remote-workers.html) — the routing these bindings
  inherit.
- [Language guide](guides/language.html) — the `.mnd` you will be calling.
