#!/bin/sh
# ============================================================================
# capture.sh -- the outputs the tutorial page shows, produced by running the project
# ----------------------------------------------------------------------------
# usage: ./capture.sh            (both workers; EMPTIES the memories first; ~1 min + 05_eval.sh if asked)
#        CAPTURE_EVAL=1 ./capture.sh      also runs 05_eval.sh (the four passes) and captures its summary
#
# Writes work/out/<name>.txt, one per `@@out <name>` of docs/site/tutorial-accurate-src/*.md:
#   download, setup, query_first, query_second, pending, query_known, rebuild, consumer_python,
#   eval_passes, eval_summary (the last two from 05_eval.sh's log).
# The page generator splices them in; a missing one stops the generation, so the page can
# never show an output that was not produced.
# ============================================================================
. "$(dirname "$0")/_common.sh"
mkdir -p work/out
cap() { out=work/out/$1.txt; shift; "$@" > "$out" 2>&1 || { echo "capture: $out failed:" >&2; cat "$out" >&2; exit 1; }; echo "  work/out/$(basename "$out")"; }
./00_download.sh > work/out/download.txt 2>&1 || true; echo "  work/out/download.txt"
cap setup ./00_setup.sh
cap query_first ./04_query.sh "Our servers crashed again, customers cannot log in, fix it within the hour." urgent later careful
cap query_second ./04_query.sh "Here is the monthly newsletter with photos from the picnic." urgent later careful
cut -f1-5 work/pending.tsv > work/out/pending.txt; echo "  work/out/pending.txt"
{ S1_LEARN_RULE=all ./04_query.sh "Please review the attached contract clauses on liability before signing." urgent later careful; echo; ./04_query.sh "Please review the attached contract clauses on liability before signing." urgent later careful; } > work/out/query_known.txt 2>&1; echo "  work/out/query_known.txt"
cap rebuild ./06_rebuild.sh
{ "${S1_PYTHON:-python3}" consumers/python/decide.py "Bitte bis Freitag den Vertrag prüfen" urgent later careful; echo; echo '$ python3 consumers/python/decide.py --pending'; "${S1_PYTHON:-python3}" consumers/python/decide.py --pending; echo; echo '$ python3 consumers/python/decide.py --resolve accept'; "${S1_PYTHON:-python3}" consumers/python/decide.py --resolve accept; } > work/out/consumer_python.txt 2>&1; echo "  work/out/consumer_python.txt"
if [ "${CAPTURE_EVAL:-0}" = 1 ]; then
  ./05_eval.sh > work/out/eval_full.txt 2>&1 || true
  grep -E '^== pass|requests in' work/out/eval_full.txt > work/out/eval_passes.txt
  sed -n '/^== 05_eval.mnd/,$p' work/out/eval_full.txt | grep -E 'checks|learned|xlm_acc|ans_acc|n_known|n_judge|n_xlm|judge_auto_acc|n_judge_auto|t_answer|t_xlm|t_lookup|^== ' > work/out/eval_summary.txt
  echo "  work/out/eval_passes.txt  work/out/eval_summary.txt"
fi
echo "capture done"
