# Acceptance tests of the build plan

The build plan of `design/DESIGN-shared-spaces.md` (section 17) ends each phase of the revision with an acceptance test. This file says, for each one, how it is checked: by the automated suite, by the live Hub test, or by a run that needs real agents and accounts, with the steps for that run.

Automated suite: `uv run --no-project --with pytest --with httpx --with-requirements space/requirements.txt --with "mcp>=1.12,<2" pytest -q tests/`. Live Hub test: `uv run tests/hub_e2e.py` (needs `hf auth login`; creates and then deletes private scratch repositories and a Space under your account).

The tests of version 0.3.0 (re-check propagation, deterministic views, parallel sessions on the Hub, blind review, the reviewer benchmark) still hold and are still in the suite; they are not repeated here.

## Phase A — the human files, in local mode

| Test | How it is checked |
|---|---|
| Three local sessions where the researcher acts only by editing debriefs and `project.md` in a text editor; each decision is applied by the session after it | Automated, with the agents' work simulated: `test_local_flow.py::test_three_local_sessions_driven_by_debriefs`. It checks the start output of each session (answers, ticked and unticked lines, the note, the researcher's edits with line counts, the first next step, the previous handoff), that a debrief already read is not delivered again, that a question answered in the terminal is recorded as the researcher's, and *Changed by this session* in each debrief. **On your side:** the same with a real agent (below). |
| A result copied into the draft shows as established in `INDEX.md` | Automated: `test_local_flow.py` (after S2) and `test_cards.py::test_established_means_a_result_of_the_draft`. |
| A result without a confirming review is refused and offered as a conjecture | `check` refuses it: `test_local_flow.py` (S2), `test_cards.py::test_check_on_the_draft_blames_only_the_session`, and in the Space `test_space_backend.py::test_saving_the_researchers_files`. That the session then offers it as a conjecture in its debrief is the prompt's job (`/session-run` §2, AGENTS.md §8): **on your side**. |

**Running phase A with a real agent.**

1. `./init-physics-hive.sh --mode local --harness claude --dir /tmp/toy --yes`. In `/tmp/toy/project.md`, write a title and a goal for a small problem with a known answer (the period of a pendulum to second order in the amplitude, or one of `problems/validated/`). Do not commit.
2. `claude` in `/tmp/toy`, then `/session-run`. Expect: your edits committed as yours, a brief you confirm, autonomous work, `sessions/S1/note.tex` (compile it with `uv run .physics-hive/scripts/pdf.py S1`), and a one-screen `sessions/S1/debrief.md` with a few questions, tick lines and an empty note box; `check` passing at the end.
3. Answer the debrief in your editor: one answer, two ticks (one copying a reviewed result into the draft, one adding a next step), one note. Leave one question empty. Also edit `project.md`.
4. `/session-run` again. Expect: the start output lists exactly what you wrote; the coordinator asks your empty question and waits; it applies the ticks in one commit `[S2] apply the lines ticked in the S1 debrief`; the claim shows as `established` in `INDEX.md`; the debrief of S2 lists the changes under *Changed by this session*.
5. Tick a line that copies an unreviewed claim as a result. Expect S3 to copy nothing and offer it as a conjecture in its debrief.
6. Audit the three sessions with `investigate-run`.

## Phase B — the Space

| Test | How it is checked |
|---|---|
| The five pages, editing in place with commits to `main`, the LaTeX rendering, the PDF, the rating menu | Automated in local mode: `test_space_backend.py` (every page and form through a test client, the debrief form, the editors with the draft check, ratings), and the Hub store against a local git repository with a fake API (clone, worktrees, history, commits on the page's parent commit). The converter: `test_latex.py`, on a real note and a sample draft. The PDF: `test_human.py::test_the_templates_compile_to_pdf` compiles the draft and note templates (skipped where `latexmk` is missing; the Space image installs it). Live: `tests/hub_e2e.py` answers a debrief through the Space's backend on the real Hub, and checks that the next session receives the answer and the tick. |
| The helmholtz problem rerun from scratch, with the researcher answering only in the Space; every answer and tick appears in the next session's start output, and the researcher never opens a record page unless they choose to | **On your side** (below). |

**Running phase B.**

1. `./init-physics-hive.sh --mode create --org <your org> --name helmholtz-3`. Wait for the Space to build (it installs git and a small TeX Live), sign in, and write the title and goal of `project.md` on the *Project* page, and the seeds on the *Literature* page.
2. In the workspace folder, `/session-run`. When it ends, read the note on *Sessions*, answer the debrief on *Latest*, and check that *What the next session will receive* matches what you did.
3. `/session-run` again and compare its start output with that block. Check the *Draft* page and its PDF once a result is copied.
4. Note every time you needed a record page, and why.

## Phase C — literature

| Test | How it is checked |
|---|---|
| `overview.md`, the `why`, `topic` and `rating` fields, `ratings.yaml`, `references.bib` | Automated: the card skeleton and its order of fields (`test_literature.py::test_card_follows_the_surveyor_format`), search over the overview, `references.bib` and its stable keys (`test_cards.py`), ratings written by the Space and received by the next session (`test_space_backend.py::test_rating_papers`), the Literature page grouping papers by the overview's topics. |
| After rating a few papers, the next survey's choices visibly follow the ratings | **On your side:** put five arXiv identifiers in `literature/seeds.md`, run a session whose brief is the literature, rate a few papers high and one *not relevant* in the Space, run a second survey, and compare which papers it expanded from and added. |

## Then

A calibration run with a problem whose answer you know from unpublished notes; later the Ask page and colleagues. Entirely on your side.
