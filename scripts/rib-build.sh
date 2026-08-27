#!/bin/sh
#
# rib-build.sh: generate the rib + first-row assembly visualization assets
# for the printable Earth (the assembled rib/first-row mesh for the web
# view, and a small piece manifest).
#
# Usage: rib-build.sh [options]   (passed through to the Python module)
#
# Generated output (dataflow.out/rib/) must not be edited by hand.
set -eu

DIRECTORY_SCRIPT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$DIRECTORY_SCRIPT/.." && pwd)
SCRIPT_PYTHON="$REPOSITORY_ROOT/scripts/rib_firstrow_build.py"
DIRECTORY_LOGS="$REPOSITORY_ROOT/logs"

mkdir -p "$DIRECTORY_LOGS"
TIMESTAMP_FILENAME=$(date +%Y-%m-%d-%H-%M-%S)
FILE_LOG="$DIRECTORY_LOGS/$TIMESTAMP_FILENAME-rib-build.log"
: > "$FILE_LOG"

if ! command -v python3 >/dev/null 2>&1; then
    echo "rib-build: missing tool: python3" >&2
    exit 1
fi

if ! python3 "$SCRIPT_PYTHON" "$@" >>"$FILE_LOG" 2>&1; then
    echo "rib-build: failed (log: $FILE_LOG)" >&2
    tail -n 60 "$FILE_LOG" >&2
    exit 1
fi

echo "rib-build: ok (log: $FILE_LOG)"
exit 0
