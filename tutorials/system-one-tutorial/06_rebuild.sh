#!/bin/sh
# ============================================================================
# 06_rebuild.sh -- recompute the memory from the text file
# ----------------------------------------------------------------------------
# usage: ./06_rebuild.sh
#
# needs: the memory; no worker involved
# does:  work/memory.tsv IS the dataset ("label<TAB>text", one line per
#        recorded text); work/memory.dqt is its compiled form. This empties
#        the memory and replays every line through 03_record.mnd, then
#        compares the result with the file it replaced: byte-identical means
#        the two never drifted. Edit the .tsv by hand (fix a label, drop a
#        line) and run this to make the memory follow.
# ============================================================================
. "$(dirname "$0")/_common.sh"
need work/memory.dqt "maned-run 00_init_memory.mnd"
cp work/memory.dqt work/memory.dqt.before_rebuild
mv work/memory.tsv work/memory.tsv.replay
rm -f work/memory.dqt
run_mnd 00_init_memory.mnd
: > work/memory.tsv
t0=$(ms)
count=0
while IFS="$TAB" read -r label text; do
  [ -n "$text" ] || continue
  prep "$text"
  record "$label"
  count=$((count + 1))
done < work/memory.tsv.replay
rm -f work/memory.tsv.replay
echo "replayed $count texts in $(( ($(ms) - t0) / 1000 )) s"
if cmp -s work/memory.dqt work/memory.dqt.before_rebuild; then
  echo "work/memory.dqt is byte-identical to the one it replaced: the incremental records equal a from-scratch computation"
else
  echo "work/memory.dqt differs from the previous one (expected if the .tsv was edited); the old file is work/memory.dqt.before_rebuild"
fi
