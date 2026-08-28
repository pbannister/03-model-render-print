#!/usr/bin/env python3
"""Export one hemisphere (tiles only) as a STEP file (AP214).

Each tile becomes one MANIFOLD_SOLID_BREP at its world position in the
assembled hemisphere, so the file can be edited in OnShape, FreeCAD, etc.
The tiles are rendered at `--sample-degrees` (default 5) so the STEP stays
compact enough for CAD work; raise the density for more relief detail.

Usage: hemisphere_step.py [--hemisphere north|south] [--sample-degrees 5]
                          [--radius-mm 100] [--output-dir dataflow.out/step]
"""

import argparse
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stl_tiles_build as tiles


def format_real(value):
    """STEP real literal: always carries a decimal point."""
    text = "%.6f" % value
    return text


def local_to_world(point, frame, z_bottom):
    """Tile-local point (bottom at z = 0) -> world coordinates."""
    east, north, up = frame
    p = (point[0], point[1], point[2] + z_bottom)
    return (
        p[0] * east[0] + p[1] * north[0] + p[2] * up[0],
        p[0] * east[1] + p[1] * north[1] + p[2] * up[1],
        p[0] * east[2] + p[1] * north[2] + p[2] * up[2],
    )


def build_hemisphere_tiles(tiles_hemisphere, radius_mm, base_mm, grid,
                           transform, elevation_min, elevation_max,
                           parameters, sample_degrees):
    """World-space triangle soups for the hemisphere's tiles."""
    pieces = []
    for tile in tiles_hemisphere:
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


class StepWriter(object):
    """Minimal AP214 triangle-mesh STEP writer (one solid per part)."""

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

    def manifold_solid(self, shell_id):
        return self.add("MANIFOLD_SOLID_BREP('',#%d)" % shell_id)

    def product_block(self, name, solid_id, context_id, product_context_id):
        product = self.add("PRODUCT('%s','%s','',(#%d))"
                           % (name, name, product_context_id))
        formation = self.add("PRODUCT_DEFINITION_FORMATION('','',#%d)"
                             % product)
        definition = self.add("PRODUCT_DEFINITION('design','',#%d,#%d)"
                              % (formation, product_context_id))
        shape = self.add("PRODUCT_DEFINITION_SHAPE('','',#%d)" % definition)
        representation = self.add(
            "ADVANCED_BREP_SHAPE_REPRESENTATION('',(#%d),#%d)"
            % (solid_id, context_id))
        self.add("SHAPE_DEFINITION_REPRESENTATION(#%d,#%d)"
                 % (shape, representation))

    def write(self, path, parts, file_name):
        """parts: list of (name, triangles)."""
        context = self.add(
            "APPLICATION_CONTEXT('configuration controlled 3d designs of "
            "mechanical parts and assemblies')")
        self.add("APPLICATION_PROTOCOL_DEFINITION('international "
                 "standard','config_control_design',1994,#%d)" % context)
        product_context = self.add("PRODUCT_CONTEXT('',#%d,'mechanical')"
                                   % context)

        for name, triangles in parts:
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

            def get_edge(v1, v2):
                pair = (min(v1, v2), max(v1, v2))
                if pair in edge_of_pair:
                    return edge_of_pair[pair], v1 == pair[0]
                start = point_of_vertex[pair[0]]
                end = point_of_vertex[pair[1]]
                dx = end[0] - start[0]
                dy = end[1] - start[1]
                dz = end[2] - start[2]
                length = math.sqrt(dx * dx + dy * dy + dz * dz)
                origin_id = self.cartesian_point(start)
                if length > 1e-12:
                    direction_id = self.direction(
                        (dx / length, dy / length, dz / length))
                else:
                    direction_id = self.direction((1.0, 0.0, 0.0))
                vector_id = self.vector(direction_id, length)
                line_id = self.line(origin_id, vector_id)
                edge_id = self.edge_curve(pair[0], pair[1], line_id)
                edge_of_pair[pair] = edge_id
                return edge_id, v1 == pair[0]

            face_ids = []
            for tri in triangles:
                v = [get_vertex(p) for p in tri]
                # outward face normal for the plane geometry
                a, b, c = tri
                ux, uy, uz = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
                vx, vy, vz = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
                nx, ny, nz = (uy * vz - uz * vy, uz * vx - ux * vz,
                              ux * vy - uy * vx)
                nlen = math.sqrt(nx * nx + ny * ny + nz * nz)
                if nlen > 1e-12:
                    nx, ny, nz = nx / nlen, ny / nlen, nz / nlen
                else:
                    nx, ny, nz = 0.0, 0.0, 1.0
                plane_point_id = self.cartesian_point(a)
                plane_normal_id = self.direction((nx, ny, nz))
                plane_id = self.plane(plane_point_id, plane_normal_id)

                oriented = []
                for i in range(3):
                    edge_id, same_sense = get_edge(v[i], v[(i + 1) % 3])
                    oriented.append(self.oriented_edge(edge_id, same_sense))
                loop_id = self.edge_loop(oriented)
                bound_id = self.face_outer_bound(loop_id)
                face_ids.append(self.advanced_face([bound_id], plane_id))

            shell_id = self.closed_shell(face_ids)
            solid_id = self.manifold_solid(shell_id)
            self.product_block(name, solid_id, context, product_context)

        header = [
            "ISO-10303-21;",
            "HEADER;",
            "FILE_DESCRIPTION(('STEP file generated by model-render-print'),"
            "'2;1');",
            "FILE_NAME('%s','',(''),(''),'model-render-print','','');"
            % file_name,
            "FILE_SCHEMA(('CONFIG_CONTROL_DESIGN'));",
            "ENDSEC;",
            "DATA;",
        ]
        footer = ["ENDSEC;", "END-ISO-10303-21;"]
        with open(path, "w") as handle:
            handle.write("\n".join(header) + "\n")
            handle.write("\n".join(self.lines) + "\n")
            handle.write("\n".join(footer) + "\n")


def run(arguments):
    from osgeo import gdal

    gdal.UseExceptions()
    working = tempfile.mkdtemp(prefix="hemisphere-step-")
    try:
        path_vrt = tiles.build_vrt(arguments.source_dir, working)
        grid, transform = tiles.load_global_grid(
            path_vrt, arguments.sample_degrees, working
        )
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
        if arguments.hemisphere == "north":
            band_ids = ("tile-N00", "tile-N30", "tile-N90")
        else:
            band_ids = ("tile-S60", "tile-S30", "tile-S90")
        hemisphere_tiles = [
            tile for tile in all_tiles
            if tile["id"].startswith(band_ids)
        ]
        if not hemisphere_tiles:
            raise RuntimeError("no tiles for hemisphere %s"
                               % arguments.hemisphere)
        pieces = build_hemisphere_tiles(
            hemisphere_tiles, arguments.radius_mm, arguments.base_mm,
            grid, transform, elevation_min, elevation_max, parameters,
            arguments.sample_degrees,
        )
    finally:
        shutil.rmtree(working, ignore_errors=True)

    os.makedirs(arguments.output_dir, exist_ok=True)
    name = "hemisphere-%s.step" % arguments.hemisphere
    path = os.path.join(arguments.output_dir, name)
    writer = StepWriter()
    writer.write(path, pieces, name)
    total_triangles = sum(len(triangles) for _, triangles in pieces)
    print(
        "hemisphere-step: %d tiles, %d triangles -> %s (%.1f MB)"
        % (len(pieces), total_triangles, path,
           os.path.getsize(path) / 1e6)
    )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="hemisphere_step",
        description="Export one hemisphere (tiles only) as a STEP file.",
    )
    parser.add_argument(
        "--hemisphere",
        choices=("north", "south"),
        default="north",
        help="which hemisphere (default north)",
    )
    parser.add_argument(
        "--sample-degrees",
        type=float,
        default=5.0,
        help="tile mesh grid spacing (default 5; lower = more relief "
        "detail but a much larger STEP file)",
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
        repository_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        arguments.output_dir = os.path.join(repository_root, "dataflow.out", "step")
    try:
        run(arguments)
    except (ValueError, RuntimeError) as error:
        print("hemisphere-step: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
