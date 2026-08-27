# Episode: Assembled globe export

[EPISODE]
Record each tile's placement in `manifest.json` at build time and add an
`assemble` mode that merges the tile STLs into one positioned mesh, so the
assembled globe can be imported into any mesh viewer (OnShape, FreeCAD,
MeshLab, Blender) for inspection.

[PHASE]
phase 1

[ACCEPTANCE]
- Does `manifest.json` record per-tile placement (`center_lat`,
  `center_lon`, `z_bottom`) for every built tile?
- Does `stl_tiles_build.py assemble` write `globe.stl` (merged binary STL),
  `globe.obj` (per-tile groups), and `globe-assembly.json` into
  `dataflow.out/stl-assembled/` from an existing tile set and its manifest?
- Does the assembled mesh match the globe geometry: total triangle count
  equals the sum of per-tile counts, and the bounding radius stays within
  R + base + relief?
- Do adjacent tiles' shared boundary vertices coincide after placement
  within print tolerance (1e-3 mm)?
- Is the whole change reviewable in one sitting?

[RISK]
- Is the placement (rotation from the tile-local frame, translation by
  `z_bottom` along the local up axis) exact enough that shared boundaries
  coincide — the neighbors sample the same global grid, but each is placed
  in its own frame?
- Does the merged mesh stay intended-for-viewing only (internal coincident
  faces make it unsuitable for printing), and is that stated in the
  output and the README?

[SUB-TASKS]
- Extend `run_build` to record `center_lat`, `center_lon`, and `z_bottom`
  in each manifest tile entry.
- Add pure-Python placement helpers (placement from a manifest entry;
  world transform of a placed point) to `stl_tiles_build.py`.
- Add the `assemble` mode: read the manifest and tile STLs, apply each
  placement, write the merged STL/OBJ/assembly JSON into
  `dataflow.out/stl-assembled/`.
- Add `assemble --check`: triangle-count sum, bounding radius, and
  adjacent-tile shared-edge coincidence.
- Extend `tests/04-stl-tiles-math.sh` with placement-transform invariants
  and a synthetic adjacent-pair coincidence check; extend the tool-gated
  build test to run assemble + check on its region output.
- Add a Makefile `assemble` target and document the output in the README.
- Run assemble on the full 42-tile set and verify the acceptance counts.

[OUTPUT FORMAT]
Report the placement math, the changed files, the assembled-output file
sizes, and the `--check` result.

[FILES]
- `scripts/stl_tiles_build.py` — existing (build manifest + new assemble mode)
- `scripts/stl-tiles-build.sh` — existing (mode pass-through, usage comment)
- `tests/04-stl-tiles-math.sh` — existing
- `tests/03-stl-tiles-build.sh` — existing
- `Makefile` — existing
- `README.md` — existing

[BRANCH]
llm/episode-01
