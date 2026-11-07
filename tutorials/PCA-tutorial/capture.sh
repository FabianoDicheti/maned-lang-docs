#!/bin/sh
# Capture the outputs the tutorial page shows, into work/out/. Optional: the page
# generator reads these files, so every output on the page is from a real run.
#
#   sh capture.sh               needs maned-run, maned-serve, curl; ports 8090-8091 free
#
# Long lines are cut at 150 characters and end in " …", so a 231-number model
# descriptor doesn't take over the page.
#
# The 11 example images come from check/expected.dqt, already gray and 128x128, so
# this needs no browser. maned-run and maned-serve are taken from $MANED_RUN and
# $MANED_SERVE, then this workspace, then PATH.
set -eu
LC_ALL=C
export LC_ALL
cd "$(dirname "$0")"
HERE=$(pwd)
OUT="$HERE/work/out"
mkdir -p "$OUT"

tool() {   # the variable's value, else this workspace's build, else PATH
  if [ -n "$1" ]; then echo "$1"
  elif [ -x "$HERE/../../../$2" ]; then echo "$(cd "$HERE/../../.." && pwd)/$2"
  else echo "$2"; fi
}
MANED_RUN=$(tool "${MANED_RUN:-}" maned-run)
MANED_SERVE=$(tool "${MANED_SERVE:-}" maned-serve)

WORK=$(mktemp -d)
cleanup() {   # keeps the script's own exit status, not a killed server's
  status=$?
  for pid in ${FEATURES_PID:-} ${PCA_PID:-}; do
    kill "$pid" 2>/dev/null && { wait "$pid" 2>/dev/null || true; }
  done
  rm -rf "$WORK"
  exit "$status"
}
trap cleanup EXIT
cp features.mnd pca.mnd check/expected.dqt "$WORK"
cd "$WORK"

# One image through features.mnd, then all eleven.
: > rows.csv
i=0
while [ "$i" -lt 11 ]; do
  sed "s|^in::gray = csv();.*|in::gray = dqt(\"expected.dqt\", \"img$i\");|" features.mnd > one.mnd
  if [ "$i" = 0 ]; then
    "$MANED_RUN" one.mnd > "$OUT/features_one.txt"
  else
    "$MANED_RUN" one.mnd > /dev/null
  fi
  cat row.csv >> rows.csv
  i=$((i + 1))
done

# pca.mnd reads decimals; the features are integers x1000.
awk -F, '{ for (k = 1; k <= NF; k++) printf "%.3f%s", $k / 1000, (k < NF ? "," : "\n") }' \
  rows.csv > x.csv
sed 's|^in::x = csv();.*|in::x = csv("x.csv");|' pca.mnd > one.mnd
"$MANED_RUN" one.mnd > "$OUT/pca_run.txt"

# The same two programs as HTTP services, as the page calls them.
cat > gray.mnd <<'E'
mnd::quantmax=2000000000;
mnd::quantmin=-2000000000;
mnd::quantres=0;
in::g = dqt("expected.dqt", "img0");
calc::lambda_flow f(g) {
    g 1 scalar_mul gray =
} return gray;
out::gray = csv("gray.csv");
E
"$MANED_RUN" gray.mnd > /dev/null
awk 'BEGIN { printf "{\"gray\": [" } { printf "%s[%s]", (NR > 1 ? "," : ""), $0 } END { print "]}" }' \
  gray.csv > gray.json
awk 'BEGIN { printf "{\"x\": [" } { printf "%s[%s]", (NR > 1 ? "," : ""), $0 } END { print "]}" }' \
  x.csv > x.json

cp "$HERE/features.mnd" "$HERE/pca.mnd" .
"$MANED_SERVE" features.mnd --port 8090 > features.log 2>&1 &
FEATURES_PID=$!
"$MANED_SERVE" pca.mnd --port 8091 > pca.log 2>&1 &
PCA_PID=$!
tries=0
until curl -s -m 1 localhost:8090/health > /dev/null && curl -s -m 1 localhost:8091/health > /dev/null; do
  tries=$((tries + 1))
  [ "$tries" -lt 50 ] || { echo "capture.sh: the servers did not start" >&2; exit 1; }
  sleep 1
done
curl -s localhost:8090/run.json -d @gray.json > "$OUT/features_http.txt"
echo >> "$OUT/features_http.txt"
curl -s localhost:8091/run.json -d @x.json > "$OUT/pca_http.txt"
echo >> "$OUT/pca_http.txt"

cd "$HERE"
sh check/check.sh > "$OUT/check.txt"

for f in "$OUT"/*.txt; do
  awk '{ if (length($0) > 150) print substr($0, 1, 150) " …"; else print }' "$f" > "$f.cut"
  mv "$f.cut" "$f"
done
echo "captured into work/out: $(ls "$OUT" | tr '\n' ' ')"
