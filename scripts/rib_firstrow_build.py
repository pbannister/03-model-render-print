#!/usr/bin/env python3
#
# rib_firstrow_build.py: visualization generator for the hemispheric
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
# This tool renders exactly that starting state so the plan can be seen:
#   - the north rib + the 12 first-row tiles just above the equator (N00),
#   - the south rib + the 12 first-row tiles just below the equator (S30),
#   - a faint reference ring at the equator.
#
# The tiles are the real tile shells (chamfered walls, flat bottoms) built
# with stl_tiles_build.build_mesh at uniform relief so only the assembly
# placement matters here.  Output is a grouped Wavefront OBJ plus a small
# manifest (dataflow.out/rib/).
#
# Usage: rib_firstrow_build.py [--radius-mm N] [--base-mm N] ...
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stl_tiles_build as tiles  # noqa: E402

RIB_TUBE_RADIUS_MM = 3.0   # rib hoop cross-section (minor radius)
RIB_SEGMENTS = 128         # torus samples around the ring
RIB_TUBE_SEGMENTS = 12     # torus samples around the tube
EQUATOR_TUBE_RADIUS_MM = 0.4


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


def torus_mesh(major_radius, tube_radius, z_center, segments, tube_segments):
    """Triangle soup for a torus centred on the z-axis at z = z_center."""
    triangles = []

    def center_point(u):
        return (major_radius * math.cos(u), major_radius * math.sin(u))

    def radial(u):
        return (math.cos(u), math.sin(u))

    for i in range(segments):
        u0 = 2.0 * math.pi * i / segments
        u1 = 2.0 * math.pi * (i + 1) / segments
        c0 = center_point(u0)
        c1 = center_point(u1)
        r0 = radial(u0)
        r1 = radial(u1)
        for j in range(tube_segments):
            v0 = 2.0 * math.pi * j / tube_segments
            v1 = 2.0 * math.pi * (j + 1) / tube_segments

            def tube_point(center, outward, v):
                radius = tube_radius * math.cos(v)
                z = z_center + tube_radius * math.sin(v)
                return (
                    center[0] + outward[0] * radius,
                    center[1] + outward[1] * radius,
                    z,
                )

            p00 = tube_point(c0, r0, v0)
            p10 = tube_point(c1, r1, v0)
            p01 = tube_point(c0, r0, v1)
            p11 = tube_point(c1, r1, v1)
            triangles.append((p00, p10, p11))
            triangles.append((p00, p11, p01))
    return triangles


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


def equator_bottom_radius(tiles_row, radius_mm, base_mm, sample_degrees):
    """Mean radius (from the z-axis) of the row's equator-edge bottom seam.

    The first-row tiles touch the equator along one wall: the south edge for
    the northern row (lat_min == 0) and the north edge for the southern row
    (lat_max == 0).  This measures where that seam sits so the rib can be
    sized to contact the tile inner faces there.
    """
    seam_points = []
    for tile in tiles_row:
        latitudes, longitudes = tiles.grid_lines(tile, sample_degrees)
        elevation_mm = [[base_mm for _ in longitudes] for _ in latitudes]
        center_lat, center_lon = tiles.tile_center(tile)
        frame = tiles.local_frame(center_lat, center_lon)
        top = tiles.top_grid(tile, latitudes, longitudes, elevation_mm,
                             radius_mm, frame)
        z_bottom = min(point[2] for row in top for point in row) - base_mm
        boundary, _, lats, _ = tiles.boundary_ring(tile, top, latitudes,
                                                   longitudes)
        for point, lat in zip(boundary, lats):
            if abs(lat) > 1e-9:
                continue
            projected = tiles.radial_projection(point, z_bottom)
            translated = (projected[0], projected[1], projected[2] - z_bottom)
            world = local_to_world(translated, frame, z_bottom)
            seam_points.append(world)
    if not seam_points:
        raise RuntimeError("no equator-edge seam points found")
    return sum(math.hypot(w[0], w[1]) for w in seam_points) / len(seam_points)


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

    radius_north = equator_bottom_radius(north, arguments.radius_mm,
                                         arguments.base_mm,
                                         arguments.sample_degrees)
    radius_south = equator_bottom_radius(south, arguments.radius_mm,
                                         arguments.base_mm,
                                         arguments.sample_degrees)
    radius_equator = 0.5 * (radius_north + radius_south)

    rib_major = radius_equator - RIB_TUBE_RADIUS_MM
    rib_north = torus_mesh(rib_major, RIB_TUBE_RADIUS_MM,
                           +RIB_TUBE_RADIUS_MM, RIB_SEGMENTS,
                           RIB_TUBE_SEGMENTS)
    rib_south = torus_mesh(rib_major, RIB_TUBE_RADIUS_MM,
                           -RIB_TUBE_RADIUS_MM, RIB_SEGMENTS,
                           RIB_TUBE_SEGMENTS)
    equator_ring = torus_mesh(arguments.radius_mm, EQUATOR_TUBE_RADIUS_MM,
                              0.0, RIB_SEGMENTS, RIB_TUBE_SEGMENTS)

    groups = [("rib-north", rib_north), ("rib-south", rib_south),
              ("equator", equator_ring)]
    groups.extend(build_row(north, arguments.radius_mm, arguments.base_mm,
                            arguments.sample_degrees))
    groups.extend(build_row(south, arguments.radius_mm, arguments.base_mm,
                            arguments.sample_degrees))

    os.makedirs(arguments.output_dir, exist_ok=True)
    path_obj = os.path.join(arguments.output_dir, "rib-firstrow.obj")
    write_obj(path_obj, groups)

    total_triangles = sum(len(triangles) for _, triangles in groups)
    manifest = {
        "generated_by": "scripts/rib_firstrow_build.py",
        "do_not_edit_by_hand": True,
        "parameters": {
            "band_degrees": arguments.band_degrees,
            "radius_mm": arguments.radius_mm,
            "base_mm": arguments.base_mm,
            "sample_degrees": arguments.sample_degrees,
            "rib_tube_radius_mm": RIB_TUBE_RADIUS_MM,
            "rib_major_radius_mm": round(rib_major, 3),
            "seam_radius_mm": round(radius_equator, 3),
        },
        "groups": [{"name": name, "triangles": len(triangles)}
                   for name, triangles in groups],
        "total_triangles": total_triangles,
    }
    path_manifest = os.path.join(arguments.output_dir, "rib.json")
    with open(path_manifest, "w") as handle:
        json.dump(manifest, handle, indent=4)
        handle.write("\n")
    print("rib-firstrow: wrote %s and %s (%d groups, %d triangles)"
          % (path_obj, path_manifest, len(groups), total_triangles))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="rib_firstrow_build",
        description="Render the rib + first-row assembly visualization.")
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
