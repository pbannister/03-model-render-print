# Task: Implement the STL Tiles feature

## TASK-DESCRIPTION

- Modify: `scripts/stl-tiles-build.sh`
- Modify: `scripts/stl_tiles_build.py`
- Modify: `tests/03-stl-tiles-build.sh`
- Modify: `tests/04-stl-tiles-math.sh`
- Modify: `Makefile`
- Modify: `scripts/site-state-fetch.sh`
- Modify: `TODO.md`

Implement feature `prompts/features/03-stl-tiles.md` (STL Tiles) in
`scripts/stl-tiles-build.sh` plus a Python module `scripts/stl_tiles_build.py`
that the script drives.

The build renders the Earth's surface from the ETOPO 2022 source tiles
(`/datasets/dataset-etopo-2022/`, read-only) into watertight binary-STL
tiles in `dataflow.out/stl/` with a manifest, a `--check` validation mode,
and subset rendering (`--tiles`, `--region`).

## TASK-OUTPUT

- Implement the files, then run `make build`, `make check`, and `make test`
  from the repository root.
- Report the tile counts, sizes, and verification results.
- End with the `VERIFICATION:` line.

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

| Operation | Path |
|---|---|
| modify | `scripts/stl-tiles-build.sh` |
| modify | `scripts/stl_tiles_build.py` |
| modify | `tests/03-stl-tiles-build.sh` |
| modify | `tests/04-stl-tiles-math.sh` |
| modify | `Makefile` |
| modify | `scripts/site-state-fetch.sh` |
| modify | `TODO.md` |

## TASK-VERIFY
- Run: `make build`, `make check`, and `make test` from the repository root.
- Expected: exit status 0 from each.

## TASK-FEATURES
- `prompts/features/03-stl-tiles.md`

## TASK-ACCEPTANCE
- `STL-TILES-R001`
- `STL-TILES-R002`
- `STL-TILES-R003`

OUTPUT: the implemented files, the tile counts and sizes, and the verification results, ending with the `VERIFICATION:` line.
