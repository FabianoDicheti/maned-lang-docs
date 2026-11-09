#!/bin/sh
# ============================================================================
# _common.sh -- the shell every step shares (sourced, not run)
# ----------------------------------------------------------------------------
# Every number in this project comes out of a .mnd program: tokenizing, the
# memory lookup (features, the known-text check, the judge, the tier), the
# record, the label embeddings and the cosine classification on the worker,
# the eval metrics and its checks. The shell does what the language has no
# type for: the text of a request, the names of the labels, appending a line
# to a file, starting a process, reading the clock. Each function below is
# one of those.
#
# Every .mnd uses paths RELATIVE to this folder (work/...), so each step cd's
# here first. All generated files land in work/ (gitignored).
#
# Before any step that talks to the worker, source the private env file:
#     . ~/.config/maned/xlm.env        (mode 600: XLM_USER, XLM_PASS, S1_WORKER_HOST)
# The device blocks read all three with env(); a missing one is maned's E035.
# MANED_RUN / MANED_SERVE override the tools found on your PATH.
# ============================================================================
set -eu
export LC_ALL=C   # numbers print with a dot, whatever the user's locale

HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"
MANED_RUN=${MANED_RUN:-$(command -v maned-run || true)}
[ -n "$MANED_RUN" ] && [ -x "$MANED_RUN" ] || { echo "error: maned-run not found on PATH (install Maned 0.4.2 or newer, or set MANED_RUN=)" >&2; exit 1; }
export MANED_RUN
mkdir -p work/q/out work/ranges
TAB=$(printf '\t')

# ---- running a program
# run_mnd PROGRAM.mnd -> runs it, keeps the log in work/PROGRAM.log, stops on failure
run_mnd() {
  log="work/$(basename "$1" .mnd).log"
  "$MANED_RUN" "$1" > "$log" 2>&1 || { echo "error: $1 failed; log follows" >&2; cat "$log" >&2; exit 1; }
}
# val NAME -> the values of flow output NAME in the last log, space separated.
# The log prints raw integers: a permille 955 is "955", a count is itself.
val() { sed -n "s/^$1 : \[[^]]*\] = \[\(.*\)\]\$/\1/p" "$log" | tr -d ','; }
# nth "VALUES" I -> the I-th value (0-based)
nth() { echo "$1" | awk -v i="$2" '{print $(i + 1)}'; }
# tiername TIER -> review / verify / auto
tiername() { case $1 in 2) echo auto ;; 1) echo verify ;; *) echo review ;; esac; }
# need FILE STEP -> stop with a hint when an earlier step has not run yet
need() { [ -f "$1" ] || { echo "error: $1 is missing - run $2 first" >&2; exit 1; }; }
# ms -> the wall clock in milliseconds
ms() { perl -MTime::HiRes=time -e 'printf "%d\n", time*1000'; }

# ---- the label registry: work/labels.tsv, line i = memory column i
col_of() {   # col_of NAME -> its column, registering a new name
  touch work/labels.tsv
  n=$(grep -nxF -- "$1" work/labels.tsv | head -1 | cut -d: -f1)
  if [ -z "$n" ]; then
    [ "$(grep -c . work/labels.tsv)" -lt 32 ] || { echo "error: the memory's 32 label columns are all taken" >&2; exit 1; }
    printf '%s\n' "$1" >> work/labels.tsv
    n=$(grep -c . work/labels.tsv)
  fi
  echo $((n - 1))
}
name_of() { sed -n "$(( $1 + 1 ))p" work/labels.tsv; }   # column -> name

# ---- descriptions, for the XLM path. Each (label, description) is embedded
# ONCE on the worker (02_label_embed.mnd) and appended to work/descs.tsv
# (name<TAB>description, row i) and work/labels_u.csv (its unit vector, row i).
DESCS=work/descs.tsv
register_desc() {   # register_desc NAME DESCRIPTION
  touch "$DESCS" work/labels_u.csv
  grep -qxF -- "$1$TAB$2" "$DESCS" && return 0
  printf '%s\n' "$2" > work/q/new_descs.txt
  run_mnd 02_label_embed.mnd
  cat work/q/new_u.csv >> work/labels_u.csv
  printf '%s\t%s\n' "$1" "$2" >> work/descs.tsv
}
# describe NAME[=DESCRIPTION] -> registers the label's description(s): the one
# given after '=', else the lines of corpus/labels.tsv for it, else the name itself
describe() {
  name=${1%%=*}
  case $1 in
    *=*) register_desc "$name" "${1#*=}" ;;
    *) if grep -q "^$name$TAB" corpus/labels.tsv; then
         grep "^$name$TAB" corpus/labels.tsv | cut -f2 > work/q/descs_of.txt
         while IFS= read -r d; do register_desc "$name" "$d"; done < work/q/descs_of.txt
       else register_desc "$name" "$name"; fi ;;
  esac
}

# ---- the request files under work/q/
# prep TEXT -> work/q/text.txt, one line
prep() { printf '%s\n' "$(printf '%s' "$1" | tr '\n' ' ')" > work/q/text.txt; }
# req RISK NAME[=RANK]... -> work/q/req.csv: row 0 the candidate columns, row 1
# their ranks (Score questions), row 2 the risk level in column 0, row 3 zeros
req() {
  risk=$1; shift
  spec=""
  for a in "$@"; do
    name=${a%%=*}; rank=0
    case $a in *=*) rank=${a#*=} ;; esac
    spec="$spec $(col_of "$name"):$rank"
  done
  echo "$spec" | awk -v risk="$risk" '{
    for (i = 0; i < 32; i++) { c[i] = 0; o[i] = 0 }
    for (i = 1; i <= NF; i++) { split($i, a, ":"); c[a[1]] = 1; o[a[1]] = a[2] }
    for (i = 0; i < 32; i++) printf "%d%s", c[i], (i < 31 ? "," : "\n")
    for (i = 0; i < 32; i++) printf "%d%s", o[i], (i < 31 ? "," : "\n")
    printf "%d", risk; for (i = 1; i < 32; i++) printf ",0"; printf "\n"
    for (i = 0; i < 32; i++) printf "0%s", (i < 31 ? "," : "\n") }' > work/q/req.csv
}
# cand_d NAME... -> work/q/cand_d.csv: 1 for the description rows of the
# candidates, 0 elsewhere (written as 0.001 so it lands as raw 1 at quantres 3)
cand_d() {
  cut -f1 "$DESCS" | awk -v names=" $* " '{
    printf "%s%s", (NR > 1 ? "," : ""), (index(names, " " $1 " ") ? "0.001" : "0.000") } END { print "" }' > work/q/cand_d.csv
}

# ---- the three moves of the loop (the text is in work/q/text.txt)
# lookup RISK NAME[=RANK]... -> best p_best margin tier known kbest cov_best cov_second q t_dispute informed p t_lookup
lookup() {
  req "$@"
  t0=$(ms); run_mnd 01_lookup.mnd; t_lookup=$(( $(ms) - t0 ))
  best=$(val best); p_best=$(val p_best); margin=$(val margin); tier=$(val tier); known=$(val known)
  kbest=$(val kbest); cov_best=$(val cov_best); cov_second=$(val cov_second); q=$(val q)
  t_dispute=$(val t_dispute); informed=$(val informed); expected=$(val expected); p=$(val p)
}
# xlm NAME... -> xlm_col xlm_name xlm_cos xlm_margin t_xlm   (the worker; descriptions registered first)
xlm() {
  cand_d "$@"
  t0=$(ms); run_mnd 02_xlm_classify.mnd; t_xlm=$(( $(ms) - t0 ))
  row=$(val best)
  xlm_name=$(sed -n "$((row + 1))p" "$DESCS" | cut -f1)
  xlm_col=$(col_of "$xlm_name")
  xlm_cos=$(nth "$(val s)" "$row" | awk '{printf "%.3f", $1 / 1000000}')
  # the teacher's confidence: the cosine margin (x10^6) between the best and the
  # second-best candidate LABEL (max cosine over each label's description rows)
  xlm_margin=$(awk -v names=" $* " -v s="$(val s)" '
    BEGIN { split(s, sc, " ") }
    index(names, " " $1 " ") { if (!($1 in m) || sc[FNR] > m[$1]) m[$1] = sc[FNR] }
    END { n = 0; for (k in m) v[n++] = m[k]
          for (i = 0; i < n; i++) for (j = i + 1; j < n; j++) if (v[j] > v[i]) { t = v[i]; v[i] = v[j]; v[j] = t }
          print (n >= 2 ? v[0] - v[1] : 1000000000) }' "$DESCS")
}
# record NAME -> the memory learns (text, NAME): work/memory.dqt is rewritten by
# the program, and one line goes to work/memory.tsv, the dataset
record() {
  col_of "$1" > work/q/label.csv
  run_mnd 03_record.mnd
  printf '%s\t%s\n' "$1" "$(cat work/q/text.txt)" >> work/memory.tsv
}
