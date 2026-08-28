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

## Assembly (current: interior support)

- The new approach fills the interior of each hemisphere with a **single
  solid** (the support) and subtracts a **vertical (polar-axis) cylinder**
  from it, leaving a shell the tiles sit on.
- Step 1: the solid hemisphere (radius `radius_mm`, default 100) with a
  flat equator face at z = 0 (the bed plane when printed).
- Step 2: subtract an 80 mm-diameter cylinder (just inside the 60°-row's
  100 mm diameter). The bore is a through-hole: it opens at the equator
  face and exits through the top — the solid ends at the rim where the
  bore meets the sphere (lat arccos(40/100) = 66.4°, z = 91.65), so the
  bore is open at both ends. The shell is 60 mm thick at the equator,
  ~47 mm at the 30° row and 10 mm at the 60° row.
- Step 3: the assembled view (`support.html`, `make support`) shows the
  support with all rows of tiles of the hemisphere (north: N00, N30, N90).
  The tiles' flat bottoms sit at world radii ~91–105 mm, so the support's
  outer radius must be tuned (≈90 mm, or a faceted surface matching each
  tile's bottom plane) for the tiles to seat without intersecting it.

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
- 2026-08-27 — **Interior support: fill the hemisphere with a single solid,
  subtract an 80 mm-diameter polar-axis cylinder.** Reason: the ribs only
  seated the first rows, and a full solid interior gives every row a
  seating surface. The bore is 80 mm (radius 40) — just inside the 60°-row
  diameter (100 mm) — so the shell stays 10 mm thick at the 60° row and
  thicker toward the equator; the bore closes where it meets the sphere
  (lat 66.4°). The assembled view (`support.html`) shows the support with
  all rows of tiles. Open fit item: the tiles' flat bottoms sit at world
  radii ~91–105 mm, so the support's outer radius (or a faceted seating
  surface) still needs tuning.