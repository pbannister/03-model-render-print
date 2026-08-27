#!/usr/bin/env python3
#
# rib_firstrow_build.py: visualization + STL generator for the hemispheric
# assembly concept (rib + first row of tiles).
#
# The prior "internal frame" (central hub + per-tile struts) proved too hard
# to assemble and align, so it is dropped.  The replacement plan assembles
# the north and south hemispheres independently, then joins them at the
# equator.  Each hemisphere starts from a full-diameter reinforcing rib that
# sits just above (north) or just below (south) the equator and presses
# against the inner (bottom) faces of that hemisphere's first row of tiles,
# fixing their placement and preventing cumulative error around the seam.
#
# The rib is a rectangular-cross-section ring (see documents/05-stl-approach.md):
#   - outer face at the sea-level diameter (200 mm, R = 100 mm),
#   - inside diameter 20 mm less (180 mm) -> 10 mm radial width,
#   - 10 mm axial thickness.
# It is a single full ring used for both hemispheres (flip it for the other).
#
# This tool renders the two ribs + the first-row tiles so the plan can be
# seen, and also writes the rib's own binary STL for printing:
#   - dataflow.out/rib/rib-firstrow.obj  (grouped web-view model)
#   - dataflow.out/rib/rib.stl           (the printable reinforcing rib)
#   - dataflow.out/rib/rib.json          (manifest)
#
# The tiles are the real tile shells (chamfered walls, flat bottoms) built
# with stl_tiles_build.build_mesh at uniform relief so only the assembly
# placement matters here.
#
# Usage: rib_firstrow_build.py [--radius-mm N] [--base-mm N] ...
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stl_tiles_build as tiles  # noqa: E402

RIB_OUTER_RADIUS_MM = 100.0   # outer face at the sea-level diameter (200 mm)
RIB_INNER_RADIUS_MM = 90.0    # inside diameter 20 mm less -> 10 mm width
RIB_THICKNESS_MM = 10.0       # axial thickness
RIB_SEGMENTS = 256            # circle samples (print smoothness)
EQUATOR_HALF_THICKNESS_MM = 0.25
EQUATOR_INNER_RADIUS_MM = 99.5
EQUATOR_OUTER_RADIUS_MM = 100.5


def local_to_world(point, frame, z_bottom):
    """build_mesh local point (bottom at z = 0) -> world coordinates.

    build_mesh returns triangles in a tile-local frame whose origin is the
    globe centre and whose bottom plane has been translated to local z = 0;
    this undoes that translate and rotates into world space.
    """
    east, north, up = frame
    lx, ly, lz = point
    z_original = lz + z_bottom
    return (
        east[0] * lx + north[0] * ly + up[0] * z_original,
        east[1] * lx + north[1] * ly + up[1] * z_original,
        east[2] * lx + north[2] * ly + up[2] * z_original,
    )


def rectangular_ring_mesh(inner_radius, outer_radius, z_min, z_max, segments):
    """Watertight ring of rectangular cross-section, centred on the z-axis.

    The cross-section is the rectangle [inner_radius, outer_radius] x
    [z_min, z_max], revolved around the z-axis.  Triangles are wound with
    outward normals (right-hand rule) so the result is a closed solid.
    """
    triangles = []

    def outer(u, z):
        return (outer_radius * math.cos(u), outer_radius * math.sin(u), z)

    def inner(u, z):
        return (inner_radius * math.cos(u), inner_radius * math.sin(u), z)

    for i in range(segments):
        u0 = 2.0 * math.pi * i / segments
        u1 = 2.0 * math.pi * (i + 1) / segments

        # outer cylindrical wall (normal +radial)
        p0 = outer(u0, z_min)
        p1 = outer(u1, z_min)
        p2 = outer(u1, z_max)
        p3 = outer(u0, z_max)
        triangles.append((p0, p1, p2))
        triangles.append((p0, p2, p3))

        # inner cylindrical wall (normal -radial, toward the axis)
        q0 = inner(u0, z_min)
        q1 = inner(u1, z_min)
        q2 = inner(u1, z_max)
        q3 = inner(u0, z_max)
        triangles.append((q0, q2, q1))
        triangles.append((q0, q3, q2))

        # top annulus (normal +z)
        t0 = inner(u0, z_max)
        t1 = outer(u0, z_max)
        t2 = outer(u1, z_max)
        t3 = inner(u1, z_max)
        triangles.append((t0, t1, t2))
        triangles.append((t0, t2, t3))

        # bottom annulus (normal -z)
        b0 = inner(u0, z_min)
        b1 = outer(u0, z_min)
        b2 = outer(u1, z_min)
        b3 = inner(u1, z_min)
        triangles.append((b0, b2, b1))
        triangles.append((b0, b3, b2))
    return triangles


def count_unshared_edges(triangles):
    """Number of edges not shared by exactly two faces (0 = watertight)."""
    edges = {}
    for point_a, point_b, point_c in triangles:
        for start, end in ((point_a, point_b), (point_b, point_c),
                           (point_c, point_a)):
            key_start = (round(start[0], 6), round(start[1], 6),
                         round(start[2], 6))
            key_end = (round(end[0], 6), round(end[1], 6), round(end[2], 6))
            key = (key_start, key_end) if key_start <= key_end \
                else (key_end, key_start)
            edges[key] = edges.get(key, 0) + 1
    return sum(1 for count in edges.values() if count != 2)


def build_row(tiles_row, radius_mm, base_mm, sample_degrees):
    """World-space triangle soup for a row of first-row tiles."""
    world_pieces = []
    for tile in tiles_row:
        latitudes, longitudes = tiles.grid_lines(tile, sample_degrees)
        elevation_mm = [[base_mm for _ in longitudes] for _ in latitudes]
        center_lat, center_lon = tiles.tile_center(tile)
        frame = tiles.local_frame(center_lat, center_lon)
        top = tiles.top_grid(tile, latitudes, longitudes, elevation_mm,
                             radius_mm, frame)
        z_bottom = min(point[2] for row in top for point in row) - base_mm
        mesh, _, _ = tiles.build_mesh(tile, latitudes, longitudes,
                                      elevation_mm, radius_mm, base_mm, [])
        world = [
            tuple(local_to_world(vertex, frame, z_bottom) for vertex in tri)
            for tri in mesh
        ]
        world_pieces.append((tile["id"], world))
    return world_pieces


def write_obj(path, groups):
    """Write grouped triangles as a Wavefront OBJ."""
    lines = ["# generated by rib_firstrow_build.py; do not edit manually"]
    vertex_index = 1
    with open(path, "w") as handle:
        handle.write("\n".join(lines) + "\n")
        for group, triangles in groups:
            handle.write("o %s\n" % group)
            for (a, b, c) in triangles:
                for point in (a, b, c):
                    handle.write("v %.6f %.6f %.6f\n" % point)
                handle.write("f %d %d %d\n" % (vertex_index, vertex_index + 1,
                                               vertex_index + 2))
                vertex_index += 3


def run_build(arguments):
    all_tiles = tiles.plan_tiles(arguments.band_degrees)
    north = [t for t in all_tiles if t["id"].startswith("tile-N00")]
    south = [t for t in all_tiles if t["id"].startswith("tile-S30")]
    if not north or not south:
        raise RuntimeError("expected N00 and S30 first-row bands")

    rib_north = rectangular_ring_mesh(RIB_INNER_RADIUS_MM,
                                      RIB_OUTER_RADIUS_MM, 0.0,
                                      RIB_THICKNESS_MM, RIB_SEGMENTS)
    rib_south = rectangular_ring_mesh(RIB_INNER_RADIUS_MM,
                                      RIB_OUTER_RADIUS_MM, -RIB_THICKNESS_MM,
                                      0.0, RIB_SEGMENTS)
    equator_ring = rectangular_ring_mesh(EQUATOR_INNER_RADIUS_MM,
                                         EQUATOR_OUTER_RADIUS_MM,
                                         -EQUATOR_HALF_THICKNESS_MM,
                                         EQUATOR_HALF_THICKNESS_MM,
                                         RIB_SEGMENTS)

    groups = [("rib-north", rib_north), ("rib-south", rib_south),
              ("equator", equator_ring)]
    groups.extend(build_row(north, arguments.radius_mm, arguments.base_mm,
                            arguments.sample_degrees))
    groups.extend(build_row(south, arguments.radius_mm, arguments.base_mm,
                            arguments.sample_degrees))

    os.makedirs(arguments.output_dir, exist_ok=True)
    path_obj = os.path.join(arguments.output_dir, "rib-firstrow.obj")
    write_obj(path_obj, groups)

    # The printable rib: a single full ring, bottom at z = 0 (bed plane).
    # It is symmetric, so the same part serves the north and south assembly
    # (flip it over for the other hemisphere).
    rib_stl = rectangular_ring_mesh(RIB_INNER_RADIUS_MM, RIB_OUTER_RADIUS_MM,
                                    0.0, RIB_THICKNESS_MM, RIB_SEGMENTS)
    volume = tiles.signed_volume(rib_stl)
    expected_volume = (math.pi
                       * (RIB_OUTER_RADIUS_MM ** 2 - RIB_INNER_RADIUS_MM ** 2)
                       * RIB_THICKNESS_MM)
    unshared = count_unshared_edges(rib_stl)
    path_stl = os.path.join(arguments.output_dir, "rib.stl")
    tiles.write_stl(path_stl, rib_stl,
                    "model-render-print reinforcing rib (R100/R90 x 10 mm)")

    total_triangles = sum(len(triangles) for _, triangles in groups)
    manifest = {
        "generated_by": "scripts/rib_firstrow_build.py",
        "do_not_edit_by_hand": True,
        "parameters": {
            "band_degrees": arguments.band_degrees,
            "radius_mm": arguments.radius_mm,
            "base_mm": arguments.base_mm,
            "sample_degrees": arguments.sample_degrees,
            "rib_outer_radius_mm": RIB_OUTER_RADIUS_MM,
            "rib_inner_radius_mm": RIB_INNER_RADIUS_MM,
            "rib_width_mm": RIB_OUTER_RADIUS_MM - RIB_INNER_RADIUS_MM,
            "rib_thickness_mm": RIB_THICKNESS_MM,
            "rib_outer_diameter_mm": 2.0 * RIB_OUTER_RADIUS_MM,
            "rib_inner_diameter_mm": 2.0 * RIB_INNER_RADIUS_MM,
        },
        "rib_stl": {
            "file": "rib.stl",
            "triangles": len(rib_stl),
            "volume_mm3": round(volume, 3),
            "expected_volume_mm3": round(expected_volume, 3),
            "unshared_edges": unshared,
        },
        "groups": [{"name": name, "triangles": len(triangles)}
                   for name, triangles in groups],
        "total_triangles": total_triangles,
    }
    path_manifest = os.path.join(arguments.output_dir, "rib.json")
    with open(path_manifest, "w") as handle:
        json.dump(manifest, handle, indent=4)
        handle.write("\n")
    print("rib-firstrow: wrote %s, %s and %s (%d groups, %d triangles; rib "
          "volume %.1f mm^3)" % (path_obj, path_stl, path_manifest,
                                 len(groups), total_triangles, volume))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="rib_firstrow_build",
        description="Render the rib + first-row assembly visualization and "
                    "the rib STL.")
    parser.add_argument("--output-dir", default=None,
                        help="output directory (default: dataflow.out/rib)")
    parser.add_argument("--band-degrees", type=float, default=30.0)
    parser.add_argument("--radius-mm", type=float, default=100.0)
    parser.add_argument("--base-mm", type=float, default=3.0)
    parser.add_argument("--sample-degrees", type=float, default=1.0)
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    if arguments.output_dir is None:
        repository_root = os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))
        arguments.output_dir = os.path.join(repository_root, "dataflow.out",
                                            "rib")
    try:
        return run_build(arguments)
    except (ValueError, RuntimeError) as error:
        print("rib-firstrow: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
