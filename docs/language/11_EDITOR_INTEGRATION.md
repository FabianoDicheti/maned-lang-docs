# Editor Integration

Maned ships a small VS Code language extension for `.mnd` identification,
syntax highlighting, comments/brackets, and file icons. It does not provide a
language server, semantic completion, or compiler diagnostics.

## File breakdown

| File | Responsibility | Interactions |
|---|---|---|
| `package.json` | Extension identity, supported VS Code version, language registration, grammar path, configuration path, icons, and icon theme contribution. | Root manifest loaded by VS Code. |
| `language-configuration.json` | Line-comment marker, brackets, autoclosing pairs, and surrounding pairs. | Referenced by the language entry in `package.json`. |
| `syntaxes/maned.tmLanguage.json` | TextMate scopes and regex patterns for `.mnd` syntax highlighting. | Referenced by the grammar contribution. |
| `maned-icon-theme.json` | Maps Maned files to the extension icon. | Referenced by the icon-theme contribution. |
| `images/icon_mnd.png` | Raster icon used in light/dark language entries and the icon theme. | Referenced by the two JSON manifests. |

## Installing it

There is no separate setup document (the old `VSCODE_SETUP.md` was evicted with
the 2026-09-15 reorganization). The extension is the `maned_lang` repo root
itself: point VS Code at it with **Developer: Install Extension from Location…**,
or symlink the repo into `~/.vscode/extensions/`. `package.json` is the manifest;
nothing needs building.

## Interaction flow

VS Code reads `package.json`, associates `.mnd` with language ID `maned`, loads
editing behavior from `language-configuration.json`, applies TextMate scopes from
`syntaxes/maned.tmLanguage.json`, and resolves the icon through
`maned-icon-theme.json` to `images/icon_mnd.png`.

## Synchronization rules

Language keywords/operators added to the grammar or lexer should be reflected in
the TextMate grammar when highlighting is expected. Comment and delimiter changes
must be updated in the language configuration. New asset paths must remain relative
to the extension root and match the package manifest exactly.
