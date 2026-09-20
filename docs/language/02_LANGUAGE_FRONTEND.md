# Language Frontend

The frontend turns `.mnd` text into an owned AST, validates syntax-specific
constraints, infers basic shapes/types, and reports static diagnostics.

## Language definition

| File | Purpose | Interactions |
|---|---|---|
| `grammar/maned.ebnf` | Human-readable syntax contract. | Implemented by lexer/parser; mirrored partially by editor syntax. |
| `grammar/reserved_words.txt` | Reserved vocabulary list. | Guides lexer/parser and syntax-highlighting changes. |

The EBNF is descriptive rather than generated code: changing it does not alter the
parser. Grammar and parser changes must therefore be made and tested together.

## AST, types, and operations

| File | Responsibility | Dependencies and consumers |
|---|---|---|
| `include/maned/ast/ast.h` | Source ranges, node kinds, expressions, statements, flows, devices, directives, programs, and visitor API. | Used by parser, linter, dataflow, and dispatch. |
| `src/ast/ast.cpp` | AST visitor dispatch and non-inline behavior. | Implements the AST public interface. |
| `include/maned/types/type.h` | Dtypes, quantization parameters, shapes, semantic types, inference results, broadcasting, and matmul/elementwise inference. | Used by operation metadata, literal-shape analysis, quantization, and runtime. |
| `src/types/type.cpp` | Type/shape inference and dtype utilities. | Implements `type.h`; validated by type and verification tests. |
| `include/maned/ops/op_signature.h` | Operation categories, hardware targets, signatures, shape callbacks, and `OpRegistry`. | Depends on types; queried by parser and other semantic layers. |
| `src/ops/op_registry.cpp` | Built-in operation definitions and registry lookup. | Supplies operation arity/category/shape behavior to parsing. |

AST nodes own children with smart pointers. Source ranges originate in tokens and
must remain accurate because parser and linter diagnostics report them.

## Lexer, parser, decorators, and shapes

| File | Responsibility | Dependencies and consumers |
|---|---|---|
| `include/maned/parse/lexer.h` | Token kinds, token/error records, and stateful `Lexer`. | Uses AST source locations; feeds `Parser`. |
| `src/parse/lexer.cpp` | Whitespace/comment handling and tokenization. | Produces the token stream used by all frontend clients. |
| `include/maned/parse/parser.h` | `ParseError` and recursive parser interface. | Owns a lexer and returns `ast::Program`. |
| `src/parse/parser.cpp` | Grammar implementation and AST construction. | Consults operation, decorator, and literal-shape helpers. |
| `include/maned/parse/decorator.h` | Decorator targets/kinds, schemas, and registry API. | Used while parsing decorated language constructs. |
| `src/parse/decorator.cpp` | Built-in decorator schemas and validation. | Converts recognized decorator forms into AST metadata. |
| `include/maned/parse/literal_shape.h` | Rectangularity checks and tensor-literal shape inference. | Bridges AST literals to semantic `Shape`. |
| `src/parse/literal_shape.cpp` | Recursive literal-shape implementation. | Called from parser/type-related validation. |

Data flows left-to-right: source text → lexer tokens/errors → parser AST/errors.
The parser additionally asks the operation registry about recognized operations,
the decorator registry about legal annotations, and the shape helper about tensor
literals.

## Linter

| File | Responsibility | Dependencies and consumers |
|---|---|---|
| `include/maned/lint/linter.h` | Diagnostic severity, source position, message, and `lint(program)`. | Takes a parsed AST; exposed to the lint CLI and tests. |
| `src/lint/linter.cpp` | AST traversal and static checks. | Produces warnings/errors without executing the program. |

The linter is deliberately downstream of successful parsing. Lexical and parse
failures are reported by the CLI before AST lint checks run.

## Extension checklist

For new syntax, update the grammar, token model if necessary, parser/AST model,
visitor dispatch, and parser tests. If the construct affects execution, also update
dataflow/interpreter or MLIR paths. If it should be diagnosed statically, add a
linter rule and CLI fixture. Finally, keep the TextMate grammar synchronized.
