# Lambda calculus and the birds

Maned's functional core is combinatory logic under Smullyan's bird names —
identity, kestrel, kite, bluebird, cardinal, warbler, thrush. What makes the
language unusual is that **you never call them**. In a postfix language the
stack operators *are* the combinators: combinatory logic and RPN are the same
idea written down twice.

This page is that correspondence, what it buys you, and — because the docs here
try to be honest about it — exactly which of the bird names are implemented,
which are reserved, and which one can never work.

Every code block below was run to produce the output beside it.

## Postfix *is* combinatory logic

| Bird | λ-term | Maned postfix | Meaning |
|---|---|---|---|
| identity `I` | `λx. x` | `x` | the value itself |
| kestrel `K` | `λx.λy. x` | `x y drop` | keep the first |
| kite `KI` | `λx.λy. y` | `x y swap drop` | keep the second |
| warbler `W` | `λf.λx. f x x` | `x dup f` | feed `x` to `f` twice |
| cardinal `C` | `λf.λx.λy. f y x` | `x y swap f` | flip the arguments |
| bluebird `B` | `λf.λg.λx. f (g x)` | `x g f` | composition |
| thrush `T` | `λx.λf. f x` | `x f` | postfix itself |

Read the bluebird row twice. `x g f` needs **no combinator at all** —
juxtaposition in postfix *is* composition. Which is why `B`, `T` and `I` have
no runtime cost here: they are the notation, not a function you apply. The
compositional plumbing that a prefix language needs combinators to express is,
in RPN, the order you already wrote the tokens in.

That is also one of the language's stated design goals: *function application
is naturally postfix, so combinators compose without parentheses*.

## The stack operators, precisely

Six of them, with standard Forth semantics. A binary operator takes its
operands in push order — second-from-top is the left-hand side, top is the
right:

| Op | Stack before → after | `a b [op] elemwise_sub` with a=100, b=20, c=3 |
|---|---|---|
| `dup` | `a` → `a a` | — |
| `drop` | `a b` → `a` | — |
| `swap` | `a b` → `b a` | `-80` (b − a) |
| `over` | `a b` → `a b a` | `-80` (b − a) |
| `rot` | `a b c` → `b c a` | `-97` (c − a) |
| `-rot` | `a b c` → `c a b` | `80` (a − b) |

Without any of them, `a b elemwise_sub` is `80` — plain `a − b`.

Stack operations parse into dedicated AST nodes, so they cost nothing at run
time. Use them where they clarify data reuse and **prefer a named binding when
a longer stack sequence would be hard to review** — the point of `dup` is to
say "this same value, twice", not to win at Tetris.

## The birds at work

Every one of these lines runs, and each is a bird:

```mnd
in::x = [[10,20],[30,40]];
in::y = [[99, 1],[ 7,77]];

calc::lambda_flow birds(x, y) {
    x same =                          # I  : an operand alone binds itself

    x y drop      kestrel_keeps_x =   # K  : push both, discard the second
    x y swap drop kite_keeps_y =      # KI : push both, swap, discard

    x dup elemwise_add warbler_doubles =   # W : dup supplies x twice
    x dup matmul       warbler_squares =

    x y elemwise_sub      cardinal_before =  # C : swap before a
    x y swap elemwise_sub cardinal_after =   #     non-commutative op

    x transpose relu bluebird_relu_of_transpose =   # B : write g, then f
} return same, kestrel_keeps_x, kite_keeps_y, warbler_doubles,
         warbler_squares, cardinal_before, cardinal_after,
         bluebird_relu_of_transpose;
```

```text
same                       : [2x2] = [10, 20, 30, 40]
kestrel_keeps_x            : [2x2] = [10, 20, 30, 40]
kite_keeps_y               : [2x2] = [99, 1, 7, 77]
warbler_doubles            : [2x2] = [20, 40, 60, 80]
warbler_squares            : [2x2] = [700, 1000, 1500, 2200]
cardinal_before            : [2x2] = [-89, 19, 23, -37]
cardinal_after             : [2x2] = [89, -19, -23, 37]
bluebird_relu_of_transpose : [2x2] = [10, 30, 20, 40]
```

`cardinal_before` and `cardinal_after` are negatives of each other, which is
the cardinal doing its one job. `warbler_squares` is `x · x` from a single
mention of `x`.

## Church booleans, without functions

In the λ-calculus `true` **is** the kestrel and `false` **is** the kite, and
`if c then x else y` is just the application `c x y` — the boolean chooses by
*being* a function that returns one of its arguments.

Maned is integer-quantized, so a predicate cannot return a function. It returns
a **0/1 mask** instead, and the choice becomes branch-free arithmetic:

```text
select(c, x, y)  =  c*x + (1−c)*y        # c is 1 (K) or 0 (KI)
```

```mnd
calc::lambda_flow choose(x, y) {
    x y > c =                                  # 1 where x > y, else 0

    c x elemwise_mul     k_branch =            # the TRUE branch, gated by c
    1 c sub              not_c =               # negation, by arithmetic
    not_c y elemwise_mul ki_branch =           # the FALSE branch
    k_branch ki_branch elemwise_add selected = # = elementwise max(x, y)

    c y elemwise_mul     k_swapped =           # the same shape, branches
    not_c x elemwise_mul ki_swapped =          # exchanged
    k_swapped ki_swapped elemwise_add selected_other =   # = min(x, y)
} return c, selected, selected_other;
```

```text
c              : [2x2] = [0, 1, 1, 0]
selected       : [2x2] = [99, 20, 30, 77]      # elementwise max
selected_other : [2x2] = [10, 1, 7, 40]        # elementwise min
```

**Swapping K and KI swaps the branches** — that is the whole content of the
second block, and it turns max into min without touching the predicate.

Predicates compose the way you would expect, because `and` is elementwise:

```mnd
    x y >  c =
    x 15 > big =
    c big and both =                 # (x > y) AND (x > 15)
```

```text
big  : [2x2] = [0, 1, 1, 1]
both : [2x2] = [0, 1, 1, 0]
```

This is not just an encoding curiosity. Branch-free selection is **identical on
the CPU interpreter and on an FPGA or Bark worker**, and every op in it —
comparison, logic, elementwise multiply and add — has a worker opcode, so a
conditional written this way routes. A conditional written with control flow
would not, because there is no control flow to route.

## The lambda you actually write

`calc::lambda_flow` is the named function, and it is the abstraction the
language kept:

```mnd
calc::lambda_flow helper(a, b) {
    a b elemwise_add s =
} return s;

calc::lambda_flow top(x, y) {
    x y helper r =           # operands first, then the name — like any op
} return r;
```

Arity is the callee's parameter count, and definition order does not matter —
the flow table is pre-scanned. Three properties worth knowing:

- **Calls inline at compile time.** The callee's graph is spliced into the caller: zero runtime cost, and identical locally and remotely.
- **A called flow is a helper.** It is not scheduled as a top-level flow, and its `@device` decorator is ignored (lint `W007`). `--flow NAME` still runs one directly.
- **One namespace.** Flows, ops, stack ops and combinators share it, so a parameter or assignment target named like any of them is a redefinition error.

## Recursion, bounded

Top-level flows stay a DAG, and **mutual recursion is always an error**. A
direct self-call is allowed with `@unroll(n)`: bounded macro expansion, exactly
`n` copies, where the innermost self-call passes its arguments through
positionally (`returns[i] = args[i]`). So you put the recursion state in the
returned positions:

```mnd
in::W = [[1,1],[0,1]];    # a shear: W^n has n in the corner
in::h = [[0],[1]];

@unroll(5)
calc::lambda_flow power_step(h, W) {
    W h matmul h2 =
    h2 W power_step out =
} return out;

calc::lambda_flow top(h, W) {
    h W power_step p =
} return p;
```

```text
p : [2x1] = [5, 1]          # @unroll(5)
p : [2x1] = [3, 1]          # the same program at @unroll(3)
```

The unroll count is *visible in the answer*: `W⁵·h` puts a 5 in the first
component, `W³·h` a 3. The compiler warns if a returned position threads a
parameter through unchanged, since that output would just equal its input.

`repeat(n)` is sugar over the same machinery, with `n` a literal in 1..256.
Both forms produce identical results. One rule catches people: **every name a
`repeat` body assigns is loop-carried** and reads the previous iteration, so
there are no body-locals — the escape hatch is that a flow call is a single
statement, so the loop body lives in a helper flow. There is a worked example
on the [linear algebra page](linear-algebra.html#bounded-iteration-and-where-the-loop-body-lives).

Bounded and total, like the rest of the language: no dynamic counts, no
`break`, no early exit.

## What is reserved, and what refuses

Here the documentation has to be careful, because this is an area where the
language once promised more than it delivered and then withdrew it on purpose.

**The anonymous lambda forms are retracted.** Version 1.0.0 of the syntax
specification gave both an arrow form `x => body` and a block form
`lambda x => ... end`. The grammar claimed them; the evaluator never
implemented them, so a program using one *silently degraded*. Rather than leave
a specified-but-dead construct in place, both were retracted and the parser now
refuses them:

```text
parse error [6:7] lambda expressions (x => body / lambda ... end) are
retracted - the evaluator never implemented them; define a
calc::lambda_flow or use the combinator ops (identity/kestrel/kite/compose)
```

`lambda` and `end` stay reserved words. The names are held so the grammar
cannot drift back into claiming them.

**Four birds exist as λ-terms.** `identity`, `kestrel`, `kite` and `compose`
are implemented in the lambda evaluator — but that evaluator is not engaged
from a flow body, and the parser says so rather than pretending:

```text
parse error [5:3] combinator 'kestrel' is not reachable from this context;
it is implemented as a λ-term only
```

```text
parse error [6:7] combinator 'kestrel' in a flow body is not executable yet
(lambda expressions are not accepted inside a flow body). Use the postfix
stack-op spelling instead.
```

That last sentence is the point of this whole page: **the postfix spelling is
the same function.** `x y drop` *is* the kestrel. Nothing is missing from your
program.

**The rest are reserved names with no implementation**: `mockingbird`,
`bluebird`, `starling`, `thrush`, `warbler`, `owl`, `bluebird_prime`,
`blackbird`, `psi`, `phoenix`, `vireo`. They are held by the grammar for a
named-combinator runtime, and using one is a parse error, not a silent
no-op.

**And `ycombinator` cannot simply be implemented.** Under a strict evaluator a
fixpoint combinator diverges — it would need call-by-name or a fuel-bounded
fixpoint first. It is reserved, it refuses, and the internal notes say
plainly: do not file "implement ycombinator" as a small ticket. Bounded
recursion is `@unroll`, and that is a deliberate substitution rather than a
missing feature: a total language cannot hand you an unbounded fixpoint.

| Name | Status |
|---|---|
| `identity`, `kestrel`, `kite`, `compose` | Implemented as λ-terms; not reachable from a flow body. Use the postfix spelling. |
| `mockingbird`, `bluebird`, `starling`, `thrush`, `warbler`, `owl`, `bluebird_prime`, `blackbird`, `psi`, `phoenix`, `vireo` | Reserved, no implementation. Refuses. |
| `ycombinator` | Reserved, and cannot become a term under a strict evaluator. |
| `x => body`, `lambda … end` | Retracted (`E017`). |

## Why the language is shaped this way

The RPN choice was not aesthetic. From the specification's design goals: an
O(n) single-pass parse with no backtracking and no precedence table; a token
stream nearly 1:1 with stack-machine bytecode, which lowers directly to the
dataflow IR a hardware back end consumes; **combinators that compose without
parentheses**; and object parameters resolved to positional arguments at
compile time, so the abstraction costs nothing.

Combinatory logic was Schönfinkel's and Curry's answer to the question of
whether variables are necessary at all. A postfix stack language is the same
answer arrived at from the direction of compilers. Maned is what you get when
the two meet and the values happen to be integer tensors.

## Next

- [Language guide](guides/language.html) — the full grammar, the op table, flows and clocks.
- [Linear algebra](linear-algebra.html) — the matmul idioms that replace the loops this language deliberately does not have.
- [RPN syntax specification](spec/rpn-syntax.html) — normative, including the retraction notices in full.
