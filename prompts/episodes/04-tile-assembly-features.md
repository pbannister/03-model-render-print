# Episode: Tile assembly features (chamfered walls, alignment keys, underside mark)

[EPISODE]
Chamfer the tile side walls so each wall's plane passes through the globe
center, add vertical fin/groove alignment keys on the mating walls, and
engrave the tile id on the underside, so the tiles assemble into a globe
without wedge gaps, print without supports, and are easy to identify and
align.

[PHASE]
phase 1

[ACCEPTANCE]
- Does every wall strip lie in a plane through the globe center (in the
  pre-translation tile frame)?
- Do adjacent tiles share exactly one wall plane per mating edge, with
  vertical fins on the north/east walls mating vertical grooves on the
  south/west walls (polar caps grooved), so the assembled set has no wedge
  gaps and every fin meets a groove?
- Are the keys vertical (running from the top edge down the wall), so the
  tiles print without supports?
- Does the underside carry an engraved (recessed) tile id while the flat
  bottom stays at z = 0?
- Does `make check` still pass (watertight, flat bottom at z = 0, expected
  bounds, positive signed volume) on the rebuilt full-globe set?
- Is the whole change reviewable in one sitting?

[RISK]
- Do the stud/socket features fit the thin (3-9 mm) wall strips — are the
  keys sized to the local wall height and skipped where the wall is too
  thin?
- Do the key and groove cut-outs keep every edge shared by exactly two
  faces (watertightness)?

[SUB-TASKS]
- Replace the vertical wall quads with chamfered strips in `build_mesh`:
  each strip is bounded above by the top-surface boundary edge and below by
  the radial projection of that edge onto the bottom plane, so the strip
  plane contains the globe center.
- Add stud/socket alignment keys: north and east walls carry studs, south
  and west walls carry sockets, polar-cap rings carry sockets per adjacent
  band tile; size each key to the local wall height and skip when too thin.
- Engrave the tile id on the underside with a minimal stroke font; keep
  z_min = 0 (recessed grooves, not raised marks).
- Extend the manifest and check mode for the new bottom-face structure
  (`faces_bottom`) and record the assembly features.
- Extend `tests/04-stl-tiles-math.sh` with chamfer-plane, key-convention,
  and underside-mark invariants.
- Rebuild the full-globe set and verify with `make check` and `make test`.

[OUTPUT FORMAT]
Report the wall/key/mark geometry, the changed files, and the
check/test results.

[FILES]
- `scripts/stl_tiles_build.py` — existing
- `tests/04-stl-tiles-math.sh` — existing
- `documents/05-stl-approach.md` — existing
- `prompts/features/03-stl-tiles.md` — existing
- `README.md` — existing
- `TODO.md` — existing

[BRANCH]
llm/episode-03
