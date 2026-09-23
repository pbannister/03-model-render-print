#!/usr/bin/env python3
"""Support ring lattice for the globe hemispheres (prints on a 220 mm bed).

Per hemisphere:

  - **horizontal rings** at the band centres (15, 45, 75 degrees): flat
    washers whose faces are parallel to the equator's, so they print flat.
    Each is keyed into the centre of every tile of its band -- a tab on
    the ring's top face into the tile's bottom-face socket -- and carries a
    notch in the face its meridians arrive at;
  - **vertical (meridian) arcs**, twelve of them, from the equator to the
    cap ring, held just inside the horizontal rings and keyed into each
    crossing with a key that seats in that notch;
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

RING_RADIAL_MM = 8.0     # ring wall thickness, measured radially
RING_HEIGHT_MM = 6.0     # ring height, measured parallel to the polar axis.
                         # The ring is a flat washer: its top and bottom
                         # faces lie in planes parallel to the equator's, so
                         # it stands on its whole face and prints flat.
MERIDIAN_WIDTH_MM = 6.0  # meridian arc width, across the arc
FIT_CLEARANCE_MM = 0.4   # total slack between a key and the socket it seats in
TAB_DEPTH_CLEARANCE_MM = 0.2   # key tip slack past the socket face
KEY_DEPTH_MM = 3.0       # how deep a meridian key seats into the ring
KEY_WINDOW_MM = 3.0      # half arc length of a key window
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


def radial_at(longitude):
    """Horizontal unit vector pointing away from the polar axis."""
    lam = math.radians(longitude)
    return (math.cos(lam), math.sin(lam), 0.0)


def ring_profile(rho_inner, rho_outer, z_low, z_high):
    """Four-point (radius, height) profile of the flat ring.

    Radial is the distance from the polar axis and height runs along it, so
    a rectangle here sweeps a washer whose faces are parallel to the
    equator's: the outer and inner faces are vertical cylinders.
    """
    return [
        (rho_inner, z_low), (rho_outer, z_low),
        (rho_outer, z_high), (rho_inner, z_high),
    ]


def meridian_profile(radius_inner, radius_outer, half_width):
    """Four-point profile (rho, east) for a meridian arc."""
    return [
        (radius_inner, -half_width), (radius_outer, -half_width),
        (radius_outer, half_width), (radius_inner, half_width),
    ]


def box_triangles(center, half_a, half_b, half_c):
    """A closed box given three half-extent vectors from its center."""
    corners = []
    for sign_a in (-1, 1):
        for sign_b in (-1, 1):
            for sign_c in (-1, 1):
                corners.append(tuple(
                    center[axis] + sign_a * half_a[axis]
                    + sign_b * half_b[axis] + sign_c * half_c[axis]
                    for axis in range(3)))
    faces = (
        (0, 2, 3, 1), (4, 5, 7, 6),
        (0, 1, 5, 4), (2, 6, 7, 3),
        (0, 4, 6, 2), (1, 3, 7, 5),
    )
    triangles = []
    for (a, b, c, d) in faces:
        triangles.append((corners[a], corners[b], corners[c]))
        triangles.append((corners[a], corners[c], corners[d]))
    return triangles


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


def ring_values(tiles_radius, center_lat, clearance_mm):
    """Geometry of one horizontal ring (millimetres).

    The ring is a flat washer: its top and bottom faces lie in planes
    parallel to the equator's, so it rests on its whole face and prints
    flat.  Its outer top rim just reaches the sphere of radius
    `tiles_radius - clearance_mm`, so the washer hugs the tiles without
    touching them, and its keys always reach the tiles they hold.
    """
    phi = math.radians(center_lat)
    sign = 1.0 if center_lat >= 0.0 else -1.0
    radius_outer = tiles_radius - clearance_mm
    rho_outer = radius_outer * math.cos(phi)
    # the outer rim reaches the clearance sphere; the washer hangs from it
    # toward the equator, so it sits under the tiles in both hemispheres
    z_rim = radius_outer * math.sin(phi)
    z_inner = z_rim - sign * RING_HEIGHT_MM
    values = {
        "center_lat": center_lat,
        "sign": sign,
        "radius_outer": radius_outer,
        "rho_inner": rho_outer - RING_RADIAL_MM,
        "rho_outer": rho_outer,
        "z_low": min(z_rim, z_inner),
        "z_high": max(z_rim, z_inner),
    }
    # the meridians come up from the equator, so their keys seat in the
    # ring face they meet first
    values["key_face"] = z_inner
    values["meridian_radius"] = meridian_key_radius(values, clearance_mm)
    return values


def meridian_key_radius(values, clearance_mm):
    """Outer radius a meridian arc may use where it crosses this ring.

    The arc has to clear the washer.  It either passes inside the ring's
    bore, or passes the ring on the side its keys come from; whichever
    lets the arc sit nearer the ring keeps the two pieces closest.
    """
    phi = math.radians(values["center_lat"])
    inside = math.sqrt(max((values["rho_inner"] - clearance_mm) ** 2
                           - KEY_WINDOW_MM ** 2, 0.0))
    inside = inside / abs(math.cos(phi)) if abs(math.cos(phi)) > 1e-9 else 0.0
    rise = math.sin(phi)
    if abs(rise) < 1e-9:
        return inside
    side = (values["key_face"]
            - values["sign"] * clearance_mm) / rise
    return max(inside, side)


def tab_triangles(tile_latitude, tile_longitude, tile_radius, values):
    """The ring's tab into one tile's underside socket.

    The tab runs along the tile's own up axis, so it fits the socket's
    rectangular opening exactly; its root sits inside the ring's body.
    """
    east, north, up = tiles.local_frame(tile_latitude, tile_longitude)
    # root the tab inside the ring's wall, far enough in that the corners of
    # the tab's cross-section stay in the ring's body
    z_root = values["radius_outer"] - RING_RADIAL_MM * 0.75
    z_tip = tile_radius + tiles.KEY_SOCKET_DEPTH_MM - TAB_DEPTH_CLEARANCE_MM
    return box_triangles(
        _scale(up, (z_root + z_tip) / 2.0),
        _scale(east, (tiles.KEY_SOCKET_WIDTH_MM - FIT_CLEARANCE_MM) / 2.0),
        _scale(north, (tiles.KEY_SOCKET_LENGTH_MM - FIT_CLEARANCE_MM) / 2.0),
        _scale(up, (z_tip - z_root) / 2.0))


def horizontal_ring(tiles_band, inner_radii, values, clearance_mm):
    """One horizontal ring piece (world coordinates)."""
    rho_inner = values["rho_inner"]
    rho_outer = values["rho_outer"]
    z_low = values["z_low"]
    z_high = values["z_high"]
    sign = values["sign"]
    center_lat = values["center_lat"]

    # meridian crossings: the notches its keys seat in
    key_lons = [(MERIDIAN_PHASE_DEG + (360.0 / MERIDIAN_COUNT) * index)
                % 360.0 for index in range(MERIDIAN_COUNT)]
    path_radius = (rho_inner + rho_outer) / 2.0
    half_window = math.degrees(KEY_WINDOW_MM / path_radius)

    steps = 720
    frames = []
    profiles = []
    for step in range(steps):
        longitude = 360.0 * step / steps
        frames.append((ZERO, radial_at(longitude), (0.0, 0.0, 1.0)))
        notched = any(abs(((key_lon - longitude + 180.0) % 360.0) - 180.0)
                      <= half_window for key_lon in key_lons)
        step_low, step_high = z_low, z_high
        if notched:
            # lift the bottom face (north) or drop the top face (south):
            # the notch always opens toward the meridian's key
            if sign > 0.0:
                step_low = z_low + KEY_DEPTH_MM
            else:
                step_high = z_high - KEY_DEPTH_MM
        profiles.append(ring_profile(rho_inner, rho_outer, step_low,
                                     step_high))
    triangles = sweep(frames, profiles, closed=True)
    # tabs: one per tile centre in this band.  A band keys through tabs only
    # when its tiles centre on the ring latitude; the polar cap centres on
    # the pole and is held by the stem instead.
    for tile in tiles_band:
        tile_lat, tile_lon = tiles.tile_center(tile)
        if abs(tile_lat - center_lat) > 1.0:
            continue
        triangles.extend(tab_triangles(tile_lat, tile_lon,
                                       inner_radii[tile["id"]], values))
    return orient(triangles)


def meridian_arc(longitude, north, ring_data, clearance_mm, steps=360):
    """One meridian arc piece from the equator to the cap ring (world).

    `ring_data` is the list of ring_values dictionaries the arc crosses;
    each crossing gets a key that seats in that ring's notch.
    """
    signature = 1.0 if north else -1.0
    latitudes = [signature * 75.0 * step / steps for step in range(steps + 1)]

    def interpolate(latitude):
        keys = sorted(((entry["center_lat"], entry["meridian_radius"])
                       for entry in ring_data), key=lambda item: item[0])
        if latitude <= keys[0][0]:
            return keys[0][1]
        if latitude >= keys[-1][0]:
            return keys[-1][1]
        for a, b in zip(keys, keys[1:]):
            if a[0] <= latitude <= b[0]:
                span = b[0] - a[0]
                if span < 1e-9:
                    return a[1]
                t = (latitude - a[0]) / span
                return a[1] + t * (b[1] - a[1])
        return keys[-1][1]

    frames = []
    profiles = []
    for latitude in latitudes:
        radius_outer = interpolate(latitude)
        radius_inner = radius_outer - RING_RADIAL_MM
        radial, _ = frame_at(latitude, longitude)
        frames.append((ZERO, radial, east_at(longitude)))
        profiles.append(meridian_profile(radius_inner, radius_outer,
                                         MERIDIAN_WIDTH_MM / 2.0))
    triangles = sweep(frames, profiles, closed=False)
    for entry in ring_data:
        triangles.extend(meridian_key_triangles(longitude, entry))
    return orient(triangles)


def meridian_key_triangles(longitude, values):
    """The box a meridian arc uses to key into one ring.

    It seats in the ring's notch with FIT_CLEARANCE_MM of slack all round
    and runs back past the ring's bore into the arc's body, so the ring and
    the arc fuse into their printed pieces across a real overlap.
    """
    rho_a = values["rho_inner"] - KEY_DEPTH_MM
    rho_b = values["rho_outer"] - FIT_CLEARANCE_MM / 2.0
    face = values["key_face"]
    sign = values["sign"]
    z_a = face - sign * KEY_DEPTH_MM
    z_b = face + sign * (KEY_DEPTH_MM - TAB_DEPTH_CLEARANCE_MM)
    radial = radial_at(longitude)
    center = _scale(radial, (rho_a + rho_b) / 2.0)
    return box_triangles(
        (center[0], center[1], (z_a + z_b) / 2.0),
        _scale(radial, (rho_b - rho_a) / 2.0),
        _scale(east_at(longitude),
               KEY_WINDOW_MM - FIT_CLEARANCE_MM / 2.0),
        (0.0, 0.0, (z_b - z_a) / 2.0))


def cap_stem(north, cap_inner_radius, values, clearance_mm):
    """Cap stem: a post from the pole down into the cap ring, with two
    crossed spokes tying it to the ring.

    The post tabs into the polar cap tile's socket; the spokes sit in the
    half of the ring nearest the pole and reach into the ring's wall.  They
    run on the diagonals so they clear the meridians' keys.
    """
    signature = 1.0 if north else -1.0
    half_north = (tiles.KEY_SOCKET_LENGTH_MM - FIT_CLEARANCE_MM) / 2.0
    half_east = (tiles.KEY_SOCKET_WIDTH_MM - FIT_CLEARANCE_MM) / 2.0
    z_pole = signature * (cap_inner_radius + tiles.KEY_SOCKET_DEPTH_MM
                          - TAB_DEPTH_CLEARANCE_MM)
    thickness = 2.5
    # the wall's far half is clear of the meridians' keys, which seat in
    # the notch on the near face
    if signature > 0.0:
        z_spoke = values["z_high"] - TAB_DEPTH_CLEARANCE_MM - thickness / 2.0
    else:
        z_spoke = values["z_low"] + TAB_DEPTH_CLEARANCE_MM + thickness / 2.0
    reach = values["rho_inner"] + 1.5
    # the post rises from the spokes' own plane, so the printed piece
    # stands on the cross rather than on the post's tip
    triangles = box_triangles(
        (0.0, 0.0, (z_spoke + z_pole) / 2.0),
        (half_north, 0.0, 0.0), (0.0, half_east, 0.0),
        (0.0, 0.0, abs(z_pole - z_spoke) / 2.0))
    for angle_deg in (45.0, 135.0):
        triangles.extend(box_triangles(
            (0.0, 0.0, z_spoke),
            _scale(radial_at(angle_deg), reach),
            _scale(east_at(angle_deg), MERIDIAN_WIDTH_MM / 2.0),
            (0.0, 0.0, thickness / 2.0)))
    return orient(triangles)


def print_ready(triangles, plane_normal):
    """Rotate a piece so its plane is horizontal, then drop it to z = 0."""
    normal = plane_normal
    length = math.sqrt(sum(value * value for value in normal))
    normal = tuple(value / length for value in normal)
    if normal[2] < -1.0 + 1e-9:
        # the piece's up axis points down (southern pieces mirror the
        # northern ones): roll it over so its up side really is on top
        triangles = [tuple((point[0], -point[1], -point[2])
                           for point in triangle)
                     for triangle in triangles]
    elif abs(normal[2]) < 1.0 - 1e-9:
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
        hemisphere_sign = 1.0 if arguments.hemisphere == "north" else -1.0
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
            tiles_radius = min(inner.values())
            values = ring_values(tiles_radius, BAND_CENTERS[band],
                                 arguments.clearance_mm)
            ring = horizontal_ring(band_tiles, inner, values,
                                   arguments.clearance_mm)
            ring_data[band] = values
            pieces.append(("ring-" + band.lower(), ring,
                           (0.0, 0.0, hemisphere_sign)))
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
                            ring_data[bands[-1]], arguments.clearance_mm)
            pieces.append(("cap-stem", stem, (0.0, 0.0, hemisphere_sign)))
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
