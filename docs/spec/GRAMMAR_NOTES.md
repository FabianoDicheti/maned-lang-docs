# grammar/

> **Role:** descriptive of the parser as built (the EBNF is regenerated from it), not normative. See docs/README.md ("Which document wins"). (gap_018)

Formal grammar artifacts for the Maned language. Produced by ticket **lang_001
(RPN Syntax Specification)**.

| File | Purpose | Consumed by |
|------|---------|-------------|
| `maned.ebnf` | Normative EBNF grammar (ISO/IEC 14977) of the surface syntax. Single source of truth for parsing. | lang_002 (AST), lang_005 (parser) |
| `reserved_words.txt` | Canonical, machine-readable list of reserved identifiers, grouped by section. | lang_005 (lexer/parser) |

The prose specification — lexical rules, worked examples, and the
ambiguity-resolution decisions `[A-1]..[A-10]` referenced from `maned.ebnf` —
lives in [`RPN_SYNTAX_SPECIFICATION.md`](RPN_SYNTAX_SPECIFICATION.md).

## Conventions

- The grammar is designed for a **single-pass, O(n), stack-based** parser with no
  backtracking and no operator-precedence table (RPN has no precedence).
- The primitive-operation set is **extensible via data**: append to the
  `[primitives]` section of `reserved_words.txt` and add the matching semantics in
  lang_004. The grammar itself does not change.
- These are specification/source artifacts: **no emojis** (DEVELOPMENT_RULES 1.1).

## Versioning

The grammar is versioned with the language. v1.0.0 corresponds to the lang_001
deliverable. Breaking grammar changes follow the integration-contract SemVer rules
and require a child ticket.
