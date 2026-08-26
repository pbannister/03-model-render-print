#!/usr/bin/env python3
#
# stl_tiles_build.py — render printable STL tile models of the Earth from
# the ETOPO 2022 source tiles on /datasets.
#
# Feature: prompts/features/03-stl-tiles.md
# Geometry decisions: documents/05-stl-approach.md
#
# Modes:
#   build   render the tile set into the output directory (default)
#   check   validate an existing tile set against its manifest
#
# The tiling-plan and coordinate-transform functions are pure Python so the
# portable test (tests/04-stl-tiles-math.sh) can exercise them without GDAL
# or numpy; GDAL and numpy are imported lazily only where needed.
#
# Usage examples:
#   stl_tiles_build.py build
#   stl_tiles_build.py build --band-degrees 15 --sample-degrees 0.5
#   stl_tiles_build.py build --region 40 50 -125 -115
#   stl_tiles_build.py build --tiles tile-N00E000,tile-S60E030
#   stl_tiles_build.py check
#   stl_tiles_build.py check --output-dir /tmp/tiles
import argparse
import json
import math
import os
import struct
import sys
import tempfile

NODATA_LIMIT = -30000.0
NODATA_REPLACEMENT = 0.0
EPSILON_FLAT = 1e-3


# ---------------------------------------------------------------------------
# Tiling plan (pure Python, no GDAL/numpy).
# ---------------------------------------------------------------------------

def plan_bands(band_degrees):
    """Latitude bands from -90 to 90; the bands that touch a pole are caps.

    A cap is a single round tile spanning the full 360 degrees of longitude.
    """
    if band_degrees <= 0:
        raise ValueError("band_degrees must be positive (got %s)" % band_degrees)
    count_bands = int(round(180.0 / band_degrees))
    if abs(band_degrees * count_bands - 180.0) > 1e-9:
        raise ValueError("band_degrees must divide 180 evenly (got %s)"
                         % band_degrees)
    bands = []
    for index in range(count_bands):
        lat_min = -90.0 + index * band_degrees
        lat_max = lat_min + band_degrees
        is_cap = lat_max == 90.0 or lat_min == -90.0
        bands.append({
            "lat_min": lat_min,
            "lat_max": lat_max,
            "is_cap": is_cap,
            "mid_lat": (lat_min + lat_max) / 2.0,
        })
    return bands


def lon_split_count(band):
    """Longitude split for a band: roughly equal surface area per tile.

    Tile area is proportional to cos(mid_lat) times the longitude span, so
    the split is round(360 * cos(mid_lat) / band_degrees).  A cap is a
    single round tile.
    """
    if band["is_cap"]:
        return 1
    band_degrees = band["lat_max"] - band["lat_min"]
    return max(1, int(round(360.0 * math.cos(math.radians(band["mid_lat"])) / band_degrees)))


def lat_label(lat):
    """Latitude edge label: 'N00', 'S60', ... for a band edge latitude."""
    if lat >= 0.0:
        return "N%02d" % int(round(lat))
    return "S%02d" % int(round(-lat))


def lon_label(lon):
    """Longitude edge label: 'E000', 'W030', ... for a tile west edge."""
    if lon >= 0.0:
        return "E%03d" % int(round(lon))
    return "W%03d" % int(round(-lon))


def plan_tiles(band_degrees):
    """The full tile list for the globe at the given band height."""
    tiles = []
    for band in plan_bands(band_degrees):
        lon_span = 360.0 / lon_split_count(band)
        for lon_min in [index * lon_span for index in range(lon_split_count(band))]:
            tile = {
                "lat_min": band["lat_min"],
                "lat_max": band["lat_max"],
                "lon_min": lon_min,
                "lon_max": lon_min + lon_span,
                "is_cap": band["is_cap"],
            }
            tile["id"] = tile_id(tile)
            tiles.append(tile)
    return tiles


def tile_id(tile):
    """Stable tile id from the tile's geographic edges."""
    if tile["is_cap"]:
        if tile["lat_max"] == 90.0:
            return "tile-N90"
        return "tile-S90"
    return "tile-%s%s" % (lat_label(tile["lat_min"]), lon_label(tile["lon_min"]))


def normalize_lon(lon):
    """Map a longitude to the -180..180 range."""
    return lon - 360.0 if lon >= 180.0 else lon


def select_tiles(tiles, requested_ids=None, region=None):
    """Filter the plan to the requested tile ids and/or the region.

    The region is (south, north, west, east) in degrees; a tile is kept when
    its latitude and longitude spans intersect the region.  Longitude west
    must be less than east (no antimeridian crossing).  Tile longitudes are
    stored in the 0..360 range and normalized for the comparison.
    """
    selected = list(tiles)
    if requested_ids:
        ids_set = set(requested_ids)
        known = set(tile["id"] for tile in tiles)
        unknown = sorted(ids_set - known)
        if unknown:
            raise ValueError("unknown tile ids: %s" % ", ".join(unknown))
        selected = [tile for tile in selected if tile["id"] in ids_set]
    if region:
        south, north, west, east = region
        if not (-90.0 <= south < north <= 90.0):
            raise ValueError("invalid region latitudes: %s" % (region,))
        if not (-180.0 <= west < east <= 180.0):
            raise ValueError("invalid region longitudes (west must be < east): %s" % (region,))
        selected = [
            tile for tile in selected
            if tile["lat_max"] > south and tile["lat_min"] < north
            and normalize_lon(tile["lon_max"]) > west
            and normalize_lon(tile["lon_min"]) < east
        ]
    return selected


# ---------------------------------------------------------------------------
# Coordinates (pure Python, no GDAL/numpy).
# ---------------------------------------------------------------------------

def unit_radial(lat_degrees, lon_degrees):
    """Unit radial vector for a geographic position."""
    phi = math.radians(lat_degrees)
    lam = math.radians(lon_degrees)
    return (math.cos(phi) * math.cos(lam),
            math.cos(phi) * math.sin(lam),
            math.sin(phi))


def local_frame(center_lat, center_lon):
    """Orthonormal tile-local frame: (east, north, up).

    Up is the sphere normal at the tile center; east and north are the
    tangent directions along longitude and latitude.
    """
    up = unit_radial(center_lat, center_lon)
    lam = math.radians(center_lon)
    east = (-math.sin(lam), math.cos(lam), 0.0)
    phi = math.radians(center_lat)
    north = (-math.sin(phi) * math.cos(lam),
             -math.sin(phi) * math.sin(lam),
             math.cos(phi))
    return (east, north, up)


def dot(point_a, point_b):
    return (point_a[0] * point_b[0]
            + point_a[1] * point_b[1]
            + point_a[2] * point_b[2])


def to_local(point, frame):
    """World point -> tile-local coordinates (east, north, up)."""
    east, north, up = frame
    return (dot(point, east), dot(point, north), dot(point, up))


# ---------------------------------------------------------------------------
# Grid sampling plan (pure Python).
# ---------------------------------------------------------------------------

def grid_lines(tile, sample_degrees):
    """(latitudes, longitudes) grid lines for a tile.

    Latitude rows span the tile south-north; longitude columns span the tile
    west-east (with wrap for the polar caps).  Longitude spacing is scaled
    by 1 / cos(mid_lat) so the physical spacing stays roughly constant.
    """
    lat_span = tile["lat_max"] - tile["lat_min"]
    count_lat = max(1, int(round(lat_span / sample_degrees)))
    latitudes = [tile["lat_min"] + index * (lat_span / count_lat)
                 for index in range(count_lat + 1)]
    latitudes[-1] = tile["lat_max"]

    mid_lat = (tile["lat_min"] + tile["lat_max"]) / 2.0
    spacing_lon = sample_degrees / math.cos(math.radians(mid_lat))
    if tile["is_cap"]:
        count_lon = max(4, int(round(360.0 / spacing_lon)))
        longitudes = [tile["lon_min"] + index * (360.0 / count_lon)
                      for index in range(count_lon)]
    else:
        lon_span = tile["lon_max"] - tile["lon_min"]
        count_lon = max(1, int(round(lon_span / spacing_lon)))
        longitudes = [tile["lon_min"] + index * (lon_span / count_lon)
                      for index in range(count_lon + 1)]
        longitudes[-1] = tile["lon_max"]
    return latitudes, longitudes


def elevation_to_mm(elevation, elevation_min, elevation_max, parameters):
    """Map an elevation (metres) to millimetres of model height.

    The mapping is linear over the global elevation range so all tiles share
    one absolute scale; the result lies in [base, base + relief].
    """
    if parameters["oceans_flat"] and elevation < 0.0:
        elevation = 0.0
    if parameters["elev_min"] is not None:
        elevation = max(elevation, parameters["elev_min"])
    if parameters["elev_max"] is not None:
        elevation = min(elevation, parameters["elev_max"])
    span = elevation_max - elevation_min
    if span <= 0.0:
        fraction = 0.5
    else:
        fraction = (elevation - elevation_min) / span
    fraction = max(0.0, min(1.0, fraction))
    return parameters["base_mm"] + parameters["relief_mm"] * fraction


# ---------------------------------------------------------------------------
# Mesh construction (pure Python).
# ---------------------------------------------------------------------------

def build_mesh(tile, latitudes, longitudes, elevation_mm, radius_mm, base_mm):
    """Triangle soup for one tile; bottom plane translated to z = 0.

    Returns (triangles, boundary_edges): boundary_edges is the number of
    boundary edges (also the number of bottom fan faces), used by check mode.
    """
    center_lat = (tile["lat_min"] + tile["lat_max"]) / 2.0
    center_lon = tile["lon_min"] if tile["is_cap"] else (
        tile["lon_min"] + tile["lon_max"]) / 2.0
    frame = local_frame(center_lat, center_lon)

    top = []
    for row_index, lat in enumerate(latitudes):
        row = []
        for col_index, lon in enumerate(longitudes):
            radial = unit_radial(lat, lon)
            height = radius_mm + elevation_mm[row_index][col_index]
            row.append(to_local((height * radial[0],
                                 height * radial[1],
                                 height * radial[2]), frame))
        top.append(row)

    z_bottom = min(point[2] for row in top for point in row) - base_mm

    triangles = []
    count_lat = len(latitudes) - 1
    if tile["is_cap"]:
        count_lon = len(longitudes)
        # One end of the latitude rows is the pole; the other is the ring.
        # Construction always runs ring -> pole regardless of orientation.
        pole_first = abs(latitudes[0]) >= 90.0
        if pole_first:
            rows_ordered = list(range(count_lat, -1, -1))
            row_pole = 0
            row_ring = count_lat
        else:
            rows_ordered = list(range(0, count_lat + 1))
            row_pole = count_lat
            row_ring = 0
        for step in range(count_lat - 1):
            row_a = rows_ordered[step]
            row_b = rows_ordered[step + 1]
            for col in range(count_lon):
                col_next = (col + 1) % count_lon
                point_a = top[row_a][col]
                point_b = top[row_a][col_next]
                point_c = top[row_b][col_next]
                point_d = top[row_b][col]
                triangles.append((point_a, point_b, point_c))
                triangles.append((point_a, point_c, point_d))
        pole = top[row_pole][0]
        row_near_pole = rows_ordered[count_lat - 1]
        for col in range(count_lon):
            col_next = (col + 1) % count_lon
            point_a = top[row_near_pole][col]
            point_b = top[row_near_pole][col_next]
            triangles.append((point_a, point_b, pole))
        boundary = [top[row_ring][col] for col in range(count_lon)]
    else:
        count_lon = len(longitudes) - 1
        for row in range(count_lat):
            for col in range(count_lon):
                point_a = top[row][col]
                point_b = top[row][col + 1]
                point_c = top[row + 1][col + 1]
                point_d = top[row + 1][col]
                triangles.append((point_a, point_b, point_c))
                triangles.append((point_a, point_c, point_d))
        boundary = []
        for col in range(count_lon + 1):
            boundary.append(top[0][col])
        for row in range(1, count_lat + 1):
            boundary.append(top[row][count_lon])
        for col in range(count_lon - 1, -1, -1):
            boundary.append(top[count_lat][col])
        for row in range(count_lat - 1, 0, -1):
            boundary.append(top[row][0])

    boundary_edges = len(boundary)

    def translate(point):
        return (point[0], point[1], point[2] - z_bottom)

    triangles = [(translate(point_a), translate(point_b), translate(point_c))
                 for (point_a, point_b, point_c) in triangles]

    bottom_center = (0.0, 0.0, 0.0)
    for index in range(boundary_edges):
        point_a = translate(boundary[index])
        point_b = translate(boundary[(index + 1) % boundary_edges])
        bottom_a = (point_a[0], point_a[1], 0.0)
        bottom_b = (point_b[0], point_b[1], 0.0)
        triangles.append((point_a, point_b, bottom_b))
        triangles.append((point_a, bottom_b, bottom_a))
        triangles.append((bottom_center, bottom_b, bottom_a))

    if signed_volume(triangles) < 0.0:
        triangles = [(point_a, point_c, point_b)
                     for (point_a, point_b, point_c) in triangles]

    return triangles, boundary_edges


def signed_volume(triangles):
    """Signed volume of a closed triangle soup (positive when outward)."""
    volume = 0.0
    for (point_a, point_b, point_c) in triangles:
        volume += (point_a[0] * (point_b[1] * point_c[2] - point_c[1] * point_b[2])
                   + point_b[0] * (point_c[1] * point_a[2] - point_a[1] * point_c[2])
                   + point_c[0] * (point_a[1] * point_b[2] - point_b[1] * point_a[2]))
    return volume / 6.0


# ---------------------------------------------------------------------------
# STL writing and checking (pure Python).
# ---------------------------------------------------------------------------

def compute_normal(point_a, point_b, point_c):
    """Unit facet normal via the right-hand rule; zero for degenerate faces."""
    ux = point_b[0] - point_a[0]
    uy = point_b[1] - point_a[1]
    uz = point_b[2] - point_a[2]
    vx = point_c[0] - point_a[0]
    vy = point_c[1] - point_a[1]
    vz = point_c[2] - point_a[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length < 1e-12:
        return (0.0, 0.0, 0.0)
    return (nx / length, ny / length, nz / length)


def write_stl(path, triangles, header_text):
    """Write a binary STL file (little-endian floats, millimetres)."""
    header_bytes = header_text.encode("ascii", "replace")[:79]
    header = header_bytes.ljust(80, b" ")
    with open(path, "wb") as handle:
        handle.write(header)
        handle.write(struct.pack("<I", len(triangles)))
        for (point_a, point_b, point_c) in triangles:
            normal = compute_normal(point_a, point_b, point_c)
            handle.write(struct.pack("<12fH",
                                     normal[0], normal[1], normal[2],
                                     point_a[0], point_a[1], point_a[2],
                                     point_b[0], point_b[1], point_b[2],
                                     point_c[0], point_c[1], point_c[2],
                                     0))


def read_stl(path):
    """Parse a binary STL file; returns the list of triangles."""
    with open(path, "rb") as handle:
        data = handle.read()
    if len(data) < 84:
        raise ValueError("%s: too small for a binary STL" % path)
    count = struct.unpack("<I", data[80:84])[0]
    if len(data) != 84 + count * 50:
        raise ValueError("%s: size %d does not match %d triangles"
                         % (path, len(data), count))
    triangles = []
    for index in range(count):
        offset = 84 + index * 50
        values = struct.unpack("<12fH", data[offset:offset + 50])
        point_a = (values[3], values[4], values[5])
        point_b = (values[6], values[7], values[8])
        point_c = (values[9], values[10], values[11])
        triangles.append((point_a, point_b, point_c))
    return triangles


def check_tile(path, expected, radius_mm, relief_mm):
    """Validate one tile; returns a list of error strings (empty when ok)."""
    errors = []
    triangles = read_stl(path)
    if len(triangles) != expected["triangles"]:
        errors.append("%s: %d triangles, expected %d"
                      % (path, len(triangles), expected["triangles"]))

    vertices = [vertex for triangle in triangles for vertex in triangle]
    z_min = min(point[2] for point in vertices)
    z_max = max(point[2] for point in vertices)
    if z_min < -EPSILON_FLAT or z_min > EPSILON_FLAT:
        errors.append("%s: bottom z = %.6g, expected 0" % (path, z_min))
    limit = radius_mm + relief_mm + 1.0
    for point in vertices:
        if abs(point[0]) > limit or abs(point[1]) > limit:
            errors.append("%s: vertex outside horizontal bounds: %s" % (path, point))
            break
    if z_max > 2.0 * limit:
        errors.append("%s: z max %.3f exceeds expected bound" % (path, z_max))

    edges = {}
    for (point_a, point_b, point_c) in triangles:
        for (start, end) in ((point_a, point_b), (point_b, point_c), (point_c, point_a)):
            key_start = (round(start[0], 6), round(start[1], 6), round(start[2], 6))
            key_end = (round(end[0], 6), round(end[1], 6), round(end[2], 6))
            key = (key_start, key_end) if key_start <= key_end else (key_end, key_start)
            edges[key] = edges.get(key, 0) + 1
    edges_odd = [key for (key, count) in edges.items() if count != 2]
    if edges_odd:
        errors.append("%s: not watertight (%d edges not shared by exactly 2 faces)"
                      % (path, len(edges_odd)))

    faces_bottom = sum(
        1 for (point_a, point_b, point_c) in triangles
        if abs(point_a[2]) <= EPSILON_FLAT
        and abs(point_b[2]) <= EPSILON_FLAT
        and abs(point_c[2]) <= EPSILON_FLAT)
    if faces_bottom != expected["edges_boundary"]:
        errors.append("%s: %d flat-bottom faces, expected %d"
                      % (path, faces_bottom, expected["edges_boundary"]))

    volume = signed_volume(triangles)
    if volume <= 0.0:
        errors.append("%s: signed volume %.6g, expected positive" % (path, volume))
    return errors


# ---------------------------------------------------------------------------
# Build mode (GDAL/numpy gated).
# ---------------------------------------------------------------------------

def load_global_grid(vrt_path, sample_degrees, working_directory):
    """Warp the source VRT to one global grid; returns (grid, geotransform).

    The grid is Float32 with pixel-is-area registration covering
    [-180, 180] x [-90, 90]; every tile samples the same aligned grid, so
    shared boundaries read identical pixels.
    """
    from osgeo import gdal
    gdal.UseExceptions()
    width = max(2, int(round(360.0 / sample_degrees)))
    height = max(2, int(round(180.0 / sample_degrees)))
    path_grid = os.path.join(working_directory, "grid-%.4gdeg.tif" % sample_degrees)
    dataset = gdal.Warp(path_grid, vrt_path,
                        format="GTiff",
                        resampleAlg="average",
                        outputBounds=(-180.0, -90.0, 180.0, 90.0),
                        width=width, height=height,
                        outputType=gdal.GDT_Float32,
                        dstNodata=NODATA_LIMIT,
                        creationOptions=["COMPRESS=DEFLATE", "PREDICTOR=3"])
    if dataset is None:
        raise RuntimeError("gdal.Warp failed for the global grid")
    band = dataset.GetRasterBand(1)
    grid = band.ReadAsArray()
    transform = dataset.GetGeoTransform()
    dataset = None
    return grid, transform


def sample_grid(grid, transform, latitudes, longitudes):
    """Nearest-pixel elevation (metres) for each (lat, lon) grid point."""
    pixel_x = transform[1]
    pixel_y = -transform[5]
    rows = []
    for lat in latitudes:
        row_y = int(round((90.0 - lat) / pixel_y - 0.5))
        row_y = max(0, min(grid.shape[0] - 1, row_y))
        row = []
        for lon in longitudes:
            col_x = int(round((lon + 180.0) / pixel_x - 0.5))
            col_x = max(0, min(grid.shape[1] - 1, col_x))
            value = float(grid[row_y][col_x])
            if value <= NODATA_LIMIT or math.isnan(value):
                value = NODATA_REPLACEMENT
            row.append(value)
        rows.append(row)
    return rows


def build_vrt(source_directory, working_directory):
    """Build a VRT over the *_surface.tif tiles; returns its path."""
    from osgeo import gdal
    gdal.UseExceptions()
    files_source = sorted(
        os.path.join(source_directory, name)
        for name in os.listdir(source_directory)
        if name.endswith("_surface.tif"))
    if not files_source:
        raise RuntimeError("no ETOPO surface tiles under %s" % source_directory)
    path_vrt = os.path.join(working_directory, "etopo-source.vrt")
    gdal.BuildVRT(path_vrt, files_source)
    return path_vrt


def run_build(arguments):
    import datetime
    import shutil
    import subprocess

    from osgeo import gdal
    gdal.UseExceptions()

    if arguments.sample_degrees <= 0.0:
        raise ValueError("sample_degrees must be positive")

    parameters = {
        "band_degrees": arguments.band_degrees,
        "radius_mm": arguments.radius_mm,
        "base_mm": arguments.base_mm,
        "relief_mm": arguments.relief_mm,
        "sample_degrees": arguments.sample_degrees,
        "elev_min": arguments.elev_min,
        "elev_max": arguments.elev_max,
        "oceans_flat": arguments.oceans_flat,
        "units": "mm",
    }
    tiles = plan_tiles(arguments.band_degrees)
    tiles = select_tiles(tiles, arguments.tiles, arguments.region)

    os.makedirs(arguments.output_dir, exist_ok=True)
    working_directory = tempfile.mkdtemp(prefix="stl-tiles-build-")
    try:
        path_vrt = build_vrt(arguments.source_dir, working_directory)
        grid, transform = load_global_grid(path_vrt, arguments.sample_degrees,
                                           working_directory)
        grid_valid = [value for row in grid for value in row if value > NODATA_LIMIT]
        if not grid_valid:
            raise RuntimeError("the global grid has no valid pixels")
        elevation_min = float(min(grid_valid))
        elevation_max = float(max(grid_valid))
        if arguments.elev_min is not None:
            elevation_min = arguments.elev_min
        if arguments.elev_max is not None:
            elevation_max = arguments.elev_max

        print("stl-tiles-build: %d tile(s), elevation %.1f..%.1f m, "
              "radius %g mm, base %g mm, relief %g mm, samples %g deg"
              % (len(tiles), elevation_min, elevation_max,
                 arguments.radius_mm, arguments.base_mm, arguments.relief_mm,
                 arguments.sample_degrees))

        manifest_tiles = []
        for tile in tiles:
            latitudes, longitudes = grid_lines(tile, arguments.sample_degrees)
            elevations = sample_grid(grid, transform, latitudes, longitudes)
            elevation_mm = [
                [elevation_to_mm(value, elevation_min, elevation_max, parameters)
                 for value in row]
                for row in elevations
            ]
            triangles, boundary_edges = build_mesh(
                tile, latitudes, longitudes, elevation_mm,
                arguments.radius_mm, arguments.base_mm)
            path_stl = os.path.join(arguments.output_dir, tile["id"] + ".stl")
            write_stl(path_stl, triangles,
                      "model-render-print %s; R %g mm; base %g; relief %g; "
                      "lat %.1f..%.1f lon %.1f..%.1f"
                      % (tile["id"], arguments.radius_mm, arguments.base_mm,
                         arguments.relief_mm, tile["lat_min"], tile["lat_max"],
                         tile["lon_min"], tile["lon_max"]))
            manifest_tiles.append({
                "id": tile["id"],
                "file": os.path.basename(path_stl),
                "lat_min": tile["lat_min"],
                "lat_max": tile["lat_max"],
                "lon_min": tile["lon_min"],
                "lon_max": tile["lon_max"],
                "is_cap": tile["is_cap"],
                "triangles": len(triangles),
                "edges_boundary": boundary_edges,
                "size_bytes": os.path.getsize(path_stl),
            })
            print("stl-tiles-build: %s -> %s (%d triangles, %d bytes)"
                  % (tile["id"], os.path.basename(path_stl),
                     len(triangles), os.path.getsize(path_stl)))
    finally:
        shutil.rmtree(working_directory, ignore_errors=True)

    repository_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        commit_git = subprocess.run(
            ["git", "-C", repository_root, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=False).stdout.strip() or "unknown"
    except OSError:
        commit_git = "unknown"
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    manifest = {
        "generated_from": arguments.source_dir,
        "generated_by": "scripts/stl-tiles-build.sh",
        "generator_module": "scripts/stl_tiles_build.py",
        "do_not_edit_by_hand": True,
        "dataset_id": "etopo-2022",
        "dataset_resolution": "15s",
        "parameters": parameters,
        "elevation": {
            "data_min": elevation_min,
            "data_max": elevation_max,
        },
        "build": {
            "timestamp": timestamp,
            "git_commit": commit_git,
        },
        "tiles": manifest_tiles,
    }
    path_manifest = os.path.join(arguments.output_dir, "manifest.json")
    with open(path_manifest, "w") as handle:
        json.dump(manifest, handle, indent=4)
        handle.write("\n")
    print("stl-tiles-build: wrote %s (%d tiles)"
          % (path_manifest, len(manifest_tiles)))
    return 0


# ---------------------------------------------------------------------------
# Check mode.
# ---------------------------------------------------------------------------

def run_check(arguments):
    path_manifest = os.path.join(arguments.output_dir, "manifest.json")
    if not os.path.isfile(path_manifest):
        raise RuntimeError("no manifest at %s" % path_manifest)
    with open(path_manifest) as handle:
        manifest = json.load(handle)
    parameters = manifest["parameters"]
    errors_all = []
    for entry in manifest["tiles"]:
        path_stl = os.path.join(arguments.output_dir, entry["file"])
        if not os.path.isfile(path_stl):
            errors_all.append("missing tile: %s" % path_stl)
            continue
        errors = check_tile(path_stl, entry,
                            parameters["radius_mm"], parameters["relief_mm"])
        for error in errors:
            errors_all.append(error)
        if not errors:
            print("stl-tiles-check: %s ok (%d triangles)"
                  % (entry["id"], entry["triangles"]))
    if errors_all:
        for error in errors_all:
            print("stl-tiles-check: %s" % error)
        return 1
    print("stl-tiles-check: %d tile(s) ok" % len(manifest["tiles"]))
    return 0


# ---------------------------------------------------------------------------
# Command line.
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="stl_tiles_build",
        description="Render printable STL tile models of the Earth from "
                    "the ETOPO 2022 source tiles.")
    parser.add_argument("mode", nargs="?", default="build",
                        choices=("build", "check"),
                        help="build (default) or check the tile set")
    parser.add_argument("--source-dir", default="/datasets/dataset-etopo-2022",
                        help="ETOPO 2022 source tile directory (default: "
                             "/datasets/dataset-etopo-2022)")
    parser.add_argument("--output-dir", default=None,
                        help="tile output directory (default: "
                             "dataflow.out/stl under the repository root)")
    parser.add_argument("--band-degrees", type=float, default=30.0,
                        help="latitude band height in degrees (must divide "
                             "180; default 30)")
    parser.add_argument("--radius-mm", type=float, default=100.0,
                        help="globe radius in millimetres (default 100)")
    parser.add_argument("--base-mm", type=float, default=3.0,
                        help="minimum base slab thickness in millimetres "
                             "(default 3)")
    parser.add_argument("--relief-mm", type=float, default=20.0,
                        help="elevation relief range in millimetres "
                             "(default 20)")
    parser.add_argument("--sample-degrees", type=float, default=0.25,
                        help="mesh grid spacing in degrees (default 0.25)")
    parser.add_argument("--elev-min", type=float, default=None,
                        help="clamp input elevations to this minimum")
    parser.add_argument("--elev-max", type=float, default=None,
                        help="clamp input elevations to this maximum")
    parser.add_argument("--oceans-flat", action="store_true",
                        help="clamp water-covered cells to sea level")
    parser.add_argument("--tiles", default=None,
                        help="comma-separated tile ids to build")
    parser.add_argument("--region", nargs=4, type=float, default=None,
                        metavar=("SOUTH", "NORTH", "WEST", "EAST"),
                        help="build only tiles intersecting the region")
    return parser


def main(argv=None):
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.output_dir is None:
        repository_root = os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))
        arguments.output_dir = os.path.join(repository_root,
                                            "dataflow.out", "stl")
    if arguments.tiles is not None:
        arguments.tiles = [item.strip() for item in arguments.tiles.split(",")
                           if item.strip()]
    try:
        if arguments.mode == "build":
            return run_build(arguments)
        return run_check(arguments)
    except (ValueError, RuntimeError) as error:
        print("stl-tiles-build: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
