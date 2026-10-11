# Python — manedpy

*The step-by-step guide to running `.mnd` scripts from Python, in-process.
The package is [`manedpy` on PyPI](https://pypi.org/project/manedpy/); the
wrapper source lives at
[github.com/FabianoDicheti/manedpy](https://github.com/FabianoDicheti/manedpy).
For the contract all three bindings share, start at the
[Integration overview](bindings.html).*

## 1. Install

```sh
pip install manedpy
```

That is the whole install: the wheel bundles the Maned embedding library
(`libmaned_c`) for your platform — macOS (universal), Linux x86-64 and
Linux arm64 — and has no runtime dependencies. Python 3.9 or newer.

Installing from source (the sdist) deliberately ships no binary; point
`$MANEDPY_LIB` at the `libmaned_c` from a `maned-capi-*` release tarball
instead. Everything below assumes the wheel.

## 2. A project, from zero

```sh
mkdir scoring && cd scoring
python3 -m venv .venv && . .venv/bin/activate
pip install manedpy
```

Save the script every page in this section shares as `scoring.mnd`:

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

Save as `scoring.py`:

```python
from manedpy import maned as mnd

script = mnd.load("scoring.mnd")
result = script.run({"x": [[2, 0], [0, 2]]})
print("y =", result.outputs["y"])
print("engine", mnd.lib_version)
```

```text
$ python scoring.py
y = [[2, 4], [0, 2]]
engine 0.4.0
```

`load` parses and validates the script once; `run` sends one payload
through it. Both are plain synchronous calls into the in-process engine —
no server, no socket, and the result is byte-identical to what
`maned-serve`'s HTTP API returns for the same script and body.

Scripts are cached on `(realpath, mtime, size)`, so editing a `.mnd` and
re-running in the same REPL picks the change up automatically.

## 4. Payloads and errors

A payload is a JSON-shaped dict: one key per `in::` you want to override,
tensors as nested lists of integers. Inputs you omit keep their script
defaults — `w` above. A key that names no input is **refused**, with the
same message the HTTP API answers 400 — never silently ignored:

```python
script.run({"x": [[2, 0], [0, 2]], "nope": 7})
```

```text
manedpy.errors.ManedInputError: scoring.mnd: HTTP 400: 'nope' names no request input
```

Errors form a hierarchy under `ManedError`, each carrying `.status`,
`.body` and `.script`: bad payloads raise `ManedInputError` (also a
`ValueError`), a flow failure raises `ManedRuntimeError` (also a
`RuntimeError`), and a script that fails to load raises `ManedLoadError`.
Catch `ManedError` to catch them all.

## 5. File routes: bytes in, file bytes back

A file-sourced input — `in::data = csv("data.csv")` — can be overridden by
name with raw bytes, and every `out::` comes back as the bytes of its
output file. This is the in-process twin of
`curl -F data=@data.csv http://.../run`. With `pipeline.mnd`:

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

```python
from manedpy import maned as mnd

script = mnd.load("pipeline.mnd")
with open("data.csv", "rb") as f:
    csv_bytes = f.read()

out = script.run_files(data=csv_bytes)
print("outputs:", list(out))
print(out["g"].decode().strip())
```

```text
outputs: ['g']
8.75,3.50
3.50,5.00
```

One caution that saves an afternoon: a script's *own* `csv("data.csv")`
sources resolve against the **process working directory**, so either run
from the script's directory or use absolute paths inside the `.mnd`.

## 6. Exact decimals

At `quantres > 0` the integers carry a decimal scale: `quantres=2` makes
the integer `1999` mean `19.99`. Division truncates — deliberately, and
identically on every machine — so there is nothing float-shaped anywhere.
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

```python
script = mnd.load("decimal.mnd")
result = script.run({})
print("total =", result.outputs["total"])
print("mean  =", result.outputs["mean"])
```

```text
total = [55.48]
mean  = [18.49]
```

The outputs arrive already decoded at the script's declared scale —
`55.48/3` lands on `18.49` exactly.

## 7. Routing to a Bark worker

A script with a `device::` block dispatches its `@device` flows from
inside your Python process — to a [Bark machine](bark-machines.html) on
your network, or with `host = "local"` to the bundled local VM (the
worker's real compute core, spawned as a child process). The local case
needs the [maned toolchain](install.html) installed, which puts `bark-vm`
on your `PATH`. With `routed.mnd`:

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

```python
script = mnd.load("routed.mnd")
result = script.run({})
print("r =", result.outputs["r"])
```

```text
r = [[19, 22], [43, 50]]
```

Swap `host = "local"` for a worker's address and nothing else changes —
same code, same integers back.

## 8. The API at a glance

| Call | What it does |
|---|---|
| `mnd.load(path)` | parse + validate once, return a cached `Script` |
| `script.run(payload)` | one JSON payload through → `Result` |
| `script.run_files(**named_bytes)` | multipart twin: bytes in, `{name: bytes}` back |
| `result.outputs` | decoded outputs, keyed by `out::` name |
| `mnd.io.scoring(payload)` | sugar: find `scoring.mnd` on `mnd.search_path` and run it |
| `mnd.lib_version` | the bundled engine's version |

A `Script` takes a lock per call by default, which makes the routed case
correct by construction; `mnd.load(path, concurrent=True)` drops the lock
for non-routed scripts, which are provably safe to share.

## 9. If something refuses to run

- **`ManedLibraryError: no libmaned_c found`** — you are running from a
  source checkout, not the wheel. Either `pip install manedpy`, or set
  `$MANEDPY_LIB` to a `libmaned_c` from a `maned-capi-*` tarball.
- **A `csv(...)` source is "not found"** — relative paths in `.mnd` files
  resolve against the process CWD; run from the script's directory.
- **`cannot spawn the Bark VM ('bark-vm')`** — the routed example needs the
  [toolchain install](install.html), which provides `bark-vm` on `PATH`.

Runnable copies of all four programs on this page ship in
[manedpy/examples](https://github.com/FabianoDicheti/manedpy/tree/master/examples),
with `data.csv` beside them.

## Next

- [Integration overview](bindings.html) — the contract shared with Kotlin
  and Rust, and the platform matrix.
- [Language guide](guides/language.html) — the `.mnd` you are calling.
- [Remote workers](guides/remote-workers.html) — the routing these scripts
  inherit.
