# Maned RPN Syntax Specification

> **Role:** NORMATIVE specification — on conflict among the documents, this one wins. See docs/README.md ("Which document wins") for the full precedence order. (gap_018)

**Ticket:** lang_001 (RPN Syntax Specification)
**Status:** Normative, with five constructs RETRACTED (see below)
**Version:** 1.1.0
**Last Updated:** 2026-09-17 (gap_041 retraction pass; originally 2026-06-01)
**Owner:** frontend_parser_engineer
**Companion artifacts:** a formal EBNF grammar and the reserved-word list, both maintained alongside the parser. The reserved words are reproduced in §8.

> ### Retracted constructs
>
> Five constructs specified by version 1.0.0 are **retracted**. They are not
> deprecated and not unimplemented-but-planned: the parser refuses them with a
> numbered diagnostic, so a script using one does not run.
>
> | Construct | Diagnostic | Use instead |
> |---|---|---|
> | `calc::lambda_symphony` | `E013` | `calc::lambda_flow` |
> | `calc::lambda_calculator` (+ `channels`, `port::`/`receiver::`/`responser::`) | `E014` | `calc::lambda_flow` |
> | `mnd::backpropagation` | `E015` | — (reserved for a future autodiff phase) |
> | `mnd::device::{fpga\|cpu}` block | `E016` | `device::alias { … }` + `@device(alias)` |
> | Lambda expressions — arrow `x => body` and block `lambda … end`, incl. `ycombinator` | `E017` | `calc::lambda_flow`, or the combinator ops `identity`/`kestrel`/`kite`/`compose` |
>
> Each is struck through below rather than deleted, so a reader holding an old
> script can find the construct and learn what replaced it. See
> [`docs/language/16_DIAGNOSTICS.md`](../language/16_DIAGNOSTICS.md).

---

## 1. Purpose and Scope

This document is the authoritative **prose specification** of the Maned surface
syntax. It pins down the lexical structure, the grammatical constructs, and — most
importantly — the **ambiguity-resolution decisions** that turn the informal design
in the original informal design notes into a precisely parsable language.

A formal EBNF grammar accompanies this prose. Every decision
below is tagged `[A-n]` and cross-referenced from the grammar. Where the informal
spec was silent or contradictory, this document **makes the decision** and records
the rationale, which is exactly the deliverable lang_001 is responsible for.

This ticket defines **syntax only**. Static semantics (type checking, arity
checking, quantization range validation) belong to lang_003/lang_004; the AST
shape belongs to lang_002; the parser implementation to lang_005.

---

## 2. Design Goals (why RPN)

1. **O(n) parse, single pass, no backtracking.** Postfix notation maps directly to
   an operand stack: operands push, operators pop their arity and push a result.
   No precedence table, no recursive-descent expression grammar.
2. **Direct lowering.** The token stream is nearly 1:1 with stack-machine bytecode,
   which in turn maps cleanly to the dataflow IR consumed by maned_board.
3. **Lambda-calculus fit.** Function application is naturally postfix, so combinators
   compose without parentheses.
4. **Zero-overhead abstraction.** Object parameters (`{stride: 1}`) are resolved to
   positional arguments at compile time `[A-7]`.

These goals constrain the grammar: anything that would force multi-pass parsing or
a precedence climb is rejected in favor of an explicit, flat form.

---

## 3. Lexical Structure

The lexer produces a token stream and is itself O(n). Tokens are separated by
whitespace (space, tab) and newlines.

### 3.1 Character set
UTF-8 source. Outside string literals and comments, only ASCII letters, digits,
`_`, and the punctuation listed below are significant.

### 3.2 Token classes
| Class | Examples | Notes |
|-------|----------|-------|
| Identifier | `result`, `matrix_a`, `W_conv1` | `(letter \| "_") (letter \| digit \| "_")*` |
| Number | `5`, `-75.5`, `3.14` | integer or float; leading `-` is part of the literal `[A-10]` |
| String | `"hello"`, `'./file.txt'` | double- or single-quoted; no escapes in v1.0 |
| Namespace sep | `::` | binds tighter than any other token; part of a qualified name |
| Property sep | `.` | as in `eigen_result.eigenvalues`, `tensor.init` |
| Punctuation | `{ } [ ] ( ) : , ; =` | structural |
| ~~Arrow~~ | ~~`=>`~~ | **RETRACTED (E017)** — the lexer still produces the token so the parser can refuse it by name |
| Comparison | `> < == >= <= !=` | recognized as operators |
| Comment | `# ...` | from `#` to end of line, discarded |

### 3.3 Comments
`#` starts a comment that runs to the end of the line. Comments may stand alone or
be inline after a statement. They are discarded by the lexer and never affect
parsing.

### 3.4 Newlines and whitespace `[A-4]`
Whitespace separates tokens and is otherwise insignificant **except** that a
**newline terminates a statement**. A semicolon `;` is an equivalent explicit
terminator. This dual rule reconciles the informal spec, where RPN assignments are
newline-terminated but directives, `return(...)` prints, and function returns end
with `;`. Inside brackets/braces/parens that are still open (`[ { (`), newlines are
**not** terminators — this allows multi-line tensor and object literals.

---

## 4. Ambiguity-Resolution Decisions

These are the normative decisions of lang_001. They are referenced by tag from the
grammar.

### [A-1] Mandatory quantization preamble
Every program **must** begin (after optional blank lines/comments) with a
quantization block: one or more `mnd::quant*` directives. `quantres` is required.
The range must be supplied by **either** `quantmax`+`quantmin`, **or** `quantrange`
(symmetric), **or** the legacy `quant`+`decimal_places` pair. A program with no
quantization preamble is a syntax error. *Rationale:* the compiler cannot assign
bit-widths or quantize literals without it; making it positionally first keeps the
lexer/parser from having to scan ahead.

### [A-2] Directives are infix and `;`-terminated
Directives (`mnd::key = value;`) are the **only** infix `=` construct. They are
distinguished from RPN assignment by the `mnd::`/`calc::` namespace prefix and the
trailing `;`. *Rationale:* directives are compile-time configuration, not stack
values; keeping them syntactically distinct avoids confusing them with assignment.

### [A-3] Two forms of `return`
- **Print form:** `return( <expr> );` — a statement that emits/logs a value. The
  parenthesis immediately follows `return` with no space.
- **Function-return form:** `return <name_list> ;` — the trailing clause of a
  `lambda_flow` (and, before its retraction, `lambda_symphony`), with a space
  before the name(s).

The lexer disambiguates purely on the token after `return`: `(` ⇒ print form,
otherwise ⇒ function-return form. *Rationale:* matches the informal spec's
convention and needs only one token of lookahead.

### [A-4] Statement termination
See §3.4. A statement ends at the first newline or `;` encountered at bracket depth
zero.

### [A-5] Assignment target identification
An assignment is `<rpn_sequence> <name_list> [type_annotation] "="`. Because the
value sequence may itself end in identifiers, the parser identifies the **target**
as follows: scanning left from the `=` (and skipping an optional `type_annotation`),
the **maximal trailing comma-list of bare identifiers** that are *not* reserved
words and are *not* consumed as operands of a preceding operator is the target.
In practice, after the stack machine reduces the value expression to a single
result (or a tuple), exactly the names left un-reduced immediately before `=` are
the targets. *Rationale:* this is the rule the reference parser in
the original informal notes' "Parser" section already described (pop name(s), then the value is
whatever remains on the stack).

### [A-6] No operator precedence
RPN has no precedence and no associativity. The grammar therefore contains no
expression-precedence rules. Evaluation order is exactly left-to-right token order.
*Rationale:* this is the central reason for choosing RPN.

### [A-7] Object parameters resolve at compile time
`{ key: value, ... }` is sugar for positional arguments to the operator that
immediately follows it on the stack. Field order in the source is irrelevant; the
compiler maps fields to the callee's positional signature. Object parameters carry
**zero** runtime cost. *Rationale:* readability at the source level, no overhead at
runtime.

### [A-8] Lambda forms — ~~RETRACTED (E017)~~
> **Retracted.** Version 1.0.0 specified two anonymous-function forms: the arrow
> form `x => body` and the block form `lambda x => ... end` (for Church encodings
> and `ycombinator` recursion), both operands pushing a function value.
>
> The grammar claimed them; the evaluator never implemented them, so a statement
> using one silently degraded. Rather than leave a specified-but-dead construct,
> lang_058/gap_002 retracted both: the parser now refuses them with **E017**.
>
> Use a named `calc::lambda_flow`, or the four implemented combinator ops —
> `identity`, `kestrel`, `kite`, `compose`.

### [A-9] Operators vs. operands are decided by the reserved-words table
A bare identifier is an **operator/combinator/stack-op** iff it appears in
the reserved-word list (§8); otherwise it is an **operand** (a variable
reference). Arity for reduction comes from the operator's signature (defined in
lang_004), not from the grammar. *Rationale:* keeps the grammar fixed while letting
the primitive set grow through data, not grammar edits.

### [A-10] Negative numbers are literals, not `sub`
A `-` immediately prefixing a digit with no intervening space (`-75.5`) is the sign
of a numeric literal. Subtraction is the reserved word `sub`, never the `-`
character. *Rationale:* removes the classic `a - b` vs `a -b` ambiguity; consistent
with the all-named-operators rule.

---

## 5. Grammatical Constructs (overview)

The normative form is the EBNF. This section is an orientation.

- **Program** = quantization block, then any mix of directives, definitions, and
  top-level statements.
- **Definitions** = `calc::lambda_flow` — a parameter list, a brace block, and a
  function-return clause. (`calc::lambda_symphony` and `calc::lambda_calculator`,
  the latter with `channels=N` and `port::N`/`receiver::`/`responser::` channels,
  are **retracted**: E013 and E014.)
- **Blocks** may be partitioned into `@clock(n):` sections. All statements in one
  clock level are semantically parallel; level `n+1` waits for level `n`. The
  grammar treats a clock section as a labeled group of statements; the parallel
  semantics are attached later (lang_002/lang_014).
- **Statements** = assignment, print, `memory::write`. (The
  `mnd::device::{fpga|cpu}` block and `mnd::backpropagation` are **retracted**:
  E016 and E015. Route work with a `device::alias { … }` declaration and
  `@device(alias)` on a flow or statement.)
- **RPN expression** = a flat sequence of operands, operators, stack ops,
  combinators and object-params. (Lambdas were part of this list until E017.)
- **Operands** = literals (number, string, tensor literal), qualified refs
  (`port::0`), indexed refs (`A[0][1]`, `x[0:32]`), property refs
  (`r.eigenvalues`), and plain identifiers.

---

## 6. Worked Examples (with parse notes)

### 6.1 Minimal assignment
```maned
mnd::quantmax=100;
mnd::quantmin=-100;
mnd::quantres=2;

5 3 add result =
```
Tokens after the preamble: `5 3 add result =`. Stack trace: push 5, push 3, `add`
pops 2 pushes 8, push name `result`, `=` stores. Target by `[A-5]` = `result`.

### 6.2 Object parameters and chaining
```maned
image filter {stride: 1, padding: 0} conv2d conv2d_result oc::tensor =
```
`{stride:1, padding:0}` `[A-7]` resolves to positional `1 0`; `conv2d` consumes
`image filter 1 0`; result bound to `conv2d_result` with type `oc::tensor`.

### 6.3 Tuple result
```maned
matrix_a svd svd_result os::dictionary =
updated_params, loss =
```
`[A-5]` allows a comma name-list as target (`updated_params, loss`).

### 6.4 Clock-parallel block
```maned
calc::lambda_flow f(a, b, c, d) {
    @clock(1):
        a b add r1 =
        c d mul r2 =
    @clock(2):
        r1 r2 add result =
} return result;
```
Two clock sections; `return result;` is the function-return clause `[A-3]`.

### 6.5 Combinator + recursion — ~~RETRACTED (E017)~~
> **Retracted.** Version 1.0.0 gave this example:
>
> ```maned
> lambda f => lambda n => 1 n 1 sub f mul n mul n 0 == end end ycombinator fact =
> ```
>
> Block lambdas `[A-8]` delimited the bodies and `ycombinator` produced the
> fixpoint. Neither the block lambda nor `ycombinator` was ever implemented; both
> now refuse (E017). Bounded recursion is expressed with a `calc::lambda_flow`
> plus `@unroll`, which the inliner expands — see
> [`docs/language/12_MANED_LANGUAGE_GUIDE.md`](../language/12_MANED_LANGUAGE_GUIDE.md).

---

## 7. Comparison with Prior RPN Languages

| Aspect | Forth | PostScript | **Maned** |
|--------|-------|------------|-------------|
| Core model | Threaded stack machine | Stack + graphics state | Stack + lambda calculus |
| Definitions | `: word ... ;` | `/name { ... } def` | `calc::lambda_flow name(...) {...} return ...;` |
| Naming | Dictionary words | Name/exec arrays | Reserved-word table `[A-9]` |
| Numbers | Cell-typed | Real/integer | Compile-time quantized integers |
| Parallelism | None (cooperative) | None | Explicit `@clock(n)` levels |
| Comments | `( ... )` / `\` | `% ...` | `# ...` |
| Assignment | `value name !` (store) | `/n value def` | `value name [type] =` |

Maned keeps Forth's parse-time simplicity and PostScript's deferred-execution
flavor for lambdas, but adds (a) a typed, namespaced naming scheme, (b)
compile-time quantization, and (c) first-class clock-level parallelism — none of
which exist in the classic languages.

---

## 8. Reserved Words

The canonical list is loaded by the lexer and grouped into: namespaces,
directives, definitions, keywords, types, stack ops, arithmetic, comparison,
logic, combinators, and primitives. Using any reserved word as an assignment
target or parameter name is a compile error `[A-9]`. The primitive set is
**extensible**: adding one needs a new entry plus a semantics spec, not a
grammar change.

---

## 9. Acceptance Mapping (lang_001)

| Acceptance criterion | Where satisfied |
|----------------------|-----------------|
| Complete BNF/EBNF grammar | the companion EBNF artifact |
| Reserved keywords | §8 |
| Operator/precedence rules | §4 `[A-6]` (none, by design) |
| Tensor literal syntax | EBNF §8; this doc §5 |
| Function/lambda syntax | EBNF §3/§7; `[A-8]` |
| Type-annotation syntax | EBNF §4; this doc §5 |
| Decorator/object-param syntax | EBNF §6; `[A-7]` |
| Comments & whitespace rules | §3.3, §3.4 `[A-4]` |
| Ambiguity-resolution rules | §4 `[A-1]..[A-10]` |
| Comparison with existing RPN languages | §7 |
| Rationale for design decisions | §2 and each `[A-n]` |

---

## 10. Open Items Handed to Downstream Tickets

- **lang_002 (AST):** node shapes for clock sections, tuple results, lambdas.
- **lang_003 (types):** semantics of `oc`/`ot`/`os` namespaces and tensor types.
- **lang_004 (primitives):** arity and signature table backing `[A-9]`.
- **lang_005 (parser):** implement the stack parser and the `[A-5]` target rule;
  golden test corpus from §6 and from the original informal notes' examples.
- **lang_006 (decorators):** if decorator syntax diverges from object params,
  extend §6/`[A-7]`.

---

*This specification unblocks lang_002 through lang_010. Changes after review are
tracked via child tickets per DEVELOPMENT_RULES Rule 2.4.*

---

## 11. Calls & Helpers (lang_051, decided 2026-09-02)

A flow may call another flow exactly like a primitive op: operands first, then
the flow's name. Arity is the callee's declared param count, known before any
body is parsed (the lang_048 two-pass flow table), so definition order does not
matter.

```maned
calc::lambda_flow scale_sum(a, b) {
    a b elemwise_add s =
    s 2 scalar_mul r =
} return r;

calc::lambda_flow top(x, y) {
    x y scale_sum out =        # a call: pops x and y, pushes scale_sum's r
} return out;
```

### Call semantics: compile-time inlining
A call is expanded at compile time (lang_052): the callee's dataflow graph is
spliced into the caller — params replaced by the argument expressions, returns
mapped positionally onto the caller's stack, intermediate names α-renamed
(`callee$3$tmp`) to avoid capture. Calls therefore cost **nothing at run time**
and work identically local and remote; inlining runs before the local/remote
split, so `--verify` parity is structural. Host-mediated (RPC) calls and
worker-side CALL/RET frames are deferred backlog (plan Phases 4/5).

### Placement: `@device` on a called flow is ignored
A called flow is inlined, so its `@device` decorator has no effect and lint
reports W007. `@device` is honored only on flows scheduled top-level.

### Helper visibility
**A flow that is called anywhere is not scheduled top-level.** There is no
`@helper` keyword; being called is what makes a flow a helper. Its params are
bound at the call sites, so they need no in::/--in/flow-output filling.
"Called and also top-level" is unsupported in v1; `--flow NAME` still selects
a helper directly for testing. An `@schedule` escape hatch may be added if a
real program needs both. (Lint W008, which flagged unfillable helper params
in the window between lang_050 and lang_052, is retired.)

### Recursion
The top-level flow graph stays DAG-only (the dispatcher's circular-dependency
error). Mutual recursion is always a compile error (lang_049 call-graph SCC).
A **direct self-call** is legal only under `@unroll(n)` (lang_054): **bounded
macro expansion**, exactly `n` copies of the body execute. There is no branch
opcode, hence no runtime base case; instead the `n`-th self-call is the
**positional pass-through** of its arguments — `returns[i]` takes `args[i]`
of the innermost call, the only base case expressible without branches (and
what makes `f(h){ ...; h' f out = }` expand into the stress generator's
n-block chain). Consequences: the recursion state must ride in the returned
argument positions (the compiler warns when a returned position threads a
param through unchanged — that output would provably equal the initial
input), and a self-call whose returns cannot map onto its arguments is
refused ("recursion in 'f' exceeds @unroll(n)"). Base-case-dependent
recursion stays a Phase 5 item.

### Strictness
Ops are eager. Laziness lives at exactly one level: the flow DAG — a flow runs
when its inputs are ready, and that dependency graph is the futures system.

### Namespaces: one namespace, shadowing is an error
Flows, primitive ops, stack ops, combinators, params, and value names share a
single namespace. A flow named like a primitive, a param or assignment target
named like a flow, or any name matching a reserved word is a **redefinition
error** — never a silent shadow (a shadowed flow name would otherwise turn
value references into calls, since operator lookup wins). There are no
precedence rules to remember.

### Post-inline limits
The inlined graph must respect the worker contract, enforced with refusal
messages by lang_053: ≤ 255 live value ids (RF_SLOTS), ≤ 16 tensors per job
(MNPK_MAX_TENSORS), payload ≤ the worker-advertised maximum, and the arena
bound estimate.

## 12. File I/O (lang_061-064, decided 2026-09-03)

### Where I/O runs
All file I/O is **coordinator-side** (FILE_IO_PLAN.md D1). Workers are
bare-metal and never see a file: a file-sourced `in::` is read on the host
and becomes an ordinary input tensor before any dispatch, and `out::` writes
happen on the host after flows complete. Local runs, `--device`, and script
dispatch therefore behave identically, and no protocol or worker change was
needed.

### Syntax
Per-format keywords, in directive position only:

```
in::x  = csv("data/train.csv");     # numeric CSV  -> [rows, cols]
in::t  = text("notes.txt");         # UTF-8 bytes  -> [N]
in::im = image("photo.png");        # 8-bit image  -> [H,W] or [H,W,C]
in::p  = parquet("table.parquet");  # numeric cols -> [rows, cols]

out::result = csv("results.csv");   # decoded through the quant directives
out::mask   = image("mask.png");    # clamped 0..255; .png/.bmp/.jpg
out::bytes  = text("log.txt");      # rank-1, clamped 0..255
```

`csv`, `text`, `image`, `parquet` are **contextual keywords** — special only
in this position, never reserved (`image` is a live operand name in the
conv2d idiom; `text` was already a type name). `--in name=...` still
overrides a file-sourced `in::`. `parquet` is read-only; `out::name =
parquet(...)` is a targeted parse error.

### The quantization boundary
CSV and Parquet numbers cross the FP<->INT boundary through the program's
`mnd::` quant directives exactly like literals: `encode(x) =
round(x * 10^quantres)` clamped to the range, with a counting note when
anything clamps. `quantres=0` means integer datasets round-trip untouched;
`out::x = csv(...)` decodes back, so csv-out then csv-in is the identity.
`text` and `image` are raw bytes 0..255 in both directions and are **never**
quantres-scaled; byte writes clamp with a counting note (D5).

### Name binding and failure
An `out::name` must name a flow return or an `in::` input (writing an input
back out makes format conversion a one-flow script); an unknown name is a
parse error with a nearest-name suggestion, and a name whose flow was
excluded at runtime (--flow, helper) is "was not produced". A missing or
corrupt input file fails before anything executes; write failures are all
attempted, then reported together with a non-zero exit (D8). Lint W009 warns
when two out:: directives write the same path. CSV reads auto-skip a
non-numeric FIRST row as a header (with a note); any other non-numeric cell
is an error naming line and column.

### Format subsets (the refusal message is the contract)
Images: vendored stb_image (`third_party/stb`, the repo's only vendored
code, D9) — 8-bit PNG/JPEG/BMP read, PNG/BMP/JPG write; 16-bit refuses by
name. Parquet: hand-written reader — Thrift compact footer, v1 data pages,
PLAIN + dictionary encodings, UNCOMPRESSED + SNAPPY codecs, flat numeric
columns (BOOLEAN/INT32/INT64/FLOAT/DOUBLE); string columns are skipped with
a note; nulls, nested schemas, and every other codec/encoding/page version
refuse with the feature's own name.

### Serving the same contract over HTTP (lang_066-068)
`maned-serve script.mnd --port 8080` serves one script as an HTTP API
with NO new syntax: the `in::`/`out::` directives above ARE the request/
response schema. `POST /run` takes multipart/form-data (part name = `in::`
name, bytes decoded by the declared format) and answers with the `out::`
values; `POST /run.json` speaks JSON tensors through the same quant
boundary; `GET /health` reports the contract. In serve mode `out::` values
go to the client, not to disk (an image `out::`'s path contributes only its
extension). A script must declare at least one `out::` to be servable, and
serving requires nothing of workers - the engine underneath is exactly
maned-run's. See [`docs/language/SERVE_PLAN.md`](../language/SERVE_PLAN.md) for the decision table.

Two companions make an upload API expressible (lang_070-072). `in::x =
fmt();` with EMPTY parens declares a wire format with no default: the value
always arrives with the request, so no placeholder file is invented on the
server. And `profile::name;` puts the matrix DESCRIPTOR in the response
instead of the values - the same canonical document `maned-run
--profile-json` prints - so a script can answer "what is this matrix"
rather than returning it. Profiles travel as one JSON document on both wire
formats; a rank-3 value profiles per leading-dimension plane. A script is
servable when it declares out::, profile::, or both.

The `slice` op (lang_070) is the inverse of `concat`: `x { axis: 2,
index: 0 } slice red =` takes one index off an axis and DROPS that axis
(rank R -> R-1), which is how a channel-last image [H,W,C] becomes the
plain [H,W] matrices every matrix op and profile:: expect. It is
single-result by design - the registry's `split` declares two results, but
multi-result binding exists nowhere in the parser, dataflow or interpreter,
so split remains deferred.


## 13. Dataframes (lang_074-078, decided 2026-09-04)

`frame::name = jsonl("path");` builds a coordinator-side TABLE from JSON
documents of differing shapes; `jsonl()` takes them from the request under
maned-serve, and `profiles()` tabulates the descriptors the run produced.
See documentation/DATAFRAME_PLAN.md for the decision table.

### The union rule
The column set is the union of every document's leaf paths, in first-seen
order. A document lacking a column contributes an ABSENT cell, tracked in a
validity bitmap (1 bit per cell) rather than filled with a value. Objects
flatten to dotted paths, arrays to index-suffixed ones, and the column set
widens to the longest array seen.

### Projections and the mask
`f.values` [rows,cols], `f.present` [rows,cols] of 0/1, `f.shape` [2] and
`f.missing` [cols] are ordinary input tensors from the moment they are
bound; nothing downstream knows the data came from a table. `values` holds 0
where a cell is absent and that 0 is MEANINGLESS without `present` -
integer tensors have no NaN and every sentinel collides with real data.
Column names and string dictionaries are text, so they live in the frame's
schema JSON, not in a projection.

### Types
bool -> 0/1, string -> dictionary code (one interned copy per distinct
string, code 0 reserved for ""), double -> the program's quant boundary,
exactly like csv/parquet. Widening is Bool -> Int -> Double; a column mixing
string and numeric values refuses by name with the document index.

### Streaming
Documents are split from a chunked reader (JSONL lines, or a top-level array
by bracket depth) and scanned into leaf events with no tree and no per-leaf
allocation, so peak memory is one document plus one chunk whatever the input
size. A `profiles()` frame is built AFTER the flows run, so it can be
reported but never fed back into the same run.

## 14. Serving and binding resolution (normative)

Added 2026-09-15 (gap_001/gap_017). Applies to `maned-serve` and to every
tool that resolves a named binding.

1. **Binding resolution is last-wins, everywhere.** Wherever a list of
   name/value bindings can hold the same name more than once (script
   defaults followed by request overrides; repeated `--in`; repeated
   `in::`), the LAST binding of the name is the value of the name. No
   component may resolve first-match.
2. **Outputs shadow inputs (D7).** A produced flow output with the same
   name as an input wins over the input for `out::`, `profile::` and
   frame views. Rule 1 applies within each class.
3. **Wire formats.** The serve surface (`/run` multipart, `/run.json`,
   `/frame` views) carries the same MNPK-quantized integer values as the
   CLI; JSON numbers cross the quant boundary exactly like csv.
4. **Format-only inputs.** `in::name = fmt();` (empty parens, lang_072)
   declares the wire FORMAT with no default: maned-run then requires
   `--in name=...`, and maned-serve requires the request to carry it.
5. **Source-mode capability (gap_011).** Every `in::`/`frame::` source
   kind declares the execution modes that can load it; a mode that cannot
   REFUSES with E018 naming the supported modes. `profiles()` is
   serve-only today.

## 15. Supervised learning: `calc::ml::` (ML_PLAN, decided 2026-09-20)

A `calc::ml::<algorithm>` definition is a `top_level_item` parallel to
`lambda_flow`. Its trailing brace holds **hyperparameters** — `key: value`
object fields, never RPN statements — which is what syntactically
distinguishes it from a flow body. The algorithm set is closed (E021):
`linear_regression`, `logistic_regression`, `svm`, `kmeans`, `knn`,
`naive_bayes`, `decision_tree`, `isolation_forest`, `pca` (reserved,
refuses — no eigensolver exists yet), `xgboost` and `hmm`
(ML_PLAN_XGB_HMM, 2026-09-20 — both desugar to wire-legal primitives:
gradient-boosted trees as histogram matmuls, Baum-Welch as batched
forward-backward matmuls; `xgboost` takes `(X, y)`, `hmm` takes the
single `[sequences, steps]` observation matrix `O`).

```maned
mnd::quantmax=100;
mnd::quantmin=-100;
mnd::quantres=2;

in::X = csv("train_x.csv");
in::y = csv("train_y.csv");

calc::ml::linear_regression fit(X, y) {
    iters: 200,
    lr: 5,
    features: 2,
    fit_intercept: true,
    standardize: true
} return model, loss;

out::model = model("house.mnm");
```

Decisions:

1. **Hyperparameter values are scaled integers, `true`/`false`, or a flat
   `[v, v, ...]` sweep list.** Floats are refused (E022): every number in
   the language is a scaled integer, and a silently truncated `0.05` is
   the exact failure the quantization review documented. A sweep list
   fans one configuration per value across the `@device(a, b, c)`
   aliases (`i mod N`), and the return clause names one output set per
   configuration.
2. **The construct never reaches IR lowering.** It desugars — before
   inlining and flow segmentation — into ordinary flows: a local init
   flow, gradient-descent round flows chained through `#`/`$` wire names
   (the segment_flows convention), and a local epilogue that keeps the
   declared name and return list. The gradient-descent family emits only
   wire-legal ops, so `@device` routing and `--verify` apply unchanged;
   the other algorithms train through the coordinator-only `ml_fit` op
   and refuse `@device` honestly.
3. **`features: <d>` is required for the gradient-descent family.**
   Input shapes are dynamic at compile time (csv arrives at run time);
   β₀, the divisor tensors and the int32-overflow refusal all need the
   feature count at desugar time.
4. **A fitted model is one rank-1 integer descriptor vector** (magic
   `0x4D4E444D`, version, algo_id, quantres, feature count, flags,
   payload), persisted by the fifth file format `model("path.mnm")` — a
   length-prefixed little-endian int64 dump plus an FNV-1a checksum,
   deliberately not the MNPK envelope and never quantizer-encoded.
   `model` is a CONTEXTUAL word like `csv`: it stays a legal value name,
   which the construct's own `return model, loss;` depends on.
5. **Inference is the `ml_predict` primitive** (model, X → predictions),
   coordinator-only by design; it applies the model's recorded
   standardization and refuses a `quantres` mismatch rather than
   decoding garbage.
