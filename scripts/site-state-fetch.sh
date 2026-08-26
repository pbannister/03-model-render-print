#!/bin/sh
#
# site-state-fetch.sh: gather live dataset and tile state and write it as
# KEY=value lines to the site state file.
#
# The state file is generated output and must not be edited by hand.
# The site build (scripts/site-build.sh) substitutes these values for
# __KEY__ placeholders in site.in/dashboard.txt.
#
# Reads the shared datasets volume (/datasets) on the owning host — the same
# ETOPO 2022 source the model-elevation-earth project maintains — plus this
# repository's git state, the volume's disk usage, and the derived STL tile
# manifest (dataflow.out/stl/manifest.json).
#
# Usage: site-state-fetch.sh [OUTPUT_FILE]
# The default OUTPUT_FILE is dataflow.out/site-state.txt relative to the
# repository root.
set -eu

DIRECTORY_SCRIPT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$DIRECTORY_SCRIPT/.." && pwd)
OUTPUT_FILE=${1:-"$REPOSITORY_ROOT/dataflow.out/site-state.txt"}

DIRECTORY_VOLUME=/datasets
DIRECTORY_DATASET_ETOPO="$DIRECTORY_VOLUME/dataset-etopo-2022"
FILE_MANIFEST="$DIRECTORY_VOLUME/manifest.yml"
ID_ETOPO=etopo-2022
FILE_TILE_MANIFEST="$REPOSITORY_ROOT/dataflow.out/stl/manifest.json"

fetched=$(date -Is 2>/dev/null || date)
branch=$(git -C "$REPOSITORY_ROOT" symbolic-ref -q --short HEAD 2>/dev/null || echo unknown)
commit=$(git -C "$REPOSITORY_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)

manifest_count=0
if [ -f "$FILE_MANIFEST" ]; then
    manifest_count=$(grep -c '^  - id:' "$FILE_MANIFEST" 2>/dev/null || true)
fi

etopo_date=unknown
etopo_files=0
etopo_size=unknown
etopo_resolution=unknown
if [ -d "$DIRECTORY_DATASET_ETOPO" ]; then
    etopo_date=$(awk -v id="$ID_ETOPO" '
        $0 == "  - id: " id { found = 1 }
        found && /download_date:/ { print $2; exit }
    ' "$FILE_MANIFEST" 2>/dev/null || echo unknown)
    etopo_files=$(find "$DIRECTORY_DATASET_ETOPO" -name '*.tif' | wc -l)
    etopo_size=$(du -sh "$DIRECTORY_DATASET_ETOPO" 2>/dev/null | cut -f1 || echo unknown)
    etopo_resolution=$(ls "$DIRECTORY_DATASET_ETOPO" 2>/dev/null | grep -o '15s' | head -1 || echo unknown)
fi

volume_total=unknown
volume_used=unknown
volume_free=unknown
if [ -d "$DIRECTORY_VOLUME" ]; then
    volume_total=$(df -h "$DIRECTORY_VOLUME" 2>/dev/null | awk 'NR == 2 { print $2 }')
    volume_used=$(df -h "$DIRECTORY_VOLUME" 2>/dev/null | awk 'NR == 2 { print $3 }')
    volume_free=$(df -h "$DIRECTORY_VOLUME" 2>/dev/null | awk 'NR == 2 { print $4 }')
fi

stl_tile_count=0
stl_tiles_size=unknown
stl_build_timestamp=unknown
stl_band_degrees=unknown
stl_radius_mm=unknown
if [ -f "$FILE_TILE_MANIFEST" ]; then
    stl_tile_count=$(python3 -c '
import json
import sys
with open(sys.argv[1]) as handle:
    manifest = json.load(handle)
print(len(manifest.get("tiles", [])))
' "$FILE_TILE_MANIFEST" 2>/dev/null || echo 0)
    stl_tiles_size=$(du -sh "$REPOSITORY_ROOT/dataflow.out/stl" 2>/dev/null | cut -f1 || echo unknown)
    stl_build_timestamp=$(python3 -c '
import json
import sys
with open(sys.argv[1]) as handle:
    manifest = json.load(handle)
print(manifest.get("build", {}).get("timestamp", "unknown"))
' "$FILE_TILE_MANIFEST" 2>/dev/null || echo unknown)
    stl_band_degrees=$(python3 -c '
import json
import sys
with open(sys.argv[1]) as handle:
    manifest = json.load(handle)
print(manifest.get("parameters", {}).get("band_degrees", "unknown"))
' "$FILE_TILE_MANIFEST" 2>/dev/null || echo unknown)
    stl_radius_mm=$(python3 -c '
import json
import sys
with open(sys.argv[1]) as handle:
    manifest = json.load(handle)
print(manifest.get("parameters", {}).get("radius_mm", "unknown"))
' "$FILE_TILE_MANIFEST" 2>/dev/null || echo unknown)
fi

mkdir -p "$(dirname "$OUTPUT_FILE")"

cat > "$OUTPUT_FILE" <<EOF
FETCHED=$fetched
BRANCH=$branch
COMMIT=$commit
MANIFEST_COUNT=$manifest_count
VOLUME_TOTAL=$volume_total
VOLUME_USED=$volume_used
VOLUME_FREE=$volume_free
ETOPO_DATE=$etopo_date
ETOPO_FILES=$etopo_files
ETOPO_SIZE=$etopo_size
ETOPO_RESOLUTION=$etopo_resolution
STL_TILE_COUNT=$stl_tile_count
STL_TILES_SIZE=$stl_tiles_size
STL_BUILD_TIMESTAMP=$stl_build_timestamp
STL_BAND_DEGREES=$stl_band_degrees
STL_RADIUS_MM=$stl_radius_mm
EOF

echo "site-state-fetch: wrote $OUTPUT_FILE"
exit 0
