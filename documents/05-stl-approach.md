# STL Tile Approach (Printable Earth)

This document captures how `model-render-print` turns the GDEM data on the
shared `/datasets` volume into STL models that load into a slicer and print
on a 3D printer. It is a decision log; mark each option decided with a date
and reason.

## Goal

Printable 3D models of the Earth's surface from the ETOPO 2022 dataset
(`/datasets/dataset-etopo-2022/`, 15-arcsecond GeoTIFF tiles, ~6 GB). The
surface of the globe is divided into roughly equal-size tiles along lines
of latitude and longitude; each tile is an STL file that:
- loads into OrcaSlicer / PrusaSlicer (binary STL, millimeters, watertight),
- prints on a common FDM printer (each tile fits the bed, flat bottom down),
- has a flat bottom so it sits against the printer bed,
- mates with its neighbors along the top surface, so the assembled set
  shows the whole globe.

## Source data

- `ETOPO 2022` — global relief model combining land elevation and seafloor
  bathymetry at 15-arcsecond (~450 m) resolution, as 350 GeoTIFF tiles.
- Maintained and versioned by the `model-elevation-earth` project; the
  manifest is `/datasets/manifest.yml` (`etopo-2022`).
- Read-only consumption: this project never writes to `/datasets`; derived
  tiles go in `dataflow.out/stl/`.

## Candidate approaches

1. **Spherical patch tiles** — CHOSEN (decided 2026-08-26)
   - Each tile is the solid piece of a globe: the top surface is the
     sphere at radius R + relief, the bottom is a flat chord plane, and the
     side walls are vertical in the tile's local frame. Tiles placed
     bottom-down print flat; the top surfaces are the exact spherical
     surface, so the assembled outside of a set is the globe.
2. **Flattened relief plaques** — rejected (decided 2026-08-26)
   - Each tile is a flat map projection extruded with relief on top (the
     common "terrain plate" approach). Simpler, but the pieces are flat
     plaques that cannot assemble into a globe; the task names the surface
     of the globe, so the pieces must carry the sphere's curvature.
3. **Full solid globe / slice stack** — deferred (decided 2026-08-26)
   - Print the whole globe (possibly in stacked rings) in one model.
     Larger prints than the bed allows at useful sizes; the task asks for
     lat/lon tiles.

## Tiling scheme

- Latitude bands of equal height `band_degrees` (default 30).
- Within a band, longitude is split into `N = round(360 · cos(mid_lat) / band)`
  tiles, so each tile covers roughly equal surface area.
- The highest and lowest bands are a single round tile each (the polar
  caps, spanning the full 360 degrees of longitude). Decided 2026-08-26:
  the task allows "the highest latitude can be a single (round) tile";
  both poles get the same treatment for symmetry.
- Defaults (band 30): south cap 1 + 8 + 12 + 12 + 8 + north cap 1 = 42
  tiles. Band 15 gives 180 tiles (regional detail).

## Geometry (per tile)

- Globe radius R (default 100 mm → 200 mm globe; fits a 220 mm bed).
- Tile-local frame: `up` is the sphere normal at the tile center; `east`
  and `north` complete the frame.
- Top surface: for each sample (lat, lon), the point is `(R + h) · r̂`
  where `h` is the mapped elevation and `r̂` the unit radial vector; the
  point is expressed in the tile-local frame.
- Elevation mapping: `h = base + relief · (e − e_min) / (e_max − e_min)`
  with the global ETOPO range (so neighboring tiles share absolute scale).
  Defaults: base 3 mm, relief 20 mm → Everest ≈ 23 mm above the bed,
  Challenger Deep ≈ 3 mm.
- Bottom: a flat plane at the local z of the shallowest top point minus
  `base`, translated so the plane is z = 0 (the bed plane in the STL).
- Side walls: chamfered. Each wall quad is bounded above by the top-surface
  boundary edge and below by the radial projection of that edge onto the
  bottom plane, so every wall plane contains the globe center. In the
  assembled globe each shared edge pair therefore lies in one common wall
  plane (no wedge gaps), and the walls flare slightly outward going up
  (a trivially printable overhang).
- Underside mark: the tile id (e.g. `N30E045`) is engraved as recessed
  grooves on the underside (z stays 0; the grooves cut upward into the
  base). Engraved, not raised, so the tile still sits flat on the bed.
- Key socket: a rectangular recess cut into the centre of the underside,
  6 mm (tile east) × 4 mm (tile north) × 2 mm deep, centred on the tile
  centre. It receives the support ring's tab (see the ring lattice below);
  the engraved id sits in the lower rows of a taller, still centred label
  box so the socket stays clear.
- The tile is watertight: top quads (fan at the pole), chamfered wall
  strips, engraved bottom face (ring fan around the label grid).
- Units: millimeters; the STL's z = 0 is the bed plane, so slicers can
  "lay on face" without translation.

## Sampling

- Per-tile mesh grid at `sample_degrees` (default 0.25) in latitude.
- Longitude spacing scales by `1 / cos(mid_lat)` so the physical vertex
  spacing stays roughly constant across the globe (a polar cap is not
  over-built at 360-degree density).
- Average resampling via GDAL from the source VRT; a coarse global grid
  supplies the elevation range used for the mapping.

## Toolchain

- GDAL 3.8.4 on the build host (`gdalbuildvrt` for the source VRT,
  `osgeo.gdal.Warp` for per-tile sampling) plus Python 3 with osgeo/numpy.
  Verified on the build host 2026-08-26.

## Assembly (superseded: internal frame)

- An earlier plan added an internal hub-and-strut frame. It is **dropped**:
  the glued seams need help, but a central hub with one strut per tile is
  too hard to assemble and align (see the decision log below).

## Assembly (superseded: rib + hemispheres)

- An intermediate plan assembled each hemisphere from a full-diameter
  reinforcing rib that seated the first row of tiles, with tile-to-ring
  sockets and between-tile wall keys. The ribs, the sockets and the wall
  keys are **dropped** (see the decision log below).

## Assembly (tiles only: STEP export of the hemisphere)

- The interior solid with the through-bore is dropped. A hemisphere (tiles
  only) can still be exported as a STEP file (AP214, one solid per tile at
  its world position) for editing in a CAD tool:
  `python3 scripts/hemisphere_step.py` writes
  `dataflow.out/step/hemisphere-north.step` (sample density and hemisphere
  are parameters; the default 5-degree sampling keeps the file compact).

## Assembly (current: support ring lattice)

- The globe is larger than the print bed, so the internal support is
  printed in sections and assembled inside the tiles: 3 horizontal rings +
  12 meridian arcs + 1 cap stem = **16 pieces per hemisphere**, rendered by
  `make rings` (`scripts/rings_build.py`) into `dataflow.out/rings/`.
- **Horizontal rings**: one hoop per latitude band, at the band centres
  (15° / 45° / 75° N for the north hemisphere; -15° / -45° / -75° for the
  south). Cross-section 8 mm radial × 6 mm lateral, sitting just inside the
  band's tiles with 0.6 mm clearance. A ring carries a **tab** at every
  tile centre of its band (12 on the equatorial ring, 8 on the temperate
  ring): the tab is 5.6 × 3.6 mm and reaches 1.8 mm into the tile's 6 × 4
  × 2 mm centre socket, leaving 0.2 mm of clearance per side and at the
  tip (the slanted tab side wall costs a few hundredths of a millimetre of
  that). Tabs are aligned with the tile sockets because a band's tile
  centre latitude is exactly the ring latitude, so the ring's cross-section
  frame (radial + north) is the tile's local frame (up + north).
- **Cap ring**: the 75°-band ring has no tabs — the polar cap tile centres
  on the pole, not on the ring — so it is the structural ring that the
  meridian arcs and the cap stem tie into.
- **Meridian arcs**: 12 arcs, each running from the equator up to the cap
  ring, 8 mm radial × 6 mm lateral, just inside the rings (0.6 mm
  clearance). At every ring crossing the meridian carries a **tongue**
  (5.6 × 5.6 mm, reaching 2.8 mm into the ring's 3 mm-deep, 6 mm-wide
  **groove**). The meridians sit at 0° / 30° / ... / 330°: those longitudes
  are the equatorial band's tile seams, so a groove never lands on a tab
  (the equatorial tiles centre on 15° + 30°k and the temperate tiles on
  22.5° + 45°k, both at least 7.5° away).
- **Cap stem**: a post on the polar axis from the cap ring's plane up into
  the polar cap tile's socket (6 × 4 mm section, 0.2 mm tip clearance),
  plus two crossed 6 × 6 mm spoke bars in the ring's plane, on the
  diagonals so they clear the cap ring's grooves.
- **Bed fit**: the 15° ring is the largest piece at Ø190.8 mm, leaving
  ~15 mm on a 220 mm bed; the meridian arcs are ~105 × 105 × 6 mm and the
  cap stem 36 × 36 × 12 mm. `print_ready` lays every piece flat (meridian
  planes rotated horizontal) with z = 0 on the bed.
- **Verification**: `tests/05-rings-math.sh` is a portable (no GDAL) check
  that the tabs seat inside the sockets in the tile's own frame, the
  tongues reach into the grooves, no ring carries a groove and a tab at the
  same longitude, the cap stem reaches the pole socket and its spokes land
  in the cap ring's body, and every print-ready piece fits the bed. The
  rendered STLs are checked separately for watertightness, positive volume
  and z = 0.

## Row diameters

- The horizontal (small-circle) diameter of the base sphere at the latitude
  rows between the 30-degree bands, for R = 100 mm:
  - 0° (equator, N00 ↔ S30 join): 2·R·cos 0° = **200.0 mm**
  - 30° (N00 ↔ N30, S30 ↔ S60 joins): 2·R·cos 30° = **173.2 mm**
  - 60° (N30 ↔ cap, S60 ↔ cap joins): 2·R·cos 60° = **100.0 mm**
- With relief, the local diameter at any point is 2·(R + h)·cos φ, up to
  ~220 / 190.5 / 110 mm where the topography is highest.

## Open questions

- Print calibration: relief/base defaults tuned against a real print on the
  Elegoo Centauri Carbon (0.4 mm nozzle).
- Larger fidelity: finer sample spacing (e.g. 0.1 degree) and/or smaller
  band heights for regional tiles; watch STL size per tile.

## Decision log

- 2026-08-26 — **Approach: spherical patch tiles** (candidate 1). Reason:
  tiles carry the globe's curvature and assemble along the top surface;
  flattened plaques (candidate 2) cannot assemble and the task names the
  globe's surface.
- 2026-08-26 — **Tiling: 30-degree bands, longitude split by cos(mid_lat),
  single polar cap tiles**. Reason: roughly equal surface area per tile,
  42 tiles for the whole globe, round polar caps.
- 2026-08-26 — **Globe size: R = 100 mm (200 mm diameter)**. Reason: fits a
  common 220 mm bed while keeping 30-degree tiles ~52 mm across.
- 2026-08-26 — **Solid construction: top surface + flat bottom + vertical
  local walls, watertight per tile**; bottom translated to z = 0.
  Reason: prints flat on the bed; slicers need watertight solids.
  Superseded the same day: the walls are now chamfered (below).
- 2026-08-26 — **Elevation mapping: global ETOPO range, base 3 mm + relief
  20 mm**. Reason: consistent absolute scale across tiles; print-friendly
  relief; deepest ocean floor still clears the base plate.
- 2026-08-26 — **Sampling: 0.25-degree default, longitude spacing scaled by
  1/cos(mid_lat)**. Reason: ~0.4 mm vertex spacing at the 200 mm globe
  (matches the 0.4 mm nozzle); polar caps are not over-built.
- 2026-08-26 — **Output: binary STL + manifest.json** in
  `dataflow.out/stl/`. Reason: compact, universally accepted by slicers;
  the manifest carries parameters and provenance for `make check` and the
  dashboard.
- 2026-08-26 — **Toolchain: GDAL 3.8.4 + Python 3 with osgeo/numpy**.
  Reason: available on this host (verified 2026-08-26); no custom reader
  needed.
- 2026-08-26 — **Oceans: flat for now (`--oceans-flat` on the standard
  run)**. Reason: the near-term prints are land-focused; seafloor relief is
  deferred. Flat oceans clamp water-covered cells to 0 m elevation, so all
  ocean cells map to one sea-level plateau height above the base and the
  coastline rim stays visible; a flush-to-base variant remains possible.
- 2026-08-26 — **Chamfered walls through the globe center**. Each wall
  quad's plane contains the globe center, so every shared edge pair lies
  in one common plane in the assembled globe and the wedge gaps disappear.
  Reason: the vertical walls left per-tile wedge gaps when tiles were
  tilted up and joined; the chamfer makes the mating walls coplanar.
- 2026-08-26 — **Underside id: engraved (recessed) tile id on the
  underside**. Reason: the user asked for an identifying mark to aid
  assembly; engraving keeps z = 0 so the tile still sits flat on the bed.
- 2026-08-26 — **Verification: watertightness (edge-manifold), flat bottom
  at z = 0, expected bounds, positive signed volume** via `make check`.
  Reason: these are the properties slicers rely on.
- 2026-08-27 — **Ribs and between-tile alignment keys deleted; the assembly approach is under revision.** The reinforcing ribs (with the tile-to-ring underside sockets) and the wall fin/groove keys are removed from the tile build, the site (the rib page is gone) and this document; the previous state was tagged in git for reference. Row diameters of the base sphere (R = 100 mm) at the 0/30/60-degree rows are 200.0 / 173.2 / 100.0 mm.
- 2026-08-27 — **Interior support dropped; the hemisphere is exported as
  a STEP file (tiles only) instead.** The interior-solid-and-bore support
  did not match what was wanted, so it is removed entirely; the tiles
  remain the deliverable. A hemisphere (tiles only, one solid per tile at
  its world position) is written as an AP214 STEP file
  (`scripts/hemisphere_step.py`) for editing in OnShape or FreeCAD, with
  the sample density parameterized to keep the file size practical.
- 2026-09-23 — **Support: horizontal rings keyed into the tile centres,
  vertical meridian arcs keyed into the rings** (the user's plan). Reason:
  the support must print on a 220 mm bed while the assembled globe is
  200 mm across, so it is printed in sections (16 pieces per hemisphere)
  and assembled inside the tiles. The ring's tab goes into a 6 × 4 × 2 mm
  socket cut into each tile's underside centre; the socket is 0.4 mm larger
  than the tab in both lateral directions and 0.2 mm deeper, so the parts
  drop together after printing.
- 2026-09-23 — **Meridians sit on the equatorial tile seams (0° + 30°k).**
  Reason: the first draft put the meridians at the equatorial tile centres
  (15° + 30°k), where a ring would then need a groove and a tab at the same
  longitude — geometrically impossible. At the seams, no crossing lands on
  a tab (nearest tab 7.5° away), so every meridian keeps a key at all three
  ring crossings.
- 2026-09-23 — **Ring lattice verified by a portable math test**
  (`tests/05-rings-math.sh`) plus STL checks (watertight, positive volume,
  z = 0, ≤ 220 mm). Reason: the ring geometry is easy to get subtly wrong
  (the first render silently built every ring at twice its radius, and the
  cap ring at latitude 90°), so the checks assert the tile-frame fit and
  the assembled radii numerically rather than by eye.