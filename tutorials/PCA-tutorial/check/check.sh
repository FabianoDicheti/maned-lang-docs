#!/bin/sh
# Check the app against numpy's answers, with only maned and a shell. It runs
# features.mnd and pca.mnd on the images in expected.dqt, then:
#   check_features.mnd, check_pca.mnd   the results against numpy's
#   check_fft.mnd, check_pca.mnd        properties that hold with no reference
#
#   sh check/check.sh           exit status 0 only if every check passes
#
# maned-run is taken from $MANED_RUN, then this workspace, then PATH.
set -eu
# awk formats numbers by locale, and a decimal comma would split every csv column.
LC_ALL=C
export LC_ALL
cd "$(dirname "$0")"
HERE=$(pwd)

MANED_RUN="${MANED_RUN:-}"
if [ -z "$MANED_RUN" ]; then
  if [ -x ../../../../maned-run ]; then MANED_RUN=$(cd ../../../.. && pwd)/maned-run
  else MANED_RUN=maned-run; fi
fi

# maned-run writes each out:: file into the current folder, so it works in its own.
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cp "$HERE"/*.mnd "$HERE"/*.dqt "$HERE"/../features.mnd "$HERE"/../pca.mnd "$WORK"
cd "$WORK"

failed=0
report() {   # a name, then the text 0 if it passed
  if [ "$2" = "0" ]; then echo "ok    $1"; else echo "FAIL  $1"; failed=1; fi
}

: > got_features.csv
: > fft_fails.csv
i=0
while [ "$i" -lt 11 ]; do
  sed "s|^in::gray = csv();.*|in::gray = dqt(\"expected.dqt\", \"img$i\");|" features.mnd > one.mnd
  "$MANED_RUN" one.mnd > run.log
  cat row.csv >> got_features.csv
  sed "s|IMG|img$i|" check_fft.mnd > one_fft.mnd
  "$MANED_RUN" one_fft.mnd > run.log
  cat fails.csv >> fft_fails.csv
  i=$((i + 1))
done

"$MANED_RUN" check_features.mnd > features.log
grep '^worst' features.log
report "features match numpy" "$(cat fails.csv)"
report "fft2d keeps each image's energy" "$(sort -u fft_fails.csv)"

# pca.mnd reads decimals, and the features are integers x1000.
awk -F, '{ for (k = 1; k <= NF; k++) printf "%.3f%s", $k / 1000, (k < NF ? "," : "\n") }' \
  got_features.csv > got_x.csv
sed 's|^in::x = csv();.*|in::x = csv("got_x.csv");|' pca.mnd > one.mnd
"$MANED_RUN" one.mnd > run.log
"$MANED_RUN" check_pca.mnd > pca.log
grep -E '^(e_|explained_sum)' pca.log
# Written at quantres 3, so a clean run can read 0.000.
report "PCA matches numpy, and obeys what any PCA must" "$(awk '{ print $1 + 0 }' fails_scaled.csv)"

if [ "$failed" = 0 ]; then echo "RESULT: all checks passed"; else echo "RESULT: FAILED"; exit 1; fi
