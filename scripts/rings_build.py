#!/usr/bin/env python3
"""Support ring lattice for the globe hemispheres (prints on a 220 mm bed).

Per hemisphere:

  - **horizontal rings** at the band centres (15, 45, 75 degrees), each
    seated against the tiles' inner (bottom) faces and keyed into the
    centre of every tile of that band -- a tab on the ring's outer face
    into the tile's bottom-face socket;
  - **vertical (meridian) arcs**, twelve of them, from the equator to the
    cap ring, held just inside the horizontal rings and keyed into each
    crossing with a tongue-in-groove;
  - a **cap stem** from the 75-degree ring to the pole, keyed into the
    cap tile's socket.

Every piece fits a 220 mm square bed; the largest is the 15-degree ring
(~190 mm across).  Pieces are written print-ready (flat, bottom at z = 0)
plus an assembled OBJ for the web view.

Usage: rings_build.py [--hemisphere north|south] [--clearance-mm 0.6]
                      [--sample-degrees 0.25] [--output-dir dataflow.out/rings]
"""

import argparse
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stl_tiles_build as tiles

RING_RADIAL_MM = 8.0     # ring thickness measured radially
RING_LATERAL_MM = 6.0    # ring width along the path normal
FIT_CLEARANCE_MM = 0.4   # total slack between a key and the socket it seats in
TAB_DEPTH_CLEARANCE_MM = 0.2   # tab tip slack inside the socket
KEY_DEPTH_MM = 3.0       # tongue/groove radial engagement
KEY_WINDOW_MM = 3.0      # half arc length of a tongue/groove window
MERIDIAN_COUNT = 12
MERIDIAN_PHASE_DEG = 0.0  # meridians run along the equatorial tile seams
BAND_CENTERS = {"N00": 15.0, "N30": 45.0, "N90": 75.0,
                "S30": -15.0, "S60": -45.0, "S90": -75.0}
BAND_ORDER = {"north": ("N00", "N30", "N90"), "south": ("S30", "S60", "S90")}


ZERO = (0.0, 0.0, 0.0)


def _add(point_a, point_b):
    return (point_a[0] + point_b[0], point_a[1] + point_b[1],
            point_a[2] + point_b[2])


def _scale(point, factor):
    return (point[0] * factor, point[1] * factor, point[2] * factor)


def tile_inner_radius(tile, grid, transform, elevation_min, elevation_max,
                      parameters, sample_degrees, radius_mm, base_mm):
    """Radius of the tile's inner (bottom) face at its centre."""
    latitudes, longitudes = tiles.grid_lines(tile, sample_degrees)
    elevations = tiles.sample_grid(grid, transform, latitudes, longitudes)
    elevation_mm = [
        [tiles.elevation_to_mm(value, elevation_min, elevation_max, parameters)
         for value in row]
        for row in elevations
    ]
    center_lat, center_lon = tiles.tile_center(tile)
    frame = tiles.local_frame(center_lat, center_lon)
    top = tiles.top_grid(tile, latitudes, longitudes, elevation_mm,
                         radius_mm, frame)
    return min(point[2] for row in top for point in row) - base_mm


def frame_at(latitude, longitude):
    """(radial, north) unit frame at that point.

    Profiles swept on this frame carry an absolute radius from the globe
    centre, so the sweep origin is the centre itself.
    """
    phi = math.radians(latitude)
    lam = math.radians(longitude)
    radial = (math.cos(phi) * math.cos(lam), math.cos(phi) * math.sin(lam),
              math.sin(phi))
    north = (-math.sin(phi) * math.cos(lam), -math.sin(phi) * math.sin(lam),
             math.cos(phi))
    return (radial, north)


def east_at(longitude):
    lam = math.radians(longitude)
    return (-math.sin(lam), math.cos(lam), 0.0)


def ring_profile(radius_inner, radius_outer, radius_mid, half_width,
                 groove, tab_radius):
    """Eight-point profile (rho, lateral) for a horizontal ring.

    Slots 2..5 carry the feature: a groove (outer half removed, radius_mid)
    at a meridian crossing, or a tab (outer radius extended to tab_radius)
    at a tile centre.  When no feature applies the extra points collapse
    onto the plain rectangle corners.
    """
    lo, hi = -half_width, half_width
    if groove is not None:
        g_lo, g_hi = groove
        return [
            (radius_inner, lo), (radius_outer, lo),
            (radius_outer, g_lo), (radius_mid, g_lo),
            (radius_mid, g_hi), (radius_outer, g_hi),
            (radius_outer, hi), (radius_inner, hi),
        ]
    if tab_radius is not None:
        half_tab = (tiles.KEY_SOCKET_LENGTH_MM - FIT_CLEARANCE_MM) / 2.0
        return [
            (radius_inner, lo), (radius_outer, lo),
            (radius_outer, -half_tab), (tab_radius, -half_tab),
            (tab_radius, half_tab), (radius_outer, half_tab),
            (radius_outer, hi), (radius_inner, hi),
        ]
    return [
        (radius_inner, lo), (radius_outer, lo),
        (radius_outer, lo), (radius_outer, lo),
        (radius_outer, hi), (radius_outer, hi),
        (radius_outer, hi), (radius_inner, hi),
    ]


def meridian_profile(radius_inner, radius_outer, half_width):
    """Four-point profile (rho, east) for a meridian arc."""
    return [
        (radius_inner, -half_width), (radius_outer, -half_width),
        (radius_outer, half_width), (radius_inner, half_width),
    ]


def sweep(frames, profiles, closed):
    """Loft profiles along path frames; returns triangles."""
    count = len(frames)
    point_count = len(profiles[0])
    rings = []
    for index in range(count):
        origin, radial, lateral = frames[index]
        ring = []
        for (rho, lateral_offset) in profiles[index]:
            ring.append(tuple(
                origin[axis] + rho * radial[axis]
                + lateral_offset * lateral[axis] for axis in range(3)))
        rings.append(ring)

    def emit(triangles, point_a, point_b, point_c):
        ux = point_b[0] - point_a[0]
        uy = point_b[1] - point_a[1]
        uz = point_b[2] - point_a[2]
        vx = point_c[0] - point_a[0]
        vy = point_c[1] - point_a[1]
        vz = point_c[2] - point_a[2]
        cross = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
        if cross[0] * cross[0] + cross[1] * cross[1] + cross[2] * cross[2] \
                > 1e-12:
            triangles.append((point_a, point_b, point_c))

    triangles = []
    steps = count if closed else count - 1
    for index in range(steps):
        ring_a = rings[index]
        ring_b = rings[(index + 1) % count]
        for j in range(point_count):
            k = (j + 1) % point_count
            emit(triangles, ring_a[j], ring_a[k], ring_b[k])
            emit(triangles, ring_a[j], ring_b[k], ring_b[j])
    if not closed:
        for ring, reverse in ((rings[0], True), (rings[-1], False)):
            center = (
                sum(p[0] for p in ring) / point_count,
                sum(p[1] for p in ring) / point_count,
                sum(p[2] for p in ring) / point_count,
            )
            for j in range(point_count):
                k = (j + 1) % point_count
                if reverse:
                    emit(triangles, center, ring[k], ring[j])
                else:
                    emit(triangles, center, ring[j], ring[k])
    return triangles


def orient(triangles):
    """Flip the soup when its signed volume is negative."""
    if tiles.signed_volume(triangles) < 0.0:
        return [(point_a, point_c, point_b)
                for (point_a, point_b, point_c) in triangles]
    return triangles


def horizontal_ring(tiles_band, inner_radii, center_lat, clearance_mm):
    """One horizontal ring piece (world coordinates)."""
    tiles_radius = min(inner_radii[tile["id"]] for tile in tiles_band)
    radius_outer = tiles_radius - clearance_mm
    radius_inner = radius_outer - RING_RADIAL_MM
    radius_mid = radius_inner + KEY_DEPTH_MM
    radius_center = radius_outer - RING_RADIAL_MM / 2.0
    half_width = RING_LATERAL_MM / 2.0

    # tile centres sitting on this ring: the tab angles and their reach.
    # A band only keys through tabs when its tiles centre on the ring
    # latitude; the polar cap centres on the pole and is held by the stem.
    tab_by_lon = {}
    for tile in tiles_band:
        tile_lat, tile_lon = tiles.tile_center(tile)
        if abs(tile_lat - center_lat) > 1.0:
            continue
        reach = inner_radii[tile["id"]] + tiles.KEY_SOCKET_DEPTH_MM \
            - TAB_DEPTH_CLEARANCE_MM
        tab_by_lon[tile_lon % 360.0] = reach
    tab_lons = sorted(tab_by_lon)

    # meridian crossings: the groove angles
    grove_lons = [(MERIDIAN_PHASE_DEG + (360.0 / MERIDIAN_COUNT) * index)
                  % 360.0 for index in range(MERIDIAN_COUNT)]

    # the frame origins trace a parallel, not a great circle
    path_radius = radius_center * math.cos(math.radians(center_lat))
    steps = 720
    frames = []
    profiles = []
    for step in range(steps):
        longitude = 360.0 * step / steps
        radial, northward = frame_at(center_lat, longitude)
        frames.append((ZERO, radial, northward))

        def nearest(values, target):
            best = None
            best_d = None
            for value in values:
                delta = abs(((value - target + 180.0) % 360.0) - 180.0)
                if best_d is None or delta < best_d:
                    best_d = delta
                    best = value
            return best, best_d

        tab_lon, tab_delta = nearest(tab_lons, longitude)
        groove_window = math.degrees(
            KEY_WINDOW_MM / path_radius) if path_radius > 0 else 180.0
        tab_window = math.degrees(
            (tiles.KEY_SOCKET_WIDTH_MM - FIT_CLEARANCE_MM) / 2.0
            / path_radius) if path_radius > 0 else 180.0
        groove = None
        tab_radius = None
        meridian_lon, meridian_delta = nearest(grove_lons, longitude)
        if meridian_delta <= groove_window:
            span = KEY_WINDOW_MM
            groove = (-span, span)
        elif tab_delta is not None and tab_delta <= tab_window:
            tab_radius = tab_by_lon[tab_lon]
        profiles.append(ring_profile(radius_inner, radius_outer, radius_mid,
                                     half_width, groove, tab_radius))
    return orient(sweep(frames, profiles, closed=True))


def meridian_arc(longitude, north, ring_data, clearance_mm, steps=360):
    """One meridian arc piece from the equator to the cap ring (world)."""
    signature = 1.0 if north else -1.0
    # ring_data: [(center_lat, radius_inner, radius_outer, radius_center)]
    latitudes = []
    for step in range(steps + 1):
        latitude = signature * 75.0 * step / steps
        latitudes.append(latitude)

    def interpolate(latitude, index):
        # latitudes are monotonic along the arc in both hemispheres
        keys = sorted(((entry[0], entry[index]) for entry in ring_data),
                      key=lambda item: item[0])
        target = latitude
        if target <= keys[0][0]:
            return keys[0][1]
        if target >= keys[-1][0]:
            return keys[-1][1]
        for a, b in zip(keys, keys[1:]):
            if a[0] <= target <= b[0]:
                span = b[0] - a[0]
                if span < 1e-9:
                    return a[1]
                t = (target - a[0]) / span
                return a[1] + t * (b[1] - a[1])
        return keys[-1][1]

    frames = []
    profiles = []
    for latitude in latitudes:
        key_inner = interpolate(latitude, 1)      # the ring's inner face
        radius_outer = key_inner - clearance_mm
        radius_inner = radius_outer - RING_RADIAL_MM
        radius_center = radius_outer - RING_RADIAL_MM / 2.0
        radial, _ = frame_at(latitude, longitude)
        frames.append((ZERO, radial, east_at(longitude)))
        # tongue at each horizontal-ring crossing; both its reach along the
        # meridian and its width across it sit FIT_CLEARANCE_MM inside the
        # groove it keys into
        tongue = False
        for entry in ring_data:
            crossing_lat = entry[0]
            arc = abs(latitude - crossing_lat) * math.pi / 180.0 \
                * radius_center
            if arc <= KEY_WINDOW_MM - FIT_CLEARANCE_MM / 2.0:
                tongue = True
                break
        if tongue:
            radius_outer_here = key_inner + KEY_DEPTH_MM \
                - TAB_DEPTH_CLEARANCE_MM
            half_lateral = (RING_LATERAL_MM - FIT_CLEARANCE_MM) / 2.0
        else:
            radius_outer_here = radius_outer
            half_lateral = RING_LATERAL_MM / 2.0
        profiles.append(meridian_profile(radius_inner, radius_outer_here,
                                         half_lateral))
    return orient(sweep(frames, profiles, closed=False))


def cap_stem(north, cap_inner_radius, ring_data, clearance_mm):
    """Cap stem: a post from the 75-degree ring's centre to the pole, with
    the tab into the cap tile's socket, plus the spokes to the ring."""
    signature = 1.0 if north else -1.0
    cap = next(entry for entry in ring_data if abs(entry[0]) == 75.0)
    center_radius = cap[3]
    z_ring = center_radius * math.sin(math.radians(75.0))
    z_pole = cap_inner_radius + tiles.KEY_SOCKET_DEPTH_MM \
        - TAB_DEPTH_CLEARANCE_MM
    triangles = []

    def box(center, half_x, half_y, half_z, angle=0.0):
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        corners = []
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    local_x = sx * half_x
                    local_y = sy * half_y
                    corners.append((center[0] + local_x * cos_a
                                    - local_y * sin_a,
                                    center[1] + local_x * sin_a
                                    + local_y * cos_a,
                                    center[2] + sz * half_z))
        # 8 corners in (x,y,z) sign order: index = 4*i + 2*j + k
        faces = (
            (0, 2, 3, 1), (4, 5, 7, 6),
            (0, 1, 5, 4), (2, 6, 7, 3),
            (0, 4, 6, 2), (1, 3, 7, 5),
        )
        for (a, b, c, d) in faces:
            triangles.append((corners[a], corners[b], corners[c]))
            triangles.append((corners[a], corners[c], corners[d]))

    half = RING_LATERAL_MM / 2.0
    # The cap tile's local frame at the pole has east along world +y and
    # north along world -x, so the socket's 6 mm runs along y and its 4 mm
    # along x.  Keep every key FIT_CLEARANCE_MM inside those.
    half_east = (tiles.KEY_SOCKET_WIDTH_MM - FIT_CLEARANCE_MM) / 2.0
    half_north = (tiles.KEY_SOCKET_LENGTH_MM - FIT_CLEARANCE_MM) / 2.0
    # stem post: from the ring plane up to the tab
    stem_bottom = signature * z_ring
    stem_top = signature * z_pole
    stem_height = abs(stem_top - stem_bottom)
    stem_center = (0.0, 0.0, (stem_bottom + stem_top) / 2.0)
    box(stem_center, half_north, half_east, stem_height / 2.0)
    # spokes: two bars crossing at the stem, in the ring's plane, run out
    # into the cap ring body.  They sit on the diagonals to clear the ring's
    # grooves, which are cut at every meridian.
    spoke_reach = center_radius * math.cos(math.radians(75.0))
    plane_z = signature * z_ring
    for angle_deg in (45.0, 135.0):
        box((0.0, 0.0, plane_z), spoke_reach, half, half,
            math.radians(angle_deg))
    return orient(triangles)


def print_ready(triangles, plane_normal):
    """Rotate a piece so its plane is horizontal, then drop it to z = 0."""
    normal = plane_normal
    length = math.sqrt(sum(value * value for value in normal))
    normal = tuple(value / length for value in normal)
    if abs(normal[2]) < 1.0 - 1e-9:
        axis = (-normal[1], normal[0], 0.0)
        axis_len = math.sqrt(sum(value * value for value in axis))
        axis = tuple(value / axis_len for value in axis)
        angle = math.acos(max(-1.0, min(1.0, normal[2])))
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        def rotate(point):
            dot = sum(axis[i] * point[i] for i in range(3))
            cross = (axis[1] * point[2] - axis[2] * point[1],
                     axis[2] * point[0] - axis[0] * point[2],
                     axis[0] * point[1] - axis[1] * point[0])
            return tuple(
                point[i] * cos_a + cross[i] * sin_a
                + axis[i] * dot * (1.0 - cos_a) for i in range(3))
        triangles = [tuple(rotate(point) for point in tri)
                     for tri in triangles]
    z_min = min(point[2] for tri in triangles for point in tri)
    return [tuple((p[0], p[1], p[2] - z_min) for p in tri)
            for tri in triangles]


def run(arguments):
    from osgeo import gdal

    gdal.UseExceptions()
    working = tempfile.mkdtemp(prefix="rings-build-")
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
            "oceans_flat": True,
            "elev_min": None,
            "elev_max": None,
            "base_mm": arguments.base_mm,
            "relief_mm": arguments.relief_mm,
        }
        all_tiles = tiles.plan_tiles(arguments.band_degrees)
        bands = BAND_ORDER[arguments.hemisphere]
        pieces = []
        ring_data = {}
        cap_inner = None
        for band in bands:
            band_tiles = [tile for tile in all_tiles
                          if tile["id"].startswith("tile-" + band)]
            inner = {}
            for tile in band_tiles:
                inner[tile["id"]] = tile_inner_radius(
                    tile, grid, transform, elevation_min, elevation_max,
                    parameters, arguments.sample_degrees, arguments.radius_mm,
                    arguments.base_mm)
            center_lat = BAND_CENTERS[band]
            ring = horizontal_ring(band_tiles, inner, center_lat,
                                   arguments.clearance_mm)
            tiles_radius = min(inner.values())
            radius_outer = tiles_radius - arguments.clearance_mm
            radius_inner = radius_outer - RING_RADIAL_MM
            radius_center = radius_outer - RING_RADIAL_MM / 2.0
            ring_data[band] = (center_lat, radius_inner, radius_outer,
                               radius_center)
            pieces.append(("ring-" + band.lower(), ring, (0.0, 0.0, 1.0)))
            if band in ("N90", "S90"):
                cap_inner = tiles_radius
        order = [ring_data[band] for band in bands]
        for index in range(MERIDIAN_COUNT):
            longitude = MERIDIAN_PHASE_DEG \
                + (360.0 / MERIDIAN_COUNT) * index
            arc = meridian_arc(longitude, arguments.hemisphere == "north",
                               order, arguments.clearance_mm)
            pieces.append(("meridian-%02d" % (index + 1), arc,
                           east_at(longitude)))
        if cap_inner is not None:
            stem = cap_stem(arguments.hemisphere == "north", cap_inner,
                            order, arguments.clearance_mm)
            pieces.append(("cap-stem", stem, (0.0, 0.0, 1.0)))
    finally:
        shutil.rmtree(working, ignore_errors=True)

    os.makedirs(arguments.output_dir, exist_ok=True)
    manifest = {"pieces": [], "total_triangles": 0}
    for name, triangles, normal in pieces:
        ready = print_ready(triangles, normal)
        path_stl = os.path.join(arguments.output_dir,
                                "%s-%s.stl" % (name, arguments.hemisphere))
        tiles.write_stl(path_stl, ready,
                        "model-render-print support %s (%s)"
                        % (name, arguments.hemisphere))
        manifest["pieces"].append({
            "name": name,
            "file": os.path.basename(path_stl),
            "triangles": len(ready),
            "volume_mm3": tiles.signed_volume(ready),
            "z_max": max(point[2] for tri in ready for point in tri),
        })
        manifest["total_triangles"] += len(ready)
        print("rings-build: %s -> %s (%d triangles, volume %.0f mm^3)"
              % (name, path_stl, len(ready), tiles.signed_volume(ready)))

    groups = [(name, triangles) for (name, triangles, _) in pieces]
    path_obj = os.path.join(arguments.output_dir,
                            "rings-%s.obj" % arguments.hemisphere)
    write_obj(path_obj, groups)
    print("rings-build: assembled %d pieces (%d triangles) -> %s"
          % (len(groups), sum(len(t) for _, t in groups), path_obj))
    import json
    with open(os.path.join(arguments.output_dir,
                           "rings-%s.json" % arguments.hemisphere), "w") as fh:
        json.dump(manifest, fh, indent=2)


def write_obj(path, groups):
    lines = ["# generated by rings_build.py; do not edit manually"]
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


def build_parser():
    parser = argparse.ArgumentParser(
        prog="rings_build",
        description="Render the hemisphere support ring lattice.")
    parser.add_argument("--hemisphere", choices=("north", "south"),
                        default="north")
    parser.add_argument("--clearance-mm", type=float, default=0.6)
    parser.add_argument("--sample-degrees", type=float, default=0.25)
    parser.add_argument("--radius-mm", type=float, default=100.0)
    parser.add_argument("--base-mm", type=float, default=3.0)
    parser.add_argument("--relief-mm", type=float, default=10.0)
    parser.add_argument("--band-degrees", type=float, default=30.0)
    parser.add_argument("--source-dir", default="/datasets/dataset-etopo-2022")
    parser.add_argument("--output-dir", default=None)
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    if arguments.output_dir is None:
        repository_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))
        arguments.output_dir = os.path.join(repository_root, "dataflow.out",
                                            "rings")
    try:
        run(arguments)
    except (ValueError, RuntimeError) as error:
        print("rings-build: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
