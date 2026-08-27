# Episode: FreeCAD assembly view

[EPISODE]
Assemble and render the globe in FreeCAD: a scripted assembly that loads
the tile STLs with their recorded placements and produces an assembled
FreeCAD document and a rendered image of the globe.

[PHASE]
phase 1

[ACCEPTANCE]
- Does `scripts/freecad-assemble.py` build an assembled FreeCAD document
  from the tile set and `globe-assembly.json` (or the manifest placements)
  produced by episode `02-assembled-globe-export.md`?
- Does it export an assembled `.FCStd` document and a rendered image
  (PNG) of the globe, with each tile visible in place?
- Does the tool-gated test skip cleanly when `freecadcmd` is absent?
- Is the whole change reviewable in one sitting?

[RISK]
- Is `freecadcmd` installable on this build host (package availability,
  size, Python compatibility), and is that install part of this episode or
  an owner action?
- Does the headless render work (Qt offscreen platform) without a display?

[SUB-TASKS]
- Install FreeCAD (`freecadcmd`) on the build host, or record the install
  as an explicit owner action with a setup note in `documents/`.
- Write `scripts/freecad-assemble.py`: read placements, load each tile STL
  as a mesh, apply the placement transform, add to a document, export
  `.FCStd` and a PNG render.
- Add the tool-gated test `tests/06-freecad-assemble.sh` (skips cleanly
  without `freecadcmd`).
- Verify the assembled document and render on the full 42-tile set.

[OUTPUT FORMAT]
Report the FreeCAD setup state, the changed files, and the verification
result (document + image paths).

[FILES]
- `scripts/freecad-assemble.py` — new
- `tests/06-freecad-assemble.sh` — new
- `documents/07-freecad-setup.md` — new (install + headless render note)
- `prompts/episodes/02-assembled-globe-export.md` — existing (dependency)

[BRANCH]
llm/episode-02
