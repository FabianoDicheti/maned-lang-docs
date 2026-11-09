#!/bin/sh
# ============================================================================
# 00_setup.sh -- the two empty memories (run once; run again to start over)
# ----------------------------------------------------------------------------
# usage: ./00_setup.sh
# does:  work/memory.dqt (00_init_memory.mnd: the count memory and the index
#        rows) and work/protos.dqt (00_init_protos.mnd: the centroid memory),
#        and empties the registries and the dataset files they go with.
# ============================================================================
. "$(dirname "$0")/_common.sh"
rm -f work/memory.dqt work/protos.dqt work/memory.tsv work/vectors.csv work/labels.tsv work/descs.tsv work/descs_nli.tsv work/labels_u.csv work/pending.tsv work/decisions.tsv
run_mnd 00_init_memory.mnd
run_mnd 00_init_protos.mnd
: > work/memory.tsv; : > work/vectors.csv
echo "work/memory.dqt and work/protos.dqt are empty; the memories start here"
