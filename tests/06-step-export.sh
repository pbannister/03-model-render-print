#!/bin/sh
#
# Test for the STEP tile export (scripts/tiles_step.py).
#
# Portable tier: the writer and the assembly maths, checked on synthetic
# solids with no GDAL needed.  Tool-gated tier: when python3 with the osgeo
# module and the ETOPO tiles are present, render the whole tile set at a
# coarse sampling into a temporary directory and validate the assembled
# orientation of every solid in the STEP file.
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DIRECTORY_SOURCE=/datasets/dataset-etopo-2022
DIRECTORY_OUTPUT_TEMPORARY=$(mktemp -d)

trap 'rm -rf "$DIRECTORY_OUTPUT_TEMPORARY"' EXIT HUP INT TERM

python3 - "$REPOSITORY_ROOT" <<'PY'
import math
import os
import re
import sys

sys.path.insert(0, os.path.join(sys.argv[1], "scripts"))
import tiles_step
import stl_tiles_build as tiles


# --- reading a STEP file back -------------------------------------------
def read_entities(path):
    """{id: body} plus the header lines, validating the file's shape."""
    with open(path) as handle:
        text = handle.read()
    lines = text.split("\n")
    assert lines[0] == "ISO-10303-21;", lines[0]
    assert lines[-1] == "", lines[-1]
    assert lines[-2] == "END-ISO-10303-21;", lines[-2]
    assert "FILE_SCHEMA(('CONFIG_CONTROL_DESIGN'));" in lines, "schema"
    entities = {}
    for line in lines:
        if not line.startswith("#"):
            continue
        match = re.match(r"^#(\d+) = (.*);$", line)
        assert match, "malformed entity line: %r" % line
        identifier = int(match.group(1))
        assert identifier not in entities, "duplicate id %d" % identifier
        entities[identifier] = match.group(2)
    assert sorted(entities) == list(range(1, len(entities) + 1)), \
        "entity ids must be 1..N with no gaps"
    return text, entities


def references(body):
    return [int(value) for value in re.findall(r"#(\d+)", body)]


def triple(body):
    values = re.findall(r"\(([-0-9.E+]+,[-0-9.E+]+,[-0-9.E+]+)\)", body)
    return tuple(float(value) for value in values[-1].split(","))


def solid_boxes(entities):
    """{solid name: ((min x, min y, min z), (max x, max y, max z))}.

    Walking the graph this way also proves every reference resolves.
    """
    for identifier, body in entities.items():
        for reference in references(body):
            assert reference in entities, \
                "#%d references missing #%d" % (identifier, reference)
    boxes = {}
    for body in entities.values():
        match = re.match(r"^MANIFOLD_SOLID_BREP\('([^']*)',#(\d+)\)$", body)
        if not match:
            continue
        points = []
        shell = entities[int(match.group(2))]
        for face_id in references(shell):
            face = entities[face_id]
            assert face.startswith("ADVANCED_FACE("), face[:40]
            bound_id = references(face)[0]
            loop_id = references(entities[bound_id])[0]
            for oriented_id in references(entities[loop_id]):
                edge_refs = references(entities[oriented_id])
                edge = entities[edge_refs[0]]
                assert edge.startswith("EDGE_CURVE("), edge[:40]
                for vertex_id in references(edge)[:2]:
                    point_id = references(entities[vertex_id])[0]
                    points.append(triple(entities[point_id]))
        assert points, "solid %s has no vertices" % match.group(1)
        boxes[match.group(1)] = (
            tuple(min(point[axis] for point in points) for axis in range(3)),
            tuple(max(point[axis] for point in points) for axis in range(3)),
        )
    return boxes


def direction_of(point):
    """(latitude, longitude) degrees of a world point."""
    radius = math.sqrt(sum(value * value for value in point))
    latitude = math.degrees(math.asin(point[2] / radius))
    longitude = math.degrees(math.atan2(point[1], point[0]))
    return latitude, longitude


def longitude_gap(first, second):
    return abs(((first - second + 180.0) % 360.0) - 180.0)


# --- the writer, on synthetic solids ------------------------------------
def cube(size, origin):
    x, y, z = origin
    corners = [
        (x, y, z), (x + size, y, z), (x + size, y + size, z), (x, y + size, z),
        (x, y, z + size), (x + size, y, z + size),
        (x + size, y + size, z + size), (x, y + size, z + size),
    ]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
             (2, 3, 7, 6), (3, 0, 4, 7)]
    triangles = []
    for (a, b, c, d) in faces:
        triangles.append((corners[a], corners[b], corners[c]))
        triangles.append((corners[a], corners[c], corners[d]))
    return triangles


path_sample = os.path.join(os.environ.get("TMPDIR", "/tmp"),
                           "tiles-step-sample.step")
parts = [("cube-a", cube(10.0, (0.0, 0.0, 0.0))),
         ("cube-b", cube(5.0, (20.0, 1.0, 2.0)))]
tiles_step.write_step(path_sample, parts, "sample")
text, entities = read_entities(path_sample)
try:
    os.remove(path_sample)
except OSError:
    pass

# millimetre units are declared, so CAD tools import at the right scale
assert "SI_UNIT(.MILLI.,.METRE.)" in text, "the file must declare millimetres"
assert "LENGTH_UNIT()" in text, "the file must declare a length unit"
assert "GEOMETRIC_REPRESENTATION_CONTEXT(3)" in text, "missing units context"
assert "ADVANCED_BREP_SHAPE_REPRESENTATION" in text, "missing shape"
# one product holding both solids, so a CAD import gives two bodies
assert sum(1 for body in entities.values()
           if body.startswith("PRODUCT(")) == 1
assert sum(1 for body in entities.values()
           if body.startswith("SHAPE_DEFINITION_REPRESENTATION")) == 1
boxes = solid_boxes(entities)
assert sorted(boxes) == ["cube-a", "cube-b"], sorted(boxes)
assert boxes["cube-a"] == ((0.0, 0.0, 0.0), (10.0, 10.0, 10.0)), boxes
assert boxes["cube-b"] == ((20.0, 1.0, 2.0), (25.0, 6.0, 7.0)), boxes

# --- assembly maths ------------------------------------------------------
equator_frame = tiles.local_frame(0.0, 0.0)
assert tiles_step.local_to_world((0.0, 0.0, 95.0), equator_frame, 3.0) \
    == (98.0, 0.0, 0.0), tiles_step.local_to_world((0.0, 0.0, 95.0),
                                                   equator_frame, 3.0)
cap_frame = tiles.local_frame(90.0, 0.0)
world = tiles_step.local_to_world((0.0, 0.0, 90.0), cap_frame, 3.0)
assert abs(world[0]) < 1e-9 and abs(world[1]) < 1e-9 \
    and abs(world[2] - 93.0) < 1e-9, world
south_frame = tiles.local_frame(-90.0, 0.0)
world = tiles_step.local_to_world((0.0, 0.0, 90.0), south_frame, 3.0)
assert abs(world[2] + 93.0) < 1e-9, world
# --- tile selection ------------------------------------------------------
planned = tiles.plan_tiles(30.0)
assert len(planned) == 42, len(planned)
covered = []
for hemisphere, prefixes in tiles_step.BAND_IDS.items():
    selected = [tile for tile in planned
                if tile["id"].startswith(prefixes)]
    assert selected, hemisphere
    covered.extend(tile["id"] for tile in selected)
assert sorted(covered) == sorted(tile["id"] for tile in planned), \
    "the band prefixes must cover every tile exactly once"

print("06-step-export: writer, assembly maths and selection ok")
PY

# --- tool-gated: render the tile set and check every solid's placement ---
skip() {
    echo "06-step-export: skipped: $1"
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

# a handful of tiles at a coarse grid: the engraved id dominates the
# triangle count, so a whole-globe run is far too big for a test
python3 "$REPOSITORY_ROOT/scripts/tiles_step.py" \
    --sample-degrees 20 \
    --radius-mm 50 \
    --tile tile-N90 --tile tile-N00E000 \
    --tile tile-S30E000 --tile tile-S90 \
    --output-dir "$DIRECTORY_OUTPUT_TEMPORARY" >/dev/null

python3 - "$REPOSITORY_ROOT" "$DIRECTORY_OUTPUT_TEMPORARY" <<'PY'
import glob
import math
import os
import re
import sys

sys.path.insert(0, os.path.join(sys.argv[1], "scripts"))
import tiles_step
import stl_tiles_build as tiles

directory = sys.argv[2]
path = os.path.join(directory, "tiles-selected.step")
with open(path) as handle:
    text = handle.read()
entities = {}
for line in text.split("\n"):
    match = re.match(r"^#(\d+) = (.*);$", line)
    if match:
        entities[int(match.group(1))] = match.group(2)
assert "SI_UNIT(.MILLI.,.METRE.)" in text, "millimetres missing"
for identifier, body in entities.items():
    for reference in (int(value) for value in re.findall(r"#(\d+)", body)):
        assert reference in entities, \
            "#%d references missing #%d" % (identifier, reference)

boxes = tiles_step.__dict__ and None
# walk each solid's faces down to its vertices, as the portable tier does
def references(body):
    return [int(value) for value in re.findall(r"#(\d+)", body)]


def triple(body):
    values = re.findall(r"\(([-0-9.E+]+,[-0-9.E+]+,[-0-9.E+]+)\)", body)
    return tuple(float(value) for value in values[-1].split(","))


def solid_points(entities):
    """{solid name: [vertex, ...]}, walking the whole reference graph."""
    points_of_solid = {}
    for body in entities.values():
        match = re.match(r"^MANIFOLD_SOLID_BREP\('([^']*)',#(\d+)\)$", body)
        if not match:
            continue
        points = []
        for face_id in references(entities[int(match.group(2))]):
            bound_id = references(entities[face_id])[0]
            loop_id = references(entities[bound_id])[0]
            for oriented_id in references(entities[loop_id]):
                edge = entities[references(entities[oriented_id])[0]]
                for vertex_id in references(edge)[:2]:
                    point_id = references(entities[vertex_id])[0]
                    points.append(triple(entities[point_id]))
        assert points, match.group(1)
        points_of_solid[match.group(1)] = points
    return points_of_solid


points_of_solid = solid_points(entities)
boxes = {
    name: (tuple(min(point[axis] for point in points)
                 for axis in range(3)),
           tuple(max(point[axis] for point in points)
                 for axis in range(3)))
    for name, points in points_of_solid.items()
}
wanted = ("tile-N90", "tile-N00E000", "tile-S30E000", "tile-S90")
expected = [tile for tile in tiles.plan_tiles(30.0)
            if tile["id"] in wanted]
assert len(boxes) == len(expected) == 4, (len(boxes), len(expected))
assert sorted(boxes) == sorted(wanted), sorted(boxes)

for tile in expected:
    low, high = boxes[tile["id"]]
    centre = [(low[axis] + high[axis]) / 2.0 for axis in range(3)]
    radius = math.sqrt(sum(value * value for value in centre))
    latitude = math.degrees(math.asin(centre[2] / radius))
    longitude = math.degrees(math.atan2(centre[1], centre[0]))
    # the solid must sit inside its own tile's patch of the globe
    assert tile["lat_min"] - 1.0 <= latitude <= tile["lat_max"] + 1.0, \
        (tile["id"], latitude)
    span = tile["lon_max"] - tile["lon_min"]
    if span < 359.0:
        gap = abs(((longitude - (tile["lon_min"] + span / 2.0) + 180.0)
                   % 360.0) - 180.0)
        assert gap <= span / 2.0 + 1.0, (tile["id"], longitude)

# a hemisphere's tiles sit in its half of the globe, and the caps on the axis
for tile in expected:
    low, high = boxes[tile["id"]]
    centre = [(low[axis] + high[axis]) / 2.0 for axis in range(3)]
    if tile["id"] == "tile-N90":
        assert centre[2] > 0.0 and math.hypot(centre[0], centre[1]) \
            < abs(centre[2]), (tile["id"], centre)
    elif tile["id"] == "tile-S90":
        assert centre[2] < 0.0 and math.hypot(centre[0], centre[1]) \
            < abs(centre[2]), (tile["id"], centre)
    elif tile["id"].startswith("tile-N"):
        assert centre[2] > 0.0, (tile["id"], centre)
    else:
        assert centre[2] < 0.0, (tile["id"], centre)

# and the solids sit on the globe's shell, never through its middle
radii = [math.sqrt(sum(value * value for value in point))
         for points in points_of_solid.values() for point in points]
assert 40.0 < min(radii) <= 50.0, min(radii)
assert 50.0 < max(radii) < 65.0, max(radii)

files = sorted(glob.glob(os.path.join(directory, "tiles", "*.step")))
assert len(files) == 4, files
sample = os.path.join(directory, "tiles", "tile-N00E000.step")
with open(sample) as handle:
    text_tile = handle.read()
assert "MANIFOLD_SOLID_BREP('tile-N00E000'" in text_tile, sample
assert text_tile.count("MANIFOLD_SOLID_BREP(") == 1, sample
print("06-step-export: assembled orientation ok (%d solids)" % len(boxes))
PY

echo "06-step-export: ok"
