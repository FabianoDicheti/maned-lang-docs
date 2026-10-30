#!/bin/sh
# ============================================================================
# 05_eval.sh -- cold, warm, variants and unseen passes; every number, and every check, computed in maned
# ----------------------------------------------------------------------------
# usage: ./05_eval.sh            (~4 min: 288 requests, each one XLM call)
#
# needs: the worker (. ~/.config/maned/xlm.env)
# does:  EMPTIES the memory, then sends every request through 04_query.sh's
#        `decide` (risk medium, policy.csv) in training mode (S1_XLM=always):
#          pass 0 cold      108 messages (3 labels x en/pt/de)  - the memory fills, the XLM decides
#          pass 1 warm      the same 108                         - known texts: the memory answers
#          pass 2 variants  36 near-duplicates                   - punctuation, a new first word, a trailing word
#          pass 3 unseen    36 new messages, never recorded      - the judge alone, the honest number
#        One row per request (indices and ms) goes to work/eval/rows.csv;
#        05_eval.mnd computes every metric and the four PASS checks from it,
#        and its printed log is the report.
# ============================================================================
S1_LIB=1 . "$(dirname "$0")/04_query.sh"
mkdir -p work/eval
passname() { case $1 in 0) echo cold ;; 1) echo warm ;; 2) echo variants ;; *) echo unseen ;; esac; }
langidx() { case $1 in en) echo 0 ;; pt) echo 1 ;; *) echo 2 ;; esac; }

echo "== four passes (the memory is emptied first) =="
rm -f work/memory.dqt work/memory.tsv work/labels.tsv work/descs.tsv work/labels_u.csv work/review.tsv work/decisions.tsv
run_mnd 00_init_memory.mnd
labels="urgent later careful"
for l in $labels; do col_of "$l" > /dev/null; done        # columns 0, 1, 2 in this order
: > work/eval/rows.csv
t_start=$(ms)
pass=0
for src in messages messages variants unseen; do
  echo "== pass $pass $(passname "$pass"): $(grep -c . "corpus/$src.tsv") requests =="
  while IFS="$TAB" read -r lang truth text; do
    [ -n "$text" ] || continue
    prep "$text"
    S1_XLM=always decide 1 $labels
    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
      "$pass" "$(langidx "$lang")" "$(col_of "$truth")" "$xlm_col" "$(col_of "$answer")" "$how" \
      "$best" "$p_best" "$tier" "$known" "$p_xlm" "$disputed" "$t_answer" "$t_xlm" "$t_lookup" >> work/eval/rows.csv
    printf '  %-3s %-8s -> %-8s via %-16s (xlm %-8s %s%%o, tier %s) %4d ms%s\n' "$lang" "$truth" "$answer" "$via" "$xlm_name" "$p_best" "$tier" "$t_answer" \
      "$([ "$disputed" = 1 ] && echo '  DISPUTED' || echo '')"
  done < "corpus/$src.tsv"
  pass=$((pass + 1))
done
echo "$(grep -c . work/eval/rows.csv) requests in $(( ($(ms) - t_start) / 1000 )) s -> work/eval/rows.csv"
echo
echo "== 05_eval.mnd over work/eval/rows.csv (columns: cold, warm, variants, unseen) =="
"$MANED_RUN" 05_eval.mnd | tee work/05_eval.log
checks=$(sed -n 's/^checks : \[[^]]*\] = \[\(.*\)\]$/\1/p' work/05_eval.log | tr -d ',')
echo "checks: cold-never-known, warm->=95%-by-memory, warm-as-right-as-xlm, unseen-auto->=xlm = $checks (1 = PASS)"
case $checks in *0*) exit 1 ;; esac
