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
- Alignment keys: vertical lens-shaped fins and grooves on the walls.
  North and east walls carry fins (studs); south and west carry grooves
  (sockets); polar-cap rings carry grooves. A fin is only placed where its
  mating groove exists (pair-wise decision from the wall heights at the
  key position), so every fin meets a groove in the assembled globe. Each
  key tapers to zero depth at both ends (a lens over the reference height
  of 3.2 mm — the shortest wall that hosts a key, so keys appear on every
  tile boundary in the real build), so every key surface is slanted and
  the tiles print without supports. The equator join (N00 south ↔ S30
  north) carries no wall key:
  the rib seats the first rows and the tile-to-ring socket stays centred
  on the underside instead (see Assembly).
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

## Assembly (current: rib + hemispheres)

- Assemble the **north and south hemispheres independently**, then join them
  at the equator.
- Each hemisphere starts from a **reinforcing rib**: a full ring around the
  entire diameter, sitting just above the equator (north) or just below it
  (south), whose outer face makes contact with the inner (bottom) faces of
  that hemisphere's first row of tiles. The rib fixes the first row all the
  way around the seam, so no cumulative error can accumulate before the rows
  above stack up.
- The rib is not a smooth ring: its outer surface is a series of flat
  facets, one per first-row tile, each lying in that tile's bottom plane, so
  the rib's outer faces make full contact with the tiles' inner (flat-bottom)
  faces. Each facet carries a centred trapezoidal **stud fin** (3 mm wide,
  2 mm deep, chamfered ends) that seats into a matching **socket** (groove)
  cut in the tile's underside — 4 mm wide, 3 mm deep, spanning the fin's
  full base band so the fin drops fully in with 0.5 mm side and 1 mm depth
  slack — so the first row cannot slide sideways on the rib. Its
  inside diameter is 20 mm less than the sea-level diameter
  (200 mm → 180 mm, inner radius 90 mm) and it is 10 mm thick. One rib is
  printed per hemisphere (`rib-north.stl` / `rib-south.stl`, both flat at
  z = 0).
- The rib and first rows are generated by `scripts/rib_firstrow_build.py`
  (`make rib`) into `dataflow.out/rib/` and rendered interactively on the
  project page `rib.html` (tiles shown semi-transparent so the ribs' contact
  is visible). The first rows are N00 (0–30°N) and S30 (30°S–0). Facet
  heights come from the same elevation pipeline as the tile build, so they
  match the tiles' actual bottom planes.

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
- 2026-08-26 — **Alignment keys: vertical fins (north/east) and grooves
  (south/west), socketed polar-cap rings, placed pair-wise**. Reason:
  chamfered walls alone leave the tiles free to slide; a fin always meets
  a groove because a fin is only placed where the mating groove exists.
  The keys are vertical so all key surfaces are near-vertical and the
  tiles print without supports.
  Superseded the same day by the vertical-key orientation (below): the
  first keys were horizontal ridges along the edges, and the printed
  tiles needed a great deal of supports, so the keys were re-oriented.
- 2026-08-26 — **Lens-shaped keys**. The vertical fins and grooves taper
  to zero depth at both ends (a lens over the reference height of 3.2 mm),
  so they have no horizontal end faces at all. Reason: the slicer flagged
  the flat bottom-end shelves and groove ceilings of the plain vertical
  keys as floating regions; the lens makes every key surface slanted.
  (The reference was originally 8 mm; see the 2026-08-27 entry below.)
- 2026-08-26 — **Underside id: engraved (recessed) tile id on the
  underside**. Reason: the user asked for an identifying mark to aid
  assembly; engraving keeps z = 0 so the tile still sits flat on the bed.
- 2026-08-26 — **Verification: watertightness (edge-manifold), flat bottom
  at z = 0, expected bounds, positive signed volume** via `make check`.
  Reason: these are the properties slicers rely on.
- 2026-08-27 — **Assembly: drop the internal hub-and-strut frame; assemble
  north and south hemispheres independently around a full-diameter
  reinforcing rib just above/below the equator, then join them.** Reason:
  the internal frame was too hard to assemble and align. The rib seats the
  first row of tiles (N00 north, S30 south) all the way around the seam, so
  placement is fixed before any row stacks and cumulative error is
  precluded. Visualized at `rib.html`.
- 2026-08-27 — **Rib geometry: faceted outer surface, one facet per
  first-row tile, each lying in the tile's bottom plane; inner diameter
  180 mm (20 mm less than the sea-level 200 mm) and 10 mm thick.** Reason:
  a cylindrical outer face would leave gaps against the tiles' flat bottoms;
  matching each tile's bottom plane makes full contact and seats the first
  row without play. One rib prints per hemisphere, flat at z = 0.
- 2026-08-27 — **Tile-to-ring sockets: a recessed groove (4 mm wide, 3 mm
  deep) cut into the underside of every first-row tile (N00 north, S30
  south), centred on the tile's longitude, receiving the rib facet's stud
  fin; the equator wall key (N00 south ↔ S30 north) is dropped.** Reason:
  the printed rib + tiles showed the fin seats well, and the fin needs a
  receiving groove so the first row cannot slide sideways on the rib; the
  equator wall key was dropped so the socket can stay centred on the tile
  longitude without a competing wall key at the same position. The socket
  is a true hole in the bottom face: the fan triangles that reach the
  opening are re-triangulated around it (region boundary walked and ear
  clipped per triangle), and walls + floor close the recess. Verified
  watertight with `make check` on the full real-data tile set.
- 2026-08-27 — **Between-tile wall keys on every boundary: the key lens
  reference (and its gate) drops from 8 mm to 3.2 mm, with the lens
  constants scaled proportionally, and the north fins are placed one per
  overlapping tile above (at the overlap's centre) instead of one per
  tile.** Reason: the real-data wall heights at the boundary mid-samples
  are ~6.8–8.3 mm (band tiles) and ~3.5 mm (polar-cap rings), so the 8 mm
  gate placed keys on almost no boundary at all (2 of 162 in the real
  build). The lens profile is scale-invariant — the depth is a function of
  the v-fraction times the reference, so scaling reference and constants
  together leaves the key geometry unchanged — and the gate now admits
  every boundary (the shortest, the cap rings at ~3.5 mm, still host the
  lens). The equal-area bands hold different tile counts (12 tiles at
  0–30° against 8 at 30–60°), so the joins misalign; placing each fin at
  the overlap's centre (and deriving every socket from its fin's actual
  position) keys every shared segment, with fins and sockets exactly
  matched (88 = 88 in the real build). The equator join stays unkeyed
  (the rib seats the first rows).
- 2026-08-27 — **Between-tile keys reach full nominal depth; the rib page
  renders the real first-row tiles; the ring-wall key direction is
  fixed.** The lens rise/fall spans were 1.4 mm over the 3.2 mm reference,
  so the rise and fall overlapped and every key reached only 51% of its
  nominal depth (1.0 mm fins, 1.5 mm grooves); the spans are now 0.6 mm
  each, so the lens plateaus at full depth (2.0 mm fins, 3.0 mm grooves)
  with the same v-lines and slanted end faces. The rib page's first-row
  tiles were built without wall keys (`keys=[]`), so the assembled view
  showed only the underside socket insets; the rib build now computes the
  pair-wise key decisions and renders the real tiles, and the key-quad
  guard admits two-quad keys so the keys also place at the rib view's
  1-degree sampling. Finally, the wall normals were oriented away from the
  tile's interior direction (the radial at the tile centre), which for the
  polar caps is the pole axis and does not point from the ring wall into
  the cap body — the ring sockets on the southern cap were inverted
  (protruding outward instead of recessing, and poking below the bottom
  plane at full depth). The normals are now oriented away from the
  boundary centroid, so every fin protrudes and every groove recesses into
  its own tile.
