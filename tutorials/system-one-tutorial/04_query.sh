#!/bin/sh
# ============================================================================
# 04_query.sh -- the loop: the memory first; the XLM when the policy asks; learn; verify
# ----------------------------------------------------------------------------
# usage: ./04_query.sh [--risk low|medium|high] "Bitte bis Freitag den Vertrag prüfen" urgent later careful
#        ./04_query.sh "text" spam="unsolicited advertising or a scam" ham="a normal message"
#        ./04_query.sh --yesno "Please wire the deposit today." "This message asks for money to be sent" ["its negation"]
#        ./04_query.sh --score "The kitchen will be repainted next spring." 1="no action" 2="look this week" 3="act today"
#        S1_NO_RECORD=1 ./04_query.sh ...      ask, do not learn
#        S1_LEARN=70 ./04_query.sh ...         min teacher cosine margin (permille) to learn; a
#                                              less confident first answer is held in work/pending.tsv
#        S1_XLM=always ./04_query.sh ...       TRAINING MODE: the XLM runs on every request and its
#                                              label is learned even when the memory answered alone;
#                                              the answer does not change. 05_eval.sh measures in it.
#
# needs: the memory (00_init_memory.mnd), the worker (. ~/.config/maned/xlm.env)
# does:  one request, in order:
#          1. 01_lookup.mnd    the memory: known text? the judge's p per label, the tier
#          2. answer at once when the text is KNOWN or the tier is AUTO - the
#             worker is not called at all
#          3. otherwise 02_xlm_classify.mnd on the worker; in tier VERIFY the
#             memory's label stands if the XLM agrees ("verified"), else the
#             XLM's label is the answer
#          4. the verifier (training mode): the memory was confident (tier
#             auto) and informed (30 texts or more), and the XLM contradicts
#             it with a label the memory gives less than t_dispute - the
#             pair goes to work/review.tsv instead of being learned
#          5. 03_record.mnd: whenever the XLM ran, its label is learned,
#             unless the text was known with that label already, OR the
#             teacher's cosine margin was below S1_LEARN (permille) - then the
#             answer is held in work/pending.tsv, not learned (resolve later)
#        One line per request goes to work/decisions.tsv.
# A yes/no question is the labels `yes` (the statement) and `no` (its
# negation, given or generated); a Score question's label names are the ranks.
# The function `decide` is the whole of it; 05_eval.sh sources this file with
# S1_LIB=1 to reuse it.
# ============================================================================
. "$(dirname "$0")/_common.sh"

# decide RISK NAME[=DESCRIPTION]...   (the text is in work/q/text.txt; ordinal=1
# when the names are ranks) -> answer via how t_answer t_xlm xlm_name disputed recorded, and lookup's values
decide() {
  risk=$1; shift
  names=""; reqargs=""
  for a in "$@"; do
    n=${a%%=*}; names="$names $n"
    if [ "${ordinal:-0}" = 1 ]; then reqargs="$reqargs $n=$n"; else reqargs="$reqargs $n"; fi
  done
  lookup "$risk" $reqargs
  best_name=$(name_of "$best"); kbest_name=$(name_of "$kbest")
  answer=""; via=""; how=""; xlm_name=""; xlm_col=""; xlm_cos=""; xlm_margin=""; t_xlm=0; p_xlm=""; disputed=0; recorded=""; held=""
  if [ "$known" = 1 ]; then answer=$kbest_name; via="memory:known"; how=0
  elif [ "$tier" = 2 ]; then answer=$best_name; via="memory:auto"; how=1
  fi
  if [ -z "$answer" ] || [ "${S1_XLM:-}" = always ]; then
    for a in "$@"; do describe "$a"; done
    xlm $names
    if [ -z "$answer" ]; then
      if [ "$tier" = 1 ] && [ "$best" = "$xlm_col" ]; then answer=$best_name; via="memory:verified"; how=2
      else answer=$xlm_name; via="xlm"; how=3; fi
    fi
    p_xlm=$(nth "$p" "$xlm_col")
    if [ "$informed" = 1 ] && [ "$tier" = 2 ] && [ "$best" != "$xlm_col" ] && [ "$p_xlm" -lt "$t_dispute" ]; then disputed=1; fi
    learn=${S1_LEARN:-70}; confident=0
    if [ "${S1_XLM:-}" = always ] || { [ "$tier" = 1 ] && [ "$best" = "$xlm_col" ]; } || [ "${xlm_margin:-0}" -ge "$((learn * 1000))" ]; then confident=1; fi
    if [ "${S1_NO_RECORD:-}" != 1 ]; then
      if [ "$disputed" = 1 ]; then
        printf '%s\t%s\t%s\t%s\t%s\n' "$xlm_name" "$best_name" "$p_best" "$p_xlm" "$(cat work/q/text.txt)" >> work/review.tsv
      elif [ "$known" = 1 ] && [ "$xlm_name" = "$kbest_name" ]; then :
      elif [ "$confident" = 1 ]; then record "$xlm_name"; recorded=$xlm_name
      else held=$((xlm_margin / 1000))
        printf '%s\t%s\t%s\t%s\n' "$xlm_name" "$held" "$(echo $names | tr ' ' '|')" "$(cat work/q/text.txt)" >> work/pending.tsv; fi
    fi
  fi
  t_answer=$t_lookup; [ "$how" -ge 2 ] && t_answer=$((t_lookup + t_xlm))
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$(date +%FT%T)" "$answer" "$via" "$t_answer" "$tier" "$p_best" "${xlm_name:--}" \
    "$([ "$disputed" = 1 ] && echo disputed || echo "${recorded:+recorded:$recorded}")" "$(cat work/q/text.txt)" >> work/decisions.tsv
}

# report -> the transcript of the last decide
report() {
  printf 'memory  %-10s p %s%%o  tier %s (%s)  known %s' "$best_name" "$p_best" "$tier" "$(tiername "$tier")" "$known"
  [ "$known" = 1 ] && printf ' (%s, coverage %s/%s)' "$kbest_name" "$cov_best" "$q"
  printf '   %s ms\n' "$t_lookup"
  [ -n "$xlm_name" ] && printf 'xlm     %-10s cosine %s   %s ms\n' "$xlm_name" "$xlm_cos" "$t_xlm"
  printf 'ANSWER  %-10s via %s in %s ms' "$answer" "$via" "$t_answer"
  [ -n "$recorded" ] && printf '  (recorded as %s)' "$recorded"
  [ -n "$held" ] && printf '  HELD: low teacher confidence (margin %s%%o) -> work/pending.tsv, not learned' "$held"
  [ "$disputed" = 1 ] && printf '  DISPUTED: the memory says %s at %s%%o, the XLM'"'"'s %s has %s%%o -> work/review.tsv, not learned' "$best_name" "$p_best" "$xlm_name" "$p_xlm"
  printf '\n'
}

if [ "${S1_LIB:-}" != 1 ]; then
  need work/memory.dqt "maned-run 00_init_memory.mnd"
  risk=1; kind=choice
  while [ $# -gt 0 ]; do
    case $1 in
      --risk) case ${2:-} in low) risk=0 ;; medium) risk=1 ;; high) risk=2 ;; *) echo "usage: --risk low|medium|high" >&2; exit 1 ;; esac; shift 2 ;;
      --yesno) kind=yesno; shift ;;
      --score) kind=score; shift ;;
      *) break ;;
    esac
  done
  [ $# -ge 2 ] || { echo "usage: $0 [--risk low|medium|high] [--yesno | --score] \"text\" label[=description]..." >&2; exit 1; }
  text=$1; shift
  prep "$text"
  case $kind in
    choice)
      decide "$risk" "$@"; report ;;
    yesno)
      statement=$1
      negation=${2:-"It is not the case that $(printf '%s' "$statement" | cut -c1 | tr 'A-Z' 'a-z')$(printf '%s' "$statement" | cut -c2-)"}
      decide "$risk" "yes=$statement" "no=$negation"; report
      printf 'P(yes)  %s%%o\n' "$(nth "$p" "$(col_of yes)")" ;;
    score)
      for a in "$@"; do case ${a%%=*} in ''|*[!0-9]*) echo "error: a Score question's label names are the ranks: 1=\"...\" 2=\"...\"" >&2; exit 1 ;; esac; done
      ordinal=1 decide "$risk" "$@"; report
      printf 'expected rank %s\n' "$(echo "$expected" | awk '{printf "%.2f", $1 / 1000}')" ;;
  esac
fi
