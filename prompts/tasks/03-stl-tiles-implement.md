# Task: Implement the STL Tiles feature

## TASK-DESCRIPTION

Implement feature `prompts/features/03-stl-tiles.md` (STL Tiles) in
`scripts/stl-tiles-build.sh` plus a Python module `scripts/stl_tiles_build.py`
that the script drives.

The build renders the Earth's surface from the ETOPO 2022 source tiles
(`/datasets/dataset-etopo-2022/`, read-only) into watertight binary-STL
tiles in `dataflow.out/stl/` with a manifest, a `--check` validation mode,
and subset rendering (`--tiles`, `--region`).

## TASK-CONTEXT

- The geometry decisions are recorded in `documents/05-stl-approach.md`:
  spherical patch tiles, latitude bands (default 30 degrees) with longitude
  split by `round(360 * cos(mid_lat) / band)`, single polar-cap tiles,
  tile-local frame with up = sphere normal at tile center, flat bottom
  translated to z = 0, base 3 mm + relief 20 mm over the global ETOPO
  elevation range, 0.25-degree samples with longitude spacing scaled by
  `1 / cos(mid_lat)`, globe radius 100 mm.
- The shell script owns the log file and the GDAL VRT over the source
  tiles; the Python module owns the tiling math, per-tile sampling
  (average resampling via `osgeo.gdal.Warp`), mesh construction, STL
  writing, manifest, and `--check` validation.
- The tiling/geometry math must be importable without `osgeo` or `numpy`
  (pure Python), so `tests/04-stl-tiles-math.sh` stays portable.
- Tests: tool-gated `tests/03-stl-tiles-build.sh` (builds a small region,
  then validates), portable `tests/04-stl-tiles-math.sh` (tiling math
  invariants).

## TASK-FILES

- `create scripts/stl-tiles-build.sh`
- `create scripts/stl_tiles_build.py`
- `create tests/03-stl-tiles-build.sh`
- `create tests/04-stl-tiles-math.sh`
- `modify Makefile` (wire `build` and `check` targets)
- `modify scripts/site-state-fetch.sh` (STL tile state keys for the dashboard)
- `modify TODO.md` (mark the STL tile tasks complete after verification)

## TASK-OUTPUT

- Implement the files, then run `make build`, `make check`, and `make test`
  from the repository root.
- Report the tile counts, sizes, and verification results.
