#!/bin/sh
#
# frame-build.sh: generate the internal assembly frame assets for the
# printable Earth (the assembled frame mesh for the web view, and the
# piece manifest).
#
# Feature: prompts/features/04-assembly-frame.md (planned)
#
# Usage: frame-build.sh [options]   (passed through to the Python module)
#
# Prerequisites: gdalbuildvrt-capable GDAL and python3 with the osgeo and
# numpy modules, plus the ETOPO source tiles under /datasets (read-only).
#
# Generated output (dataflow.out/frame/) must not be edited by hand.
set -eu

DIRECTORY_SCRIPT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$DIRECTORY_SCRIPT/.." && pwd)
SCRIPT_PYTHON="$REPOSITORY_ROOT/scripts/frame_tiles_build.py"
DIRECTORY_LOGS="$REPOSITORY_ROOT/logs"

mkdir -p "$DIRECTORY_LOGS"
TIMESTAMP_FILENAME=$(date +%Y-%m-%d-%H-%M-%S)
FILE_LOG="$DIRECTORY_LOGS/$TIMESTAMP_FILENAME-frame-build.log"
: > "$FILE_LOG"

if ! command -v python3 >/dev/null 2>&1; then
    echo "frame-build: missing tool: python3" >&2
    exit 1
fi

if ! python3 "$SCRIPT_PYTHON" "$@" >>"$FILE_LOG" 2>&1; then
    echo "frame-build: failed (log: $FILE_LOG)" >&2
    tail -n 60 "$FILE_LOG" >&2
    exit 1
fi

echo "frame-build: ok (log: $FILE_LOG)"
exit 0
