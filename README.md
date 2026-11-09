# Maned documentation

The published documentation for **Maned**, an integer-only dataflow language
(`.mnd`) for linear algebra and small ML workloads.

📖 **<https://fabianodicheti.github.io/maned-lang-docs/>**

## This repository is a mirror

Do not send pull requests against the markdown here, and do not edit it in the
GitHub web editor — **the next sync overwrites it**. Every file in this repo is
copied from a private workspace by `tools/sync_docs.sh`, which derives the list
of publishable documents from the site generator itself, so what is rendered
and what is published cannot drift apart.

If you spot an error, open an issue. That is the channel that reaches the
source.

## What is here

| Path | What |
|---|---|
| `docs/` | The published markdown, mirrored from the workspace |
| `docs/site/render_html.py` | The static site generator — standard library only, no dependencies |
| `docs/site/maned_md.py` | The markdown grammar and Maned syntax highlighter, shared with the PDF build |
| `docs/site/assets/` | Stylesheet; `tokens.css` is generated at build time from the highlighter's palette |
| `tutorials/system-one-tutorial/` | The complete project of the [System One tutorial](https://maned-lang.com/tutorial.html), speed-first edition: programs, policy, corpus, the shell runbook and the Python, Kotlin and Rust apps, deployable from zero |
| `tutorials/system-one-accurate/` | The [accuracy-first edition](https://maned-lang.com/tutorial-accurate.html) of the same project: two teachers (XLM-R and an entailment model), a prototype judge, the agreement learning rule, the Python app |
| `tutorials/PCA-tutorial/` | The complete project of the [PCA explorer tutorial](https://maned-lang.com/tutorial-pca.html): the features and PCA programs, the page, the example images and the numpy check |
| `.github/workflows/pages.yml` | Builds and deploys on every push to `main` |

## Building locally

```sh
python3 docs/site/render_html.py --out _site
python3 -m http.server -d _site 8000
```

No `pip install` step — that is deliberate. The generator uses only the Python
standard library, so the runner's stock `python3` is the entire toolchain.

## Scope

This site carries the language reference, the guides, the normative RPN syntax
specification and the cross-repo integration contract. Development history —
gap analyses, capability reviews, campaign logs — stays in the private
workspace; it is dated, superseded material that would mislead more than it
explains.
