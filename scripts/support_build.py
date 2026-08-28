#!/usr/bin/env python3
"""Interior support for one globe hemisphere (step 1 of the new approach).

The solid hemisphere fills the interior of the globe's hemisphere: the
spherical cap of radius `radius_mm` with a flat circular face at the
equator plane, z = 0 (the bed plane when printed).  The next steps
subtract the central cylinder and assemble the tiles around it.

Usage: support_build.py [--hemisphere north|south] [--radius-mm 100]
                        [--sample-degrees 2] [--output-dir ...]
"""

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stl_tiles_build as tiles


def solid_hemisphere(radius_mm, north, sample_degrees):
    """Watertight solid hemisphere; returns (triangles, boundary_count)."""
    count_lon = max(24, int(round(360.0 / sample_degrees)))
    count_lat = max(2, int(round(90.0 / sample_degrees)))

    def point(lat, lon):
        phi = math.radians(lat)
        lam = math.radians(lon)
        return (
            radius_mm * math.cos(phi) * math.cos(lam),
            radius_mm * math.cos(phi) * math.sin(lam),
            radius_mm * math.sin(phi),
        )

    # latitude rows from the equator (row 0) to the pole (last row)
    rows = []
    for i in range(count_lat + 1):
        lat = 90.0 * i / count_lat
        if not north:
            lat = -lat
        rows.append([point(lat, 360.0 * j / count_lon) for j in range(count_lon)])

    triangles = []
    # spherical cap: quads between consecutive rows, pole fan at the top
    for i in range(count_lat):
        row_a = rows[i]
        row_b = rows[i + 1]
        if i == count_lat - 1:
            pole = row_b[0]
            for j in range(count_lon):
                j2 = (j + 1) % count_lon
                triangles.append((row_a[j], row_a[j2], pole))
            continue
        for j in range(count_lon):
            j2 = (j + 1) % count_lon
            a = row_a[j]
            b = row_a[j2]
            c = row_b[j2]
            d = row_b[j]
            triangles.append((a, b, c))
            triangles.append((a, c, d))

    # flat face: fan the equator disc from the center at z = 0
    center = (0.0, 0.0, 0.0)
    equator = rows[0]
    for j in range(count_lon):
        j2 = (j + 1) % count_lon
        triangles.append((center, equator[j], equator[j2]))

    if tiles.signed_volume(triangles) < 0.0:
        triangles = [
            (point_a, point_c, point_b) for (point_a, point_b, point_c) in triangles
        ]
    return triangles, len(equator)


def cone_bore_hemisphere(radius_mm, bore_diameter_mm, bore_angle_deg, north,
                         sample_degrees):
    """Solid hemisphere minus a conical bore.

    The bore is a cone whose base (diameter `bore_diameter_mm`) sits at the
    equator face and whose wall tilts inward at `bore_angle_deg` from the
    vertical as it ascends: radius(z) = base_radius - z*tan(angle), ending
    at the apex where the radius reaches 0.  The dome above the apex stays,
    so the bore is a conical pocket open only at the equator face.  Returns
    (triangles, boundary_count).
    """
    count_lon = max(24, int(round(360.0 / sample_degrees)))
    base_radius = bore_diameter_mm / 2.0
    slope = math.tan(math.radians(bore_angle_deg))
    apex_z = base_radius / slope if slope > 1e-9 else 0.0
    sign = 1.0 if north else -1.0
    count_cone = max(2, int(round(apex_z / sample_degrees)))

    def sphere_point(lat, lon):
        phi = math.radians(lat)
        lam = math.radians(lon)
        return (
            radius_mm * math.cos(phi) * math.cos(lam),
            radius_mm * math.cos(phi) * math.sin(lam),
            sign * radius_mm * math.sin(phi),
        )

    def cone_point(lon, z):
        lam = math.radians(lon)
        r = max(0.0, base_radius - z * slope)
        return (r * math.cos(lam), r * math.sin(lam), sign * z)

    triangles = []

    # sphere surface: rows from the equator to the pole, pole fan at the top
    count_lat = max(2, int(round(90.0 / sample_degrees)))
    sphere_rows = []
    for i in range(count_lat + 1):
        lat = 90.0 * i / count_lat
        sphere_rows.append(
            [sphere_point(lat, 360.0 * j / count_lon) for j in range(count_lon)]
        )
    for i in range(count_lat):
        row_a = sphere_rows[i]
        row_b = sphere_rows[i + 1]
        if i == count_lat - 1:
            pole = row_b[0]
            for j in range(count_lon):
                j2 = (j + 1) % count_lon
                triangles.append((row_a[j], row_a[j2], pole))
            continue
        for j in range(count_lon):
            j2 = (j + 1) % count_lon
            a = row_a[j]
            b = row_a[j2]
            c = row_b[j2]
            d = row_b[j]
            triangles.append((a, b, c))
            triangles.append((a, c, d))

    # cone wall: from the equator face (z = 0) up to the apex; the wall
    # faces the bore, so its outward normal points toward the axis
    cone_rows = []
    for i in range(count_cone + 1):
        cone_rows.append(
            [cone_point(360.0 * j / count_lon, apex_z * i / count_cone)
             for j in range(count_lon)]
        )
    for i in range(count_cone):
        row_a = cone_rows[i]
        row_b = cone_rows[i + 1]
        if i == count_cone - 1:
            apex = row_b[0]
            for j in range(count_lon):
                j2 = (j + 1) % count_lon
                triangles.append((apex, row_a[j2], row_a[j]))
            continue
        for j in range(count_lon):
            j2 = (j + 1) % count_lon
            a = row_b[j]
            b = row_b[j2]
            c = row_a[j2]
            d = row_a[j]
            triangles.append((a, b, c))
            triangles.append((a, c, d))

    # equator face: the annulus between the cone base and the outer circle
    equator = sphere_rows[0]
    inner = cone_rows[0]
    for j in range(count_lon):
        j2 = (j + 1) % count_lon
        a = inner[j]
        b = inner[j2]
        c = equator[j2]
        d = equator[j]
        triangles.append((a, b, c))
        triangles.append((a, c, d))

    if tiles.signed_volume(triangles) < 0.0:
        triangles = [
            (point_a, point_c, point_b) for (point_a, point_b, point_c) in triangles
        ]
    return triangles, len(equator)


def local_to_world(point, frame, z_bottom):
    """Tile-local point (bottom at z = 0) -> world coordinates."""
    east, north, up = frame
    p = (point[0], point[1], point[2] + z_bottom)
    return (
        p[0] * east[0] + p[1] * north[0] + p[2] * up[0],
        p[0] * east[1] + p[1] * north[1] + p[2] * up[1],
        p[0] * east[2] + p[1] * north[2] + p[2] * up[2],
    )


def build_tiles_world(tiles_hemisphere, radius_mm, base_mm, grid, transform,
                      elevation_min, elevation_max, parameters, sample_degrees):
    """World-space triangle soup for the hemisphere's tiles (real relief)."""
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


def write_obj(path, groups):
    """Write grouped triangles as a Wavefront OBJ."""
    lines = ["# generated by support_build.py; do not edit manually"]
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


def run(arguments):
    os.makedirs(arguments.output_dir, exist_ok=True)
    for hemisphere in (arguments.hemisphere,):
        north = hemisphere == "north"
        if arguments.bore_diameter_mm and arguments.bore_diameter_mm > 0.0:
            triangles, boundary = cone_bore_hemisphere(
                arguments.radius_mm,
                arguments.bore_diameter_mm,
                arguments.bore_angle_deg,
                north,
                arguments.sample_degrees,
            )
            description = (
                "hemispherical shell with a %g mm conical bore at %g deg"
                % (arguments.bore_diameter_mm, arguments.bore_angle_deg)
            )
        else:
            triangles, boundary = solid_hemisphere(
                arguments.radius_mm, north, arguments.sample_degrees
            )
            description = "solid hemisphere (step 1)"
        name = "support-%s.stl" % hemisphere
        path = os.path.join(arguments.output_dir, name)
        tiles.write_stl(
            path,
            triangles,
            "model-render-print %s interior support; R %g mm; %s"
            % (hemisphere, arguments.radius_mm, description),
        )
        print(
            "support-build: %s -> %s (%d triangles, volume %.0f mm^3)"
            % (hemisphere, path, len(triangles), tiles.signed_volume(triangles))
        )
    if arguments.assemble:
        run_assemble(arguments)


def run_assemble(arguments):
    """Step 3: the support with all rows of tiles for one hemisphere."""
    import shutil
    import tempfile

    from osgeo import gdal

    gdal.UseExceptions()
    working = tempfile.mkdtemp(prefix="support-assemble-")
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
            raise RuntimeError("no tiles for hemisphere %s" % arguments.hemisphere)

        pieces = build_tiles_world(
            hemisphere_tiles, arguments.radius_mm, arguments.base_mm,
            grid, transform, elevation_min, elevation_max, parameters,
            arguments.sample_degrees,
        )
        support = tiles.read_stl(
            os.path.join(arguments.output_dir,
                         "support-%s.stl" % arguments.hemisphere)
        )
        groups = [("support-%s" % arguments.hemisphere, support)]
        groups.extend(pieces)
        path_obj = os.path.join(arguments.output_dir,
                                "support-%s.obj" % arguments.hemisphere)
        write_obj(path_obj, groups)
        total = sum(len(triangles) for _, triangles in groups)
        print(
            "support-build: assembled %d pieces (%d triangles) -> %s"
            % (len(groups), total, path_obj)
        )
    finally:
        shutil.rmtree(working, ignore_errors=True)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="support_build",
        description="Render the interior support for one globe hemisphere.",
    )
    parser.add_argument(
        "--hemisphere",
        choices=("north", "south"),
        default="north",
        help="which hemisphere (default north)",
    )
    parser.add_argument("--radius-mm", type=float, default=100.0)
    parser.add_argument(
        "--bore-diameter-mm",
        type=float,
        default=160.0,
        help="diameter of the conical bore's base at the equator (0 for a "
        "plain solid hemisphere)",
    )
    parser.add_argument(
        "--bore-angle-deg",
        type=float,
        default=45.0,
        help="the conical bore's wall tilt inward from the vertical, in "
        "degrees",
    )
    parser.add_argument("--sample-degrees", type=float, default=2.0)
    parser.add_argument(
        "--assemble",
        action="store_true",
        help="also build the assembled view (support + all rows of tiles)",
    )
    parser.add_argument(
        "--source-dir",
        default="/datasets/dataset-etopo-2022",
        help="ETOPO 2022 source tile directory",
    )
    parser.add_argument("--band-degrees", type=float, default=30.0)
    parser.add_argument("--base-mm", type=float, default=3.0)
    parser.add_argument("--relief-mm", type=float, default=10.0)
    parser.add_argument("--oceans-flat", action="store_true", default=True)
    parser.add_argument(
        "--output-dir",
        default=None,
        help="output directory (default: dataflow.out/support)",
    )
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    if arguments.output_dir is None:
        repository_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        arguments.output_dir = os.path.join(repository_root, "dataflow.out", "support")
    try:
        run(arguments)
    except (ValueError, RuntimeError) as error:
        print("support-build: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
