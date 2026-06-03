#!/usr/bin/env bash
# Kick off a full 50-state + DC buildings PMTiles build and upload.
#
# Runs prepare_buildings_pmtiles.py in the background, tees per-state output
# to a timestamped log under data/out/logs/, and prints the log path + PID
# so you can tail/disown.
#
# Usage:
#   ./buildings/run_all_states.sh                 # default bucket: prefire-data
#   ./buildings/run_all_states.sh my-bucket       # override
#   ./buildings/run_all_states.sh prefire-data --skip-upload   # dry run
#
# Tail with:   tail -f data/out/logs/buildings-<timestamp>.log

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$(dirname "$SCRIPT_DIR")"
cd "$DATA_DIR"

BUCKET="${1:-prefire-data}"
shift || true

TS="$(date +%Y%m%d-%H%M%S)"
WORK_DIR="out/buildings-${TS}"
LOG_DIR="out/logs"
LOG="${LOG_DIR}/buildings-${TS}.log"
mkdir -p "$WORK_DIR" "$LOG_DIR"

echo "bucket:   $BUCKET"
echo "workdir:  $DATA_DIR/$WORK_DIR"
echo "log:      $DATA_DIR/$LOG"
echo

# /usr/bin/time -p prints real/user/sys at the end.
nohup /usr/bin/env bash -c "
  /usr/bin/time -p ./buildings/prepare_buildings_pmtiles.py \
    --bucket '$BUCKET' \
    --workdir '$WORK_DIR' \
    $* 2>&1
" > "$LOG" 2>&1 &

PID=$!
echo "started pid $PID"
echo "tail -f $DATA_DIR/$LOG"
