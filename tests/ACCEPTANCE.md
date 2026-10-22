# Acceptance tests of the build plan

The build plan of `design/DESIGN-shared-spaces.md` (section 13) ends each phase with an acceptance test. This file says, for each one, how it is checked: by the automated suite, by the live Hub test, or by a run that needs real agents and accounts, with the steps for that run.

Automated suite: `uv run --no-project --with pytest --with httpx --with-requirements space/requirements.txt --with "mcp>=1.12,<2" pytest -q tests/`. Live Hub test: `uv run tests/hub_e2e.py` (needs `hf auth login`; creates and then deletes private scratch repositories under your account).

## Phase 1 — workspace format and session driver (local)

| Test | How it is checked |
|---|---|
| Refuting one claim marks all its dependents as *needs re-check* in `INDEX.md` | Automated: `test_cards.py::test_refutation_marks_all_dependents`. |
| Deleting and regenerating the views gives identical files | Automated: `test_cards.py::test_regeneration_is_deterministic`. |
| A workspace rendered for two harnesses opens in both without re-rendering, and OpenCode shows each skill once | Rendering is automated (`test_local_flow.py`: `AGENTS.md` holds both sections, both harnesses' files exist, adding a third keeps them). OpenCode's skill list was checked with `opencode debug skill` on a workspace rendered for Claude Code, Codex and OpenCode: each skill once, identical bodies. **On your side:** open the same workspace in two harnesses and run `/session-run` in each. |
| A full local `/autoresearch` run completes on the new format, promotes claims and writes `answer.md` | **On your side** (needs a model run). See below. |
| A `/session-run` whose brief is not a plan item (re-check a claim after a planted refutation) completes, stops on its own, and writes a report | **On your side**. See below. |

**Running the two agent tests.**

1. `./init-physics-intern.sh --mode local --harness claude,opencode --dir /tmp/toy --yes`, then write a small problem with a known answer in `/tmp/toy/problem.md` (for instance the period of a pendulum to second order in the amplitude, or one of the validated benchmark problems in `problems/validated/`), and commit it.
2. Launch a harness in `/tmp/toy` and run `/autoresearch`. Expect: a session folder `sessions/S1/` with a brief, a log with numbered dispatches and a `## Decisions taken without the operator` section, cards in `claims/`, LaTeX derivations with summaries, computations, reviews named `<artefact>_R-S1-<k>.md`, promotion records in `feedback/` (by an agent), `answer.md`, and `uv run .physics-intern/scripts/check.py` passing.
3. Plant a refutation by hand: write `claims/DE-<you>-20261005T120000.md`, a dead-end card with `id` matching the file name, `refutes: [<an established claim>]`, `produced_by: {kind: human, user: <you>}` and `session: null` (copy the rest of the header from another card), commit it, and run `uv run .physics-intern/scripts/regen.py`: the claim shows as refuted and its dependents as *needs re-check*.
4. Run `/session-run` and give as goal: "re-check the cards flagged needs re-check". Expect a brief you confirm, autonomous work, a stop on one of the four conditions, a report with the required sections, and `session.py end` passing.
5. Audit both sessions with the `investigate-run` skill.

## Phase 2 — sessions and the Hub

| Test | How it is checked |
|---|---|
| Hub behaviours (merge squashes; a rebased branch can be force-pushed to `refs/pr/<n>`) | Checked on scratch repositories before writing `session.py end`; recorded in DOCUMENTATION.md. |
| Two operators with two harnesses join one space and run sessions with overlapping briefs in parallel (both add evidence to the same claim); both pull requests merge without conflict and `INDEX.md` lists both pieces of evidence | Live: `tests/hub_e2e.py` (two checkouts on one machine, agents' work simulated by the script). **On your side:** the same with real agents, on two machines. |
| A promotion recorded by the lead with the script shows the claim as established; one by a non-lead is refused | Live: `tests/hub_e2e.py` (the non-lead is simulated by changing `leads`). **On your side:** with a second account. |
| Every claim leads to the trace that produced it | Cards record their session; `traces/S<n>/meta.json` and `trace.jsonl` are uploaded at the end of each session (checked live, with an empty trace since no harness ran). **On your side:** after a real session, check that `trace.jsonl` holds the conversation. |

## Phase 3 — review

| Test | How it is checked |
|---|---|
| No reviewer brief contains authorship information | By construction: `/review` passes the claim's statement, never the card's path, model or operator. The `investigate-run` audit checks every reviewer dispatch for leaks. |
| The benchmark reports catch and false-alarm rates for at least two models | **On your side:** `uv run bench/reviewer/run.py` (see `bench/reviewer/README.md`; real runs call models). The pipeline is tested in dry-run mode by `tests/test_reviewer_bench.py`. |

## Phase 4 — the Space

| Test | How it is checked |
|---|---|
| A browser-only reviewer reads a result, reacts, writes a question card and a claim card; a member verifies a claim and a lead promotes it; the reaction, the question and the new card appear in the next session's brief; the promoted claim shows as established | The backend (every write, the promotion rule, card views, chat tools) is tested in local mode by `tests/test_space_backend.py`. Deployment was checked live: `init --mode create` deploys the Space, which builds and reaches the RUNNING stage on the Hub and serves its page. Sign-in, the writes from a browser and the chat were not exercised. **On your side:** create a shared space (the Space is deployed by `init --mode create`), sign in as a reviewer and as a lead, do each action, then run `session.py start` and check the waiting list. |

## Phase 5 — literature

| Test | How it is checked |
|---|---|
| From five seed papers, `/survey` produces triage-ready cards, and triage decisions visibly change the next survey | The tools are tested live by hand and offline by `tests/test_literature.py`. **On your side:** put five arXiv identifiers in `literature/seeds.md`, run a session whose brief is the literature, triage the paper cards in the Space, and run a second survey. |

## Phase 6 — calibration run

With the lead scientist, on a problem whose answer they know from unpublished notes. Entirely on your side.
