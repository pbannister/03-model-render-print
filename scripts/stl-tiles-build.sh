#!/bin/sh
#
# stl-tiles-build.sh: render (or validate) the printable STL tile set of
# the Earth from the ETOPO 2022 source tiles on /datasets.
#
# Feature: prompts/features/03-stl-tiles.md
#
# Usage:
#   stl-tiles-build.sh build [options]   render tiles into dataflow.out/stl/
#   stl-tiles-build.sh check             validate tiles against the manifest
#
# The Python module scripts/stl_tiles_build.py owns the pipeline; this script
# owns the timestamped log file and passes its arguments through.
#
# Prerequisites (build mode): gdalbuildvrt-capable GDAL and python3 with the
# osgeo and numpy modules, plus the ETOPO source tiles under /datasets
# (read-only).  Check mode needs only python3.
#
# Generated output (dataflow.out/stl/) must not be edited by hand.
set -eu

DIRECTORY_SCRIPT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$DIRECTORY_SCRIPT/.." && pwd)
SCRIPT_PYTHON="$REPOSITORY_ROOT/scripts/stl_tiles_build.py"
DIRECTORY_LOGS="$REPOSITORY_ROOT/logs"

mkdir -p "$DIRECTORY_LOGS"
TIMESTAMP_FILENAME=$(date +%Y-%m-%d-%H-%M-%S)
FILE_LOG="$DIRECTORY_LOGS/$TIMESTAMP_FILENAME-stl-tiles-build.log"
: > "$FILE_LOG"

if ! command -v python3 >/dev/null 2>&1; then
    echo "stl-tiles-build: missing tool: python3" >&2
    exit 1
fi

if ! python3 "$SCRIPT_PYTHON" "$@" >>"$FILE_LOG" 2>&1; then
    echo "stl-tiles-build: failed (log: $FILE_LOG)" >&2
    tail -n 60 "$FILE_LOG" >&2
    exit 1
fi

echo "stl-tiles-build: ok (log: $FILE_LOG)"
exit 0
