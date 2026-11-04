# Reviewer benchmark

This benchmark measures each reviewer configuration (a harness and a model, running the reviewer prompt of the current method) on two numbers:

- the **catch rate**: how often it refutes a derivation or computation that holds a planted error;
- the **false-alarm rate**: how often it refutes correct work.

It is the "measured reviewers" part of the review design (`design/DESIGN-shared-spaces.md`, section 8, and Phase 3 of section 13). Its results inform whether version 0 should later require a reviewer from a different model family than the author.

**A real run calls models and costs money.** Each review is a full agentic session that reads the artefact and runs its own checks, so it takes minutes and its cost depends on the model. The default `configs.toml` has 4 configurations and there are 12 cases, so a full run is 48 reviews. Start with `--dry-run`, then one case on one configuration, and look at the time and cost it reports before running more. For Claude Code, `--max-budget-usd` in a configuration's `args` caps the cost of each review.

## How it works

For each configuration in `configs.toml` and each case in `cases/`, `run.py`:

1. creates a fresh local workspace for that harness with `scripts/init.py --mode local --harness <h> --yes`, in a temporary folder with a neutral name;
2. writes the case's problem into `project.md`, and `conventions.md`, copies the artefact into `derivations/` or `computations/`, and commits, as a session would leave it (no claim card is written: the reviewer may not read `claims/`, and the card would need an invented author);
3. runs the harness non-interactively, in the workspace, with a prompt that tells it to act as the reviewer by following its rendered role file (`.claude/agents/reviewer.md`, `.codex/agents/reviewer.toml`, `.opencode/agents/reviewer.md` or `.pi/agents/reviewer.md`), followed by the dispatch that `/review` would send: the target, the statement of the claim, `supports: [CL-S1-1]`, the output path `<folder>/<artefact>_R-S1-1.md`, session `S1` and `conventions.md`. Nothing in the prompt or the workspace says who wrote the artefact, that it is a test, or which case it is;
4. reads the `verdict:` of the review file and its `## Remarks`, and scores them.

The role runs in the harness's main context rather than as a dispatched sub-agent, so the benchmark measures the model and the reviewer prompt, not the dispatch mechanics of each harness.

The exact harness commands, with their flags checked against each CLI's `--help`:

| Harness | Command (run in the workspace) |
|---|---|
| Claude Code | `claude -p --model <model> --permission-mode dontAsk --allowedTools "Read,Write,Edit,Glob,Grep,Bash(uv run:*),Bash(python:*),Bash(python3:*)" --output-format json <args> <prompt>` |
| Codex CLI | `codex exec --model <model> --sandbox workspace-write -c sandbox_workspace_write.network_access=true --cd <ws> <args> <prompt>` |
| OpenCode | `opencode run --model <provider/model> --dir <ws> --auto <args> <prompt>` |
| Pi | `pi -p --model <model> <args> <prompt>` |

A non-interactive run cannot answer permission prompts, and the reviewer must be able to run `uv run python` for spot checks (which fetches SymPy from PyPI) and write scratch scripts outside the workspace. That is why Claude Code gets an explicit allowlist (file tools and Python; anything else is denied without a prompt), Codex gets network access in its workspace sandbox, and OpenCode auto-approves (its workspace configuration already allows file and shell tools; `--auto` covers the rest, such as scratch files in `/tmp`); Pi does not ask. The workspace is a throwaway copy, but the reviewer does run with your user account, so read the logs of a first run. `<args>` are the optional extra arguments of the configuration. Claude Code's JSON output carries the cost of each review, which the runner adds up; the other harnesses do not report it.

## The cases

Six problems, each written twice: once correct and once with one planted error. The two versions are identical except for the error and its consequences, so that style does not give the planted one away, and each workspace holds only one of them. Every planted error changes the final result, so a correct reviewer should refute the claim.

| Pair | Field | Artefact | Planted error |
|---|---|---|---|
| `kapitza` | classical mechanics | derivation: stability of the inverted pendulum with an oscillating pivot | factor of two: the time average $\langle\cos^2\omega t\rangle = 1/2$ is dropped (Eq. 9), so the condition becomes $a^2\omega^2 > gl$ instead of $2gl$ |
| `anharmonic` | quantum mechanics | computation: ground-state energy of $x^4$ oscillator to second order | dropped term: an off-by-one loop omits the $k = 4$ intermediate state (line 27), giving $-9/4$ instead of $-21/8$ |
| `bouncer` | quantum mechanics | derivation: WKB levels of a particle bouncing on a hard floor | wrong limiting case: the hard wall is treated as a smooth turning point (Eq. 5), giving $n + 1/2$ instead of $n - 1/4$ |
| `sphere` | electromagnetism | derivation: force between a charge and an isolated neutral conducting sphere | dimensional inconsistency: a factor $R^2$ is lost when combining fractions (Eq. 9) |
| `square-well` | statistical mechanics | computation: second virial coefficient of the square-well gas | sign error: the well is set to $+\epsilon$ instead of $-\epsilon$ (line 21), shared by both numerical paths |
| `orbit-clock` | general relativity | derivation: clock rate on a circular Schwarzschild orbit | unjustified assumption: the coordinate speed is taken as the speed measured by a static observer (Eq. 8); the weak-field check still passes |

`verify_cases.py` checks the physics of every pair by a route independent of the artefact (SymPy derivations, numerical integration of the equations of motion, exact diagonalisation, Airy zeros, Christoffel symbols from the metric), and shows that each planted result fails the same check. Run it after editing or adding a case: `uv run bench/reviewer/verify_cases.py`.

## Running it

You need `uv`, git with a user name and e-mail, and each harness of the selected configurations installed and logged in, with access to the model named in `configs.toml`. Edit `configs.toml` to the models you want to compare; its comments say where the example identifiers come from.

```bash
uv run bench/reviewer/run.py --dry-run                                        # free: tests the pipeline
uv run bench/reviewer/run.py --config claude-opus --case kapitza-planted      # one real review
uv run bench/reviewer/run.py --config claude-opus --config opencode-glm --jobs 4
```

| Option | Effect |
|---|---|
| `--config LABEL` | run only this configuration (repeatable) |
| `--case NAME` | run only this case, by folder name (repeatable) |
| `--dry-run` | replace the harness call by a fake reviewer that refutes every planted case and confirms every correct one |
| `--keep` | keep the temporary workspaces, to inspect what the reviewer did; their paths are in the results |
| `--timeout SECONDS` | time allowed per review, default 1800; a review that runs out is killed and counted as missing |
| `--jobs N` | reviews run in parallel, default 1 |
| `--results-dir DIR` | where results go, default `bench/reviewer/results/` |

Pi installs its packages (`pi-subagents`, `pi-web-access`) in each fresh workspace on first launch, which adds time and needs network access.

## Reading the results

The runner prints one Markdown table per configuration:

- **Catch rate**: planted cases refuted, over planted cases with a valid review.
- **False-alarm rate**: correct cases refuted, over correct cases with a valid review.
- **Inconclusive**: `inconclusive` verdicts over all valid reviews. In the method, an inconclusive review triggers a second review, so it is neither a catch nor a pass.
- **No valid review**: reviews that are missing (the harness failed, timed out or wrote nothing), or malformed (no front matter, or a `verdict:` that is not one of the three words). They are left out of the rates and should be investigated, not ignored.

The per-case table gives the verdict, the outcome (`caught`, `missed`, `passed`, `false alarm`, `inconclusive`, `no review`), the number of remarks of each severity, and, for planted cases refuted with a *breaks the result* remark, whether one of those remarks points within one equation or three lines of the planted location. That last column is indicative only: a reviewer can find the error by a test without naming its line. A note flags a review written under another file name, or a `## Verdict` section that disagrees with the `verdict:` field.

Everything is also saved under `results/`: `<run>.json` holds the configurations, the summaries and one record per review, and the folder `<run>/<config>/` holds each harness log (the command, the prompt and the output) and a copy of each review file. Results are not committed: the rule `results/` of the repository's `.gitignore` covers this folder. That is deliberate, because every run writes there, dry runs included, and the logs are large and hold machine-specific temporary paths. To keep a run as evidence (for example the one that informs the decision on model diversity), add its JSON file with `git add -f`.

With 6 planted and 6 correct cases, one review more or less moves a rate by 17 points, and a model does not give the same review twice. Repeat a run before drawing conclusions, pool the JSON files, and do not read much into a difference of one or two cases. Some problems are textbook material (Kapitza's pendulum, the anharmonic oscillator); a reviewer that recognises the right answer from memory still catches the error, which is a fair outcome but makes those cases easier.

## Adding a case

1. Create two folders, `cases/<pair>-correct/` and `cases/<pair>-planted/`. Each holds the artefact files and a `case.toml`, and nothing else. A derivation is `D-S1-1.summary.md` and `D-S1-1.tex`; a computation is `C-S1-1.md`, `C-S1-1.py` and `C-S1-1.out` (plus data files `C-S1-1.<name>.csv` if needed). Follow the formats of `commons/agents/deriver.md` and `commons/agents/computer.md` exactly, with `supports: [CL-S1-1]`.
2. Write the correct version first and check it independently; add the check to `verify_cases.py`. Derivations should compile with `pdflatex`, and the equation numbers cited in the summary must match the compiled document. For a computation, produce the `.out` file by running the script as the computer role does: `uv run --with sympy --with numpy --with scipy python computations/C-S1-1.py 2>&1 | tee computations/C-S1-1.out`.
3. Derive the planted version from it by changing one step and carrying the consequences through, so that the artefact is self-consistent. The summary's sanity checks must be ones the planted error does not affect, as happens when an author misses an error. The error must change the final result.
4. Fill in `case.toml`. Both versions need `label` (`correct` or `planted`), `artefact`, `claim` (the statement of what the artefact obtains, as the coordinator would put it on the card; it differs between the two versions), `problem` and `conventions` (identical in both versions), and `pair` and `field`. The planted version also needs `error` (what was planted and why it matters), `error_kind`, `location` (an equation such as `Eq. (9)` or a line such as `C-S1-1.py, line 21`) and `severity` (`breaks the result` or `weakens it`).
5. Run the tests: `uv run --no-project --with pytest --with pyyaml pytest -q tests/test_reviewer_bench.py`. They check the folders, the pairing, that no artefact file contains the words "planted" or "benchmark", and a dry run over all cases.
