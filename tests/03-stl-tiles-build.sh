#!/bin/sh
#
# Test for the STL tile pipeline (scripts/stl-tiles-build.sh).
# Tool-gated tier: requires python3 with the osgeo and numpy modules and the
# ETOPO source tiles under /datasets on the owning host; skips cleanly with
# a message when a prerequisite is absent.
#
# The test renders a small region (a couple of tiles at coarse sampling)
# into a temporary output directory, then validates the result with check
# mode, so the main dataflow.out/stl/ tile set is left untouched.
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SCRIPT_BUILD="$REPOSITORY_ROOT/scripts/stl-tiles-build.sh"
DIRECTORY_SOURCE=/datasets/dataset-etopo-2022
DIRECTORY_OUTPUT_TEMPORARY=$(mktemp -d)

trap 'rm -rf "$DIRECTORY_OUTPUT_TEMPORARY"' EXIT HUP INT TERM

skip() {
    echo "03-stl-tiles-build: skipped: $1"
    exit 0
}

if ! command -v python3 >/dev/null 2>&1; then
    skip "missing tool: python3"
fi

if ! python3 -c 'import osgeo.gdal, numpy' 2>/dev/null; then
    skip 'python3 lacks the osgeo or numpy module'
fi

if [ ! -d "$DIRECTORY_SOURCE" ]; then
    skip "missing dataset directory: $DIRECTORY_SOURCE"
fi

if ! find "$DIRECTORY_SOURCE" -name '*_surface.tif' | grep -q .; then
    skip "no ETOPO tiles under $DIRECTORY_SOURCE"
fi

sh "$SCRIPT_BUILD" build \
    --output-dir "$DIRECTORY_OUTPUT_TEMPORARY" \
    --band-degrees 10 \
    --sample-degrees 1 \
    --radius-mm 50 \
    --relief-mm 10 \
    --region 40 50 -125 -115 >/dev/null

if ! sh "$SCRIPT_BUILD" check \
        --output-dir "$DIRECTORY_OUTPUT_TEMPORARY" >/dev/null; then
    echo '03-stl-tiles-build: check failed' >&2
    exit 1
fi

python3 - "$DIRECTORY_OUTPUT_TEMPORARY" "$REPOSITORY_ROOT/scripts" <<'PY'
import json
import os
import sys

sys.path.insert(0, sys.argv[2])
import stl_tiles_build as build

directory_output = sys.argv[1]
with open(os.path.join(directory_output, "manifest.json")) as handle:
    manifest = json.load(handle)

assert manifest["parameters"]["band_degrees"] == 10
assert manifest["parameters"]["radius_mm"] == 50
assert manifest["parameters"]["relief_mm"] == 10
assert manifest["parameters"]["sample_degrees"] == 1

assert len(manifest["tiles"]) >= 1, manifest["tiles"]
for tile in manifest["tiles"]:
    path_stl = os.path.join(directory_output, tile["file"])
    assert os.path.isfile(path_stl), path_stl
    assert tile["triangles"] > 0, tile
    assert os.path.getsize(path_stl) == 84 + tile["triangles"] * 50, tile
    # region filter: the tile must intersect lat 40..50, lon -125..-115
    assert tile["lat_max"] > 40.0 and tile["lat_min"] < 50.0, tile
    assert build.normalize_lon(tile["lon_max"]) > -125.0, tile
    assert build.normalize_lon(tile["lon_min"]) < -115.0, tile

print('03-stl-tiles-build: manifest ok (%d tiles)' % len(manifest["tiles"]))
PY

echo '03-stl-tiles-build: ok'
exit 0
