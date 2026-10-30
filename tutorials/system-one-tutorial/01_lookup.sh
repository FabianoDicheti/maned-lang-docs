#!/bin/sh
# ============================================================================
# 01_lookup.sh -- the fast lane alone: what the memory says about a text
# ----------------------------------------------------------------------------
# usage: ./01_lookup.sh [--risk low|medium|high] "Attention: the server is down" urgent later careful
#
# needs: the memory (maned-run 00_init_memory.mnd); no worker involved
# prints: the known-text lane (known 0/1, its label, coverage = the text's
#         features seen under that label / all its features, the runner-up's),
#         the judge (label, p in permille, margin, tier for the risk level),
#         p for every candidate, and the time
# ============================================================================
. "$(dirname "$0")/_common.sh"
need work/memory.dqt "maned-run 00_init_memory.mnd"
risk=1
if [ "${1:-}" = "--risk" ]; then
  case ${2:-} in low) risk=0 ;; medium) risk=1 ;; high) risk=2 ;; *) echo "usage: --risk low|medium|high" >&2; exit 1 ;; esac
  shift 2
fi
[ $# -ge 2 ] || { echo "usage: $0 [--risk low|medium|high] \"text\" label label..." >&2; exit 1; }
text=$1; shift
prep "$text"
lookup "$risk" "$@"
printf 'known   %s  %-10s coverage %s/%s features, runner-up %s\n' "$known" "$(name_of "$kbest")" "$cov_best" "$q" "$cov_second"
printf 'judge   %-10s p %s%%o  margin %s%%o  tier %s (%s)  [%s texts in memory%s]\n' \
  "$(name_of "$best")" "$p_best" "$margin" "$tier" "$(tiername "$tier")" "$(grep -c . work/memory.tsv 2>/dev/null || echo 0)" "$([ "$informed" = 1 ] && echo ', informed' || echo '')"
printf 'p      '
for a in "$@"; do printf ' %s %s%%o' "${a%%=*}" "$(nth "$p" "$(col_of "${a%%=*}")")"; done
printf '\n%s ms (process start, tokenizing, the lookup)\n' "$t_lookup"
