#!/bin/sh
#
# Test for the support ring-lattice math (scripts/rings_build.py).
# Portable tier: pure Python, no GDAL, numpy, or datasets required.
# Exercises the ring profiles, the tile-socket tabs, the meridian
# tongues/grooves, the cap stem, and the print-ready orientation.
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

python3 - "$REPOSITORY_ROOT" <<'PY'
import math
import os
import sys

sys.path.insert(0, os.path.join(sys.argv[1], "scripts"))
import rings_build as build
import stl_tiles_build as tiles

# Inner face radius at the tile centre, per band (measured from the build).
INNER_RADIUS = {"N00": 98.15, "N30": 96.67, "N90": 90.89}
CLEARANCE = 0.6
CAP_DEPTH = 2.0
FIT = build.FIT_CLEARANCE_MM


def band_tiles(name, lat_min, lat_max, count):
    width = 360.0 / count
    return [{
        "id": "tile-%sE%03d" % (name, int(round(index * width))),
        "is_cap": False,
        "lat_min": lat_min,
        "lat_max": lat_max,
        "lon_min": index * width,
        "lon_max": (index + 1) * width,
    } for index in range(count)]


equatorial = band_tiles("N00", 0.0, 30.0, 12)
temperate = band_tiles("N30", 30.0, 60.0, 8)
cap = {"id": "tile-N90", "is_cap": True, "lat_min": 60.0,
       "lat_max": 90.0, "lon_min": 0.0, "lon_max": 360.0}

radii = {
    "equatorial": {tile["id"]: INNER_RADIUS["N00"] for tile in equatorial},
    "temperate": {tile["id"]: INNER_RADIUS["N30"] for tile in temperate},
    "cap": {"tile-N90": INNER_RADIUS["N90"]},
}

ring_15 = build.horizontal_ring(equatorial, radii["equatorial"], 15.0,
                                CLEARANCE)
ring_45 = build.horizontal_ring(temperate, radii["temperate"], 45.0,
                                CLEARANCE)
ring_75 = build.horizontal_ring([cap], radii["cap"], 75.0, CLEARANCE)

# --- every piece is a closed, positively oriented solid ------------------
def radius(point):
    return math.sqrt(sum(value * value for value in point))


rings = {"15": (ring_15, INNER_RADIUS["N00"]),
         "45": (ring_45, INNER_RADIUS["N30"]),
         "75": (ring_75, INNER_RADIUS["N90"])}
for name, (ring, inner) in rings.items():
    assert len(ring) > 1000, (name, len(ring))
    assert tiles.signed_volume(ring) > 0.0, name
    distances = [radius(point) for triangle in ring for point in triangle]
    outer = inner - CLEARANCE
    low = outer - build.RING_RADIAL_MM
    # the body sits between the inner and outer faces, plus the key depth
    assert low - 0.01 <= min(distances), (name, min(distances), low)
    assert max(distances) <= outer + build.KEY_DEPTH_MM + 0.01, \
        (name, max(distances))

# --- 12 meridian arcs key into every ring -------------------------------
order = [(15.0, INNER_RADIUS["N00"] - CLEARANCE - build.RING_RADIAL_MM,
          INNER_RADIUS["N00"] - CLEARANCE,
          INNER_RADIUS["N00"] - CLEARANCE - build.RING_RADIAL_MM / 2.0),
         (45.0, INNER_RADIUS["N30"] - CLEARANCE - build.RING_RADIAL_MM,
          INNER_RADIUS["N30"] - CLEARANCE,
          INNER_RADIUS["N30"] - CLEARANCE - build.RING_RADIAL_MM / 2.0),
         (75.0, INNER_RADIUS["N90"] - CLEARANCE - build.RING_RADIAL_MM,
          INNER_RADIUS["N90"] - CLEARANCE,
          INNER_RADIUS["N90"] - CLEARANCE - build.RING_RADIAL_MM / 2.0)]

longitudes = [build.MERIDIAN_PHASE_DEG
              + (360.0 / build.MERIDIAN_COUNT) * index
              for index in range(build.MERIDIAN_COUNT)]
arcs = []
for longitude in longitudes:
    arc = build.meridian_arc(longitude, True, order, CLEARANCE)
    assert len(arc) > 500, (longitude, len(arc))
    assert tiles.signed_volume(arc) > 0.0, longitude
    arcs.append((longitude, arc))

# a tongue reaches KEY_DEPTH - TAB_DEPTH_CLEARANCE past the ring's inner face
tongue_tips = [entry[1] + build.KEY_DEPTH_MM
               - build.TAB_DEPTH_CLEARANCE_MM for entry in order]
for longitude, arc in arcs:
    distances = [radius(point) for triangle in arc for point in triangle]
    assert abs(max(distances) - max(tongue_tips)) < 0.05, \
        (longitude, max(distances))
    # the body stays inside the innermost ring face it spans
    assert min(distances) > order[2][1] - CLEARANCE \
        - build.RING_RADIAL_MM - 0.01, (longitude, min(distances))

# --- the south hemisphere mirrors the north -----------------------------
mirrored = [(-entry[0], entry[1], entry[2], entry[3]) for entry in order]
arc_south = build.meridian_arc(0.0, False, mirrored, CLEARANCE)
arc_north = build.meridian_arc(0.0, True, order, CLEARANCE)


def vertex_set(triangles, flip):
    # compare geometry, not triangulation: a mirrored piece may split its
    # quads along the other diagonal, and collapsed profile slots leave a
    # different number of duplicate vertices
    points = set()
    for triangle in triangles:
        for point in triangle:
            if flip:
                point = (point[0], point[1], -point[2])
            points.add(tuple(round(value, 6) for value in point))
    return sorted(points)


assert vertex_set(arc_north, True) == vertex_set(arc_south, False), \
    "the south meridian must mirror the north"
ring_south = build.horizontal_ring(
    band_tiles("S30", -30.0, 0.0, 12),
    {"tile-S30E%03d" % int(round(index * 30.0)): INNER_RADIUS["N00"]
     for index in range(12)}, -15.0, CLEARANCE)
assert vertex_set(ring_15, True) == vertex_set(ring_south, False), \
    "the south ring must mirror the north"

# --- no ring carries a groove and a tab at the same longitude -----------
def angular_gap(first, second):
    return abs(((first - second + 180.0) % 360.0) - 180.0)


for name, (ring, inner) in rings.items():
    center_lat = build.BAND_CENTERS[{"15": "N00", "45": "N30",
                                     "75": "N90"}[name]]
    path = (inner - CLEARANCE - build.RING_RADIAL_MM / 2.0) \
        * math.cos(math.radians(center_lat))
    groove_window = math.degrees(build.KEY_WINDOW_MM / path)
    tab_window = math.degrees((tiles.KEY_SOCKET_WIDTH_MM - FIT) / 2.0 / path)
    for meridian in longitudes:
        for tile in (equatorial if name == "15" else
                     temperate if name == "45" else [cap]):
            latitude, longitude = tiles.tile_center(tile)
            if abs(latitude - center_lat) > 1.0:
                continue
            gap = angular_gap(meridian, longitude)
            assert gap > tab_window, (name, meridian, longitude, gap)
            assert gap > groove_window - tab_window, (name, gap)

# --- the tabs seat inside the tile sockets ------------------------------
def to_local(point, tile_latitude, tile_longitude):
    east, north, up = tiles.local_frame(tile_latitude, tile_longitude)
    return (tiles.dot(point, east), tiles.dot(point, north),
            tiles.dot(point, up))


for tiles_band, ring, inner, name in ((equatorial, ring_15,
                                       INNER_RADIUS["N00"], "N00"),
                                      (temperate, ring_45,
                                       INNER_RADIUS["N30"], "N30")):
    half_width = (tiles.KEY_SOCKET_WIDTH_MM - FIT) / 2.0
    half_length = (tiles.KEY_SOCKET_LENGTH_MM - FIT) / 2.0
    depth = tiles.KEY_SOCKET_DEPTH_MM - build.TAB_DEPTH_CLEARANCE_MM
    for tile in tiles_band:
        latitude, longitude = tiles.tile_center(tile)
        bottom = inner
        seated = []
        for triangle in ring:
            for point in triangle:
                local = to_local(point, latitude, longitude)
                if local[2] > bottom + 0.5:
                    seated.append(local)
        assert seated, (name, longitude)
        worst_x = worst_y = 0.0
        for local in seated:
            # the tab's slanted side wall adds a few hundredths of a
            # millimetre at the swept edge; the fit clearance must survive it
            assert abs(local[0]) <= half_width + 0.05, (name, local)
            assert abs(local[1]) <= half_length + 0.05, (name, local)
            assert local[2] <= bottom + depth + 1e-6, (name, local)
            worst_x = max(worst_x, abs(local[0]))
            worst_y = max(worst_y, abs(local[1]))
        assert FIT / 2.0 - max(worst_x - half_width, worst_y - half_length) \
            > 0.1, (name, worst_x, worst_y)
        assert max(local[2] for local in seated) > bottom + depth - 1e-3, \
            (name, longitude)

# --- the cap stem reaches the pole socket and ties to the cap ring ------
stem = build.cap_stem(True, INNER_RADIUS["N90"], order, CLEARANCE)
assert len(stem) > 20, len(stem)
assert tiles.signed_volume(stem) > 0.0
highest = max(point[2] for triangle in stem for point in triangle)
assert abs(highest - (INNER_RADIUS["N90"] + CAP_DEPTH
                      - build.TAB_DEPTH_CLEARANCE_MM)) < 0.03, highest
corners = [point for triangle in stem for point in triangle
           if abs(point[2] - highest) < 1e-6]
half_north = (tiles.KEY_SOCKET_LENGTH_MM - FIT) / 2.0
half_east = (tiles.KEY_SOCKET_WIDTH_MM - FIT) / 2.0
for point in corners:
    # the cap tile's frame at the pole: east along +y, north along -x
    assert abs(point[0]) <= half_north + 1e-6, point
    assert abs(point[1]) <= half_east + 1e-6, point
# the spokes reach into the cap ring body: every spoke point lies in the
# ring's radial band, and reaches past the ring's inner face
band_low = order[2][1] - 0.01
band_high = order[2][2] + 0.01
spokes = [point for triangle in stem for point in triangle
          if math.hypot(point[0], point[1]) > 4.0]
assert spokes, "the stem has no spokes"
for point in spokes:
    assert band_low <= radius(point) <= band_high, point
inner_cylinder = order[2][1] * math.cos(math.radians(75.0))
assert max(math.hypot(point[0], point[1]) for point in spokes) \
    > inner_cylinder + 0.5

# --- print-ready pieces sit on the bed and fit a 220 mm square ----------
pieces = [("ring-15", ring_15, (0.0, 0.0, 1.0)),
          ("ring-45", ring_45, (0.0, 0.0, 1.0)),
          ("ring-75", ring_75, (0.0, 0.0, 1.0)),
          ("cap-stem", stem, (0.0, 0.0, 1.0))]
pieces += [("meridian-%02d" % (index + 1), arc, build.east_at(longitude))
           for index, (longitude, arc) in enumerate(arcs)]
for name, piece, normal in pieces:
    ready = build.print_ready(piece, normal)
    assert len(ready) == len(piece), (name, len(ready), len(piece))
    assert tiles.signed_volume(ready) > 0.0, name
    heights = [point[2] for triangle in ready for point in triangle]
    assert abs(min(heights)) < 1e-9, (name, min(heights))
    span_x = max(point[0] for triangle in ready for point in triangle) \
        - min(point[0] for triangle in ready for point in triangle)
    span_y = max(point[1] for triangle in ready for point in triangle) \
        - min(point[1] for triangle in ready for point in triangle)
    assert span_x <= 220.0 and span_y <= 220.0, (name, span_x, span_y)

print("05-rings-math: ok")
PY
