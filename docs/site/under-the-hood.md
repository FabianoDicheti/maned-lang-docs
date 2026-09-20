# How Maned runs your program

You do not need any of this to write Maned. You need it when you want to know
*why* a limit exists, why two machines agree to the byte, or what a refusal is
protecting you from.

Nothing here is about the compiler's source. It is about the shape of your
program after you hit enter, and what that shape costs and buys you.

## Your program becomes a graph

A `calc::lambda_flow` body is read strictly left to right against an operand
stack. That is not a stylistic preference — it is what makes the token order
*already* a dependency order:

```mnd
x w matmul    p =
p bias elemwise_add s =
s relu        result =
```

Each binding names a value; each operation consumes values and produces one.
Written out, that is a graph with three nodes and no ambiguity about what
depends on what. There is no precedence to resolve and no parenthesis to
associate, so there is nothing to disagree about between a reader, the
interpreter, and a piece of hardware.

This is why Maned has no infix arithmetic. An expression like `a + b * c` has
to be *resolved* into a graph, and the resolution is a convention you have to
know. `a b c mul add` is already the graph.

**What it means for you:** if you can read your flow top to bottom, you can
read its execution order. There is no second mental model.

## What the optimizer does, and what it refuses to do

Before your flow runs or ships anywhere, it is rewritten twice:

- **Repeated literals collapse.** Write `2` in five places and it costs one
  value, not five.
- **Unread values disappear.** A binding nothing reads — directly or through
  a return — is dropped.

Both are safe by construction: removing a value nothing reads cannot change a
value something does read. The results are bit-identical before and after,
and that claim is a test gate, not an aspiration.

What is **never** removed is a parameter. Parameters are your input contract;
dropping an unused one would renumber the slots a worker binds its inputs to.
An unused parameter earns a lint warning and keeps its slot.

**What it means for you:** you can name intermediates freely for readability.
Clarity is not paid for in the register budget.

## The budget you can actually hit

A compiled flow has to fit the machine that will run it, and Maned checks that
before sending anything:

| Limit | Value | What counts |
|---|---|---|
| Register file | 256 or 4096 values | every parameter, constant and operation result, after inlining |
| Tensors per job | 16 in, 16 out | a flow's parameters and returns |
| Tensor rank | 1 to 4 | each input and output |

The register file is 256 on the original wire format and 4096 on the newer
one; the toolchain negotiates which applies with the worker that answers, and
checks your flow against *that* worker's number. It refuses with the measured
figure rather than truncating:

```text
flow 'wide' compiles to 312 values, but the target register file has 256
slots (ABI v1 RF_SLOTS); split the flow or reduce intermediates
```

Helper flows are inlined at their call sites before this count, so a flow that
calls three helpers is measured as one graph — which is the graph that
actually ships.

**What it means for you:** a flow that is too big fails on your machine, with
a number, before it ever reaches hardware. `maned-lint` applies the same rule,
so your editor can tell you first.

## Crossing the wire

To run somewhere else, a flow is packed into a single envelope: the
quantization contract you declared, the compiled graph, and the input tensors.
The reply carries the output tensors and nothing else.

Two properties are worth knowing:

**The envelope carries your quantization contract.** `mnd::quantres`,
`quantmin` and `quantmax` travel *with* the program. A worker cannot
misinterpret your integers, because the scale is not an out-of-band agreement
— it is part of the shipment.

**The wire format is versioned, and version skew refuses.** An older worker
speaks the 256-slot encoding; a newer one speaks the 4096-slot encoding. The
toolchain asks before it sends. If a construct cannot survive the older
format, it is refused rather than silently degraded — the failure mode Maned
consistently prefers.

**What it means for you:** the same `.mnd` file is the unit of deployment.
There is no separate model file, no config to keep in sync, and no way for the
numbers to mean one thing locally and another remotely.

## Where a flow can run

| Target | How you ask for it | What executes |
|---|---|---|
| Your machine | the default | the integer interpreter |
| A local worker VM | `--device local`, or `host = "local"` | the worker's real compute core, hosted on your machine |
| A worker on the network | `device::` + `@device(alias)` | that worker |

Routing is per flow, not per program: one script can leave preprocessing local
and send a matmul to hardware, and the toolchain moves the tensors between
them. Flows with no dependency on each other run concurrently; a flow starts
the moment its inputs exist rather than waiting on a slower sibling.

The VM path matters even if you have no hardware. It is the worker's actual
compute core compiled for your laptop — not a simulation of it — so what you
see locally is what the hardware produces.

## Why the answer is identical everywhere

This is the claim the rest of the design exists to protect.

**There is no floating point in the compute path.** Not reduced, not
carefully-ordered — absent. The classic sources of cross-machine drift
(reassociation, fused multiply-add, x87 excess precision, `-ffast-math`) have
nothing to act on, because there are no floats for them to act on.

**The kernels are shared, not reimplemented.** The interpreter and the worker
compile the same integer routines for activations and normalizations. They do
not agree because two teams were careful; they agree because there is one
implementation.

**Threading cannot move a number.** Work splits into fixed bands of output
rows, decided by the shape and the thread count, never by timing or completion
order. No accumulator is ever split. `--threads 1` and `--threads 16` are the
same program at different speeds.

**Overflow is defined, not undefined.** Integer results wrap at 32 bits, and
every target wraps the same way. `--trap-overflow` turns a wrap into an error
naming the value, for when you want to find one rather than tolerate it.

And the claim is checkable rather than asserted:

```sh
maned-run flow.mnd --verify
```

runs your flow on the target *and* locally, compares every output exactly, and
tells you which two things it compared. A mismatch is a bug report, not a
tolerance to tune.

## The hardware path

Maned also has an MLIR-based compiler path, which lowers flows toward standard
MLIR dialects and toward an FPGA-oriented dialect, with a profiling pass that
inspects matrix multiplications to inform target selection.

This is the route from a `.mnd` flow to generated hardware rather than to a
running process, and it is relevant to you only if that is where your program
is heading. It needs a separate tool and an MLIR toolchain; the ordinary
`maned-run` path does not, and nothing in this page above depends on it.

## Where the rules are written down

This page explains behaviour. When you need the normative answer:

- [RPN syntax specification](spec/rpn-syntax.html) — what the language *is*.
  On conflict between documents, it wins.
- [Language guide](guides/language.html) — the complete operation table,
  including which operations run locally, which cross the wire, and which are
  declared but not executable.
- [Diagnostics](guides/diagnostics.html) — every error and warning code,
  including the limit refusals quoted above.
