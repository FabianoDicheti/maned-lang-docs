#!/bin/sh
# Start the backend: two maned-serve processes, one script each, and the page.
#   features.mnd on :8090, which also serves web/
#   pca.mnd      on :8091, which the page reaches by CORS
#
#   sh serve.sh                 then open http://localhost:8090
#
# maned-serve is taken from $MANED_SERVE, then this workspace, then PATH. It needs
# Maned 0.4.3 or newer, for --static and --cors. A browser keeps connections open, and each one
# holds a worker, hence --workers.
set -e
cd "$(dirname "$0")"

MANED_SERVE="${MANED_SERVE:-}"
if [ -z "$MANED_SERVE" ]; then
  if [ -x ../../../maned-serve ]; then MANED_SERVE=../../../maned-serve
  else MANED_SERVE=maned-serve; fi
fi

"$MANED_SERVE" features.mnd --port 8090 --workers 8 --static web &
FEATURES=$!
"$MANED_SERVE" pca.mnd --port 8091 --workers 8 --cors http://localhost:8090 &
PCA=$!
trap 'kill "$FEATURES" "$PCA" 2>/dev/null' INT TERM EXIT

echo "open http://localhost:8090"
wait
