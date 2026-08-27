# Feature: STL Tiles

## Purpose

Printable 3D models of the Earth rendered from the GDEM data on the shared
`/datasets` volume: the surface of the globe is divided into roughly
equal-size tiles along lines of latitude and longitude, and each tile is
rendered as an STL file that loads into a slicer (OrcaSlicer, PrusaSlicer)
and prints on a 3D printer.

## Requirements

- `scripts/stl-tiles-build.sh` must render the tile set into
  `dataflow.out/stl/` from the ETOPO 2022 source tiles
  (`/datasets/dataset-etopo-2022/`, read-only).
- The globe surface must be divided into tiles along latitude and longitude
  lines; tiles in the same latitude band must have roughly equal surface
  area (longitude split scales by the cosine of the band's mid latitude).
- The highest and lowest latitude bands must each be a single round tile
  (the polar caps, spanning the full 360 degrees of longitude).
- Each tile must have a flat bottom that sits against the printer bed; the
  STL's z = 0 is the bed plane.
- Each tile must be a watertight solid (every edge shared by exactly two
  triangles), so slicers accept it.
- Each tile must mate with its neighbors along the top surface: the top
  surface is the spherical surface of the globe at radius R with elevation
  relief, and neighboring tiles sample the same geographic boundary.
- The side walls must be chamfered so each wall plane contains the globe
  center, so the walls of assembled neighbors are coplanar.
- Alignment keys: north and east walls carry studs, south and west walls
  carry sockets, polar-cap rings carry a socket groove; a stud is placed
  only when its mating socket exists, so every stud meets a socket in the
  assembled globe.
- The underside must carry an engraved (recessed) tile id; z = 0 must stay
  the lowest plane.
- Elevation must be mapped with a global (not per-tile) range, so all tiles
  share the same absolute scale.
- Output format: binary STL, millimeters.
- `scripts/stl-tiles-build.sh --check` must validate every generated tile
  (watertight, flat bottom at z = 0, expected bounds, positive signed
  volume) without rebuilding.
- The build must write `dataflow.out/stl/manifest.json`: parameters,
  tile list with bounds and sizes, and provenance (dataset, script,
  timestamp, git commit).
- The build must support rendering a subset: `--tiles <ids>` (specific
  tiles) and `--region <south> <north> <west> <east>` (tiles intersecting a
  geographic region).
- Derived output (`dataflow.out/stl/`) is generated and must not be edited
  by hand.

## Behavior

- Running the script recreates the tile set deterministically from the
  source tiles and the given parameters.
- Re-running the script overwrites existing tiles.

## Dependencies

- Tool-gated: GDAL 3.8+ and Python 3 with the `osgeo` and `numpy` modules,
  plus the ETOPO source tiles under `/datasets` on the owning host.
- Dataset `etopo-2022` maintained by the `model-elevation-earth` project.
