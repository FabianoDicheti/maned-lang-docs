#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# maned_md.py - the one definition of "how Maned documentation is read".
#
# Two renderers consume this module: render_pdf.py (ReportLab -> PDF) and
# render_html.py (-> the GitHub Pages site). Everything here is the part that
# MUST NOT DRIFT between them - if the PDF and the site disagree about which
# tokens are keywords, or what counts as a table, the same source file means
# two different things depending on where you read it.
#
# This is the same discipline as maned_lang/scripts/gate_manifest.sh, and it
# exists for the same reason: the lists used to be copy-pasted, and a copy you
# forget to update is a bug you find months later.
#
# Standard library only. `pip` is PEP-668 locked on the build machines and the
# Pages runner installs nothing, so a dependency here is a dependency the site
# cannot have. render_pdf.py's reportlab import is the one exception, and it
# is that script's problem, not this module's.
# ---------------------------------------------------------------------------

from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Brand palette. Raw hex strings, because ReportLab wants colors.HexColor(...)
# and CSS wants the string - neither should own the value.
# ---------------------------------------------------------------------------

PALETTE = {
    "maned": "#A95F2A",       # the brand orange
    "maned_dark": "#633518",   # headings
    "cream": "#FBF6EF",        # quote / alternating row background
    "ink": "#292521",          # body text
    "muted": "#756D66",        # source lines, captions
    "line": "#DFD3C7",         # rules and table grid
    "code_bg": "#28231F",      # code block background
    "link": "#995324",
}

# ---------------------------------------------------------------------------
# The Maned syntax highlighter.
#
# Kept deliberately small and regex-based: this highlights DOCUMENTATION
# snippets, not the real language. The parser in maned_lang/src/parse/ is the
# authority on what Maned is; this only has to make a code block readable.
# ---------------------------------------------------------------------------

CODE_COLORS = {
    "comment": "#8FE388",
    "string": "#FFD166",
    "number": "#FF8FAB",
    "directive": "#C77DFF",
    "keyword": "#55DDE0",
    "builtin": "#FF9F43",
    "operator": "#7AB8FF",
    "plain": "#FFF8EE",
}

CODE_TOKEN = re.compile(
    r"(?P<comment>#[^\n]*)"
    r'|(?P<string>"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')'
    r"|(?P<number>\b(?:0x[0-9A-Fa-f]+|\d+(?:\.\d+)?)\b)"
    r"|(?P<directive>\b(?:mnd|in|device|calc|out|status|profile|receiver"
    r"|memory|port)::|@device\b)"
    r"|(?P<keyword>\b(?:lambda_flow|return|flow|if|else|match|case|let|true"
    r"|false|env)\b)"
    r"|(?P<builtin>\b(?:add|sub|mul|div|relu|scalar_mul|matmul|transpose"
    r"|elemwise_add|elemwise_sub|elemwise_mul|elemwise_div"
    r"|tensor_sum|tensor_mean|tensor_min|tensor_max)\b)"
    r"|(?P<operator>::|->|=>|==|!=|<=|>=|[=@{}()[\],;:+*/.-])"
)

# Fence tags that should get the Maned highlighter. An untagged fence is
# sniffed (see looks_like_maned) because most fences in these docs predate any
# tagging convention.
MANED_FENCE_TAGS = {"mnd", "maned"}

_MANED_SNIFF = re.compile(r"(?m)^\s*(?:mnd|in|out|calc|device|status)::|lambda_flow\b")


def looks_like_maned(source: str) -> bool:
    """True when an untagged fence is clearly a Maned program.

    Conservative on purpose: a shell transcript that merely mentions
    `maned-run` must not be syntax-coloured as if it were source.
    """
    return bool(_MANED_SNIFF.search(source))


# ---------------------------------------------------------------------------
# Titles and identifiers
# ---------------------------------------------------------------------------

def document_title(path: Path) -> str:
    """The document's first H1, or a title-cased filename as a fallback."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("_", " ").title()


def chapter_id(path: Path) -> str:
    """Stable per-document anchor, shared by the PDF bookmarks and the site."""
    return "chapter-" + re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")


_ANCHOR_STRIP = re.compile(r"`|\*\*|\[|\]\([^)]*\)")


def heading_slug(text: str) -> str:
    """GitHub-compatible heading anchor, so links copied from GitHub still work."""
    text = _ANCHOR_STRIP.sub("", text)
    slug = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_]+", "-", slug)


# ---------------------------------------------------------------------------
# The block scanner.
#
# This is the grammar both renderers agree on. It is deliberately the SAME
# subset render_pdf.py has always parsed - ATX headings, paragraphs, fenced
# code, blockquotes, GFM tables, flat lists, horizontal rules - because that
# is the subset the documents are actually written in. Adding a construct here
# means teaching both renderers, which is the point.
#
# Yields tuples, not classes, so the consumers stay trivially readable:
#   ("heading", level:int, text:str)
#   ("para",    text:str)
#   ("code",    lang:str, source:str)
#   ("quote",   text:str)
#   ("table",   rows:list[list[str]])      # rows[0] is the header
#   ("list",    ordered:bool, items:list[str])
#   ("rule",)
# ---------------------------------------------------------------------------

_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(.+)$")
_ORDERED = re.compile(r"^\s*\d+\.")
_RULE = re.compile(r"^\s*---+\s*$")
_TABLE_DELIM = re.compile(r"^\s*\|?[\s:|-]+\|")


# HTML comments are invisible in every markdown renderer, and several of these
# documents open with a machine-readable banner in one. Strip before scanning,
# or the banner renders as a paragraph of literal angle brackets.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def scan_blocks(text: str):
    text = _HTML_COMMENT.sub("", text)
    lines = text.splitlines()
    blocks = []
    paragraph: list[str] = []

    def flush():
        if paragraph:
            blocks.append(("para", " ".join(paragraph)))
            paragraph.clear()

    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):
            flush()
            lang = line[3:].strip().lower()
            body: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1  # closing fence (or EOF - an unclosed fence still emits)
            blocks.append(("code", lang, "\n".join(body)))
            continue

        if not line.strip():
            flush()
            i += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            flush()
            blocks.append(("heading", len(heading.group(1)), heading.group(2)))
            i += 1
            continue

        if line.startswith(">"):
            flush()
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip("> ").rstrip())
                i += 1
            blocks.append(("quote", " ".join(q for q in quote if q)))
            continue

        # A table is a pipe row followed by a delimiter row. Checking the NEXT
        # line is what keeps prose containing a pipe from becoming a table.
        if "|" in line and i + 1 < len(lines) and _TABLE_DELIM.match(lines[i + 1]):
            flush()
            rows = [[c.strip() for c in line.strip().strip("|").split("|")]]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            blocks.append(("table", rows))
            continue

        item = _LIST_ITEM.match(line)
        if item:
            flush()
            ordered = bool(_ORDERED.match(line))
            items = []
            while i < len(lines):
                match = _LIST_ITEM.match(lines[i])
                if not match:
                    break
                items.append(match.group(1))
                i += 1
            blocks.append(("list", ordered, items))
            continue

        if _RULE.match(line):
            flush()
            blocks.append(("rule",))
            i += 1
            continue

        paragraph.append(line.strip())
        i += 1

    flush()
    return blocks
