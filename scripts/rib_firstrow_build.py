#!/usr/bin/env python3
#
# rib_firstrow_build.py: visualization + STL generator for the hemispheric
# assembly concept (rib + first row of tiles).
#
# The prior "internal frame" (central hub + per-tile struts) proved too hard
# to assemble and align, so it is dropped.  The replacement plan assembles
# the north and south hemispheres independently, then joins them at the
# equator.  Each hemisphere starts from a full-diameter reinforcing rib that
# sits just above (north) or just below (south) the equator and whose outer
# face(s) make full contact with the inner (flat-bottom) faces of that
# hemisphere's first row of tiles, fixing their placement and preventing
# cumulative error around the seam.
#
# The rib's outer surface is NOT a cylinder: it is a series of flat facets,
# one per first-row tile, each lying in that tile's bottom plane, so each
# facet mates flush with the tile's inner face.  The rib is otherwise a
# rectangular ring: inner diameter 180 mm (inner radius 90 mm) and 10 mm
# axial thickness.
#
# Outputs under dataflow.out/rib/:
#   - rib-firstrow.obj   grouped web-view model (ribs + first-row tiles)
#   - rib-north.stl      the printable north rib (bottom at z = 0)
#   - rib-south.stl      the printable south rib (bottom at z = 0)
#   - rib.json           manifest
#
# The facets are sized from the real elevation field (same pipeline as the
# tile build), so they match the tiles' actual bottom planes.  --sample-degrees
# defaults to 1.0 for a light web view; use 0.25 to match the production
# tile build exactly (the view OBJ then gets much larger).
#
# Usage: rib_firstrow_build.py [--sample-degrees N] [--relief-mm N] ...
import argparse
import json
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stl_tiles_build as tiles  # noqa: E402

RIB_INNER_RADIUS_MM = 90.0   # inside diameter 180 mm (20 mm less than sea level)
RIB_THICKNESS_MM = 10.0      # axial thickness
EQUATOR_HALF_THICKNESS_MM = 0.25
EQUATOR_INNER_RADIUS_MM = 99.5
EQUATOR_OUTER_RADIUS_MM = 100.5


def local_to_world(point, frame, z_bottom):
    """build_mesh local point (bottom at z = 0) -> world coordinates."""
    east, north, up = frame
    lx, ly, lz = point
    z_original = lz + z_bottom
    return (
        east[0] * lx + north[0] * ly + up[0] * z_original,
        east[1] * lx + north[1] * ly + up[1] * z_original,
        east[2] * lx + north[2] * ly + up[2] * z_original,
    )


def rectangular_ring_mesh(inner_radius, outer_radius, z_min, z_max, segments):
    """Watertight ring of rectangular cross-section, centred on the z-axis."""
    triangles = []

    def outer(u, z):
        return (outer_radius * math.cos(u), outer_radius * math.sin(u), z)

    def inner(u, z):
        return (inner_radius * math.cos(u), inner_radius * math.sin(u), z)

    for i in range(segments):
        u0 = 2.0 * math.pi * i / segments
        u1 = 2.0 * math.pi * (i + 1) / segments
        p0 = outer(u0, z_min)
        p1 = outer(u1, z_min)
        p2 = outer(u1, z_max)
        p3 = outer(u0, z_max)
        triangles.append((p0, p1, p2))
        triangles.append((p0, p2, p3))
        q0 = inner(u0, z_min)
        q1 = inner(u1, z_min)
        q2 = inner(u1, z_max)
        q3 = inner(u0, z_max)
        triangles.append((q0, q2, q1))
        triangles.append((q0, q3, q2))
        t0 = inner(u0, z_max)
        t1 = outer(u0, z_max)
        t2 = outer(u1, z_max)
        t3 = inner(u1, z_max)
        triangles.append((t0, t1, t2))
        triangles.append((t0, t2, t3))
        b0 = inner(u0, z_min)
        b1 = outer(u0, z_min)
        b2 = outer(u1, z_min)
        b3 = inner(u1, z_min)
        triangles.append((b0, b2, b1))
        triangles.append((b0, b3, b2))
    return triangles


def facet_vertex(up, z_bottom, lon_degrees, z):
    """Intersection of the tile bottom plane with a longitude plane and z."""
    lam = math.radians(lon_degrees)
    c = math.cos(lam)
    s = math.sin(lam)
    denom = up[0] * c + up[1] * s
    if abs(denom) < 1e-12:
        raise RuntimeError("degenerate rib facet")
    radius = (z_bottom - up[2] * z) / denom
    return (radius * c, radius * s, z)


def build_rib(tiles_row, z_min, z_max, radius_mm, base_mm, sampler,
              sample_degrees):
    """Faceted rib for one hemisphere; returns a closed triangle soup.

    Each first-row tile contributes one outer facet: a quad in the tile's
    bottom plane.  Because the first-row tiles all reach sea level at their
    equator edge, they share one z_bottom, so adjacent facets meet exactly
    along the shared chamfer wall and the rib is a clean 12-facet ring (no
    steps between facets).
    """
    planes = []
    for tile in tiles_row:
        latitudes, longitudes = tiles.grid_lines(tile, sample_degrees)
        elevation_mm = sampler(latitudes, longitudes)
        center_lat, center_lon = tiles.tile_center(tile)
        frame = tiles.local_frame(center_lat, center_lon)
        up = tiles.unit_radial(center_lat, center_lon)
        top = tiles.top_grid(tile, latitudes, longitudes, elevation_mm,
                             radius_mm, frame)
        z_bottom = min(point[2] for row in top for point in row) - base_mm
        planes.append((up, z_bottom, tile["lon_min"], tile["lon_max"]))

    n = len(planes)
    south_west, south_east = [], []
    north_east, north_west = [], []
    for (up, z_bottom, lon_min, lon_max) in planes:
        south_west.append(facet_vertex(up, z_bottom, lon_min, z_min))
        south_east.append(facet_vertex(up, z_bottom, lon_max, z_min))
        north_east.append(facet_vertex(up, z_bottom, lon_max, z_max))
        north_west.append(facet_vertex(up, z_bottom, lon_min, z_max))

    # The first-row tiles share one z_bottom (all touch the ocean at their
    # equator edge), so a tile's east corners coincide with its east
    # neighbour's west corners; warn if that assumption breaks.
    max_gap = 0.0
    for k in range(n):
        k_next = (k + 1) % n
        max_gap = max(max_gap, _distance(south_east[k], south_west[k_next]),
                      _distance(north_east[k], north_west[k_next]))
    if max_gap > 0.02:
        print("rib-firstrow: warning: facet corners differ by %.3f mm "
              "(steps between facets are not modelled)" % max_gap,
              file=sys.stderr)

    # Uniform facet subdivision (the facets all have the same width).
    facet_width = _distance(north_west[0], north_east[0])
    segment_count = max(5, int(round(facet_width / tiles.KEY_STUD_WIDTH_MM)))
    fin_segments = max(1, int(round(
        tiles.KEY_STUD_WIDTH_MM * segment_count / facet_width)))
    fin_start = (segment_count - fin_segments) // 2
    fin_end = fin_start + fin_segments

    inner_bottom = []
    inner_top = []
    for k in range(n):
        lam = math.radians(30.0 * k)
        inner_bottom.append((RIB_INNER_RADIUS_MM * math.cos(lam),
                             RIB_INNER_RADIUS_MM * math.sin(lam), z_min))
        inner_top.append((RIB_INNER_RADIUS_MM * math.cos(lam),
                          RIB_INNER_RADIUS_MM * math.sin(lam), z_max))

    triangles = []

    for k in range(n):
        k_next = (k + 1) % n
        top_pts = [_lerp3(north_west[k], north_east[k], i / segment_count)
                   for i in range(segment_count + 1)]
        bot_pts = [_lerp3(south_west[k], south_east[k], i / segment_count)
                   for i in range(segment_count + 1)]
        # outer facet strip (with the centred fin)
        triangles.extend(_facet_strip(top_pts, bot_pts, fin_start, fin_end,
                                      planes[k][0]))
        # top annulus (fan from the inner vertex over the subdivided edge)
        triangles.extend(_annulus_fan(inner_top[k], inner_top[k_next],
                                      top_pts, flip=False))
        # bottom annulus (fan, reversed winding for the -z outward normal)
        triangles.extend(_annulus_fan(inner_bottom[k], inner_bottom[k_next],
                                      bot_pts, flip=True))
        # inner cylindrical wall (r = RIB_INNER_RADIUS_MM; normal toward axis)
        triangles.extend(tiles.quad_triangles(
            inner_bottom[k], inner_top[k], inner_top[k_next],
            inner_bottom[k_next]))
    return triangles


def _lerp3(point_a, point_b, t):
    return (point_a[0] + (point_b[0] - point_a[0]) * t,
            point_a[1] + (point_b[1] - point_a[1]) * t,
            point_a[2] + (point_b[2] - point_a[2]) * t)


def _facet_strip(top_pts, bot_pts, fin_start, fin_end, direction):
    """Facet strip with a centred lens fin; returns triangles."""
    segment_count = len(top_pts) - 1
    triangles = []
    for i in range(segment_count):
        p_a = top_pts[i]
        p_b = top_pts[i + 1]
        q_a = bot_pts[i]
        q_b = bot_pts[i + 1]
        if fin_start <= i < fin_end:
            triangles.extend(_fin_bump(p_a, p_b, q_a, q_b, direction,
                                       i == fin_start, i == fin_end - 1))
        elif i == fin_start - 1:
            triangles.extend(_fan_transition(p_a, p_b, q_a, q_b, "low"))
        elif i == fin_end:
            triangles.extend(_fan_transition(p_a, p_b, q_a, q_b, "high"))
        else:
            triangles.extend(tiles.quad_triangles(q_a, q_b, p_b, p_a))
    return triangles


FIN_V_BASE_LO = tiles.RIB_KEY_V_BASE_LO
FIN_V_TOP_LO = tiles.RIB_KEY_V_TOP_LO
FIN_V_TOP_HI = tiles.RIB_KEY_V_TOP_HI
FIN_V_BASE_HI = tiles.RIB_KEY_V_BASE_HI


def _fin_bump(p_a, p_b, q_a, q_b, direction, side_low, side_high):
    """Trapezoidal fin protruding `direction` from one facet segment."""
    return tiles.trapezoid_key_triangles(
        p_a, p_b, q_a, q_b, direction, tiles.KEY_STUD_HEIGHT_MM,
        side_low, side_high)


def _fan_transition(p_a, p_b, q_a, q_b, side):
    """Fan a plain facet segment against a neighbouring fin's side profile.

    p_a/p_b are the segment's top edge, q_a/q_b its bottom edge.  For the
    "low" side the fin lies to the east (shared edge p_b->q_b); for "high"
    it lies to the west (shared edge p_a->q_a).
    """
    if side == "low":
        far_top, far_bot = p_a, q_a
        shared_top, shared_bot = p_b, q_b
    else:
        far_top, far_bot = p_b, q_b
        shared_top, shared_bot = p_a, q_a
    splits = [_lerp3(shared_top, shared_bot, v)
              for v in (FIN_V_BASE_LO, FIN_V_BASE_HI)]
    if side == "low":
        return [
            (far_top, splits[0], shared_top),
            (far_top, splits[1], splits[0]),
            (far_top, shared_bot, splits[1]),
            (far_top, far_bot, shared_bot),
        ]
    return [
        (far_top, shared_top, splits[0]),
        (far_top, splits[0], splits[1]),
        (far_top, splits[1], shared_bot),
        (far_top, shared_bot, far_bot),
    ]


def _annulus_fan(inner_a, inner_b, edge_pts, flip):
    """Fan an annulus sector from inner_a over a subdivided outer edge."""
    triangles = []
    count = len(edge_pts) - 1
    for i in range(count):
        a = edge_pts[i]
        b = edge_pts[i + 1]
        if flip:
            triangles.append((inner_a, b, a))
        else:
            triangles.append((inner_a, a, b))
    if flip:
        triangles.append((inner_a, inner_b, edge_pts[count]))
    else:
        triangles.append((inner_a, edge_pts[count], inner_b))
    return triangles


def _distance(point_a, point_b):
    return math.sqrt((point_a[0] - point_b[0]) ** 2
                     + (point_a[1] - point_b[1]) ** 2
                     + (point_a[2] - point_b[2]) ** 2)


def build_row(tiles_row, radius_mm, base_mm, sampler, sample_degrees):
    """World-space triangle soup for a row of first-row tiles (real relief)."""
    world_pieces = []
    for tile in tiles_row:
        latitudes, longitudes = tiles.grid_lines(tile, sample_degrees)
        elevation_mm = sampler(latitudes, longitudes)
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


def translate_z(triangles, delta):
    return [tuple((a[0], a[1], a[2] + delta) for a in tri)
            for tri in triangles]


def run_build(arguments):
    from osgeo import gdal
    gdal.UseExceptions()
    working = tempfile.mkdtemp(prefix="rib-firstrow-build-")
    try:
        path_vrt = tiles.build_vrt(arguments.source_dir, working)
        grid, transform = tiles.load_global_grid(path_vrt,
                                                 arguments.sample_degrees,
                                                 working)
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

        def sampler(latitudes, longitudes):
            elevations = tiles.sample_grid(grid, transform, latitudes,
                                           longitudes)
            return [[tiles.elevation_to_mm(value, elevation_min,
                                           elevation_max, parameters)
                     for value in row] for row in elevations]

        all_tiles = tiles.plan_tiles(arguments.band_degrees)
        north = [t for t in all_tiles if t["id"].startswith("tile-N00")]
        south = [t for t in all_tiles if t["id"].startswith("tile-S30")]
        if not north or not south:
            raise RuntimeError("expected N00 and S30 first-row bands")

        rib_north = build_rib(north, 0.0, RIB_THICKNESS_MM,
                              arguments.radius_mm, arguments.base_mm,
                              sampler, arguments.sample_degrees)
        rib_south = build_rib(south, -RIB_THICKNESS_MM, 0.0,
                              arguments.radius_mm, arguments.base_mm,
                              sampler, arguments.sample_degrees)
        equator_ring = rectangular_ring_mesh(EQUATOR_INNER_RADIUS_MM,
                                             EQUATOR_OUTER_RADIUS_MM,
                                             -EQUATOR_HALF_THICKNESS_MM,
                                             EQUATOR_HALF_THICKNESS_MM, 128)

        groups = [("rib-north", rib_north), ("rib-south", rib_south),
                  ("equator", equator_ring)]
        groups.extend(build_row(north, arguments.radius_mm, arguments.base_mm,
                                sampler, arguments.sample_degrees))
        groups.extend(build_row(south, arguments.radius_mm, arguments.base_mm,
                                sampler, arguments.sample_degrees))
    finally:
        shutil.rmtree(working, ignore_errors=True)

    os.makedirs(arguments.output_dir, exist_ok=True)
    path_obj = os.path.join(arguments.output_dir, "rib-firstrow.obj")
    write_obj(path_obj, groups)

    # Printable ribs: both sit flat with the bottom at z = 0.  The north rib
    # already spans z in [0, 10]; the south rib spans [-10, 0] in world space,
    # so it is translated up for printing.
    rib_south_print = translate_z(rib_south, RIB_THICKNESS_MM)
    volume_north = tiles.signed_volume(rib_north)
    volume_south = tiles.signed_volume(rib_south_print)
    path_stl_north = os.path.join(arguments.output_dir, "rib-north.stl")
    path_stl_south = os.path.join(arguments.output_dir, "rib-south.stl")
    tiles.write_stl(path_stl_north, rib_north,
                    "model-render-print north rib (faceted, R90 inner)")
    tiles.write_stl(path_stl_south, rib_south_print,
                    "model-render-print south rib (faceted, R90 inner)")

    total_triangles = sum(len(triangles) for _, triangles in groups)
    manifest = {
        "generated_by": "scripts/rib_firstrow_build.py",
        "do_not_edit_by_hand": True,
        "parameters": {
            "band_degrees": arguments.band_degrees,
            "radius_mm": arguments.radius_mm,
            "base_mm": arguments.base_mm,
            "relief_mm": arguments.relief_mm,
            "oceans_flat": arguments.oceans_flat,
            "sample_degrees": arguments.sample_degrees,
            "rib_inner_radius_mm": RIB_INNER_RADIUS_MM,
            "rib_inner_diameter_mm": 2.0 * RIB_INNER_RADIUS_MM,
            "rib_thickness_mm": RIB_THICKNESS_MM,
            "rib_outer": "faceted (one facet per first-row tile bottom plane)",
        },
        "rib_stl": [
            {
                "file": "rib-north.stl",
                "triangles": len(rib_north),
                "volume_mm3": round(volume_north, 3),
                "unshared_edges": count_unshared_edges(rib_north),
            },
            {
                "file": "rib-south.stl",
                "triangles": len(rib_south_print),
                "volume_mm3": round(volume_south, 3),
                "unshared_edges": count_unshared_edges(rib_south_print),
            },
        ],
        "groups": [{"name": name, "triangles": len(triangles)}
                   for name, triangles in groups],
        "total_triangles": total_triangles,
    }
    path_manifest = os.path.join(arguments.output_dir, "rib.json")
    with open(path_manifest, "w") as handle:
        json.dump(manifest, handle, indent=4)
        handle.write("\n")
    print("rib-firstrow: wrote %s, %s, %s and %s (%d groups, %d triangles; "
          "rib volumes %.1f / %.1f mm^3)" % (path_obj, path_stl_north,
                                             path_stl_south, path_manifest,
                                             len(groups), total_triangles,
                                             volume_north, volume_south))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="rib_firstrow_build",
        description="Render the faceted rib + first-row assembly "
                    "visualization and the rib STLs.")
    parser.add_argument("--source-dir", default="/datasets/dataset-etopo-2022",
                        help="ETOPO 2022 source tile directory")
    parser.add_argument("--output-dir", default=None,
                        help="output directory (default: dataflow.out/rib)")
    parser.add_argument("--band-degrees", type=float, default=30.0)
    parser.add_argument("--radius-mm", type=float, default=100.0)
    parser.add_argument("--base-mm", type=float, default=3.0)
    parser.add_argument("--relief-mm", type=float, default=10.0)
    parser.add_argument("--sample-degrees", type=float, default=1.0,
                        help="grid spacing (1.0 for a light view; 0.25 to "
                             "match the production tile build)")
    parser.add_argument("--oceans-flat", action="store_true", default=True,
                        help="clamp water-covered cells to sea level")
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
