#!/bin/sh
#
# Test for the support ring-lattice math (scripts/rings_build.py).
# Portable tier: pure Python, no GDAL, numpy, or datasets required.
# Exercises the flat rings, the tile-socket tabs, the meridian keys, the cap
# stem, and the print-ready orientation.
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
KEY_LONS = [build.MERIDIAN_PHASE_DEG
            + (360.0 / build.MERIDIAN_COUNT) * index
            for index in range(build.MERIDIAN_COUNT)]


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

bands = (
    ("equatorial", equatorial, 15.0, INNER_RADIUS["N00"]),
    ("temperate", temperate, 45.0, INNER_RADIUS["N30"]),
    ("cap", [cap], 75.0, INNER_RADIUS["N90"]),
)

values = {}
rings = {}
for name, tiles_band, latitude, inner in bands:
    radii = {tile["id"]: inner for tile in tiles_band}
    value = build.ring_values(inner, latitude, CLEARANCE)
    values[name] = value
    rings[name] = build.horizontal_ring(tiles_band, radii, value, CLEARANCE)


def triangle_normal(triangle):
    point_a, point_b, point_c = triangle
    u = [point_b[i] - point_a[i] for i in range(3)]
    v = [point_c[i] - point_a[i] for i in range(3)]
    normal = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
              u[0] * v[1] - u[1] * v[0]]
    length = math.sqrt(sum(value * value for value in normal))
    return [value / length for value in normal] if length > 1e-12 else normal


# --- a ring is a flat washer: its faces are parallel to the equator ------
for name, tiles_band, latitude, inner in bands:
    value = values[name]
    ring = rings[name]
    assert len(ring) > 1000, (name, len(ring))
    assert tiles.signed_volume(ring) > 0.0, name
    assert value["rho_inner"] > 0.0, name
    # the outer rim reaches the clearance sphere
    rim = (value["rho_outer"] * math.cos(math.radians(latitude))
           + value["radius_outer"] * math.sin(math.radians(latitude)) ** 2)
    assert abs(rim - value["radius_outer"]) < 1e-9, (name, rim)
    # every horizontal face lies at the ring's bottom/top or the notch roof
    heights = {round(value["z_low"], 6), round(value["z_high"], 6),
               round(value["key_face"] + value["sign"] * build.KEY_DEPTH_MM,
                     6)}
    for triangle in ring:
        normal = triangle_normal(triangle)
        if abs(abs(normal[2]) - 1.0) > 1e-9:
            continue
        for point in triangle:
            assert round(point[2], 6) in heights, (name, point, heights)
    # the ring stands on a face, not an edge: its bottom plane carries a
    # whole annulus of vertices, spanning the wall
    bottom = [point for triangle in ring for point in triangle
              if abs(point[2] - value["z_low"]) < 1e-9]
    assert len(bottom) > 200, (name, len(bottom))
    radii = [math.hypot(point[0], point[1]) for point in bottom]
    assert min(radii) < value["rho_inner"] + 0.05, (name, min(radii))
    assert max(radii) > value["rho_outer"] - 0.05, (name, max(radii))
    # only the tabs rise above the ring's top face
    top = max(point[2] for triangle in ring for point in triangle)
    if name == "cap":
        assert abs(top - value["z_high"]) < 1e-9, (name, top)
    else:
        assert top > value["z_high"] + 1.0, (name, top)


# --- the south hemisphere mirrors the north ------------------------------
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


for name, tiles_band, latitude, inner in bands:
    south_latitude = -latitude
    if name == "cap":
        south_band = [{"id": "tile-S90", "is_cap": True, "lat_min": -90.0,
                       "lat_max": -60.0, "lon_min": 0.0, "lon_max": 360.0}]
    else:
        south_name = {"equatorial": "S30", "temperate": "S60"}[name]
        south_band = band_tiles(south_name, south_latitude - 15.0,
                                south_latitude + 15.0, len(tiles_band))
    south_value = build.ring_values(inner, south_latitude, CLEARANCE)
    south_radii = {tile["id"]: inner for tile in south_band}
    south_ring = build.horizontal_ring(south_band, south_radii, south_value,
                                       CLEARANCE)
    assert vertex_set(rings[name], True) == vertex_set(south_ring, False), \
        "the south %s ring must mirror the north" % name
    assert abs(south_value["meridian_radius"]
               - values[name]["meridian_radius"]) < 1e-9, name

order = [values[name] for name, _, _, _ in bands]
arc = build.meridian_arc(0.0, True, order, CLEARANCE)
south_order = [build.ring_values(inner, -latitude, CLEARANCE)
               for _, _, latitude, inner in bands]
south_arc = build.meridian_arc(0.0, False, south_order, CLEARANCE)
assert vertex_set(arc, True) == vertex_set(south_arc, False), \
    "the south meridian must mirror the north"


# --- a meridian clears every ring it crosses ----------------------------
def inside_ring_solid(point, value):
    """Is the point inside the ring's material (the washer minus notches)?"""
    radius = math.hypot(point[0], point[1])
    if not value["rho_inner"] < radius < value["rho_outer"]:
        return False
    if not value["z_low"] < point[2] < value["z_high"]:
        return False
    longitude = math.degrees(math.atan2(point[1], point[0])) % 360.0
    for key in KEY_LONS:
        gap = abs(((key - longitude + 180.0) % 360.0) - 180.0)
        if gap * math.pi / 180.0 * value["rho_inner"] > build.KEY_WINDOW_MM:
            continue
        depth = value["key_face"] + value["sign"] * build.KEY_DEPTH_MM
        if min(value["key_face"], depth) <= point[2] \
                <= max(value["key_face"], depth):
            return False
    return True


samples = []
for point_a, point_b, point_c in arc:
    for (u, v) in ((1 / 3, 1 / 3), (0.5, 0.0), (0.0, 0.5), (0.5, 0.25),
                   (0.25, 0.5), (0.2, 0.2), (0.6, 0.2), (0.2, 0.6)):
        samples.append(tuple(point_a[i] * u + point_b[i] * v
                             + point_c[i] * (1 - u - v) for i in range(3)))
for name, _, latitude, inner in bands:
    intruders = [point for point in samples
                 if inside_ring_solid(point, values[name])]
    assert not intruders, (name, intruders[0])


# --- every meridian key seats in its ring's notch ------------------------
def arc_radius_at(latitude):
    keys = sorted((value["center_lat"], value["meridian_radius"])
                  for value in order)
    if latitude <= keys[0][0]:
        return keys[0][1]
    if latitude >= keys[-1][0]:
        return keys[-1][1]
    for a, b in zip(keys, keys[1:]):
        if a[0] <= latitude <= b[0]:
            t = (latitude - a[0]) / (b[0] - a[0])
            return a[1] + t * (b[1] - a[1])
    return keys[-1][1]


for name, _, latitude, inner in bands:
    value = values[name]
    key = build.meridian_key_triangles(0.0, value)
    assert len(key) == 12, (name, len(key))
    depth = value["key_face"] + value["sign"] * build.KEY_DEPTH_MM
    for triangle in key:
        for point in triangle:
            radius = math.hypot(point[0], point[1])
            # it seats in the notch and never passes its roof into the ring
            assert radius <= value["rho_outer"] + 1e-6, (name, radius)
            if radius > value["rho_inner"]:
                assert (point[2] - depth) * value["sign"] <= 1e-6, \
                    (name, point[2], depth)
    # the key's far end reaches into the arc's body, so the two fuse
    innermost = min((point for triangle in key for point in triangle),
                    key=lambda point: math.hypot(point[0], point[1]))
    radius = math.sqrt(sum(value * value for value in innermost))
    latitude_here = math.degrees(math.asin(innermost[2] / radius))
    outer = arc_radius_at(latitude_here)
    assert outer - build.RING_RADIAL_MM <= radius <= outer, \
        (name, radius, outer)


# --- the tabs seat inside the tile sockets ------------------------------
def to_local(point, tile_latitude, tile_longitude):
    east, north, up = tiles.local_frame(tile_latitude, tile_longitude)
    return (tiles.dot(point, east), tiles.dot(point, north),
            tiles.dot(point, up))


for name, tiles_band, latitude, inner in bands:
    ring = rings[name]
    half_width = (tiles.KEY_SOCKET_WIDTH_MM - FIT) / 2.0
    half_length = (tiles.KEY_SOCKET_LENGTH_MM - FIT) / 2.0
    depth = tiles.KEY_SOCKET_DEPTH_MM - build.TAB_DEPTH_CLEARANCE_MM
    for tile in tiles_band:
        tile_latitude, tile_longitude = tiles.tile_center(tile)
        if abs(tile_latitude - values[name]["center_lat"]) > 1.0:
            continue
        seated = []
        for triangle in ring:
            for point in triangle:
                local = to_local(point, tile_latitude, tile_longitude)
                if local[2] > inner + 0.5:
                    seated.append(local)
        assert seated, (name, tile_longitude)
        for local in seated:
            # the tab's cross-section is the socket's minus clearance
            assert abs(local[0]) <= half_width + 1e-6, (name, local)
            assert abs(local[1]) <= half_length + 1e-6, (name, local)
            assert local[2] <= inner + depth + 1e-6, (name, local)
        assert max(local[2] for local in seated) > inner + depth - 1e-3, \
            (name, tile_longitude)

# --- the cap stem reaches the pole socket and ties to the cap ring ------
stem = build.cap_stem(True, INNER_RADIUS["N90"], values["cap"], CLEARANCE)
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
# the spokes sit in the ring's wall, clear of the meridian keys
cap_value = values["cap"]
spokes = [point for triangle in stem for point in triangle
          if math.hypot(point[0], point[1]) > cap_value["rho_inner"]
          and cap_value["z_low"] <= point[2] <= cap_value["z_high"]]
assert spokes, "the stem has no spokes"
for point in spokes:
    assert math.hypot(point[0], point[1]) <= cap_value["rho_outer"] + 1e-6, \
        point
assert min(point[2] for point in spokes) \
    > cap_value["key_face"] + build.KEY_DEPTH_MM, "spokes clash with a key"

# --- print-ready pieces sit on the bed and fit a 220 mm square ----------
pieces = [(name, rings[name], (0.0, 0.0, 1.0))
          for name, _, _, _ in bands]
pieces.append(("cap-stem", stem, (0.0, 0.0, 1.0)))
for index in range(build.MERIDIAN_COUNT):
    longitude = KEY_LONS[index]
    meridian = build.meridian_arc(longitude, True, order, CLEARANCE)
    pieces.append(("meridian-%02d" % (index + 1), meridian,
                   build.east_at(longitude)))
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

# --- southern pieces print the same way up ------------------------------
# a flipped piece must stand on its washer face (or its spoke cross), never
# on the tips of its keys
for name, tiles_band, latitude, inner in bands:
    south_latitude = -latitude
    if name == "cap":
        south_band = [{"id": "tile-S90", "is_cap": True, "lat_min": -90.0,
                       "lat_max": -60.0, "lon_min": 0.0, "lon_max": 360.0}]
    else:
        south_name = {"equatorial": "S30", "temperate": "S60"}[name]
        south_band = band_tiles(south_name, south_latitude - 15.0,
                                south_latitude + 15.0, len(tiles_band))
    south_value = build.ring_values(inner, south_latitude, CLEARANCE)
    south_radii = {tile["id"]: inner for tile in south_band}
    south_ring = build.horizontal_ring(south_band, south_radii, south_value,
                                       CLEARANCE)
    ready = build.print_ready(south_ring, (0.0, 0.0, -1.0))
    assert tiles.signed_volume(ready) > 0.0, name
    heights = [point[2] for triangle in ready for point in triangle]
    assert abs(min(heights)) < 1e-9, (name, min(heights))
    contact = [point for triangle in ready for point in triangle
               if abs(point[2]) < 1e-9]
    contact_radii = [math.hypot(point[0], point[1]) for point in contact]
    assert min(contact_radii) < south_value["rho_inner"] + 0.05, name
    assert max(contact_radii) > south_value["rho_outer"] - 0.05, name

south_stem = build.cap_stem(False, INNER_RADIUS["N90"], south_order[-1],
                            CLEARANCE)
ready = build.print_ready(south_stem, (0.0, 0.0, -1.0))
heights = [point[2] for triangle in ready for point in triangle]
assert abs(min(heights)) < 1e-9, min(heights)
contact = [point for triangle in ready for point in triangle
           if abs(point[2]) < 1e-9]
contact_radii = [math.hypot(point[0], point[1]) for point in contact]
assert max(contact_radii) > south_order[-1]["rho_inner"], \
    "the south stem must stand on its spokes"

print("05-rings-math: ok")
PY
