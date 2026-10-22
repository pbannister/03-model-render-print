# Feature: Site Build

## Purpose

The project contains a static-site input directory (`site.in/`) and a generated static-site output directory (`site.out/`).

The Site Build feature provides the script that converts `site.in/` into `site.out/`.

## Requirements

- `SITE-BUILD-R001` — `scripts/site-build.sh` must generate the static site in `site.out/` from the input in `site.in/`.
- `SITE-BUILD-R002` — Each `site.in/*.txt` input file must produce `site.out/<name>.html`.
- `SITE-BUILD-R003` — Every non-`.txt`, non-`template.html` file under `site.in/` (authored assets such as scripts, styles, and images) must be copied verbatim into `site.out/`.
- `SITE-BUILD-R004` — Pages may contain `__KEY__` placeholders for live state; values come from the state file (`dataflow.out/site-state.txt` by default, overridable with `SITE_STATE_FILE`), written by `scripts/site-state-fetch.sh`. When the state file is absent, remaining placeholders render as "unavailable", so the build stays portable.
- `SITE-BUILD-R005` — Generated output must be identified as generated.
- `SITE-BUILD-R006` — The script must accept optional input and output directory arguments.
- `SITE-BUILD-R007` — When no arguments are given, the script must use `site.in/` and `site.out/` relative to the repository root.
- `SITE-BUILD-R008` — The script must be a POSIX shell script.
- `SITE-BUILD-R009` — The HTML page structure must live in `site.in/template.html`, not in the build script.
- `SITE-BUILD-R010` — `site.in/template.html` must contain the marker line `<!-- SITE-CONTENT -->` where page content is inserted.

## Behavior

- Running the script recreates `site.out/` from `site.in/` (pages and assets).
- Re-running the script overwrites existing output deterministically.

## Dependencies

- None.
