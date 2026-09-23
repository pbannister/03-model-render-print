#!/bin/sh
#
# step-build.sh: export the tile set as STEP files for CAD work.
#
# Feature: documents/05-stl-approach.md
#
# Usage: step-build.sh [options]   (options pass through to tiles_step.py)
#
# The tiles are exported in their assembled orientation: each solid sits at
# its world position in the globe, with its own local frame, exactly as it
# does when the printed tiles are glued together.  Nothing is flattened for
# printing -- the print-ready orientation lives in the STL files instead.
#
# Generated output (dataflow.out/step/) must not be edited by hand:
#   tiles-all.step          all 42 tiles, one named solid each
#   tiles-north.step        one hemisphere (--hemisphere north|south)
#   tiles-selected.step     just the tiles named with --tile
#   tiles/tile-<id>.step    one file per exported tile
#
# Prerequisites: gdalbuildvrt-capable GDAL and python3 with the osgeo and
# numpy modules, plus the ETOPO source tiles under /datasets (read-only).
set -eu

DIRECTORY_SCRIPT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$DIRECTORY_SCRIPT/.." && pwd)
SCRIPT_PYTHON="$REPOSITORY_ROOT/scripts/tiles_step.py"
DIRECTORY_LOGS="$REPOSITORY_ROOT/logs"

mkdir -p "$DIRECTORY_LOGS"
TIMESTAMP_FILENAME=$(date +%Y-%m-%d-%H-%M-%S)
FILE_LOG="$DIRECTORY_LOGS/$TIMESTAMP_FILENAME-step-build.log"
: > "$FILE_LOG"

if ! command -v python3 >/dev/null 2>&1; then
    echo "step-build: missing tool: python3" >&2
    exit 1
fi

if ! python3 "$SCRIPT_PYTHON" "$@" >>"$FILE_LOG" 2>&1; then
    echo "step-build: failed (log: $FILE_LOG)" >&2
    tail -n 60 "$FILE_LOG" >&2
    exit 1
fi

cat "$FILE_LOG"
echo "step-build: ok (log: $FILE_LOG)"
exit 0
