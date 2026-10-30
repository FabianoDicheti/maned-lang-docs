#!/bin/sh
# ============================================================================
# 02_xlm_classify.sh -- the slow lane alone: text + labels -> the nearest label, on the worker
# ----------------------------------------------------------------------------
# usage: ./02_xlm_classify.sh "Bitte bis Freitag den Vertrag prüfen" urgent later careful
#        ./02_xlm_classify.sh "text" spam="unsolicited advertising or a scam" ham="a normal message"
#
# needs: work/xlm-stats.dqt (00_download.sh), the worker (. ~/.config/maned/xlm.env)
# does:  registers the labels' descriptions once (02_label_embed.mnd on the
#        worker: the text after '=', else corpus/labels.tsv's lines for the
#        name, else the name itself), runs 02_xlm_classify.mnd; prints the
#        label, the cosine and the time.
# ============================================================================
. "$(dirname "$0")/_common.sh"
need work/xlm-stats.dqt "./00_download.sh"
[ $# -ge 2 ] || { echo "usage: $0 \"text\" label[=description] label..." >&2; exit 1; }
text=$1; shift
prep "$text"
names=""
for a in "$@"; do describe "$a"; names="$names ${a%%=*}"; done
xlm $names
printf 'xlm     %-10s cosine %s  (%s descriptions compared)\n' "$xlm_name" "$xlm_cos" "$(grep -c . work/descs.tsv)"
printf '%s ms (process start, tokenizing, the worker, the cosines)\n' "$t_xlm"
