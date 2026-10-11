# Kotlin/JVM — dev.maned:maned

*The step-by-step guide to running `.mnd` scripts from Kotlin (or any JVM
language), in-process. The artifact is
[`dev.maned:maned` on Maven Central](https://central.sonatype.com/artifact/dev.maned/maned);
the wrapper source lives at
[github.com/FabianoDicheti/maned-kotlin](https://github.com/FabianoDicheti/maned-kotlin).
For the contract all three bindings share, start at the
[Integration overview](bindings.html).*

## 1. Requirements, stated up front

- **JDK 22 or newer.** The binding uses the Foreign Function & Memory API,
  final in 22. There is no fallback path for older JDKs.
- **One JVM flag.** Every FFM consumer needs it; without it, JDK 22/23
  warn, JDK 24 warns loudly, and a future JDK refuses:

```text
--enable-native-access=ALL-UNNAMED
```

The binding detects the flag's absence and logs one actionable line rather
than letting the JVM's own warning be your first clue.

## 2. A project, from zero

The dependency comes in two parts: the library, and a **platform
classifier jar** that carries the native engine library — `macos-universal`,
`linux-x86_64` or `linux-aarch64`. Nothing else to install. A complete
`build.gradle.kts`:

```kotlin
plugins {
    kotlin("jvm") version "2.3.21"
    application
}
repositories { mavenCentral() }

dependencies {
    implementation("dev.maned:maned:0.4.2")
    runtimeOnly("dev.maned:maned:0.4.2:macos-universal")   // your platform here
}
application {
    mainClass.set("ScoringKt")
    applicationDefaultJvmArgs = listOf("--enable-native-access=ALL-UNNAMED")
}
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

`src/main/kotlin/Scoring.kt`:

```kotlin
import dev.maned.Maned

fun main() {
    Maned.load("scoring.mnd").use { s ->
        val result = s.run("""{"x": [[2,0],[0,2]]}""")
        println("y = " + result.outputs["y"] + " | engine " + Maned.version())
    }
}
```

```text
$ gradle run
y = [[2,4],[0,2]] | engine 0.4.0
```

`Maned.load` parses and validates the script once and hands back an
`AutoCloseable` script handle — hence the `use` block. `run` takes the
payload as a JSON string and returns the same document `maned-serve`'s
HTTP API would, byte for byte.

## 4. Payloads and errors

The payload is JSON: one key per `in::` you want to override, tensors as
nested arrays of integers. Inputs you omit keep their script defaults —
`w` above. A key that names no input is refused with the message the HTTP
API answers 400, as a typed `ManedInputException` — never silently
ignored. All failures are typed exceptions under `ManedException`, each
carrying the status and the engine's own message.

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

```kotlin
import dev.maned.Maned

fun main() {
    Maned.load("pipeline.mnd").use { s ->
        val out = s.runFiles("data" to java.io.File("data.csv").readBytes())
        println("outputs: " + out.keys)
        print(out["g"]!!.decodeToString())
    }
}
```

```text
outputs: [g]
8.75,3.50
3.50,5.00
```

One caution that saves an afternoon: a script's *own* `csv("data.csv")`
sources resolve against the **process working directory**, and on the JVM
setting `user.dir` does **not** chdir — Gradle daemons and app servers
start with a CWD nobody intended. Use absolute paths inside `.mnd` files,
or pin `workingDir` on the Gradle task.

## 6. Exact decimals, with coroutines

![A maned wolf having coffee](assets/img/wolf-kotlin.png)

At `quantres > 0` the integers carry a decimal scale (`1999` means
`19.99`), and `result.decimals(name)` hands back exact `BigDecimal`s —
never floats. The binding also ships a `runAsync` suspend extension, so a
coroutine suspends on a dispatcher while the engine computes. With
`decimal.mnd`:

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

```kotlin
import dev.maned.Maned
import dev.maned.runAsync
import kotlinx.coroutines.async
import kotlinx.coroutines.runBlocking

fun main() = runBlocking {
    Maned.load("decimal.mnd").use { s ->
        val result = s.run("{}")
        println("total = " + result.decimals("total") + "  mean = " + result.decimals("mean"))

        val reference = result.outputs.toString()
        val agreed = (1..4).map {
            async { s.runAsync("{}").outputs.toString() == reference }
        }.all { it.await() }
        println("4 concurrent runs agree: $agreed")
    }
}
```

```text
total = [55.48]  mean = [18.49]
4 concurrent runs agree: true
```

The four concurrent runs agreeing is not luck — it is the language's
determinism contract, and the binding's test suite asserts it byte for
byte.

## 7. Routing to a Bark worker

A script with a `device::` block dispatches its `@device` flows from
inside the JVM — to a [Bark machine](bark-machines.html) on your network,
or with `host = "local"` to the bundled local VM (the worker's real
compute core, spawned as a child process). The local case needs the
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

```kotlin
import dev.maned.Maned

fun main() {
    Maned.load("routed.mnd").use { s ->
        val result = s.run("{}")
        println("r = " + result.outputs["r"])
    }
}
```

```text
r = [[19,22],[43,50]]
```

Swap `host = "local"` for a worker's address and nothing else changes —
same code, same integers back.

## 8. The API at a glance

| Call | What it does |
|---|---|
| `Maned.load(path)` | parse + validate once → an `AutoCloseable` script |
| `script.run(json)` | one JSON payload through → the `/run.json` result |
| `script.runFiles("name" to bytes)` | multipart twin: bytes in, `Map<String, ByteArray>` back |
| `script.runAsync(json)` | the suspend variant, for coroutines |
| `result.outputs` | decoded outputs, keyed by `out::` name |
| `result.tensor(name)` / `result.decimals(name)` | exact int64 data, or exact `BigDecimal`s |
| `Maned.io["scoring"]` | sugar: find `scoring.mnd` on the search path |
| `Maned.version()` | the bundled engine's version |

## 9. If something refuses to run

- **A warning about restricted methods, or a hard refusal** — the JVM flag
  from section 1 is missing. Put it in `applicationDefaultJvmArgs` (or
  `jvmArgs` on the task).
- **Native library extraction fails** — the classifier jar's library is
  extracted to `$XDG_CACHE_HOME/maned` → `~/.cache/maned` → the JVM temp
  dir, each candidate probed with a real `dlopen` (hardened containers
  often mount `/tmp` `noexec`). The refusal names every path tried;
  `-Dmaned.library.path=<file>` is the escape hatch.
- **A `csv(...)` source is "not found"** — see the working-directory
  caution in section 5.
- **`cannot spawn the Bark VM ('bark-vm')`** — the routed example needs
  the [toolchain install](install.html), which provides `bark-vm` on
  `PATH`.

Complete runnable projects for everything on this page — resolving the
published artifact from Maven Central — live in
[maned-kotlin/examples](https://github.com/FabianoDicheti/maned-kotlin/tree/master/examples):
`examples/scoring` (`gradle run`) and `examples/deepdive`
(`gradle runFiles`, `runDecimals`, `runRouted`).

## Next

- [Integration overview](bindings.html) — the contract shared with Python
  and Rust, and the platform matrix.
- [Language guide](guides/language.html) — the `.mnd` you are calling.
- [Remote workers](guides/remote-workers.html) — the routing these scripts
  inherit.
