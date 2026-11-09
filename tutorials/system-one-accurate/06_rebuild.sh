#!/bin/sh
# ============================================================================
# 06_rebuild.sh -- recompute both memories from the text file and the vector file
# ----------------------------------------------------------------------------
# usage: ./06_rebuild.sh
#
# needs: the memory; no worker involved
# does:  work/memory.tsv IS the dataset ("label<TAB>text", one line per
#        recorded text) and work/vectors.csv its row-aligned companion (the
#        text's unit vector, or 256 zeros); work/memory.dqt and work/protos.dqt
#        are their compiled forms. This empties both memories and replays every
#        line through 03_record.mnd and 03_record_proto.mnd, then compares the
#        results with the files they replaced: byte-identical means the
#        incremental records never drifted. Edit the .tsv by hand (fix a label,
#        drop a line AND its vector line) and run this to make the memories follow.
# ============================================================================
. "$(dirname "$0")/_common.sh"
need work/memory.dqt "./00_setup.sh"
need work/protos.dqt "./00_setup.sh"
touch work/vectors.csv
[ "$(grep -c . work/memory.tsv)" -eq "$(grep -c . work/vectors.csv)" ] || { echo "error: work/memory.tsv and work/vectors.csv have different line counts; they must stay row-aligned" >&2; exit 1; }
cp work/memory.dqt work/memory.dqt.before_rebuild
cp work/protos.dqt work/protos.dqt.before_rebuild
mv work/memory.tsv work/memory.tsv.replay
mv work/vectors.csv work/vectors.csv.replay
rm -f work/memory.dqt work/protos.dqt
run_mnd 00_init_memory.mnd
run_mnd 00_init_protos.mnd
: > work/memory.tsv; : > work/vectors.csv
t0=$(ms)
count=0
paste -d "$TAB" work/memory.tsv.replay work/vectors.csv.replay | while IFS="$TAB" read -r label text vec; do
  [ -n "$text" ] || continue
  prep "$text"
  printf '%s\n' "$vec" > work/q/u.csv
  record_both "$label"
done
count=$(grep -c . work/memory.tsv)
rm -f work/memory.tsv.replay work/vectors.csv.replay
echo "replayed $count texts in $(( ($(ms) - t0) / 1000 )) s"
for m in memory protos; do
  if cmp -s "work/$m.dqt" "work/$m.dqt.before_rebuild"; then
    echo "work/$m.dqt is byte-identical to the one it replaced: the incremental records equal a from-scratch computation"
  else
    echo "work/$m.dqt differs from the previous one (expected if the files were edited); the old file is work/$m.dqt.before_rebuild"
  fi
done
