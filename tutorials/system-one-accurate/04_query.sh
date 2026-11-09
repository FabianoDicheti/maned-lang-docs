#!/bin/sh
# ============================================================================
# 04_query.sh -- the loop, accuracy edition: the cache; the prototype judge; the entailment teacher; learn what both agree on
# ----------------------------------------------------------------------------
# usage: ./04_query.sh [--risk low|medium|high] "Bitte bis Freitag den Vertrag prüfen" urgent later careful
#        ./04_query.sh "text" spam="unsolicited advertising or a scam" ham="a normal message"
#        ./04_query.sh --yesno "Please wire the deposit today." "This message asks for money to be sent" ["its negation"]
#        ./04_query.sh --score "The kitchen will be repainted next spring." 1="no action" 2="look this week" 3="act today"
#        S1_NO_RECORD=1 ./04_query.sh ...      ask, do not learn
#        S1_LEARN=250 ./04_query.sh ...        min NLI margin (permille of P(entail)) to learn
#        S1_LEARN_RULE=agree|nli|all           what is learned: `agree` (default) the NLI label when the XLM-R
#                                              zero-shot verdict (the anchor) AGREES and the margin clears S1_LEARN;
#                                              `nli` the NLI label above S1_LEARN alone; `all` every NLI label
#        S1_XLM=always ./04_query.sh ...       TRAINING MODE: both lanes run on every request (the answer
#                                              does not change); the learn rule still applies. 05_eval.sh measures in it
#        S1_SELF_LEARN=1 ./04_query.sh ...     also learn an answer the prototype judge gave alone (off: the
#                                              judge never teaches itself)
#
# needs: both memories (./00_setup.sh), both workers (. ~/.config/maned/xlm.env; . ~/.config/maned/nli.env)
# does:  one request, in order:
#          1. 01_lookup.mnd         the count memory: KNOWN text? Then its label answers in ~8 ms
#             (the count judge's tier is reported but no longer decides: it does not generalise)
#          2. 02_proto_classify.mnd one XLM-R embedding on the worker; the prototype judge scores it
#             against the learned centroids (warm-started with the label anchors). Cosine margin
#             >= t_auto AND at least min_n texts learned under the winning label (proto_policy.csv,
#             per risk): the judge answers, "proto:auto"; until then every unseen text is taught
#          3. otherwise the entailment worker (nli/nli_lane.py + 02_nli_classify.mnd) tests every
#             candidate hypothesis: the most entailed one answers, "nli"
#          4. learn: whenever the NLI ran, its label goes into BOTH memories (03_record.mnd,
#             03_record_proto.mnd) when the rule holds - by default when the XLM-R zero-shot verdict
#             (the anchor the judge was computed alongside) agrees with it and its margin clears
#             S1_LEARN. Gating on the judge's OWN verdict instead was measured to feed it its own
#             answers: 63 % label precision and a judge that stops growing. Otherwise the answer is held in
#             work/pending.tsv with both verdicts and the text's vector (resolve later: decide.py --resolve)
#        One line per request goes to work/decisions.tsv.
# A yes/no question is the labels `yes` (the statement) and `no` (its
# negation, given or generated); a Score question's label names are the ranks.
# The function `decide` is the whole of it; 05_eval.sh sources this file with
# S1_LIB=1 to reuse it.
# ============================================================================
. "$(dirname "$0")/_common.sh"

# decide RISK NAME[=DESCRIPTION]...   (the text is in work/q/text.txt; ordinal=1 when the names are ranks)
# -> answer via how t_answer, the lookup's values, anchor_* proto_* nli_* when they ran, and for the
#    trace: xlm_name xlm_col xlm_cos xlm_margin t_xlm p_xlm = the teacher (the NLI when it ran), recorded held
decide() {
  risk=$1; shift
  names=""; reqargs=""
  for a in "$@"; do
    n=${a%%=*}; names="$names $n"
    if [ "${ordinal:-0}" = 1 ]; then reqargs="$reqargs $n=$n"; else reqargs="$reqargs $n"; fi
  done
  lookup "$risk" $reqargs
  best_name=$(name_of "$best"); kbest_name=$(name_of "$kbest")
  answer=""; via=""; how=""; recorded=""; held=""; disputed=0
  anchor_name=""; proto_name=""; proto_margin=""; proto_tier=""; proto_n=""; nli_name=""; nli_margin=""; agree=""
  xlm_name=""; xlm_col=""; xlm_cos=""; xlm_margin=""; p_xlm=""; t_proto=0; t_nli=0; t_xlm=0
  : > work/q/u.csv
  if [ "$known" = 1 ]; then answer=$kbest_name; via="memory:known"; how=0; fi
  if [ -z "$answer" ] || [ "${S1_XLM:-}" = always ]; then
    for a in "$@"; do describe "$a"; done
    proto $names
    if [ -z "$answer" ] && [ "$proto_tier" = 2 ]; then answer=$proto_name; via="proto:auto"; how=4; fi
    if [ -z "$answer" ] || [ "${S1_XLM:-}" = always ]; then
      nli $names
      [ -z "$answer" ] && { answer=$nli_name; via="nli"; how=3; }
      agree=0; [ "$anchor_name" = "$nli_name" ] && agree=1   # the ANCHOR verdict: fixed, so the gate cannot feed the judge its own answers
      xlm_name=$nli_name; xlm_col=$nli_col; xlm_cos=$nli_p; xlm_margin=$nli_margin
      learn=${S1_LEARN:-250}; confident=0
      case ${S1_LEARN_RULE:-agree} in
        agree) [ "$agree" = 1 ] && [ "$nli_margin" -ge "$((learn * 1000))" ] && confident=1 ;;
        nli)   [ "$nli_margin" -ge "$((learn * 1000))" ] && confident=1 ;;
        all)   confident=1 ;;
        *) echo "error: S1_LEARN_RULE must be agree, nli or all" >&2; exit 1 ;;
      esac
      if [ "${S1_NO_RECORD:-}" != 1 ]; then
        if [ "$known" = 1 ] && [ "$nli_name" = "$kbest_name" ]; then :
        elif [ "$confident" = 1 ]; then record_both "$nli_name"; recorded=$nli_name
        else held=$((nli_margin / 1000))
          printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$nli_name" "$held" "$proto_name" "$(echo $names | tr ' ' '|')" "$(cat work/q/text.txt)" "$(cat work/q/u.csv)" >> work/pending.tsv; fi
      fi
    elif [ "${S1_SELF_LEARN:-0}" = 1 ] && [ "${S1_NO_RECORD:-}" != 1 ]; then
      record_both "$proto_name"; recorded=$proto_name
    fi
    [ -n "$xlm_name" ] || { xlm_name=$anchor_name; xlm_col=$anchor_col; xlm_cos=$anchor_cos; xlm_margin=$anchor_margin; }
    p_xlm=$(nth "$p" "$xlm_col")
  fi
  t_xlm=$((t_proto + t_nli))
  t_answer=$t_lookup
  case $how in 4) t_answer=$((t_lookup + t_proto)) ;; 3) t_answer=$((t_lookup + t_proto + t_nli)) ;; esac
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$(date +%FT%T)" "$answer" "$via" "$t_answer" "$tier" "$p_best" "${xlm_name:--}" \
    "${recorded:+recorded:$recorded}" "$(cat work/q/text.txt)" >> work/decisions.tsv
}

# report -> the transcript of the last decide
report() {
  printf 'memory  %-10s p %s%%o  tier %s (%s)  known %s' "$best_name" "$p_best" "$tier" "$(tiername "$tier")" "$known"
  [ "$known" = 1 ] && printf ' (%s, coverage %s/%s)' "$kbest_name" "$cov_best" "$q"
  printf '   %s ms\n' "$t_lookup"
  [ -n "$proto_name" ] && printf 'proto   %-10s cos %s  margin %s%%o  tier %s (%s)  from %s texts   anchor %s (cos %s)   %s ms\n' \
    "$proto_name" "$proto_cos" "$((proto_margin / 1000))" "$proto_tier" "$(tiername "$proto_tier")" "$proto_n" "$anchor_name" "$anchor_cos" "$t_proto"
  [ -n "$nli_name" ] && printf 'nli     %-10s P(entail) %s  margin %s%%o   %s   %s ms\n' \
    "$nli_name" "$nli_p" "$((nli_margin / 1000))" "$([ "$agree" = 1 ] && echo AGREE || echo DISAGREE)" "$t_nli"
  printf 'ANSWER  %-10s via %s in %s ms' "$answer" "$via" "$t_answer"
  [ -n "$recorded" ] && printf '  (recorded as %s)' "$recorded"
  [ -n "$held" ] && printf '  HELD: %s (NLI margin %s%%o) -> work/pending.tsv, not learned' \
    "$([ "$agree" = 1 ] && echo 'low teacher confidence' || echo 'the two lanes disagree')" "$held"
  printf '\n'
}

if [ "${S1_LIB:-}" != 1 ]; then
  need work/memory.dqt "./00_setup.sh"
  need work/protos.dqt "./00_setup.sh"
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
