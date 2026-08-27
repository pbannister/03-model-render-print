#!/usr/bin/env python3
#
# frame_tiles_build.py — generate the internal assembly frame for the
# printable Earth: a central hub with one strut per tile, each strut ending
# in a pad that sits on the tile's flat bottom face.
#
# The frame both aligns the tiles (each pad's position and rotation are
# fixed by the tile's bottom geometry) and stiffens the assembled globe.
# This module currently emits the ASSEMBLED frame as a single Wavefront OBJ
# (grouped per piece) for viewing on the project web page; the printable
# piece STLs are a follow-up.
#
# Geometry decisions: documents/05-stl-approach.md
# Feature: prompts/features/04-assembly-frame.md (planned)
#
# Reuses the tile-build geometry (grid sampling, bottom planes, boundary
# polygons) from stl_tiles_build.py, so the frame matches the tiles exactly.
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stl_tiles_build as tiles

FRAME_HUB_RADIUS_MM = 25.0       # central hub radius
FRAME_ROD_RADIUS_MM = 3.0        # strut rod radius
FRAME_PAD_THICKNESS_MM = 3.0     # pad plate thickness
FRAME_PAD_SCALE = 0.7            # pad polygon scale relative to the bottom
FRAME_ROD_SEGMENTS = 16          # cylinder side segments
FRAME_HUB_SEGMENTS = 32          # hub sphere segments
FRAME_PAD_TARGET_POINTS = 80     # simplified pad polygon point count


def simplify_polygon(points, target):
    """Keep every k-th point so the outline has about `target` points;
    the relief detail is invisible at the pad scale."""
    if len(points) <= target:
        return points
    step = max(1, len(points) // target)
    return [points[index] for index in range(0, len(points), step)]


# ---------------------------------------------------------------------------
# Mesh helpers (returned as triangle soups).
# ---------------------------------------------------------------------------

def cylinder_mesh(start, end, radius, segments):
    """Closed cylinder from start to end (world points), radius, with end
    caps; axis along (end - start)."""
    axis = (end[0] - start[0], end[1] - start[1], end[2] - start[2])
    length = math.sqrt(axis[0] ** 2 + axis[1] ** 2 + axis[2] ** 2)
    if length < 1e-9:
        return []
    axis = (axis[0] / length, axis[1] / length, axis[2] / length)
    # build an orthonormal basis (u, v, axis)
    helper = (0.0, 0.0, 1.0) if abs(axis[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = (helper[1] * axis[2] - helper[2] * axis[1],
         helper[2] * axis[0] - helper[0] * axis[2],
         helper[0] * axis[1] - helper[1] * axis[0])
    u_len = math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2)
    u = (u[0] / u_len, u[1] / u_len, u[2] / u_len)
    v = (axis[1] * u[2] - axis[2] * u[1],
         axis[2] * u[0] - axis[0] * u[2],
         axis[0] * u[1] - axis[1] * u[0])

    def point(along, angle):
        return (start[0] + axis[0] * along
                + radius * (math.cos(angle) * u[0] + math.sin(angle) * v[0]),
                start[1] + axis[1] * along
                + radius * (math.cos(angle) * u[1] + math.sin(angle) * v[1]),
                start[2] + axis[2] * along
                + radius * (math.cos(angle) * u[2] + math.sin(angle) * v[2]))

    triangles = []
    ring_start = []
    ring_end = []
    for index in range(segments):
        angle = 2.0 * math.pi * index / segments
        ring_start.append(point(0.0, angle))
        ring_end.append(point(length, angle))
    for index in range(segments):
        index_next = (index + 1) % segments
        triangles.append((ring_start[index], ring_start[index_next],
                          ring_end[index_next]))
        triangles.append((ring_start[index], ring_end[index_next],
                          ring_end[index]))
    for index in range(segments):
        index_next = (index + 1) % segments
        triangles.append((start, ring_start[index_next], ring_start[index]))
        triangles.append((end, ring_end[index], ring_end[index_next]))
    return triangles


def sphere_mesh(radius, segments):
    """UV sphere centered on the origin."""
    triangles = []
    for lat in range(segments // 2):
        phi_a = math.pi * lat / (segments // 2) - math.pi / 2.0
        phi_b = math.pi * (lat + 1) / (segments // 2) - math.pi / 2.0
        for lon in range(segments):
            theta_a = 2.0 * math.pi * lon / segments
            theta_b = 2.0 * math.pi * (lon + 1) / segments

            def point_at(phi, theta):
                return (radius * math.cos(phi) * math.cos(theta),
                        radius * math.cos(phi) * math.sin(theta),
                        radius * math.sin(phi))

            pa = point_at(phi_a, theta_a)
            pb = point_at(phi_a, theta_b)
            pc = point_at(phi_b, theta_b)
            pd = point_at(phi_b, theta_a)
            triangles.append((pa, pb, pc))
            triangles.append((pa, pc, pd))
    return triangles


def polygon_plate_mesh(polygon, inward, thickness):
    """Extruded plate from a planar polygon (world points, clockwise or
    not); `inward` is the direction of the extrusion.  Returns the outer
    face (fan), the inner face, and the rim walls."""
    count = len(polygon)
    centroid = (sum(p[0] for p in polygon) / count,
                sum(p[1] for p in polygon) / count,
                sum(p[2] for p in polygon) / count)
    inner = [(p[0] + inward[0] * thickness,
              p[1] + inward[1] * thickness,
              p[2] + inward[2] * thickness) for p in polygon]

    def fan(points):
        center = (sum(p[0] for p in points) / count,
                  sum(p[1] for p in points) / count,
                  sum(p[2] for p in points) / count)
        triangles = []
        for index in range(count):
            index_next = (index + 1) % count
            triangles.append((center, points[index_next], points[index]))
        return triangles

    triangles = fan(polygon) + fan(inner)
    for index in range(count):
        index_next = (index + 1) % count
        a = polygon[index]
        b = polygon[index_next]
        c = inner[index_next]
        d = inner[index]
        triangles.append((a, b, c))
        triangles.append((a, c, d))
    return triangles, centroid


# ---------------------------------------------------------------------------
# Frame assembly.
# ---------------------------------------------------------------------------

def frame_geometry(tiles_all, elevation_sampler, radius_mm, base_mm):
    """Per-tile strut geometry in world coordinates.

    Returns (pieces, hub) where pieces is a list of
    {"tile": tile, "up": up, "z_bottom": z_bottom, "triangles": soup},
    and hub is the hub sphere soup.
    """
    pieces = []
    for tile in tiles_all:
        center_lat = (tile["lat_min"] + tile["lat_max"]) / 2.0
        center_lon = tile["lon_min"] if tile["is_cap"] else (
            tile["lon_min"] + tile["lon_max"]) / 2.0
        frame = tiles.local_frame(center_lat, center_lon)
        up = tiles.unit_radial(center_lat, center_lon)

        latitudes, longitudes = tiles.grid_lines(tile, 0.25)
        elevation_mm = elevation_sampler(latitudes, longitudes)
        top = tiles.top_grid(tile, latitudes, longitudes, elevation_mm,
                             radius_mm, frame)
        z_bottom = min(point[2] for row in top for point in row) - base_mm
        boundary, edges, lats, lons = tiles.boundary_ring(tile, top,
                                                          latitudes,
                                                          longitudes)
        q_local = [tiles.radial_projection(point, z_bottom)
                   for point in boundary]
        q_local = simplify_polygon(q_local, FRAME_PAD_TARGET_POINTS)

        # pad polygon: the bottom polygon scaled around its centroid
        centroid_x = sum(point[0] for point in q_local) / len(q_local)
        centroid_y = sum(point[1] for point in q_local) / len(q_local)
        poly_local = [(centroid_x + (point[0] - centroid_x) * FRAME_PAD_SCALE,
                       centroid_y + (point[1] - centroid_y) * FRAME_PAD_SCALE,
                       z_bottom)
                      for point in q_local]

        def to_world(point):
            return (frame[0][0] * point[0] + frame[1][0] * point[1]
                    + frame[2][0] * point[2],
                    frame[0][1] * point[0] + frame[1][1] * point[1]
                    + frame[2][1] * point[2],
                    frame[0][2] * point[0] + frame[1][2] * point[1]
                    + frame[2][2] * point[2])

        poly_world = [to_world(point) for point in poly_local]
        inward = (-up[0], -up[1], -up[2])
        pad, centroid = polygon_plate_mesh(poly_world, inward,
                                           FRAME_PAD_THICKNESS_MM)
        pad_inner = (centroid[0] + inward[0] * FRAME_PAD_THICKNESS_MM,
                     centroid[1] + inward[1] * FRAME_PAD_THICKNESS_MM,
                     centroid[2] + inward[2] * FRAME_PAD_THICKNESS_MM)

        rod_start = (up[0] * FRAME_HUB_RADIUS_MM,
                     up[1] * FRAME_HUB_RADIUS_MM,
                     up[2] * FRAME_HUB_RADIUS_MM)
        rod = cylinder_mesh(rod_start, pad_inner, FRAME_ROD_RADIUS_MM,
                            FRAME_ROD_SEGMENTS)
        pieces.append({
            "tile": tile,
            "up": up,
            "z_bottom": z_bottom,
            "triangles": rod + pad,
        })
    hub = sphere_mesh(FRAME_HUB_RADIUS_MM, FRAME_HUB_SEGMENTS)
    return pieces, hub


def write_obj(path, hub, pieces):
    """Write the assembled frame as a grouped Wavefront OBJ."""
    lines = ["# generated by frame_tiles_build.py; do not edit manually"]
    vertex_index = 1
    with open(path, "w") as handle:
        handle.write("\n".join(lines) + "\n")
        for group, triangles in [("hub", hub)] + \
                [("strut-%s" % piece["tile"]["id"], piece["triangles"])
                 for piece in pieces]:
            handle.write("o %s\n" % group)
            for (a, b, c) in triangles:
                for point in (a, b, c):
                    handle.write("v %.6f %.6f %.6f\n" % point)
                handle.write("f %d %d %d\n"
                             % (vertex_index, vertex_index + 1,
                                vertex_index + 2))
                vertex_index += 3


def run_build(arguments):
    import shutil
    import tempfile
    from osgeo import gdal

    gdal.UseExceptions()
    working = tempfile.mkdtemp(prefix="frame-tiles-build-")
    try:
        path_vrt = tiles.build_vrt(arguments.source_dir, working)
        grid, transform = tiles.load_global_grid(path_vrt, 0.25, working)
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

        tiles_all = tiles.plan_tiles(arguments.band_degrees)
        pieces, hub = frame_geometry(tiles_all, sampler,
                                     arguments.radius_mm,
                                     arguments.base_mm)
    finally:
        shutil.rmtree(working, ignore_errors=True)

    os.makedirs(arguments.output_dir, exist_ok=True)
    path_obj = os.path.join(arguments.output_dir, "frame-assembled.obj")
    write_obj(path_obj, hub, pieces)
    manifest = {
        "generated_by": "scripts/frame_tiles_build.py",
        "do_not_edit_by_hand": True,
        "parameters": {
            "hub_radius_mm": FRAME_HUB_RADIUS_MM,
            "rod_radius_mm": FRAME_ROD_RADIUS_MM,
            "pad_thickness_mm": FRAME_PAD_THICKNESS_MM,
            "pad_scale": FRAME_PAD_SCALE,
            "band_degrees": arguments.band_degrees,
            "radius_mm": arguments.radius_mm,
            "base_mm": arguments.base_mm,
            "relief_mm": arguments.relief_mm,
            "oceans_flat": arguments.oceans_flat,
        },
        "pieces": [
            {
                "tile": piece["tile"]["id"],
                "z_bottom": round(piece["z_bottom"], 3),
                "strut_length_mm": round(piece["z_bottom"]
                                         - FRAME_HUB_RADIUS_MM
                                         - FRAME_PAD_THICKNESS_MM, 3),
                "triangles": len(piece["triangles"]),
            }
            for piece in pieces
        ],
        "hub_triangles": len(hub),
    }
    path_manifest = os.path.join(arguments.output_dir, "frame.json")
    with open(path_manifest, "w") as handle:
        json.dump(manifest, handle, indent=4)
        handle.write("\n")
    print("frame-tiles-build: wrote %s and %s (%d struts, %d hub triangles)"
          % (path_obj, path_manifest, len(pieces), len(hub)))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="frame_tiles_build",
        description="Generate the internal assembly frame for the printable "
                    "Earth.")
    parser.add_argument("--source-dir", default="/datasets/dataset-etopo-2022",
                        help="ETOPO 2022 source tile directory")
    parser.add_argument("--output-dir", default=None,
                        help="output directory (default: dataflow.out/frame "
                             "under the repository root)")
    parser.add_argument("--band-degrees", type=float, default=30.0)
    parser.add_argument("--radius-mm", type=float, default=100.0)
    parser.add_argument("--base-mm", type=float, default=3.0)
    parser.add_argument("--relief-mm", type=float, default=10.0)
    parser.add_argument("--oceans-flat", action="store_true", default=True,
                        help="clamp water-covered cells to sea level")
    return parser


def main(argv=None):
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.output_dir is None:
        repository_root = os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))
        arguments.output_dir = os.path.join(repository_root,
                                            "dataflow.out", "frame")
    try:
        return run_build(arguments)
    except (ValueError, RuntimeError) as error:
        print("frame-tiles-build: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
