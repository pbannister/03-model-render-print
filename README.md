# Model Render Print

Printable 3D models of the Earth rendered from the global elevation model
(GDEM) data on the shared `/datasets` volume.

The render source is **ETOPO 2022** — the global relief model maintained by
the `model-elevation-earth` project (`/datasets/dataset-etopo-2022/`,
15-arcsecond GeoTIFF tiles). This project consumes that data read-only and
renders the Earth's surface as STL tile models for 3D printing: each tile is
one slice of the globe along lines of latitude and longitude, has a flat
bottom that sits against the printer bed, mates its neighbors with chamfered
walls through the globe center plus stud/socket alignment keys, carries the
tile id engraved on the underside, and loads directly into a slicer
(OrcaSlicer, PrusaSlicer, …). The chosen approach is tracked in
`documents/05-stl-approach.md`.

This repository is structured for collaborative development with a Large
Language Model (LLM), following the `00-project-skeleton` pattern. **The
LLM should begin by reading these files in order (the numeric prefix marks
load order):**

1. `prompts/01-contract.md`
2. `prompts/02-workflow.md`
3. `prompts/03-conventions.md`

These define the interaction rules, workflow, and formatting conventions.
Human contributors should begin with `prompts/README.md` and
`documents/README.md`.

Note there are rules meant only to constrain Aider behavior:

- `tools/aider-rules.md` (Aider users only)

All project features are defined in `prompts/features/` and implemented in `sources/`.

## Top-Level Map

- `README.md` is the project overview.
- `TODO.md` tracks pending and completed project tasks.
- `prompts/` contains LLM interaction rules, common requirements, feature requirements, task definitions, and episode work orders.
- `documents/` contains human-consumption documents (incl. `05-stl-approach.md`).
- `records/` contains version-controlled outcome, incident, and handoff records.
- `tools/` contains tool-specific rules.
- `tools/aider-rules.md` is used only with Aider.
- `sources/` contains implementations.
- `scripts/` contains project scripts (`site-build.sh`, `site-condense.sh`, `site-state-fetch.sh`, `stl-tiles-build.sh`).
- `tests/` contains tests and validation code.
- `dataflow.in/` contains input data.
- `dataflow.out/` contains generated data output (not version-controlled) — the derived STL tiles live here.
- `logs/` contains generated logs (not version-controlled).
- `site.in/` contains static-site input.
- `site.out/` contains generated static-site output (not version-controlled).
- `Makefile` drives the build (`make build`), the tests (`make test`), the site (`make site`), and state (`make state`).

## Project Pages (publishing conventions)

- This project publishes the standard page set (status, dashboard,
  condensed todo/prompts/documents/records + full-text pages) per
  `prompts/features/02-project-pages.md` and `documents/06-project-pages.md`.
- `make site` builds the full set; `make state` refreshes live dataset and
  tile state.
- Publishing goes through the homelab project (homelab-publish): this
  project registers once via `pages_source` and does not push to the web
  server itself — `make deploy` is retired.

## Data access

- The dataset volume `/datasets/` is read-only input; this project never
  writes there. Derived STL tiles go in `dataflow.out/stl/` (gitignored).
- `make state` reads the ETOPO source, the volume usage, and the tile
  manifest into `dataflow.out/site-state.txt` (see the dashboard).

## Printing workflow

- `make build` renders the STL tile set into `dataflow.out/stl/` and writes
  `dataflow.out/stl/manifest.json` (tile list, parameters, provenance).
- The standard build uses flat oceans (`--oceans-flat`): water-covered cells
  are clamped to sea level, so ocean areas print as one smooth plateau
  (decided 2026-08-26; see `documents/05-stl-approach.md`). Call
  `scripts/stl-tiles-build.sh build` without the flag for a run with
  seafloor relief.
- Load one tile (or a region) into a slicer. Tiles are millimeters, origin
  at the tile's flat bottom (z = 0 is the bed plane). The tile id is
  engraved on the underside; the north/east walls carry vertical fins and
  the south/west walls vertical grooves (polar-cap rings are grooved), so
  assembled neighbors lock together and the keys print without supports.
- `make check` re-validates every generated tile (watertight, flat bottom,
  expected size) without rebuilding.
- The full globe at the default 30-degree banding is 42 tiles; use
  `--tiles` or `--region` to render a subset (e.g. one country).

## History

- Started 2026-08-26 from `00-project-skeleton`.

## Canonical Files

The following filenames are canonical and must not be renamed or duplicated without an explicit task:

- `README.md`
- `TODO.md`
- `Makefile`
