#!/usr/bin/env python3
"""Export the tile set as STEP files (AP214) for CAD editing.

Every tile becomes one MANIFOLD_SOLID_BREP at its **world position in the
assembled globe** -- each tile keeps its own local frame (up is the sphere
normal at the tile centre), so the solids sit in the assembly exactly as
they do when glued.  Nothing is laid flat for printing; the print-ready
orientation lives in the STL files instead.

Two outputs are written under `--output-dir` (default `dataflow.out/step`):

  tiles-all.step        the whole globe: one product holding all 42 tiles
                        as separately named solids, so a CAD import gives
                        one part studio with 42 bodies in place;
  tiles/tile-<id>.step  one file per tile, for editing a single tile.

Use `--hemisphere` to take one hemisphere, or `--tile` (repeatable) to take
just the tiles named.

Units are millimetres (declared through the geometric representation
context, so CAD tools import at the right scale).

The tiles are meshed at `--sample-degrees` (default 5): the STEP is a
faceted B-rep, so a finer grid multiplies the file size.

Usage: tiles_step.py [--hemisphere north|south|all] [--sample-degrees 5]
                     [--radius-mm 100] [--output-dir dataflow.out/step]
"""

import argparse
import datetime
import math
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stl_tiles_build as tiles

BAND_IDS = {
    "north": ("tile-N00", "tile-N30", "tile-N90"),
    "south": ("tile-S60", "tile-S30", "tile-S90"),
}


def format_real(value):
    """STEP real literal: always carries a decimal point."""
    return "%.6f" % value


def local_to_world(point, frame, z_bottom):
    """Tile-local point (bottom at z = 0) -> world coordinates."""
    east, north, up = frame
    p = (point[0], point[1], point[2] + z_bottom)
    return (
        p[0] * east[0] + p[1] * north[0] + p[2] * up[0],
        p[0] * east[1] + p[1] * north[1] + p[2] * up[1],
        p[0] * east[2] + p[1] * north[2] + p[2] * up[2],
    )


def build_tiles(tiles_all, radius_mm, base_mm, grid, transform,
                elevation_min, elevation_max, parameters, sample_degrees):
    """World-space triangle soups for the given tiles, in assembly."""
    pieces = []
    for tile in tiles_all:
        latitudes, longitudes = tiles.grid_lines(tile, sample_degrees)
        elevations = tiles.sample_grid(grid, transform, latitudes, longitudes)
        elevation_mm = [
            [
                tiles.elevation_to_mm(value, elevation_min, elevation_max,
                                      parameters)
                for value in row
            ]
            for row in elevations
        ]
        center_lat, center_lon = tiles.tile_center(tile)
        frame = tiles.local_frame(center_lat, center_lon)
        top = tiles.top_grid(tile, latitudes, longitudes, elevation_mm,
                             radius_mm, frame)
        z_bottom = min(point[2] for row in top for point in row) - base_mm
        mesh, _, _ = tiles.build_mesh(tile, latitudes, longitudes,
                                      elevation_mm, radius_mm, base_mm)
        world = [
            tuple(local_to_world(vertex, frame, z_bottom) for vertex in tri)
            for tri in mesh
        ]
        pieces.append((tile["id"], world))
    return pieces


def tile_bounds(triangles):
    """(min, max) corners of a triangle soup."""
    points = [point for triangle in triangles for point in triangle]
    return (
        tuple(min(point[axis] for point in points) for axis in range(3)),
        tuple(max(point[axis] for point in points) for axis in range(3)),
    )


class StepWriter(object):
    """Minimal AP214 writer: one product holding any number of solids."""

    def __init__(self):
        self.lines = []
        self.next_id = 1

    def add(self, body):
        self.lines.append("#%d = %s;" % (self.next_id, body))
        self.next_id += 1
        return self.next_id - 1

    def cartesian_point(self, p):
        return self.add("CARTESIAN_POINT('',(%s,%s,%s))"
                        % (format_real(p[0]), format_real(p[1]),
                           format_real(p[2])))

    def direction(self, d):
        return self.add("DIRECTION('',(%s,%s,%s))"
                        % (format_real(d[0]), format_real(d[1]),
                           format_real(d[2])))

    def vector(self, direction_id, magnitude):
        return self.add("VECTOR('',#%d,%s)" % (direction_id,
                                               format_real(magnitude)))

    def line(self, point_id, vector_id):
        return self.add("LINE('',#%d,#%d)" % (point_id, vector_id))

    def vertex_point(self, point_id):
        return self.add("VERTEX_POINT('',#%d)" % point_id)

    def edge_curve(self, start_vertex, end_vertex, line_id):
        return self.add("EDGE_CURVE('',#%d,#%d,#%d,.T.)"
                        % (start_vertex, end_vertex, line_id))

    def oriented_edge(self, edge_id, sense):
        return self.add("ORIENTED_EDGE('',*,*,#%d,%s)"
                        % (edge_id, ".T." if sense else ".F."))

    def edge_loop(self, oriented_ids):
        refs = ",".join("#%d" % i for i in oriented_ids)
        return self.add("EDGE_LOOP('',(%s))" % refs)

    def face_outer_bound(self, loop_id):
        return self.add("FACE_OUTER_BOUND('',#%d,.T.)" % loop_id)

    def plane(self, point_id, direction_id):
        return self.add("PLANE('',#%d,#%d)" % (point_id, direction_id))

    def advanced_face(self, bound_ids, plane_id):
        refs = ",".join("#%d" % i for i in bound_ids)
        return self.add("ADVANCED_FACE('',(%s),#%d,.T.)" % (refs, plane_id))

    def closed_shell(self, face_ids):
        refs = ",".join("#%d" % i for i in face_ids)
        return self.add("CLOSED_SHELL('',(%s))" % refs)

    def manifold_solid(self, name, shell_id):
        return self.add("MANIFOLD_SOLID_BREP('%s',#%d)" % (name, shell_id))

    def solid(self, name, triangles):
        """One closed, faceted solid: a vertex/edge shared where triangles
        meet, one planar ADVANCED_FACE per triangle."""
        vertex_of_point = {}
        point_of_vertex = {}
        edge_of_pair = {}

        def get_vertex(point):
            key = (round(point[0], 6), round(point[1], 6),
                   round(point[2], 6))
            if key in vertex_of_point:
                return vertex_of_point[key]
            point_id = self.cartesian_point(point)
            vertex_id = self.vertex_point(point_id)
            vertex_of_point[key] = vertex_id
            point_of_vertex[vertex_id] = point
            return vertex_id

        def get_edge(first, second):
            pair = (min(first, second), max(first, second))
            if pair in edge_of_pair:
                return edge_of_pair[pair], first == pair[0]
            start = point_of_vertex[pair[0]]
            end = point_of_vertex[pair[1]]
            delta = (end[0] - start[0], end[1] - start[1],
                     end[2] - start[2])
            length = math.sqrt(sum(value * value for value in delta))
            origin_id = self.cartesian_point(start)
            if length > 1e-12:
                direction_id = self.direction(
                    (delta[0] / length, delta[1] / length,
                     delta[2] / length))
            else:
                direction_id = self.direction((1.0, 0.0, 0.0))
            vector_id = self.vector(direction_id, length)
            line_id = self.line(origin_id, vector_id)
            edge_id = self.edge_curve(pair[0], pair[1], line_id)
            edge_of_pair[pair] = edge_id
            return edge_id, first == pair[0]

        face_ids = []
        for triangle in triangles:
            vertices = [get_vertex(point) for point in triangle]
            point_a, point_b, point_c = triangle
            u = [point_b[i] - point_a[i] for i in range(3)]
            v = [point_c[i] - point_a[i] for i in range(3)]
            normal = [u[1] * v[2] - u[2] * v[1],
                      u[2] * v[0] - u[0] * v[2],
                      u[0] * v[1] - u[1] * v[0]]
            length = math.sqrt(sum(value * value for value in normal))
            if length > 1e-12:
                normal = [value / length for value in normal]
            else:
                normal = [0.0, 0.0, 1.0]
            plane_id = self.plane(self.cartesian_point(point_a),
                                  self.direction(normal))
            oriented = []
            for index in range(3):
                edge_id, same_sense = get_edge(vertices[index],
                                               vertices[(index + 1) % 3])
                oriented.append(self.oriented_edge(edge_id, same_sense))
            loop_id = self.edge_loop(oriented)
            bound_id = self.face_outer_bound(loop_id)
            face_ids.append(self.advanced_face([bound_id], plane_id))
        return self.manifold_solid(name, self.closed_shell(face_ids))

    def context(self):
        """Application, product and geometric (millimetre) contexts."""
        application = self.add(
            "APPLICATION_CONTEXT('configuration controlled 3d designs of "
            "mechanical parts and assemblies')")
        self.add("APPLICATION_PROTOCOL_DEFINITION('international standard',"
                 "'config_control_design',1994,#%d)" % application)
        product_context = self.add("PRODUCT_CONTEXT('',#%d,'mechanical')"
                                   % application)
        definition_context = self.add(
            "PRODUCT_DEFINITION_CONTEXT('part definition',#%d,'design')"
            % application)
        geometric = self.add(
            "( GEOMETRIC_REPRESENTATION_CONTEXT(3) "
            "GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#%d)) "
            "GLOBAL_UNIT_ASSIGNED_CONTEXT((#%d,#%d,#%d)) "
            "REPRESENTATION_CONTEXT('','') )"
            % (self.next_id, self.next_id + 1, self.next_id + 2,
               self.next_id + 3))
        self.add("UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-06),#%d,"
                 "'distance_accuracy_value','confusion accuracy')"
                 % (self.next_id + 1))
        self.add("( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) )")
        self.add("( NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.) )")
        self.add("( NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) "
                 "SOLID_ANGLE_UNIT() )")
        return product_context, definition_context, geometric

    def write(self, path, parts, product_name, file_name):
        """parts: [(name, triangles)] -> one product holding every solid."""
        product_context, definition_context, geometric = self.context()
        solid_ids = [self.solid(name, triangles) for name, triangles in parts]
        representation = self.add(
            "ADVANCED_BREP_SHAPE_REPRESENTATION('%s',(%s),#%d)"
            % (product_name,
               ",".join("#%d" % i for i in solid_ids), geometric))
        product = self.add("PRODUCT('%s','%s','',(#%d))"
                           % (product_name, product_name, product_context))
        formation = self.add("PRODUCT_DEFINITION_FORMATION('','',#%d)"
                             % product)
        definition = self.add("PRODUCT_DEFINITION('design','',#%d,#%d)"
                              % (formation, definition_context))
        shape = self.add("PRODUCT_DEFINITION_SHAPE('','',#%d)" % definition)
        self.add("SHAPE_DEFINITION_REPRESENTATION(#%d,#%d)"
                 % (shape, representation))

        stamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        header = [
            "ISO-10303-21;",
            "HEADER;",
            "FILE_DESCRIPTION(('tiles of the printable Earth, in assembly'),"
            "'2;1');",
            "FILE_NAME('%s','%s',('model-render-print'),(''),"
            "'model-render-print','model-render-print','');"
            % (file_name, stamp),
            "FILE_SCHEMA(('CONFIG_CONTROL_DESIGN'));",
            "ENDSEC;",
            "DATA;",
        ]
        footer = ["ENDSEC;", "END-ISO-10303-21;"]
        with open(path, "w") as handle:
            handle.write("\n".join(header) + "\n")
            handle.write("\n".join(self.lines) + "\n")
            handle.write("\n".join(footer) + "\n")
        return solid_ids


def verify_step(path):
    """Re-read a written STEP file; check its structure and references.

    Returns (entity count, solid names).  Raises RuntimeError when the file
    is not a well-formed AP214 part: bad header, missing millimetre units,
    an entity id out of sequence, or a reference to a missing entity.
    """
    entities = set()
    referenced = set()
    solids = []
    expected = 1
    flags = {"schema": False, "units": False, "context": False}
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if "FILE_SCHEMA(('CONFIG_CONTROL_DESIGN'))" in line:
                flags["schema"] = True
            if "( LENGTH_UNIT()" in line:
                flags["units"] = True
            if "( GEOMETRIC_REPRESENTATION_CONTEXT(3)" in line:
                flags["context"] = True
            if not line.startswith("#"):
                continue
            match = re.match(r"^#(\d+) = (.*);$", line)
            if not match:
                raise RuntimeError("malformed entity line: %s" % line[:60])
            identifier = int(match.group(1))
            if identifier != expected:
                raise RuntimeError("entity id %d out of sequence (want %d)"
                                   % (identifier, expected))
            expected += 1
            entities.add(identifier)
            body = match.group(2)
            referenced.update(int(value) for value in re.findall(r"#(\d+)",
                                                                 body))
            if body.startswith("MANIFOLD_SOLID_BREP("):
                solids.append(body.split("'")[1])
    missing = referenced - entities
    if missing:
        raise RuntimeError("%d references point at missing entities (e.g. #%d)"
                           % (len(missing), sorted(missing)[0]))
    for name, present in sorted(flags.items()):
        if not present:
            raise RuntimeError("the STEP header is missing its %s" % name)
    return len(entities), solids


def write_step(path, parts, product_name):
    """Write one STEP file holding `parts` as named solids."""
    writer = StepWriter()
    writer.write(path, parts, product_name,
                 os.path.basename(path))
    return len(parts)


def run(arguments):
    from osgeo import gdal

    gdal.UseExceptions()
    working = tempfile.mkdtemp(prefix="tiles-step-")
    try:
        path_vrt = tiles.build_vrt(arguments.source_dir, working)
        grid, transform = tiles.load_global_grid(
            path_vrt, arguments.sample_degrees, working)
        valid = [value for row in grid for value in row
                 if value > tiles.NODATA_LIMIT]
        if not valid:
            raise RuntimeError("the global grid has no valid pixels")
        elevation_min = float(min(valid))
        elevation_max = float(max(valid))
        parameters = {
            "oceans_flat": arguments.oceans_flat,
            "elev_min": None,
            "elev_max": None,
            "base_mm": arguments.base_mm,
            "relief_mm": arguments.relief_mm,
        }
        all_tiles = tiles.plan_tiles(arguments.band_degrees)
        if arguments.tile:
            wanted = set(arguments.tile)
            selected = [tile for tile in all_tiles
                        if tile["id"] in wanted]
            missing = sorted(wanted - {tile["id"] for tile in selected})
            if missing:
                raise RuntimeError("unknown tiles: %s" % ", ".join(missing))
        elif arguments.hemisphere == "all":
            selected = all_tiles
        else:
            prefixes = BAND_IDS[arguments.hemisphere]
            selected = [tile for tile in all_tiles
                        if tile["id"].startswith(prefixes)]
        if not selected:
            raise RuntimeError("no tiles selected")
        pieces = build_tiles(selected, arguments.radius_mm, arguments.base_mm,
                             grid, transform, elevation_min, elevation_max,
                             parameters, arguments.sample_degrees)
    finally:
        shutil.rmtree(working, ignore_errors=True)

    os.makedirs(arguments.output_dir, exist_ok=True)
    selection = "selected" if arguments.tile else arguments.hemisphere
    name = "tiles-%s.step" % selection
    path = os.path.join(arguments.output_dir, name)
    write_step(path, pieces, "tiles-%s" % selection)
    total = sum(len(triangles) for _, triangles in pieces)
    entity_count, names = verify_step(path)
    if len(names) != len(pieces):
        raise RuntimeError("%s holds %d solids for %d tiles"
                           % (path, len(names), len(pieces)))
    print("tiles-step: %s -> %s (%d tiles, %d triangles, %.1f MB)"
          % (selection, path, len(pieces), total,
             os.path.getsize(path) / 1e6))
    print("tiles-step: verified %d entities, %d solids, every reference "
          "resolves" % (entity_count, len(names)))

    if arguments.split:
        directory = os.path.join(arguments.output_dir, "tiles")
        os.makedirs(directory, exist_ok=True)
        for tile_id, triangles in pieces:
            path_tile = os.path.join(directory, "%s.step" % tile_id)
            write_step(path_tile, [(tile_id, triangles)], tile_id)
        last = os.path.join(directory, "%s.step" % pieces[-1][0])
        _, names = verify_step(last)
        if names != [pieces[-1][0]]:
            raise RuntimeError("%s does not hold its own tile" % last)
        print("tiles-step: wrote %d per-tile files into %s (verified %s)"
              % (len(pieces), directory, os.path.basename(last)))

    low, high = tile_bounds([triangle for _, piece in pieces
                             for triangle in piece])
    print("tiles-step: assembled bounds x %.1f..%.1f y %.1f..%.1f "
          "z %.1f..%.1f mm"
          % (low[0], high[0], low[1], high[1], low[2], high[2]))


def build_parser():
    parser = argparse.ArgumentParser(
        prog="tiles_step",
        description="Export the tiles as STEP files, in assembly.",
    )
    parser.add_argument(
        "--hemisphere",
        choices=("north", "south", "all"),
        default="all",
        help="which tiles to export (default all: the whole globe)",
    )
    parser.add_argument(
        "--tile",
        action="append",
        default=None,
        metavar="ID",
        help="export only this tile id (repeatable), e.g. --tile tile-N90",
    )
    parser.add_argument(
        "--sample-degrees",
        type=float,
        default=5.0,
        help="tile mesh grid spacing (default 5; lower = more relief "
        "detail but a much larger STEP file)",
    )
    parser.add_argument(
        "--split",
        action="store_true",
        default=True,
        help="also write one STEP file per tile (default on)",
    )
    parser.add_argument(
        "--no-split",
        dest="split",
        action="store_false",
        help="write only the combined file",
    )
    parser.add_argument("--radius-mm", type=float, default=100.0)
    parser.add_argument("--base-mm", type=float, default=3.0)
    parser.add_argument("--relief-mm", type=float, default=10.0)
    parser.add_argument("--band-degrees", type=float, default=30.0)
    parser.add_argument("--oceans-flat", action="store_true", default=True)
    parser.add_argument(
        "--source-dir",
        default="/datasets/dataset-etopo-2022",
        help="ETOPO 2022 source tile directory",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="output directory (default: dataflow.out/step)",
    )
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    if arguments.output_dir is None:
        repository_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))
        arguments.output_dir = os.path.join(repository_root, "dataflow.out",
                                            "step")
    try:
        run(arguments)
    except (ValueError, RuntimeError) as error:
        print("tiles-step: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
