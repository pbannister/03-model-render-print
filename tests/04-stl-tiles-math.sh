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

# --- chamfered walls, alignment keys, underside mark ------------------------
def count_nonmanifold(triangles):
    edge_counts = {}
    for (a, c, d) in triangles:
        for (start, end) in ((a, c), (c, d), (d, a)):
            key_start = (round(start[0], 6), round(start[1], 6),
                         round(start[2], 6))
            key_end = (round(end[0], 6), round(end[1], 6), round(end[2], 6))
            key = (key_start, key_end) if key_start <= key_end \
                else (key_end, key_start)
            edge_counts[key] = edge_counts.get(key, 0) + 1
    return sum(1 for count in edge_counts.values() if count != 2)

# key plan conventions
plan = build.key_plan_for_tile(
    next(t for t in tiles if t["id"] == "tile-N30E000"), 30.0)
kinds = {entry["edge"]: entry["kind"] for entry in plan}
assert kinds == {"north": "stud", "east": "stud",
                 "south": "socket", "west": "socket"}, kinds
plan = build.key_plan_for_tile(
    next(t for t in tiles if t["id"] == "tile-S60E000"), 30.0)
kinds = {entry["edge"]: entry["kind"] for entry in plan}
assert kinds["south"] == "stud", "pole-side south edge carries a stud"
assert [entry["edge"] for entry in
        build.key_plan_for_tile(tiles[-1], 30.0)] == ["ring"]

# pair-wise decisions: a tall tile mates a tall tile; a thin tile skips
def synthetic_geometry(sample_degrees, width):
    """Geometry (edges, lats, lons, fabricated widths) for all tiles."""
    geometry = {}
    for tile_plan in tiles:
        lats_g, lons_g = build.grid_lines(tile_plan, sample_degrees)
        elev_g = [[12.0 for _ in lons_g] for _ in lats_g]
        center_lat = (tile_plan["lat_min"] + tile_plan["lat_max"]) / 2.0
        center_lon = tile_plan["lon_min"] if tile_plan["is_cap"] else (
            tile_plan["lon_min"] + tile_plan["lon_max"]) / 2.0
        frame_g = build.local_frame(center_lat, center_lon)
        top_g = build.top_grid(tile_plan, lats_g, lons_g, elev_g, 100.0,
                               frame_g)
        z_bottom_g = min(point[2] for row in top_g for point in row) - 12.0
        boundary_g, edges_g, lats_b, lons_b = build.boundary_ring(
            tile_plan, top_g, lats_g, lons_g)
        geometry[tile_plan["id"]] = {
            "widths": [width for _ in boundary_g],
            "edges": edges_g,
            "lats": lats_b,
            "lons": lons_b,
        }
    return geometry

def key_edges(decision):
    return {key["edge"]: key["kind"] for key in decision}

def build_key_mid(geometry, tile_id, edge):
    start, count = geometry[tile_id]["edges"][edge]
    return start + count // 2

geometry_tall = synthetic_geometry(0.25, 12.0)
decisions = build.key_decisions(tiles, geometry_tall, 30.0)
assert key_edges(decisions["tile-N30E000"]) == {
    "east": "stud", "north": "stud", "west": "socket", "south": "socket"}, \
    decisions["tile-N30E000"]
assert key_edges(decisions["tile-S60E000"])["south"] == "stud", decisions
assert key_edges(decisions["tile-N90"]) == {"ring": "socket"}, decisions
geometry_thin = synthetic_geometry(0.25, 12.0)
mid_east_neighbor = build_key_mid(geometry_thin, "tile-N30E045", "west")
geometry_thin["tile-N30E045"]["widths"][mid_east_neighbor] = 2.0
decisions_thin = build.key_decisions(tiles, geometry_thin, 30.0)
assert "east" not in key_edges(decisions_thin["tile-N30E000"]), \
    "fin needs the neighbor's groove"
assert key_edges(decisions_thin["tile-N90"]) == {"ring": "socket"}

# synthetic tile: chamfer planes through the origin, keys, id, watertight
synthetic = next(t for t in tiles if t["id"] == "tile-N30E000")
lats_s, lons_s = build.grid_lines(synthetic, 0.25)
elev_s = [[12.0 for _ in lons_s] for _ in lats_s]
mesh, boundary_edges, features = build.build_mesh(
    synthetic, lats_s, lons_s, elev_s, 100.0, 12.0,
    decisions["tile-N30E000"])
assert features["id_mark"] == "N30E000", features["id_mark"]
for (normal, point) in features["wall_planes"]:
    assert abs(build.dot(normal, point)) < 1e-6, \
        "every wall plane must contain the globe center"
kinds = {key["edge"]: key["kind"] for key in features["keys"]}
assert kinds == {"east": "stud", "north": "stud",
                 "west": "socket", "south": "socket"}, kinds
z_min = min(point[2] for triangle in mesh for point in triangle)
assert abs(z_min) < 1e-9, z_min
assert any(abs(point[2] - build.GROOVE_DEPTH_MM) < 1e-9
           for triangle in mesh for point in triangle), "groove floor"
assert count_nonmanifold(mesh) == 0, "synthetic tile must be watertight"

# polar cap: ring sockets, id, watertight
cap = next(t for t in tiles if t["id"] == "tile-N90")
lats_c, lons_c = build.grid_lines(cap, 0.25)
elev_c = [[12.0 for _ in lons_c] for _ in lats_c]
mesh_c, _, features_c = build.build_mesh(cap, lats_c, lons_c, elev_c,
                                         100.0, 12.0,
                                         decisions["tile-N90"])
assert features_c["id_mark"] == "N90", features_c["id_mark"]
assert all(key["edge"] == "ring" and key["kind"] == "socket"
           for key in features_c["keys"])
assert len(features_c["keys"]) > 0, "the ring carries the band fins"
assert count_nonmanifold(mesh_c) == 0, "cap tile must be watertight"

print('04-stl-tiles-math: tiling math invariants ok')
PY
