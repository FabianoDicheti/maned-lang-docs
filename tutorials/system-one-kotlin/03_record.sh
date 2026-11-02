#!/bin/sh
# ============================================================================
# 03_record.sh -- put one (text, label) pair into the memory, by hand
# ----------------------------------------------------------------------------
# usage: ./03_record.sh "Attention: the server is down" urgent
#
# needs: the memory (maned-run 00_init_memory.mnd); no worker involved
# does:  runs 03_record.mnd (counts += the text's features under the label,
#        written over work/memory.dqt), appends "label<TAB>text" to work/memory.tsv.
#        04_query.sh does exactly this with the XLM's answer; use it by hand
#        to seed or to correct the memory.
# ============================================================================
. "$(dirname "$0")/_common.sh"
need work/memory.dqt "maned-run 00_init_memory.mnd"
[ $# -eq 2 ] || { echo "usage: $0 \"text\" label" >&2; exit 1; }
prep "$1"
record "$2"
printf 'recorded under %s (column %s): %s features; the memory holds %s texts\n' "$2" "$(col_of "$2")" "$(val q)" "$(grep -c . work/memory.tsv)"
