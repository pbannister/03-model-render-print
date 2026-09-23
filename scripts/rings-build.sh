#!/bin/sh
#
# rings-build.sh: render the print-in-place support ring lattice that the
# printable Earth's tiles are assembled onto.
#
# Feature: prompts/features/05-stl-approach.md (documents/05-stl-approach.md)
#
# Usage: rings-build.sh [options]
#
# Both hemispheres are rendered, north first.  Options are passed through to
# scripts/rings_build.py; --hemisphere is managed here.
#
# Generated output (dataflow.out/rings/) must not be edited by hand:
#   ring-<band>-<hemisphere>.stl    one horizontal ring per latitude band
#   meridian-<nn>-<hemisphere>.stl  one arc per meridian
#   cap-stem-<hemisphere>.stl       pole post and spokes
#   rings-<hemisphere>.obj          assembled pieces, for the web viewer
#   rings-<hemisphere>.json         per-piece manifest
#
# Prerequisites: gdalbuildvrt-capable GDAL and python3 with the osgeo and
# numpy modules, plus the ETOPO source tiles under /datasets (read-only).
set -eu

DIRECTORY_SCRIPT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$DIRECTORY_SCRIPT/.." && pwd)
SCRIPT_PYTHON="$REPOSITORY_ROOT/scripts/rings_build.py"
DIRECTORY_LOGS="$REPOSITORY_ROOT/logs"

mkdir -p "$DIRECTORY_LOGS"
TIMESTAMP_FILENAME=$(date +%Y-%m-%d-%H-%M-%S)
FILE_LOG="$DIRECTORY_LOGS/$TIMESTAMP_FILENAME-rings-build.log"
: > "$FILE_LOG"

if ! command -v python3 >/dev/null 2>&1; then
    echo "rings-build: missing tool: python3" >&2
    exit 1
fi

for hemisphere_name in north south; do
    if ! python3 "$SCRIPT_PYTHON" --hemisphere "$hemisphere_name" "$@" \
            >>"$FILE_LOG" 2>&1; then
        echo "rings-build: failed ($hemisphere_name; log: $FILE_LOG)" >&2
        tail -n 60 "$FILE_LOG" >&2
        exit 1
    fi
done

echo "rings-build: ok (log: $FILE_LOG)"
exit 0
