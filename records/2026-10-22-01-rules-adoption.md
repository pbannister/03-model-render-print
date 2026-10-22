# Record: Adopt the shared rules

## Outcome

This project now pins the shared rules at `2026-10-22.12`. `rules.lock` holds the
version and a SHA-256 per vendored file, `scripts/rules-check.sh` verifies the
copy, and `tests/07-rules-pin.sh` runs it in the suite.

The adoption was `breaking`: the contract gains a non-overridable safety
precedence level, modification becomes authorization-based, and nine capability
conventions apply. Conformance cleared 50 findings across two features and two
tasks.

## Decisions

- **External inputs left the feature graph.** `03-stl-tiles.md` listed its real
  dependencies — GDAL, `osgeo`, `numpy`, the ETOPO tiles under `/datasets`, and
  the `model-elevation-earth` project — under `## Dependencies`, which the
  validator reads as *feature* dependencies and rejects anything else. Those five
  moved to a new `## External Inputs` section, and `## Dependencies` now says
  `None.` The requirement graph must stay a graph of features; a toolchain and a
  dataset volume are not features, and pretending otherwise would have been a
  dependency edge the validator could not check.
- **Both features needed identifiers only.** `SITE-BUILD-R001`–`R010` and
  `STL-TILES-R001`–`R015`, on the existing requirement sentences, wording
  unchanged.
- **One task needed rewriting rather than transforming.** Its bullets carried the
  verb inside the backticks — `` - `create scripts/stl-tiles-build.sh` `` — so a
  mechanical transform read "create scripts/…" as the path. All seven files
  already exist, so every operation is `modify`. The section order was also wrong
  (`TASK-CONTEXT` and `TASK-FILES` before `TASK-OUTPUT`), and `OUTPUT:` restated
  the mangled path.
- **`PHASES.md` is declared** in `prompts/10-project.md`.
- **Deleted three stale `common/` files** and pointed the glossary's DELTA entry
  at contract section 6.

## Verification

- `rules-conform`: nothing to conform.
- `rules-check`: ok (v2026-10-22.12, 39 files, 0 deviations).
- `make test`: 11 tests, all passed.

## Behavioral evidence

**Not run.** The six eval cases need `scripts/status.sh` or
`scripts/site-state-fetch.sh`; this project has the latter but not the former, so
`06-credential-boundary` is the only case with a chance of applying, and it was
not run. The portability gap is recorded in
`00-project-rules/documents/eval-portability.md`.

## What this adoption cost the library

Nothing — the third consecutive adoption to need no shared-rules change.

One tooling observation, not a defect: the ad-hoc task transform used for the
last four projects does not understand bullets that carry the verb inside the
backticks. It produced a syntactically valid but meaningless table, which the
validator could not catch because it only checks that the table and the operation
lines agree. If the transform is ever promoted to a shipped tool, that form needs
handling first.

## Commits

- Adoption commit — the vendored rules, conformance, and this record.
