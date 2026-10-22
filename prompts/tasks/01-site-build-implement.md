# Task: Implement the Site Build feature

## TASK-DESCRIPTION
- Create: `scripts/site-build.sh`
- Create: `site.in/hello.txt`

Create `scripts/site-build.sh`.
The script generates `site.out/` from `site.in/`.
Create `site.in/hello.txt` with example input content.
Implement the requirements in `prompts/features/01-site-build.md`.
Run `make test` from the repository root.

## TASK-OUTPUT
Report the created files and the result of `make test`.

## TASK-CONTEXT
Feature requirements: `prompts/features/01-site-build.md`.
Conventions: `prompts/03-conventions.md`.
This task is the worked example for the project skeleton.

## TASK-FILES

| Operation | Path |
|---|---|
| create | `scripts/site-build.sh` |
| create | `site.in/hello.txt` |

## TASK-VERIFY
- Run: `make test` from the repository root.
- Expected: exit status 0.

## TASK-FEATURES
- `prompts/features/01-site-build.md`

## TASK-ACCEPTANCE
- `SITE-BUILD-R001`
- `SITE-BUILD-R002`
- `SITE-BUILD-R003`

OUTPUT: the content of `scripts/site-build.sh`, as TASK-OUTPUT describes, and nothing else.
