# seed/ — a memory the worker already taught

Five files that turn a freshly initialized System One into one that answers: copy them into the
edition's `work/` after `maned-run 00_init_memory.mnd` (the `/setup` quick path does this).

| file | what | size |
|---|---|---|
| `memory.dqt` | the counts `[4096,32]` and `ntexts [1,32]` | 12 KB |
| `memory.tsv` | the 147 texts it learned, one `label<TAB>text` per line; `06_rebuild.sh` replays it | 14 KB |
| `labels.tsv` | the label registry: line i = memory column i (`urgent later careful yes no 1 2 3`) | 34 B |
| `descs.tsv` | the 16 label descriptions the worker has embedded (the corpus's 9, the demo's 7) | 1 KB |
| `labels_u.csv` | their unit vectors, row i = `descs.tsv` row i, at the worker's scale | 26 KB |

## Provenance

Built 2026-11-02 with the released maned 0.4.2 (`maned-run 0.4.2`) by replaying, through
`06_rebuild.sh` (`03_record.mnd`, no worker involved), the tutorial corpus of the editions:
`corpus/messages.tsv` (108 texts, en/pt/de) and `corpus/variants.tsv` (36), plus the three demo
texts of `decide.py`'s `demo()` with their labels (`urgent`, `yes`, `2`). The rebuild reported
the result byte-identical to the incremental run that produced it. `corpus/unseen.tsv` is **not**
included: those 36 texts stay unseen, so `05_eval.sh` keeps its meaning (that script erases the
memory before it runs anyway).

The 16 description vectors were produced by a provisioned worker (`xlmr-large.int32.dqt`) through
`02_label_embed.mnd`; the model is integers end to end, so any worker running the same model
produces the same bytes.

## Rebuild it yourself

From an edition folder with the small downloads in place:
```sh
mkdir -p work/q/out work/ranges && maned-run 00_init_memory.mnd > work/00_init_memory.log
cp seed/labels.tsv seed/memory.tsv work/ && ./06_rebuild.sh         # about 8 s
cmp work/memory.dqt seed/memory.dqt && echo identical
```
