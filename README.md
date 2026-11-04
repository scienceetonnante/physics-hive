# PhysicsIntern

PhysicsIntern is a method for using AI coding agents (Claude Code, OpenAI Codex CLI, OpenCode, Pi) to do research in theoretical physics and mathematics. It is modelled on how a theoretical physicist works with a student: the researcher sets the goal and the next steps; agents work in bounded sessions of a few hours; each session comes back with a short LaTeX note and a one-page debrief; the researcher answers in the debrief; and a shared LaTeX draft holds what the researcher decided to keep.

Behind that human view, agents keep a complete **record**: they read the literature, derive and compute in sub-agents that start from a fresh context, review every result blindly, and record results as small files called **cards**. Scripts compute each card's status and evidence, so that every result can be traced to who produced it, how, and with which version of the method. The researcher is never asked to read the record; notes and the draft link into it for anyone who wants to check a step.

A workspace is either **local** (one machine, a git repository) or a **shared space** on the Hugging Face Hub, private by default, where the researcher reads and answers in a browser while the agents run in a terminal. By default one person is both the researcher, in the browser or an editor, and the operator, in the terminal.

> **Working on the method itself?** See [DOCUMENTATION.md](DOCUMENTATION.md): render pipeline, workspace format, scripts, Hub operations, authoring contracts and the audit workflow. The design is in `design/DESIGN-shared-spaces.md`.


## Prerequisites

- **git** and **[uv](https://docs.astral.sh/uv/)** (`curl -LsSf https://astral.sh/uv/install.sh | sh`, or `brew install uv`). The scripts run through uv with their dependencies declared inline; nothing else needs installing by hand.
- At least one harness: **[Claude Code](https://claude.com/claude-code)** (`claude`), **[Codex CLI](https://github.com/openai/codex)** (`codex`), **[OpenCode](https://opencode.ai)** (`opencode`) or **[Pi](https://pi.dev)** (`pi`).
- Optional, to compile the draft and the notes to PDF on your machine: a TeX distribution with `latexmk` (TeX Live or MacTeX). The Space compiles them itself.
- For a shared space: a Hugging Face account, membership of the organisation that will own the project, and `hf auth login`. Private repositories under a personal account cannot be shared, so a team needs one organisation (one per team, not per project).
- Optional: `SEMANTIC_SCHOLAR_API_KEY`, which raises the rate limit of the citation lookups for papers outside INSPIRE.


## Quick start (local)

```bash
git clone <this repo> physics-intern
./physics-intern/init-physics-intern.sh
```

The script asks what to do (start a local workspace, create a shared space, or join one), which harnesses you will use on this machine (a tick list, with the installed ones ticked), and where (the current folder by default). Then:

1. In `project.md`, write the question in one line as the title, and the goal under *Goal*; the other sections can wait. List a few seed papers in `literature/seeds.md` if you have them. You can also dictate them to the coordinator.
2. Launch your harness in the workspace folder (`claude`, `codex`, `opencode` or `pi`).
3. Run **`/session-run`** (in Codex, `$session-run`). The coordinator proposes a brief, by default the first next step of `project.md`; you adjust and confirm it; it works on its own until a stop condition, then writes its note (`sessions/S1/note.tex`) and its debrief (`sessions/S1/debrief.md`).
4. Read the note, and answer the debrief in your editor: write under each `> **Answer:**`, tick the lines you accept (`- [x]`), and add anything under `> **Note:**`. Run `/session-run` again: the next session applies what you ticked before anything else.

To read the notes and the draft rendered, and answer debriefs in a browser, run the Space on your folder: `cd .physics-intern/space && PHYSICS_INTERN_LOCAL=../.. PHYSICS_INTERN_LOCAL_USER=<you> uv run --with-requirements requirements.txt uvicorn app:app`. To compile them to PDF: `uv run .physics-intern/scripts/pdf.py` (the draft) or `pdf.py S3` (a note).

For a benchmark problem whose shape is known in advance, `/autoresearch` runs the whole pipeline (survey, plan, derive and review, draft, finalize) in one session without stopping for you.

Every question of the init script also has a flag, for scripts and the plugin bootstraps:

```bash
./init-physics-intern.sh --mode local --harness claude,opencode --dir ../my-problem --yes
```

Run it again inside a workspace to add a harness or refresh the rendered files (`--harness codex`), or with `--upgrade` to replace the workspace's copy of the method with a newer one. Workspaces of method 0.3 (with `problem.md` and `plan.md`) are not upgraded to 0.4; they keep working on their own method copy.


## The researcher's files

| File | What it is | Who changes it |
|---|---|---|
| `project.md` | The question in one line as its title, then *Goal*, *Approach*, *Next steps*, *Done*, *Definition of done*, and the question in full | You. Agents only apply a line you ticked, and move the step their session finished to *Done*. |
| `conventions.md` | Notation, units, sign conventions | You and the agents; every change an agent makes appears as a diff in its debrief. |
| `draft.tex` | The best current state of the research, as a draft paper | You. Agents copy into it only what you tick, or edit it when a next step asks them to. |
| `sessions/S<n>/note.tex` | What session S<n> found, in two to four pages of LaTeX | A fresh writer agent. |
| `sessions/S<n>/debrief.md` | What session S<n> asks of you: a summary, *Changed by this session*, questions, tick lines, a note box | The session, then you. |
| `literature/overview.md`, `seeds.md`, `ratings.yaml` | The field in a few paragraphs; your seed papers; your rating of papers | Surveys write the overview; you write the seeds and the ratings. |

**How decisions flow.** You never ask the agents for anything in the middle of their work. You answer the latest debrief, tick its lines, and write in its note box, in an editor or in the Space; you may also edit `project.md`, `conventions.md` or the draft directly. The next `session.py start` prints, and records in `sessions/S<n>/received.md`, everything you wrote since the previous session started; the session applies the ticked lines first, asks you any question you left unanswered, and then proposes its brief. An unticked line is not applied. An unanswered question that still matters is asked again in the next debrief.

**What "established" means.** A claim is *established* when a `result` environment of `draft.tex` names its card (`\card{CL-S2-1}`). Only you decide what enters the draft, by ticking a line such as "Copy Result 1 of note S2 into the draft, as a result" or by editing it. `check` refuses a result whose claim has no confirming review of a supporting derivation or computation (or a verification by you, which you report in a debrief); such a claim goes in a `conjecture` environment instead.


## Shared spaces on the Hub

**Create** (once):

```bash
./init-physics-intern.sh --mode create --org our-lab --name x-correction
```

This creates the local workspace, the private dataset repositories `our-lab/x-correction` (the research files), `-traces`, `-sources` and `-chat-debug`, and the private Space `our-lab/x-correction-space`, and pushes the first commit.

**Join** (once per checkout, for a second machine or a second operator):

```bash
./init-physics-intern.sh --mode join --repo our-lab/x-correction
```

This clones the workspace and renders the harness files you selected from the workspace's own copy of the method, so that every checkout and the Space run exactly the same prompts and scripts. Harness files are personal: they are git-ignored, and only research content and the method copy are shared.

**What happens in a session.** `/session-run` claims a session by opening a draft pull request; its number is the session number (`S12`). It puts your checkout on the branch `session/S12`, prints what you sent since the previous session started, applies your ticked lines, and proposes a brief. You confirm it. The session then works on its own within its budget (20 dispatches by default) and stops when the goal is reached, the budget is spent, four dispatches in a row add nothing, or the work shows that `project.md` should change. At the end, it writes the note and the debrief, and `session.py end` adds *Changed by this session* to the debrief from git, checks the workspace, pushes the branch, uploads the trace, and merges the pull request. A merge adds to the record and endorses nothing: what you endorse is what is in the draft.

**The Space** shows your files, one kind per page, each with an editor. *Latest* (the first page) shows the debriefs, newest first: the open ones in full, as forms where you answer, tick and write a note; the ones a session has read, folded to one line; and what the next session will receive. *Project* shows `project.md` and `conventions.md`. *Draft* shows `draft.tex` rendered like an arXiv HTML paper (contents, numbered sections and equations, results, footnotes, references), with an editor beside a preview, and the PDF. *Sessions* lists the sessions; each opens its note, rendered the same way. *Literature* shows the overview, then the papers by topic with their one-line reason, and a menu to rate each one. Saving commits to `main` with the Space's token and names you in the commit. The Space applies nothing: ticked lines are applied by the next session. The session record (cards, artefacts, reviews, logs) has its own pages, reached from the notes, the draft and the Sessions page.

To push your own edits from a terminal, use `uv run .physics-intern/scripts/hubgit.py push origin main` (git with the Hub token, nothing stored).


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
project.md            the question, goal, approach, next steps, done steps, definition of done (yours)
conventions.md        notation, units, signs
draft.tex             the draft paper (yours); references.bib is generated from the paper cards
project.toml          method version, Hub repositories, people
.physics-intern/      copy of the method: prompts, renderer, scripts, templates, Space app
sessions/S12/         received.md, brief.md, log.md, note.tex (for you), debrief.md (for you to answer)
claims/               one card per claim or dead end
derivations/          D-S12-3.summary.md (one page) + D-S12-3.tex (full LaTeX) + reviews
computations/         C-S12-1.md (one page) + .py + .out + reviews
critiques/            strategic critiques
literature/           overview.md, one card per paper (P-<arXiv id>.md), seeds.md, ratings.yaml
answer.md             the final answer, at the end of the project
INDEX.md              generated: one line per card, artefact, paper and session (git-ignored)
```

**Cards** are the record of results. A claim is one assertion about the physics, in one sentence, that a derivation or a computation can check; a dead end records an obstacle or a refutation. A card can be corrected during the session that wrote it and never changes afterwards; everything that happens to it later is a new file that names it (an artefact that supports it, a review, a dead end that refutes it, a claim that supersedes it). The scripts compute each claim's status (`working`, `established`, `refuted`, `revised`) and evidence, and flag as *needs re-check* every card that depends on a refuted or revised one. IDs embed the session number (`CL-S12-2`), so parallel sessions never collide.


## Skills

| Skill | What it does |
|---|---|
| `/session-run` | Runs one session: start, apply your ticked lines, a brief you confirm, autonomous work within a budget, note and debrief, end (and merge, in shared mode). |
| `/survey` | Literature: expands from the seed papers and the papers you rated high, along citations (INSPIRE, arXiv), writes paper cards and updates the overview. Usable in any session. |
| `/research-plan` | Drafts an approach and next steps, which the session offers you as tick lines. |
| `/derive <target>` | Analytical derivation in LaTeX with a one-page summary, by a fresh-context sub-agent. |
| `/compute <target>` | Symbolic and numerical computation (SymPy, NumPy), with both paths compared. |
| `/review <artefact>` | Blind, test-based review: dimensions, limits, symmetries and spot checks first, then located remarks with a severity. |
| `/critique` | Strategic critique of the overall state. |
| `/finalize` | Writes `answer.md` from the results in the draft, at the end of the project. |
| `/autoresearch` | Local mode: the whole pipeline in one session, acting for you; for benchmark runs. |

## Scripts

The deterministic work is done by scripts in `.physics-intern/scripts/`, which the skills call with `uv run`: `regen.py` (rebuild `INDEX.md` and `references.bib`), `check.py` (validate cards, references, immutability, the draft's results, notes and debriefs), `session.py` (start, status, next ID, record an answer or a tick given in the terminal, brief, end, abort), `pdf.py` (compile the draft or a note), `export_trace.py`, `literature.py` (arXiv and INSPIRE search, citations, sources; also an MCP server), and `hubgit.py`.


## Limitations and next steps

- Agents run only on the operator's machine; nothing runs agents in the cloud or from the Space.
- Shared spaces are private; there are no public spaces.
- One researcher by default. The file format supports more people (IDs embed the session, every item is its own file), and colleagues can be added later; the Space records who wrote what in its commits.
- The Space's *Ask* page (a read-only assistant that answers questions about the project) is not built yet.
- Model diversity between authors and reviewers is not enforced. Every card and trace records the models used, and the reviewer benchmark (`bench/reviewer/`) measures how often each reviewer configuration catches planted errors and raises false alarms.
- Trace export is complete for OpenCode and Claude Code, best effort for Codex and Pi.
- Workspaces in earlier formats keep working with their own method copy; they are not converted.
