#!/bin/sh
#
# Test for the STL tile tiling math (scripts/stl_tiles_build.py).
# Portable tier: pure Python, no GDAL, numpy, or datasets required.
# Exercises the tiling plan, tile ids, coordinate frames, grid lines, and
# the elevation mapping invariants.
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

python3 - "$REPOSITORY_ROOT" <<'PY'
import math
import os
import sys

sys.path.insert(0, os.path.join(sys.argv[1], "scripts"))
import stl_tiles_build as build

# --- tiling plan ---------------------------------------------------------
bands = build.plan_bands(30.0)
assert len(bands) == 6, bands
assert bands[0]["is_cap"] and bands[0]["lat_min"] == -90.0
assert bands[-1]["is_cap"] and bands[-1]["lat_max"] == 90.0
assert not any(band["is_cap"] for band in bands[1:-1])

tiles = build.plan_tiles(30.0)
assert len(tiles) == 42, len(tiles)
ids = [tile["id"] for tile in tiles]
assert len(set(ids)) == len(ids), "tile ids must be unique"
caps = [tile for tile in tiles if tile["is_cap"]]
assert len(caps) == 2, caps
assert {tile["id"] for tile in caps} == {"tile-N90", "tile-S90"}

counts_by_band = {}
for tile in tiles:
    key = (tile["lat_min"], tile["lat_max"])
    counts_by_band[key] = counts_by_band.get(key, 0) + 1
assert counts_by_band[(-30.0, 0.0)] == 12, counts_by_band
assert counts_by_band[(0.0, 30.0)] == 12, counts_by_band
assert counts_by_band[(30.0, 60.0)] == 8, counts_by_band
assert counts_by_band[(-60.0, -30.0)] == 8, counts_by_band
assert counts_by_band[(-90.0, -60.0)] == 1, counts_by_band
assert counts_by_band[(60.0, 90.0)] == 1, counts_by_band

assert len(build.plan_tiles(15.0)) == 180, len(build.plan_tiles(15.0))

# every band's tiles cover the full 360 degrees of longitude
for band in build.plan_bands(30.0):
    band_tiles = [tile for tile in tiles
                  if tile["lat_min"] == band["lat_min"]]
    spans = [tile["lon_max"] - tile["lon_min"] for tile in band_tiles]
    assert abs(sum(spans) - 360.0) < 1e-9, (band, spans)
    if band["is_cap"]:
        assert spans == [360.0], spans
        continue
    assert abs(spans[0] - spans[1]) < 1e-9, spans

# tile ids encode the southwest edge
tile_n00e000 = next(tile for tile in tiles if tile["lat_min"] == 0.0
                    and tile["lon_min"] == 0.0)
assert tile_n00e000["id"] == "tile-N00E000", tile_n00e000["id"]
tile_s60w030 = next(tile for tile in tiles if tile["lat_min"] == -60.0
                    and tile["lon_min"] == 45.0)
assert tile_s60w030["id"] == "tile-S60E045", tile_s60w030["id"]

# --- region and id selection ---------------------------------------------
selected = build.select_tiles(tiles, region=(5.0, 25.0, 5.0, 25.0))
assert {tile["id"] for tile in selected} == {"tile-N00E000"}, selected
for tile in selected:
    assert tile["lat_max"] > 5.0 and tile["lat_min"] < 25.0
    assert tile["lon_max"] > 5.0 and tile["lon_min"] < 25.0

selected = build.select_tiles(tiles, requested_ids=["tile-N90", "tile-S90"])
assert {tile["id"] for tile in selected} == {"tile-N90", "tile-S90"}
try:
    build.select_tiles(tiles, requested_ids=["tile-XX00"])
    raise AssertionError("unknown tile id must raise")
except ValueError:
    pass

# --- coordinate frames ----------------------------------------------------
frame = build.local_frame(0.0, 0.0)
east, north, up = frame
for axis in (east, north, up):
    assert abs(build.dot(axis, axis) - 1.0) < 1e-12
assert abs(build.dot(east, north)) < 1e-12
assert abs(build.dot(east, up)) < 1e-12
assert abs(build.dot(north, up)) < 1e-12

point_center = build.to_local(build.unit_radial(0.0, 0.0), frame)
assert abs(point_center[0]) < 1e-12 and abs(point_center[1]) < 1e-12
assert abs(point_center[2] - 1.0) < 1e-12

# a point on the equator east of the center lies along +x
point_east = build.to_local(build.unit_radial(0.0, 10.0), frame)
assert point_east[0] > 0.0 and abs(point_east[1]) < 1e-12

# --- grid lines -----------------------------------------------------------
tile_equator = next(tile for tile in tiles if tile["id"] == "tile-N00E000")
lats, lons = build.grid_lines(tile_equator, 0.25)
assert abs(lats[0] - 0.0) < 1e-12 and abs(lats[-1] - 30.0) < 1e-12
assert lats == sorted(lats)
assert abs(lons[0] - 0.0) < 1e-12 and abs(lons[-1] - 30.0) < 1e-12
assert lons == sorted(lons)
spacing_lon = lons[1] - lons[0]
count_lon = len(lons) - 1
assert count_lon == max(1, int(round(
    30.0 / (0.25 / math.cos(math.radians(15.0)))))), count_lon
assert abs(count_lon * spacing_lon - 30.0) < 1e-9

tile_cap = next(tile for tile in tiles if tile["id"] == "tile-N90")
lats_cap, lons_cap = build.grid_lines(tile_cap, 0.25)
assert abs(lats_cap[0] - 60.0) < 1e-12 and abs(lats_cap[-1] - 90.0) < 1e-12
assert len(lons_cap) == max(4, int(round(
    360.0 / (0.25 / math.cos(math.radians(75.0)))))), len(lons_cap)

# --- elevation mapping -----------------------------------------------------
parameters = {
    "oceans_flat": False,
    "elev_min": None,
    "elev_max": None,
    "base_mm": 3.0,
    "relief_mm": 20.0,
}
mapped_low = build.elevation_to_mm(-10994.0, -10994.0, 8849.0, parameters)
mapped_high = build.elevation_to_mm(8849.0, -10994.0, 8849.0, parameters)
assert abs(mapped_low - 3.0) < 1e-9, mapped_low
assert abs(mapped_high - 23.0) < 1e-9, mapped_high
middle = build.elevation_to_mm(0.0, -10994.0, 8849.0, parameters)
assert mapped_low < middle < mapped_high
assert build.elevation_to_mm(20000.0, -10994.0, 8849.0, parameters) == mapped_high

# --- oceans-flat mapping ---------------------------------------------------
# With oceans_flat, every water-covered cell (negative elevation) maps to
# the same height as sea level: one smooth plateau, no seafloor relief.
parameters_flat = dict(parameters)
parameters_flat["oceans_flat"] = True
sea_level_mm = build.elevation_to_mm(0.0, -10994.0, 8849.0, parameters_flat)
assert abs(sea_level_mm
           - (3.0 + 20.0 * (0.0 - (-10994.0)) / (8849.0 - (-10994.0)))) < 1e-9
for value_ocean in (-10994.0, -5000.0, -1.0):
    assert build.elevation_to_mm(value_ocean, -10994.0, 8849.0,
                                 parameters_flat) == sea_level_mm, value_ocean
assert build.elevation_to_mm(1.0, -10994.0, 8849.0,
                             parameters_flat) > sea_level_mm
assert build.elevation_to_mm(8849.0, -10994.0, 8849.0,
                             parameters_flat) == mapped_high
assert sea_level_mm > mapped_low, "the sea-level plateau sits above the base"

print('04-stl-tiles-math: tiling math invariants ok')
PY
