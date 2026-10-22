# Feature: STL Tiles

## Purpose

Printable 3D models of the Earth rendered from the GDEM data on the shared
`/datasets` volume: the surface of the globe is divided into roughly
equal-size tiles along lines of latitude and longitude, and each tile is
rendered as an STL file that loads into a slicer (OrcaSlicer, PrusaSlicer)
and prints on a 3D printer.

## Requirements

- `STL-TILES-R001` — `scripts/stl-tiles-build.sh` must render the tile set into
  `dataflow.out/stl/` from the ETOPO 2022 source tiles
  (`/datasets/dataset-etopo-2022/`, read-only).
- `STL-TILES-R002` — The globe surface must be divided into tiles along latitude and longitude
  lines; tiles in the same latitude band must have roughly equal surface
  area (longitude split scales by the cosine of the band's mid latitude).
- `STL-TILES-R003` — The highest and lowest latitude bands must each be a single round tile
  (the polar caps, spanning the full 360 degrees of longitude).
- `STL-TILES-R004` — Each tile must have a flat bottom that sits against the printer bed; the
  STL's z = 0 is the bed plane.
- `STL-TILES-R005` — Each tile must be a watertight solid (every edge shared by exactly two
  triangles), so slicers accept it.
- `STL-TILES-R006` — Each tile must mate with its neighbors along the top surface: the top
  surface is the spherical surface of the globe at radius R with elevation
  relief, and neighboring tiles sample the same geographic boundary.
- `STL-TILES-R007` — The side walls must be chamfered so each wall plane contains the globe
  center, so the walls of assembled neighbors are coplanar.
- `STL-TILES-R008` — Alignment keys: north and east walls carry vertical fins, south and west
  walls carry vertical grooves, polar-cap rings carry grooves; a fin is
  placed only when its mating groove exists, so every fin meets a groove
  in the assembled globe. The keys must be vertical (running from the top
  edge down the wall) so they print without supports.
- `STL-TILES-R009` — The underside must carry an engraved (recessed) tile id; z = 0 must stay
  the lowest plane.
- `STL-TILES-R010` — Elevation must be mapped with a global (not per-tile) range, so all tiles
  share the same absolute scale.
- `STL-TILES-R011` — Output format: binary STL, millimeters.
- `STL-TILES-R012` — `scripts/stl-tiles-build.sh --check` must validate every generated tile
  (watertight, flat bottom at z = 0, expected bounds, positive signed
  volume) without rebuilding.
- `STL-TILES-R013` — The build must write `dataflow.out/stl/manifest.json`: parameters,
  tile list with bounds and sizes, and provenance (dataset, script,
  timestamp, git commit).
- `STL-TILES-R014` — The build must support rendering a subset: `--tiles <ids>` (specific
  tiles) and `--region <south> <north> <west> <east>` (tiles intersecting a
  geographic region).
- `STL-TILES-R015` — Derived output (`dataflow.out/stl/`) is generated and must not be edited
  by hand.

## Behavior

- Running the script recreates the tile set deterministically from the
  source tiles and the given parameters.
- Re-running the script overwrites existing tiles.

## Dependencies

None. This feature depends on no other feature.

## External Inputs

- Tool-gated: GDAL 3.8+ and Python 3 with the `osgeo` and `numpy` modules,
  plus the ETOPO source tiles under `/datasets` on the owning host.
- Dataset `etopo-2022` maintained by the `model-elevation-earth` project.
