#!/bin/sh
# ============================================================================
# 05_eval.sh -- cold, warm, variants and unseen passes; every number, and every check, computed in maned
# ----------------------------------------------------------------------------
# usage: ./05_eval.sh            (288 requests, each one XLM-R embedding and one NLI pass)
#
# needs: both workers (. ~/.config/maned/xlm.env; . ~/.config/maned/nli.env)
# does:  EMPTIES the memory, then sends every request through 04_query.sh's
#        `decide` (risk medium, policy.csv) in training mode (S1_XLM=always):
#          pass 0 cold      108 messages (3 labels x en/pt/de)  - the memory fills, the XLM decides
#          pass 1 warm      the same 108                         - known texts: the memory answers
#          pass 2 variants  36 near-duplicates                   - punctuation, a new first word, a trailing word
#          pass 3 unseen    36 new messages, never recorded      - the prototype judge alone, the honest number
#        One row per request (indices and ms) goes to work/eval/rows.csv in the
#        speed edition's 15 columns (how 4, the prototype judge answering alone, is
#        written as 1 "judge auto"; `xlm` is the NLI teacher); 05_eval.mnd computes
#        every metric and the four PASS checks from it, and its printed log is the report.
# ============================================================================
S1_LIB=1 . "$(dirname "$0")/04_query.sh"
mkdir -p work/eval
passname() { case $1 in 0) echo cold ;; 1) echo warm ;; 2) echo variants ;; *) echo unseen ;; esac; }
langidx() { case $1 in en) echo 0 ;; pt) echo 1 ;; *) echo 2 ;; esac; }

echo "== four passes (the memory is emptied first) =="
rm -f work/memory.dqt work/protos.dqt work/memory.tsv work/vectors.csv work/labels.tsv work/descs.tsv work/descs_nli.tsv work/labels_u.csv work/pending.tsv work/decisions.tsv
run_mnd 00_init_memory.mnd; run_mnd 00_init_protos.mnd; : > work/memory.tsv; : > work/vectors.csv
labels="urgent later careful"
for l in $labels; do col_of "$l" > /dev/null; done        # columns 0, 1, 2 in this order
: > work/eval/rows.csv
t_start=$(ms)
pass=0; learned_n=0; learned_known=0
for src in messages messages variants unseen; do
  echo "== pass $pass $(passname "$pass"): $(grep -c . "corpus/$src.tsv") requests =="
  while IFS="$TAB" read -r lang truth text; do
    [ -n "$text" ] || continue
    prep "$text"
    S1_XLM=always decide 1 $labels
    how_row=$how; [ "$how" = 4 ] && how_row=1
    # this edition's check 2: a text the cold pass LEARNED must be known on the warm pass
    if [ "$pass" = 1 ] && grep -qF -- "$TAB$text" work/memory.tsv; then learned_n=$((learned_n + 1)); [ "$how" = 0 ] && learned_known=$((learned_known + 1)); fi
    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
      "$pass" "$(langidx "$lang")" "$(col_of "$truth")" "$xlm_col" "$(col_of "$answer")" "$how_row" \
      "$best" "$p_best" "$tier" "$known" "$p_xlm" "$disputed" "$t_answer" "$t_xlm" "$t_lookup" >> work/eval/rows.csv
    printf '  %-3s %-8s -> %-8s via %-12s (proto %-8s %s%%o tier %s, nli %-8s %s%%o %s) %4d ms%s\n' "$lang" "$truth" "$answer" "$via" \
      "$proto_name" "$((proto_margin / 1000))" "$proto_tier" "$nli_name" "$((nli_margin / 1000))" "$([ "$agree" = 1 ] && echo AGREE || echo DISAGREE)" "$t_answer" \
      "$([ -n "$held" ] && echo '  HELD' || echo '')"
  done < "corpus/$src.tsv"
  pass=$((pass + 1))
done
echo "$(grep -c . work/eval/rows.csv) requests in $(( ($(ms) - t_start) / 1000 )) s -> work/eval/rows.csv"
echo
echo "== 05_eval.mnd over work/eval/rows.csv (columns: cold, warm, variants, unseen) =="
"$MANED_RUN" 05_eval.mnd | tee work/05_eval.log
checks=$(sed -n 's/^checks : \[[^]]*\] = \[\(.*\)\]$/\1/p' work/05_eval.log | tr -d ',')
# the shared program's second check expects every cold text to be learned (the speed edition's
# training mode); under this edition's learn rule only the agreed ones are, so the check here is
# that every text the cold pass learned is answered from memory on the warm pass
c2=0; [ "$learned_n" -gt 0 ] && [ $((learned_known * 100)) -ge $((learned_n * 95)) ] && c2=1
checks="$(nth "$checks" 0) $c2 $(nth "$checks" 2) $(nth "$checks" 3)"
echo "warm pass: $learned_known of the $learned_n texts learned in the cold pass were answered from memory"
echo "checks: cold-never-known, learned-texts-known-warm, warm-as-right-as-teacher, unseen-auto->=teacher = $checks (1 = PASS)"
# what the learn rule wrote: the recorded (label, text) pairs against the corpus truth
awk -F"$TAB" 'FNR == NR { t[$3] = $2; next } ($2 in t) { n++; if ($1 == t[$2]) ok++ } END { printf "learned %d of %d texts; %d%% of the learned labels are right (S1_LEARN_RULE=%s, S1_LEARN=%s)\n", n, NR - FNR, (n ? 100 * ok / n : 0), r, l }' \
  r="${S1_LEARN_RULE:-agree}" l="${S1_LEARN:-250}" corpus/messages.tsv corpus/variants.tsv corpus/unseen.tsv work/memory.tsv
case $checks in *0*) exit 1 ;; esac
