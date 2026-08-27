# TODO

## Pending Tasks

* [x] Start the project from `00-project-skeleton` (2026-08-26): repo
      `03-model-render-print`, project README/TODO, STL tile approach
      decision log (`documents/05-stl-approach.md`), project feature
      (`prompts/features/03-stl-tiles.md`) and task
      (`prompts/tasks/03-stl-tiles-implement.md`), standard page set.
* [x] Implement the STL tile pipeline: ETOPO GeoTIFF tiles
      (`/datasets/dataset-etopo-2022/`) → per-tile STL models with a flat
      bottom in `dataflow.out/stl/`, plus `manifest.json`. Implemented as
      `scripts/stl-tiles-build.sh` + `scripts/stl_tiles_build.py`; covered by
      tool-gated test `tests/03-stl-tiles-build.sh` and portable math test
      `tests/04-stl-tiles-math.sh`.
* [x] Verify the generated tiles load into a slicer: watertight (every edge
      shared by exactly two triangles), flat bottom at z = 0, expected
      bounds, positive signed volume. Verified 2026-08-26 by
      `make check` over the default full-globe run (42 tiles).

## Pending Tasks

* [ ] Assembled globe viewing (episodes written 2026-08-26; dispatch after
      the human ratifies):
      `prompts/episodes/02-assembled-globe-export.md` (merge the tiles into
      one positioned mesh for viewing in any mesh viewer, incl. OnShape
      import) and `prompts/episodes/03-freecad-assembly-view.md` (assemble
      and render in FreeCAD — long-term goal, needs FreeCAD installed).

## Open Questions

* [ ] Print calibration: verify one printed tile on the actual printer
      (Elegoo Centauri Carbon; see the workspace `profiles-elegoo-centauri-carbon`
      project) and tune relief/base defaults for the 0.4 mm nozzle.
* [ ] Larger fidelity: finer sample spacing (e.g. 0.1 degree) and/or a
      smaller band height for regional tiles; watch STL size per tile.

## Recently Completed

* [x] Re-orient the alignment keys vertically (2026-08-26): the first
      horizontal ridge keys printed with a great deal of supports, so the
      keys are now vertical fins and grooves (north/east fins, south/west
      grooves, grooved cap rings) that run from the top edge down the
      wall. Every key surface is near-vertical, so the tiles print
      support-free.
* [x] Add tile assembly features (2026-08-26): chamfered walls through the
      globe center (each wall plane contains the center, so assembled
      neighbors' walls are coplanar), stud/socket alignment channels
      (north/east studs, south/west sockets, socketed cap rings, placed
      pair-wise so every stud meets a socket), and the tile id engraved on
      the underside (recessed grooves keep z = 0). The globe-assembly open
      question is resolved; decisions logged in
      `documents/05-stl-approach.md`.
* [x] Decide the ocean treatment: flat for now (2026-08-26). The
      `--oceans-flat` option clamps water-covered cells to sea level, so
      oceans print as one smooth plateau (coastline rim visible); the
      decision is logged in `documents/05-stl-approach.md`, the standard
      run (`make build`) uses the flag, and the default full-globe set in
      `dataflow.out/stl/` was rebuilt flat.
* [x] Implement and verify the STL tile pipeline (2026-08-26): default
      full-globe run produced 42 watertight tiles (band 30 degrees,
      R = 100 mm, base 3 mm, relief 20 mm, 0.25-degree samples) into
      `dataflow.out/stl/`; `make check` validates watertightness, flat
      bottom, bounds, and orientation; `make test` green.
* [x] Decide the STL tile approach and record it in
      `documents/05-stl-approach.md` (decided 2026-08-26: spherical patch
      tiles on a 200 mm globe, latitude bands with longitude split for
      roughly equal area, single polar cap tiles, flat bottom, binary STL,
      GDAL toolchain on the build host).
