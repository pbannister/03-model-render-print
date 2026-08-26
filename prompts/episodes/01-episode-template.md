# Episode Template

- Copy this file into `prompts/episodes/` with the next free number.
- Replace every `<placeholder>` with concrete content.
- Remove the Filled Example section before dispatching the episode.
- Follow `prompts/how-to-write-episodes.md`.

[EPISODE]
<One sentence stating the single goal of the episode.>

[ACCEPTANCE]
- <Is the first criterion satisfied?>
- <Is the second criterion satisfied?>
- <Is the episode reviewable in one sitting?>

[RISK]
- <Riskiest assumption, phrased as a question?>
- <Next riskiest assumption, phrased as a question?>

[SUB-TASKS]
- <One bounded step>.
- <One bounded step>.

[OUTPUT FORMAT]
<The response representation.>

[FILES]
- `<repository-relative path>` — new
- `<repository-relative path>` — existing

[BRANCH]
llm/episode-<number>

## Filled Example

This example shows the worked Site Build feature as an episode.

It is illustrative; it is not dispatched as-is.

[EPISODE]
Implement the Site Build feature from `prompts/features/01-site-build.md`.

[ACCEPTANCE]
- Does `scripts/site-build.sh` generate `site.out/` from `site.in/`?
- Does `make test` pass from the repository root?
- Is the diff reviewable in one sitting?

[RISK]
- Is `sh` available in the target environment?
- Do the tests avoid generated output in source directories?

[SUB-TASKS]
- Create `scripts/site-build.sh`.
- Create `site.in/hello.txt`.
- Add tests in `tests/`.
- Run `make test`.

[OUTPUT FORMAT]
Report the created files and the result of `make test`.

[FILES]
- `scripts/site-build.sh` — new
- `site.in/hello.txt` — new
- `tests/01-site-build.sh` — new

[BRANCH]
llm/episode-01
