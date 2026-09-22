#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# render_html.py - build the Maned documentation site.
#
#   python3 docs/site/render_html.py --out _site
#
# Standard library only; the Pages runner installs nothing. The markdown
# grammar and the syntax highlighter come from maned_md.py, shared with
# render_pdf.py so the site and the PDF cannot disagree.
#
# THE ALLOWLIST IS A PRIVACY BOUNDARY. The workspace docs/ tree holds session
# handoffs, superseded gap analyses with internal ticket numbers, and lab
# worker IPs. PAGES is the complete list of what may be published; a file not
# named there is not built, not copied, and not linkable. Adding a page is a
# deliberate edit here, never a glob.
#
# Two link failure modes, deliberately distinguished:
#   * a link to a file that does not exist        -> FATAL, the build stops
#   * a link to a real doc that is not published  -> rendered as plain text
# The second keeps the source documents honest for local readers (00_README
# legitimately indexes the *_PLAN.md design notes) without either leaking them
# or shipping a dead link.
# ---------------------------------------------------------------------------

from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from maned_md import (  # noqa: E402
    CODE_COLORS,
    CODE_TOKEN,
    MANED_FENCE_TAGS,
    document_title,
    heading_slug,
    looks_like_maned,
    scan_blocks,
)

SITE_DIR = Path(__file__).resolve().parent
DOCS_DIR = SITE_DIR.parent
SITE_TITLE = "Maned"
SITE_TAGLINE = "An integer-only dataflow language for linear algebra and small ML workloads"
# Absolute base for og: tags, which crawlers cannot resolve relatively.
SITE_URL = "https://maned-lang.com"

# ---------------------------------------------------------------------------
# The published set, in navigation order.
#
#   (section, source path relative to docs/, output path, nav label)
#
# A section with no pages is not rendered at all - no empty heading, no dead
# nav entry. That is what keeps the Examples slot below inert until the pages
# behind it exist.
# ---------------------------------------------------------------------------

PAGES = [
    # AUDIENCE: people writing Maned programs. Not contributors - the compiler
    # source is not published, so a page that says "see src/net/dispatch.cpp"
    # sends the reader somewhere they cannot go. The workspace's 01-11
    # reference chapters, the compiler-development guide, the build-from-source
    # guide and the project scorecards are all maintenance documentation and
    # are deliberately absent; site/under-the-hood.md covers the same machinery
    # from the outside, in terms of what it costs and buys the reader.
    ("", "site/home.md", "index.html", "Home"),

    ("Getting started", "site/install.md", "install.html", "Install"),
    ("Getting started", "language/12_MANED_LANGUAGE_GUIDE.md",
     "guides/language.html", "Language guide"),
    # Written FOR the site: the workspace has the op TABLE (language guide §6)
    # and a corpus of example scripts, but nothing that teaches the integer
    # linear algebra itself - the scale arithmetic, the exact solvers, and the
    # matmul idioms that stand in for the loops the language does not have.
    ("Getting started", "site/linear-algebra.md",
     "linear-algebra.html", "Linear algebra"),
    # synth / profile:: / profile_vector - the two-directional half of the
    # algebraic story (properties -> matrix -> algebra -> matrix -> properties).
    # Its own page rather than a section of linear-algebra.md: the vocabulary
    # table alone is longer than most sections, and this is the feature with no
    # equivalent in the array languages a reader is arriving from.
    ("Getting started", "site/properties.md",
     "properties.html", "Properties and profiles"),
    # lang_084-092: importing float weight files into the integer language.
    # Written FOR the site: the workspace has the review/plan documents and
    # the op-table row, but nothing that teaches a user the width choice, the
    # per-block format, or the pack_rows story. Every code block and output
    # on the page was produced by a real run.
    ("Getting started", "site/packed-weights.md",
     "packed-weights.html", "Packed weights"),
    ("Getting started", "site/under-the-hood.md",
     "under-the-hood.html", "How Maned runs your program"),
    # Written FOR the site from maned-bark/docs/operations/OPERATOR_GUIDE.md,
    # which is an internal field document: it carries ticket numbers, file:line
    # citations, lab machine names and the `make usb` build. This page keeps the
    # facts and drops all of that - it starts from a reader who was handed a
    # .img and has never seen the repo.
    ("Getting started", "site/bark-machines.md",
     "bark-machines.html", "Set up a Bark machine"),

    # The ML pages are written FOR the site (site/*.md) rather than lifted
    # from the workspace chapters: the workspace's calc::ml:: reference lives
    # inside 12_MANED_LANGUAGE_GUIDE.md section 9.4 and is written for someone
    # who already knows the language. These teach it, and every code block and
    # output in them is copied from a tutorial script in mnd_scripts/tutorials/
    # that was run to produce it.
    ("Machine learning", "site/machine-learning.md",
     "guides/machine-learning.html", "The calc::ml:: algorithms"),
    ("Machine learning", "site/ml-parallel.md",
     "guides/ml-parallel.html", "Training across Bark devices"),

    ("Going further", "language/15_REMOTE_WORKER_GUIDE.md",
     "guides/remote-workers.html", "Remote workers"),
    # The combinator/lambda story. Section 11 of the language guide is a
    # status TABLE (what is implemented, reserved, retracted); this page is
    # the part a reader needs first - that the stack operators ARE the birds,
    # so nothing is missing from a program that never names one.
    ("Going further", "site/lambda-calculus.md",
     "guides/lambda-calculus.html", "Lambda calculus and the birds"),

    ("Going further", "language/16_DIAGNOSTICS.md",
     "guides/diagnostics.html", "Diagnostics reference"),

    ("Specification", "spec/RPN_SYNTAX_SPECIFICATION.md",
     "spec/rpn-syntax.html", "RPN syntax (normative)"),

    # ── Examples ────────────────────────────────────────────────────────────
    # Reserved slot, owned by a separate work stream. It is generated from the
    # headers of mnd_scripts/examples/*.mnd plus their captured output. To
    # light it up, append rows here in the form:
    #
    #   ("Examples", "site/generated/examples/<name>.md",
    #    "examples/<name>.html", "<label>"),
    #
    # Nothing else in this file needs to change: an empty section is skipped,
    # and a populated one renders like any other.
]

# Docs that exist in the workspace but are deliberately NOT published. Linking
# to one is not an error - the link is flattened to plain text. Anything not in
# this set and not in PAGES is a genuine broken link and fails the build.
UNPUBLISHED = {
    # Maintenance and project documentation - see the note on PAGES.
    "README.md",
    "language/00_README.md",
    "language/01_PROJECT_STRUCTURE.md",
    "language/02_LANGUAGE_FRONTEND.md",
    "language/03_IR_AND_PROTOCOLS.md",
    "language/04_INTERPRETER_AND_QUANTIZATION.md",
    "language/05_MLIR_COMPILER.md",
    "language/06_NETWORK_AND_DISPATCH.md",
    "language/07_CLI_AND_SCRIPTS.md",
    "language/08_BUILD_AND_ARTIFACTS.md",
    "language/09_TESTING.md",
    "language/10_BENCHMARKS_AND_EXAMPLES.md",
    "language/11_EDITOR_INTEGRATION.md",
    "language/13_MANED_USAGE_GUIDE.md",
    "language/14_MANED_COMPILER_DEVELOPMENT_GUIDE.md",
    "language/17_OBJECTIVES.md",
    "spec/GRAMMAR_NOTES.md",
    "contracts/INTEGRATION_CONTRACT.md",

    # Directories the docs index but the site does not carry. These are
    # listed BY NAME rather than detected on disk on purpose: the mirror does
    # not contain them at all, so a filesystem check would resolve one way in
    # the workspace and another in CI - and CI's answer is the one that ships.
    "capability",
    "history",
    "scripts",

    "language/AULA_MANED.md",
    "language/DATAFRAME_PLAN.md",
    "language/FILE_IO_PLAN.md",
    "language/LANGUAGE_IMPROVEMENTS_2026-09-14.md",
    "language/NESTED_FLOWS_PLAN.md",
    "language/NESTED_FLOWS_REQUIREMENTS.md",
    "language/SERVE_PLAN.md",
    "language/render_pdf.py",
    "CAPABILITY_REVIEW.md",
    "GAP_ANALYSIS.md",
    "GAP_ANALYSIS_2026-09-16.md",
    "GAP_VERIFICATION_2026-09-17.md",
    "QUANTIZATION_REVIEW_2026-09-18.md",
    "capability/language_surface.md",
    "capability/ops_and_execution.md",
    "capability/tooling_io_distribution.md",
    "scripts/EXAMPLES_VERIFICATION.md",
    "scripts/OBJECTIVES_VERIFICATION.md",
    "scripts/RUN_LOG.md",
    "scripts/runlog_A_examples_benchmarks.md",
    "scripts/runlog_B_demos_remote.md",
    "scripts/runlog_C_demos_verify_serve.md",
    "scripts/runlog_D_ml14sep.md",
    "history/2026-07-21_checkpoint.md",
    "history/2026-07-21_current_state.md",
    "history/review.md",
    "history/task_14_sep.md",
    "history/todo.md",
}

SOURCE_TO_OUTPUT = {src: out for _, src, out, _ in PAGES}
OUTPUTS = {out for _, _, out, _ in PAGES}


def png_size(path: Path):
    """(width, height) from a PNG's IHDR, or None.

    Emitting intrinsic dimensions stops the page reflowing when the artwork
    finishes loading - the illustrations are large enough that the jump is
    the difference between a readable page and one that moves under you.
    """
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
        if header[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        return (
            int.from_bytes(header[16:20], "big"),
            int.from_bytes(header[20:24], "big"),
        )
    except OSError:
        return None


class BuildError(Exception):
    """A problem the author must fix; aborts the build with a located message."""


# ---------------------------------------------------------------------------
# Inline markup
# ---------------------------------------------------------------------------

_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"([^\"]*)\")?\)")
_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])")
_PLACEHOLDER = re.compile(r"\x00(\d+)\x00")


def _resolve_link(target: str, src: str, where: str) -> str | None:
    """Rewrite a doc-relative markdown link to its site URL.

    Returns None when the target is a real but unpublished document, which the
    caller renders as plain text. Raises BuildError for a target that does not
    exist at all.
    """
    if target.startswith(("http://", "https://", "mailto:", "#")):
        return target

    path, _, anchor = target.partition("#")
    if not path:
        return target

    # A ".html" target is already a site URL, written site-root-relative.
    # Pages authored FOR the site (site/home.md) link to output paths rather
    # than to markdown sources, because the page they point at may have no
    # one-to-one source - so resolve it against the site root, not the disk.
    if path.endswith(".html"):
        # Validate it: these are hand-written in site/*.md and point at output
        # paths, so removing a page from PAGES silently turns every link to it
        # into a 404. The markdown-source links are checked against the
        # allowlist; these have to be checked against the built page set.
        if path not in OUTPUTS:
            raise BuildError(
                f"{where}: link to '{target}' names no published page.\n"
                f"        Published pages: {', '.join(sorted(OUTPUTS))}"
            )
        depth = SOURCE_TO_OUTPUT[src].count("/")
        return "../" * depth + target

    # Resolve relative to the SOURCE document, then express relative to docs/.
    src_dir = (DOCS_DIR / src).parent
    resolved = (src_dir / path).resolve()
    try:
        rel = resolved.relative_to(DOCS_DIR.resolve()).as_posix()
    except ValueError:
        # Points outside docs/ (e.g. ../../maned-bark/...). Those targets are
        # not part of this site and are not ours to verify; flatten them.
        return None

    if rel in SOURCE_TO_OUTPUT:
        out = SOURCE_TO_OUTPUT[rel]
        depth = SOURCE_TO_OUTPUT[src].count("/")
        prefix = "../" * depth
        return prefix + out + (f"#{anchor}" if anchor else "")

    if rel in UNPUBLISHED:
        return None

    # Any other directory link: never a site page, since only the files in
    # PAGES are published. Flatten rather than fail.
    if resolved.is_dir():
        return None

    if not resolved.exists():
        raise BuildError(
            f"{where}: link to '{target}' does not exist.\n"
            f"        Resolved to: {resolved}\n"
            f"        Fix the link, or - if the file was renamed - update the source."
        )

    raise BuildError(
        f"{where}: link to '{target}' points at '{rel}', which is neither\n"
        f"        published (PAGES) nor listed as deliberately unpublished\n"
        f"        (UNPUBLISHED). Add it to one of the two lists in render_html.py."
    )


def inline(text: str, src: str, where: str, state=None) -> str:
    """Markdown inline -> HTML. Code spans are masked so their contents are
    never re-parsed as markup (several docs contain `**` inside backticks)."""
    if state is None:
        state = {"images": 99}   # non-first: callers without page state
    spans: list[str] = []

    def stash(match: re.Match) -> str:
        spans.append(html.escape(match.group(1), quote=False))
        return f"\x00{len(spans) - 1}\x00"

    text = _CODE.sub(stash, text)
    text = html.escape(text, quote=False)

    def link(match: re.Match) -> str:
        label, target = match.group(1), html.unescape(match.group(2))
        if state.get("passthrough_links"):
            # --single renders a document this site does not own (the dist
            # repo's landing page). Its links point into ITS repo, so the
            # allowlist does not apply - emit them unchanged and let the
            # caller report anything suspicious.
            external = target.startswith(("http://", "https://", "mailto:"))
            if not external and not target.startswith("#"):
                state.setdefault("foreign_links", []).append(target)
            extra = ' target="_blank" rel="noopener"' if external else ""
            return f'<a href="{html.escape(target, quote=True)}"{extra}>{label}</a>'
        href = _resolve_link(target, src, where)
        if href is None:
            return label  # real but unpublished, or outside this site
        external = href.startswith(("http://", "https://"))
        extra = ' target="_blank" rel="noopener"' if external else ""
        return f'<a href="{html.escape(href, quote=True)}"{extra}>{label}</a>'

    def image(match: re.Match) -> str:
        alt, asset = match.group(1), html.unescape(match.group(2))
        caption = match.group(3)
        # Image sources are written site-root-relative, like .html links.
        url = "../" * SOURCE_TO_OUTPUT[src].count("/") + asset

        # Serve WebP where a sibling exists and fall back to the PNG. Both are
        # generated from the originals in IMAGENS/ by tools/build_assets.sh.
        # The first image on a page is above the fold; lazy-loading it only
        # delays the thing the reader is looking at.
        state["images"] += 1
        eager = state["images"] == 1
        load = (' loading="eager" fetchpriority="high"' if eager
                else ' loading="lazy"')
        size = png_size(SITE_DIR / asset)
        dims = f' width="{size[0]}" height="{size[1]}"' if size else ""

        webp = SITE_DIR / (asset[:-4] + ".webp")
        if asset.endswith(".png") and webp.is_file():
            webp_url = url[:-4] + ".webp"
            img = (
                f'<picture><source srcset="{html.escape(webp_url, quote=True)}" '
                f'type="image/webp">'
                f'<img src="{html.escape(url, quote=True)}" '
                f'alt="{html.escape(alt, quote=True)}"{dims}{load} '
                f'decoding="async"></picture>'
            )
        else:
            img = (
                f'<img src="{html.escape(url, quote=True)}" '
                f'alt="{html.escape(alt, quote=True)}"{dims}{load} decoding="async">'
            )
        if caption:
            return f'<figure class="illus">{img}<figcaption>{html.escape(caption)}</figcaption></figure>'
        return f'<figure class="illus">{img}</figure>'

    text = _IMAGE.sub(image, text)
    text = _LINK.sub(link, text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    text = _PLACEHOLDER.sub(lambda m: f"<code>{spans[int(m.group(1))]}</code>", text)
    return text


def highlight(source: str) -> str:
    """Colour a Maned snippet with the shared tokenizer."""
    out: list[str] = []
    cursor = 0
    for match in CODE_TOKEN.finditer(source):
        if match.start() > cursor:
            out.append(html.escape(source[cursor:match.start()]))
        category = match.lastgroup or "plain"
        out.append(
            f'<span class="t-{category}">{html.escape(match.group(0))}</span>'
        )
        cursor = match.end()
    if cursor < len(source):
        out.append(html.escape(source[cursor:]))
    return "".join(out)


# ---------------------------------------------------------------------------
# Block rendering
# ---------------------------------------------------------------------------

def render_blocks(blocks, src: str, extra_state=None):
    """Return (html, toc) where toc is a list of (level, slug, text) for h2/h3."""
    out: list[str] = []
    toc: list[tuple[int, str, str]] = []
    seen: dict[str, int] = {}
    first_h1 = True
    state = dict(extra_state or {})
    state["images"] = 0

    for block in blocks:
        kind = block[0]
        where = f"docs/{src}"

        if kind == "heading":
            _, level, text = block
            rendered = inline(text, src, where, state)
            if level == 1 and first_h1:
                first_h1 = False
                continue  # the page header already shows the title
            slug = heading_slug(text)
            if slug in seen:
                seen[slug] += 1
                slug = f"{slug}-{seen[slug]}"
            else:
                seen[slug] = 0
            if level in (2, 3):
                toc.append((level, slug, re.sub(r"<[^>]+>", "", rendered)))
            out.append(
                f'<h{level} id="{slug}">{rendered}'
                f'<a class="anchor" href="#{slug}" aria-label="Link to this section">#</a>'
                f"</h{level}>"
            )

        elif kind == "para":
            rendered = inline(block[1], src, where, state)
            if rendered.startswith("<figure") and rendered.endswith("</figure>"):
                out.append(rendered)
            else:
                out.append(f"<p>{rendered}</p>")

        elif kind == "code":
            _, lang, body = block
            maned = lang in MANED_FENCE_TAGS or (not lang and looks_like_maned(body))
            inner = highlight(body) if maned else html.escape(body)
            label = lang or ("mnd" if maned else "")
            attr = f' data-lang="{html.escape(label, quote=True)}"' if label else ""
            out.append(f'<pre class="code"{attr}><code>{inner}</code></pre>')

        elif kind == "quote":
            body = inline(block[1], src, where, state)
            # A "**Role:**" opener is the precedence marker from
            # docs/README.md; give it a callout of its own so the rule a
            # document lives under is visible at a glance on the web too.
            cls = "callout role" if block[1].lstrip().startswith("**Role:**") else "callout"
            out.append(f'<blockquote class="{cls}">{body}</blockquote>')

        elif kind == "table":
            rows = block[1]
            head = "".join(f"<th>{inline(c, src, where, state)}</th>" for c in rows[0])
            body = "".join(
                "<tr>" + "".join(f"<td>{inline(c, src, where, state)}</td>" for c in r) + "</tr>"
                for r in rows[1:]
            )
            out.append(
                f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead>'
                f"<tbody>{body}</tbody></table></div>"
            )

        elif kind == "list":
            _, ordered, items = block
            tag = "ol" if ordered else "ul"
            lis = "".join(f"<li>{inline(i, src, where, state)}</li>" for i in items)
            out.append(f"<{tag}>{lis}</{tag}>")

        elif kind == "rule":
            out.append("<hr>")

    if extra_state is not None:
        extra_state.update(state)
    body = "\n".join(out)
    # The first illustration on a page is the hero and runs the full measure;
    # any later one floats beside the prose. Deciding by position keeps the
    # markdown free of layout hints - an author writes ![alt](src) and nothing
    # else.
    first = body.find('<figure class="illus">')
    if first != -1:
        head, tail = body[: first + 1], body[first + 1 :]
        body = head + tail.replace('<figure class="illus">',
                                   '<figure class="illus side">')
    return body, toc


# ---------------------------------------------------------------------------
# Page shell
# ---------------------------------------------------------------------------

def nav_html(current_out: str) -> str:
    depth = current_out.count("/")
    prefix = "../" * depth
    parts: list[str] = []
    section = None
    for sec, _src, out, label in PAGES:
        if sec != section:
            if section is not None:
                parts.append("</ul>")
            if sec:
                parts.append(f'<h2 class="nav-section">{html.escape(sec)}</h2>')
            parts.append("<ul>")
            section = sec
        active = ' class="active"' if out == current_out else ""
        parts.append(f'<li><a href="{prefix}{out}"{active}>{html.escape(label)}</a></li>')
    parts.append("</ul>")
    return "\n".join(parts)


def page_html(title: str, body: str, toc, current_out: str, source_rel: str) -> str:
    depth = current_out.count("/")
    prefix = "../" * depth
    # "Maned · Maned" on the landing page reads like a bug, because it is one.
    page_title = title if title == SITE_TITLE else f"{title} · {SITE_TITLE}"
    page_title = html.escape(page_title)

    toc_html = ""
    if len(toc) > 1:
        items = "".join(
            f'<li class="lv{level}"><a href="#{slug}">{text}</a></li>'
            for level, slug, text in toc
        )
        toc_html = f'<nav class="toc"><h2>On this page</h2><ul>{items}</ul></nav>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title}</title>
<meta name="description" content="{html.escape(SITE_TAGLINE)}">
<link rel="stylesheet" href="{prefix}assets/site.css">
<link rel="stylesheet" href="{prefix}assets/tokens.css">
<link rel="icon" href="{prefix}assets/img/favicon.ico" sizes="any">
<link rel="icon" href="{prefix}assets/img/mark-512.png" type="image/png">
<link rel="apple-touch-icon" href="{prefix}assets/img/apple-touch-icon.png">
<meta name="theme-color" content="#A95F2A">
<meta property="og:title" content="{page_title}">
<meta property="og:description" content="{SITE_TAGLINE}">
<meta property="og:image" content="{SITE_URL}/assets/img/hero.png">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
</head>
<body>
<a class="skip" href="#content">Skip to content</a>
<input type="checkbox" id="nav-toggle" hidden>
<header class="topbar">
  <label for="nav-toggle" class="burger" aria-label="Toggle navigation">☰</label>
  <a class="brand" href="{prefix}index.html">
    <img src="{prefix}assets/img/mark-64.png" alt="" width="26" height="26">{SITE_TITLE}</a>
</header>
<div class="shell">
  <aside class="sidebar">
    <a class="brand desktop" href="{prefix}index.html">
      <img src="{prefix}assets/img/mark-64.png" alt="" width="34" height="34">{SITE_TITLE}</a>
    <p class="tagline">{html.escape(SITE_TAGLINE)}</p>
    <nav>{nav_html(current_out)}</nav>
  </aside>
  <main id="content">
    <article>
      <h1>{html.escape(title)}</h1>
      {body}
      <footer class="src">Source: <code>docs/{html.escape(source_rel)}</code></footer>
    </article>
  </main>
  {toc_html}
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def standalone_html(title: str, body: str, docs_url: str) -> str:
    """A one-page shell: same stylesheet, no sidebar.

    The dist repo (FabianoDicheti/maned) needs exactly one rendered page - its
    landing page - and rendering it here rather than with a second tool is
    what keeps that page and this site looking like the same product.
    """
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(SITE_TAGLINE)}">
<link rel="stylesheet" href="assets/site.css">
<link rel="stylesheet" href="assets/tokens.css">
<link rel="icon" href="assets/img/favicon.ico" sizes="any">
<link rel="icon" href="assets/img/mark-512.png" type="image/png">
<link rel="apple-touch-icon" href="assets/img/apple-touch-icon.png">
<meta name="theme-color" content="#A95F2A">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(SITE_TAGLINE)}">
<meta property="og:type" content="website">
</head>
<body class="standalone">
<main id="content">
  <article>
    <header class="hero">
      <img src="assets/img/mark-512.png" alt="" width="72" height="72">
      <h1>{html.escape(title)}</h1>
      <p class="tagline">{html.escape(SITE_TAGLINE)}</p>
    </header>
    {body}
    <footer class="src">
      Full documentation: <a href="{html.escape(docs_url, quote=True)}">{html.escape(docs_url)}</a>
    </footer>
  </article>
</main>
</body>
</html>
"""


def build_single(source: Path, out_dir: Path, docs_url: str) -> None:
    """Render ONE markdown file plus the stylesheet and icons into out_dir."""
    blocks = scan_blocks(source.read_text(encoding="utf-8"))
    state = {"passthrough_links": True}
    body, _toc = render_blocks(blocks, "site/home.md", state)
    title = document_title(source)

    # Relative links in a foreign page are worth naming: GitHub Pages serves
    # this file's own directory as the site root, so a link to a file that
    # lives above it resolves on github.com and 404s on the published site.
    for target in state.get("foreign_links", []):
        candidate = (source.parent / target.split("#")[0]).resolve()
        if not candidate.exists():
            print(
                f"  warning: '{target}' is not next to {source.name}; "
                f"it will 404 on the published site",
                file=sys.stderr,
            )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(
        standalone_html(title, body, docs_url), encoding="utf-8"
    )
    assets = out_dir / "assets"
    assets.mkdir(exist_ok=True)
    for name in ("site.css",):
        shutil.copy(SITE_DIR / "assets" / name, assets / name)
    write_tokens_css(assets)
    img_out = assets / "img"
    img_out.mkdir(exist_ok=True)
    for name in ("favicon.ico", "mark-512.png", "apple-touch-icon.png",
                 "mark-64.png"):
        shutil.copy(SITE_DIR / "assets" / "img" / name, img_out / name)


def write_tokens_css(assets_dir: Path) -> None:
    """Token colours, generated from CODE_COLORS so nothing is hand-copied."""
    rules = "\n".join(
        f".t-{name} {{ color: {value}; }}" for name, value in CODE_COLORS.items()
    )
    (assets_dir / "tokens.css").write_text(
        "/* Generated by render_html.py from CODE_COLORS in maned_md.py.\n"
        "   Do not edit - edit the palette there and rebuild. */\n"
        + rules
        + "\n",
        encoding="utf-8",
    )


def build(out_dir: Path) -> int:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    missing = [src for _, src, _, _ in PAGES if not (DOCS_DIR / src).is_file()]
    if missing:
        raise BuildError(
            "PAGES names files that do not exist:\n        "
            + "\n        ".join(missing)
        )

    for _section, src, out, _label in PAGES:
        source = DOCS_DIR / src
        blocks = scan_blocks(source.read_text(encoding="utf-8"))
        body, toc = render_blocks(blocks, src)
        title = document_title(source)
        target = out_dir / out
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            page_html(title, body, toc, out, src), encoding="utf-8"
        )

    assets_src = SITE_DIR / "assets"
    shutil.copytree(assets_src, out_dir / "assets")

    # Token colours are GENERATED from CODE_COLORS rather than hand-copied
    # into site.css: the highlighter's palette lives in maned_md.py, shared
    # with the PDF, and a second copy in a stylesheet is exactly the kind of
    # drift this build is organised to avoid.
    write_tokens_css(out_dir / "assets")

    (out_dir / ".nojekyll").write_text("")
    return len(PAGES)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="_site", help="output directory")
    parser.add_argument(
        "--single",
        metavar="FILE",
        help="render ONE markdown file as a standalone page (no sidebar) with "
             "the site's stylesheet and icons. Used for the dist repo's "
             "landing page - see tools/fix_dist_landing.sh",
    )
    parser.add_argument(
        "--docs-url",
        default=SITE_URL,
        help="where --single should send readers for the full documentation",
    )
    parser.add_argument(
        "--list-sources",
        action="store_true",
        help="print the published source paths (one per line) and exit; this "
             "is the allowlist tools/sync_docs.sh copies, so the two cannot "
             "disagree about what is public",
    )
    args = parser.parse_args()

    if args.list_sources:
        for _section, src, _out, _label in PAGES:
            print(src)
        return

    out_dir = Path(args.out).resolve()

    if args.single:
        source = Path(args.single).resolve()
        if not source.is_file():
            print(f"render_html: {source} is not a file", file=sys.stderr)
            raise SystemExit(1)
        try:
            build_single(source, out_dir, args.docs_url)
        except BuildError as error:
            print(f"render_html: {error}", file=sys.stderr)
            raise SystemExit(1)
        print(f"Rendered {source.name} -> {out_dir}/index.html")
        return

    try:
        count = build(out_dir)
    except BuildError as error:
        print(f"render_html: {error}", file=sys.stderr)
        raise SystemExit(1)

    sections = []
    seen = set()
    for section, _s, _o, _l in PAGES:
        if section and section not in seen:
            seen.add(section)
            sections.append(section)
    print(f"Built {count} pages into {out_dir}")
    print(f"Sections: {', '.join(sections)}")
    if not any(s == "Examples" for s, _, _, _ in PAGES):
        print("Examples section: empty (reserved slot, see PAGES)")


if __name__ == "__main__":
    main()
