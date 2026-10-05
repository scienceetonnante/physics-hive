# PhysicsIntern

PhysicsIntern is a method for using AI coding agents (Claude Code, OpenAI Codex CLI, OpenCode, Pi) to do research in theoretical physics and mathematics. A lead scientist states the question and what counts as done. Agents then work in bounded sessions: they read the literature, derive and compute in sub-agents that start from a fresh context, review every result blindly, and record results as small files called **cards**. Scripts compute each card's status and evidence, so that every result can be traced to who produced it, how, and with which version of the method.

A workspace is either **local** (one person, one machine, a git repository) or a **shared space** on the Hugging Face Hub, private by default, where several people and many agents work on the same problem:

- **Leads** own the question (`problem.md`), the strategy (`plan.md`) and the conventions, and are the only ones who mark a claim as *established*.
- **Operators** run agent sessions from their terminal, each with the harness and model of their choice. Each session ends in a pull request that merges on its own.
- **Reviewers** use only a browser: in the project's private Space they read results, react, write question and claim cards, verify claims, and ask an explainer chat.

> **Working on the method itself?** See [DOCUMENTATION.md](DOCUMENTATION.md): render pipeline, workspace format, scripts, Hub operations, authoring contracts and the audit workflow.


## Prerequisites

- **git** and **[uv](https://docs.astral.sh/uv/)** (`curl -LsSf https://astral.sh/uv/install.sh | sh`, or `brew install uv`). The scripts run through uv with their dependencies declared inline; nothing else needs installing by hand.
- At least one harness: **[Claude Code](https://claude.com/claude-code)** (`claude`), **[Codex CLI](https://github.com/openai/codex)** (`codex`), **[OpenCode](https://opencode.ai)** (`opencode`) or **[Pi](https://pi.dev)** (`pi`).
- For a shared space: a Hugging Face account, membership of the organisation that will own the project, and `hf auth login` on each operator's machine. Private repositories under a personal account cannot be shared, so a team needs one organisation (one per team, not per project).
- Optional: `SEMANTIC_SCHOLAR_API_KEY`, which raises the rate limit of the citation lookups for papers outside INSPIRE.


## Quick start (local)

```bash
git clone <this repo> physics-intern
./physics-intern/init-physics-intern.sh
```

The script asks what to do (start a local workspace, create a shared space, or join one), which harnesses you will use on this machine (a tick list, with the installed ones ticked), and where (the current folder by default). Then:

1. Write the question and its definition of done in `problem.md`, and 5 to 10 seed papers in `literature/seeds.md` if you have them. Both are free text. You can also ask the coordinator to write them with you.
2. Launch your harness in the workspace folder (`claude`, `codex`, `opencode` or `pi`).
3. Run **`/session-run`** (in Codex, `$session-run`). The coordinator proposes a brief; you adjust and confirm it; it works on its own until a stop condition and writes a report.

For a benchmark problem whose shape is known in advance, `/autoresearch` runs the whole pipeline (survey, plan, derive and review, finalize) in one session without stopping for you.

Every question of the init script also has a flag, for scripts and the plugin bootstraps:

```bash
./init-physics-intern.sh --mode local --harness claude,opencode --dir ../my-problem --yes
```

Run it again inside a workspace to add a harness or refresh the rendered files (`--harness codex`), or with `--upgrade` to replace the workspace's copy of the method with a newer one.


## Shared spaces on the Hub

**Create** (a lead, once):

```bash
./init-physics-intern.sh --mode create --org our-lab --name x-correction
```

This creates the local workspace, the private dataset repositories `our-lab/x-correction` (the research files), `-traces`, `-sources` and `-chat-debug`, and the private Space `our-lab/x-correction-space`; it pushes the first commit and prints the line to send to collaborators. The creator is the first lead (`[people] leads` in `project.toml`).

**Join** (every operator, once per checkout):

```bash
./init-physics-intern.sh --mode join --repo our-lab/x-correction
```

This clones the workspace and renders the harness files you selected from the workspace's own copy of the method, so that every operator and the Space run exactly the same prompts and scripts. Harness files are personal: they are git-ignored, and only research content and the method copy are shared.

**What happens in a session.** `/session-run` claims a session by opening a draft pull request; its number is the session number (`S12`). It puts your checkout on the branch `session/S12`, lists what is waiting (open questions, cards that need a re-check, reactions and cards written by people, plan-change proposals, other open sessions), and proposes a brief. You confirm it; this is the only step that needs your attention. The session then works on its own within its budget (20 dispatches by default) and stops when the goal is reached, the budget is spent, four dispatches pass without progress, or the work shows that `problem.md` should change. At the end, `session.py end` checks the workspace, pushes the branch, uploads the trace, and merges the pull request, rebasing on `main` first if other sessions merged in the meantime.

**What needs a lead.** A merge adds cards, artefacts, reviews and a report; it makes nothing established by itself. Promotion to *established* is a separate, recorded decision by a lead, made from the Space or with `uv run .physics-intern/scripts/promote.py <card>`. The lead's files (`problem.md`, `plan.md`, `conventions.md`, `literature/seeds.md`) change only by a lead's own edit or by a pull request a lead merges; `/research-plan` drafts plan proposals as such pull requests. To push their own edits from a terminal, leads can use `uv run .physics-intern/scripts/hubgit.py push origin main` (git with the Hub token, nothing stored).

**The Space** is where reviewers work: an overview of the question, the strategy and the active sessions; the results with their computed status and evidence and equations rendered; the literature with triage; the session reports with their proposals; the queue of open questions; reactions, question and claim cards, human verifications and, for leads, promotions; an editor for the lead's files; and an explainer chat that answers from the project's files, cites them, and can turn an unanswered question into a question card for the agents.


## Plugins

Each harness also has an installable bootstrap that asks the init questions in the chat and runs the same script:

- **Claude Code**: `/plugin marketplace add huggingface/physics-intern-claude-plugin`, then `/plugin install physics-intern@physics-intern-claude`; run `/init-physics-intern` in an empty folder.
- **Codex CLI**: `codex plugin marketplace add huggingface/physics-intern-codex-plugin`, then `codex plugin add physics-intern@physics-intern-codex`; run `$physics-intern:init-physics-intern`.
- **OpenCode** (no marketplace): `git clone https://github.com/huggingface/physics-intern-opencode-plugin && cd physics-intern-opencode-plugin && ./install.sh`; run `/init-physics-intern`.

After the bootstrap, restart the harness in the workspace folder so that the workspace's skills and agents load.


## Harness notes

- **Claude Code** reads `CLAUDE.md`, a one-line import of `AGENTS.md`. Skills are slash commands.
- **Codex CLI** reads `AGENTS.md`; skills are `$name`. Accept the project-trust prompt on first launch, otherwise `.codex/config.toml` (which allows the network access the session scripts need) is ignored.
- **OpenCode** reads `AGENTS.md`; skills are slash commands. Dispatching custom sub-agents has depended on the OpenCode version ([opencode #29616](https://github.com/anomalyco/opencode/issues/29616)); `AGENTS.md` explains the fallback.
- **Pi** reads `AGENTS.md`; skills are slash commands from `.pi/prompts/`. It installs `pi-subagents` and `pi-web-access` on first launch.

A workspace rendered for several harnesses opens in any of them without running anything again. `AGENTS.md` holds the method and one short section per harness.


## What a workspace looks like

```
problem.md            question, definition of done, sanity checks (lead's file)
plan.md               current strategy (lead's file)
conventions.md        notation, units, signs (lead's file)
project.toml          method version, Hub repositories, leads, chat model
.physics-intern/      copy of the method: prompts, renderer, scripts, Space app
claims/               one card per claim, question or dead end
derivations/          D-S12-3.summary.md (one page) + D-S12-3.tex (full LaTeX) + reviews
computations/         C-S12-1.md (one page) + .py + .out + reviews
critiques/            strategic critiques
literature/           seeds.md, one card per paper (P-<arXiv id>.md), one survey summary per session
sessions/S12/         brief.md, log.md, report.md
feedback/             reactions, human verifications, promotion records
answer.md, write-up/  the final answer and the LaTeX write-up
INDEX.md              generated: one line per item with its status and evidence (git-ignored)
research_log.md       generated: claims grouped by status, then the session reports (git-ignored)
```

**Cards.** A claim, question or dead end is one file in `claims/` with a small YAML header and a free prose body. A card never changes after it is created; everything that happens to it later is a new file that names it (an artefact that supports it, a review, a human verification, a promotion record, a dead end that refutes it, a claim that supersedes it). The scripts compute each claim's status (`working`, `established`, `refuted`, `revised`) and evidence, and flag as *needs re-check* every card that depends on a refuted or revised one. IDs embed the session number (`CL-S12-2`), so parallel sessions never collide and their pull requests never conflict.


## Skills

| Skill | What it does |
|---|---|
| `/session-run` | Runs one session: start, a brief you confirm, autonomous work within a budget, report, end (and merge, in shared mode). |
| `/survey` | Literature: expands from the seed papers along citations (INSPIRE, arXiv), writes paper cards and a survey summary. Usable in any session. |
| `/research-plan` | Drafts the strategy: `plan.md` in local mode, a proposal pull request for the lead in shared mode. |
| `/derive <target>` | Analytical derivation in LaTeX with a one-page summary, by a fresh-context sub-agent. |
| `/compute <target>` | Symbolic and numerical computation (SymPy, NumPy), with both paths compared. |
| `/review <artefact>` | Blind, test-based review: dimensions, limits, symmetries and spot checks first, then located remarks with a severity. |
| `/critique` | Strategic critique of the overall state. |
| `/finalize` | Writes `answer.md` from the established claims, at the end of the project. |
| `/write-up` | Assembles the established claims into a LaTeX document compiled to PDF, each statement naming its card. |
| `/autoresearch` | Local mode: the whole pipeline in one session, without stopping for you; for benchmark runs. |

## Scripts

The deterministic work is done by scripts in `.physics-intern/scripts/`, which the skills call with `uv run`: `regen.py` (rebuild the generated views), `check.py` (validate cards, references, immutability and the promotion rule), `session.py` (start, status, next ID, brief, end, abort), `promote.py`, `propose.py`, `export_trace.py`, `literature.py` (arXiv and INSPIRE search, citations, sources; also an MCP server), and `hubgit.py`.


## Limitations and next steps

- Agents run only on operators' machines; nothing runs agents in the cloud or from the Space.
- Shared spaces are private; there are no public spaces.
- Model diversity between authors and reviewers is not enforced. Every card and trace records the models used, and the reviewer benchmark (`bench/reviewer/`) measures how often each reviewer configuration catches planted errors and raises false alarms, which will tell whether the rule should come back.
- Trace export is complete for OpenCode and Claude Code, best effort for Codex and Pi.
- Existing workspaces in the earlier format keep working with their own rendered files; they are not converted. Migrating cards when the card format itself changes is not designed yet.
- A Mathematica backend for licence holders, as a second symbolic engine next to SymPy, is not implemented.
