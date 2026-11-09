# PhysicsHive

PhysicsHive lets a small team of scientists use AI coding agents (Claude Code, OpenAI Codex CLI, OpenCode, Pi) to work together on one problem in theoretical physics or mathematics. The team and its agents share a **space** on the Hugging Face Hub: private repositories that hold the research, and a web app, the Space, where the researchers read what the agents found and answer them in a browser, while the agents run in a terminal.

The work is organised the way a theoretical physicist works with a student. The researchers set the goal and the next steps. Agents work on their own in bounded sessions of a few hours. Each session comes back with a short LaTeX note and a one-page debrief; the researchers answer in the debrief, and the next session starts from their answers. A shared LaTeX draft holds what the researchers decided to keep.

Behind these few files, agents keep a complete **record**: they read the literature, derive and compute in sub-agents that start from a fresh context, review every result blindly, and record results as small files called **cards**. Scripts compute each card's status and evidence. The researchers are never asked to read the record; notes and the draft link into it for anyone who wants to check a step.

A space stays private while the research is done. The record is kept so that, at the end of a project, it can be published with the results: the agent traces, the researchers' answers and decisions, the reviews, and for every result who produced it (which agent and model, or which person), how, and with which version of the method. There is no publishing step yet (see [Where the project is going](#where-the-project-is-going)).

The format is built for several people, but so far PhysicsHive has been used by one person at a time, who is both the researcher, in the Space, and the operator, who runs the sessions in a terminal.

PhysicsHive grew out of [Physics Intern](https://github.com/huggingface/physics-intern), in which agents work without anyone steering them: a problem goes in and an answer comes out. Physics Intern remains the tool for such autonomous runs; PhysicsHive is for research that people steer.

> **Working on the method itself?** See [DOCUMENTATION.md](DOCUMENTATION.md): render pipeline, workspace format, scripts, Hub operations, authoring contracts and the audit workflow. The design is in `design/DESIGN-shared-spaces.md`.


## Prerequisites

- **git**, and **[uv](https://docs.astral.sh/uv/)**, which runs the scripts with their dependencies; the installer offers to install uv if it is missing. Nothing else needs installing by hand.
- At least one harness: **[Claude Code](https://claude.com/claude-code)** (`claude`), **[Codex CLI](https://github.com/openai/codex)** (`codex`), **[OpenCode](https://opencode.ai)** (`opencode`) or **[Pi](https://pi.dev)** (`pi`).
- A Hugging Face account, and membership of the organisation that will own the space; the installer logs you in if needed. Private repositories under a personal account cannot be shared, so a team needs one organisation (one per team, not per project). To try a space alone, choose your own account as the owner. A [local workspace](#working-locally) needs no account.
- Optional, to compile the draft and the notes to PDF on your machine: a TeX distribution with `latexmk` (TeX Live or MacTeX). The Space compiles them itself.
- Optional: `SEMANTIC_SCHOLAR_API_KEY`, which raises the rate limit of the citation lookups for papers outside INSPIRE.


## Quick start

In the folder where you want the workspace:

```bash
curl -LsSf https://raw.githubusercontent.com/scienceetonnante/physics-hive/master/install.sh | sh
```

The installer checks for git and uv, downloads the latest release of PhysicsHive, and runs its init script; nothing stays installed, since the workspace keeps its own copy of the method. If you are not logged in to Hugging Face, it logs you in. It asks what to do (create a shared space, which is the default; join one; or start a local workspace), which harnesses you will use on this machine (a tick list, with the installed ones ticked), where (the current folder by default), and for a new space the owner (one of your organisations, or your own account to try alone) and the name. Last, it asks for the question of the project in one line and its goal (the question in full, and what would count as an answer), and writes them into `project.md`; you may leave either for later. A session needs both to start.

`create` makes the local workspace, the private dataset repositories `our-lab/physics-hive-x-correction` (the research files), `-traces`, `-sources` and `-chat-debug`, and the private Space `our-lab/physics-hive-x-correction` (the Hub keeps datasets and Spaces apart, so they share the name), and pushes the first commit. It prints the Space's own address (`https://our-lab-physics-hive-x-correction.hf.space`): opened there rather than on huggingface.co, the Space signs you in within the same tab. Then:

1. If you left the question or the goal for later, write them in the Space, on the *Project* page: the question as the title of `project.md`, the goal under *Goal*. Write them there rather than in the local folder, because a session refuses to start while the checkout has uncommitted changes. On the *Literature* page, list a few seed papers if you have them.
2. Launch your harness in the workspace folder (`claude`, `codex`, `opencode` or `pi`).
3. Run **`/session-run`** (in Codex, `$session-run`). The coordinator proposes a brief, by default the first next step of `project.md`; you adjust and confirm it; it works on its own until a stop condition, then writes its note and its debrief, and merges its work into the space.
4. In the Space, read the note (*Sessions*) and answer the debrief (*Review*): write under each question, tick the lines you accept, and add anything in the note box. Run `/session-run` again: the next session applies what you ticked before anything else.

Every question also has a flag, passed after `sh -s --`:

```bash
curl -LsSf https://raw.githubusercontent.com/scienceetonnante/physics-hive/master/install.sh | sh -s -- \
    --mode create --org our-lab --name x-correction --harness claude \
    --question "<the question in one line>" --goal "<the goal>" --yes
```

Inside a workspace, `uv run .physics-hive/scripts/init.py --harness codex` adds a harness or refreshes the rendered files, from the workspace's own copy of the method. To move a workspace to the latest release of the method, run the installer inside it with `--upgrade` (in a shared space, this opens a pull request; once you merge it, the Space switches to the new version at the next session start).

**Working on the method.** From a clone of this repository, run `./init-physics-hive.sh` instead of the installer. It takes the same options and uses the method as it is in your clone, uncommitted changes included. To try the unreleased `master` branch without a clone, set `PHYSICS_HIVE_VERSION=master` before `sh` in the installer's command.


## Shared spaces

**The Space** shows the researchers' files, one kind per page, each with an editor. The tabs are *Project*, *Review*, *Draft*, *Sessions* and *Literature*, under the project's name. *Project* shows `project.md` and `conventions.md`. *Review* (the page the Space opens on) shows the debriefs, newest first: the open ones in full, as forms where you answer, tick and write a note, each marked *Awaiting your response* until you do. A debrief starts with the session's findings, each with what supports it and whether it is in the draft, and keeps your response in a panel beside them; the ones a session has read are folded to one line. *Draft* shows `draft.tex` rendered like an arXiv HTML paper (contents, numbered sections and equations, results, footnotes, references), with an editor beside a preview, and the PDF. *Sessions* lists the sessions; each opens its note, rendered the same way. *Literature* shows the overview, then the papers by topic with their one-line reason, and a menu to rate each one. Saving commits to `main` with the Space's token and names you in the commit. A save takes a few seconds; the editors show when you have unsaved changes, ask before you leave them, and save with Ctrl+S (Cmd+S on a Mac), and the confirmation links to the commit. The Space applies nothing: ticked lines are applied by the next session. The session record (cards, artefacts, reviews, logs) has its own pages, reached from the notes, the draft and the Sessions page. On the Hub, the Space's card reads "[Physics Hive] x-correction" and shows the question of `project.md` (each session start updates it).

**What happens in a session.** `/session-run` claims a session by opening a draft pull request; its number is the session number (`S12`). It puts your checkout on the branch `session/S12`, prints what the researchers sent since the previous session started, applies the ticked lines, and proposes a brief. You confirm it. The session then works on its own within its budget (20 dispatches by default) and stops when the goal is reached, the budget is spent, four dispatches in a row add nothing, or the work shows that `project.md` should change. At the end, it writes the note and the debrief, and `session.py end` adds *Changed by this session* to the debrief from git, checks the workspace, pushes the branch, uploads the trace, and merges the pull request. A merge adds to the record and endorses nothing: what the researchers endorse is what is in the draft.

**Join** (once per checkout, for a second machine or a second operator):

```bash
curl -LsSf https://raw.githubusercontent.com/scienceetonnante/physics-hive/master/install.sh | sh -s -- --mode join --repo our-lab/physics-hive-x-correction
```

`create` prints this command with your repository.

This clones the workspace and renders the harness files you selected from the workspace's own copy of the method, so that every checkout and the Space run exactly the same prompts and scripts. Harness files are personal: they are git-ignored, and only research content and the method copy are shared. A colleague who only reads and answers needs no checkout: as a member of the organisation, they sign in to the Space.

**The Space's token.** The Space reads the workspace and saves your edits with its own copy of a token, the Space secret `HF_TOKEN`. By default `create` copies your login token there. To give new Spaces a dedicated token instead, set `PHYSICS_HIVE_SPACE_TOKEN=hf_...` in your shell profile (`export PHYSICS_HIVE_SPACE_TOKEN=hf_...` in `~/.zshrc`). When you work from a clone of this repository, the `.env` at its root also works (it is git-ignored, and read only by `./init-physics-hive.sh`). Do not put it in a `.env` file inside the workspace: the workspace is pushed to the Hub. Make it a fine-grained token (Hugging Face → Settings → Access Tokens) with only these permissions:

- in the section for the organisation that owns your projects: read and write access to the contents of all its repositories;
- *Make calls to Inference Providers*, for the Space's assistant once it exists.

If you rotate it, update the secret `HF_TOKEN` in each Space's settings; the variable only applies to Spaces created after it is set.

If you edit `project.md`, `conventions.md` or `draft.tex` in your checkout rather than in the Space, the next session start commits your edits as yours and pushes them to `main`; to publish them now, run `uv run .physics-hive/scripts/session.py save` (or ask the coordinator to). For other git commands against the Hub, `uv run .physics-hive/scripts/hubgit.py <git arguments>` runs git with your Hub token, without storing it.


## Working locally

A local workspace is a git repository on one machine, without the Hub: to try the method, or for work that will not be shared. Sessions work the same way, without pull requests.

```bash
curl -LsSf https://raw.githubusercontent.com/scienceetonnante/physics-hive/master/install.sh | sh -s -- --mode local
```

The script asks for the question and the goal, as for a shared space (or takes them from `--question` and `--goal`). If you left them for later, write them in `project.md` in your editor, or dictate them to the coordinator. Then run `/session-run`. Answer each debrief in your editor: write under each `> **Answer:**`, tick the lines you accept (`- [x]`), and add anything under `> **Note:**`. The next `session.py start` commits your edits as yours.

To read the notes and the draft rendered, and answer debriefs in a browser, run the Space on your folder: `cd .physics-hive/space && PHYSICS_HIVE_LOCAL=../.. PHYSICS_HIVE_LOCAL_USER=<you> uv run --with-requirements requirements.txt uvicorn app:app`. To compile them to PDF: `uv run .physics-hive/scripts/pdf.py` (the draft) or `pdf.py S3` (a note).


## The researchers' files

| File | What it is | Who changes it |
|---|---|---|
| `project.md` | The question in one line as its title, then *Goal*, *Approach* and *Next steps* | The researchers. Agents only apply a line you ticked, and remove the step their session finished. |
| `conventions.md` | Notation, units, sign conventions | The researchers and the agents; every change an agent makes appears as a diff in its debrief. |
| `draft.tex` | The best current state of the research, as a draft paper | The researchers. Agents copy into it only what you tick, or edit it when a next step asks them to; such edits appear as a diff in their debrief. |
| `sessions/S<n>/note.tex` | What session S<n> found, in two to four pages of LaTeX | A fresh writer agent. |
| `sessions/S<n>/debrief.md` | What session S<n> asks of you: a summary, *Changed by this session*, questions, tick lines, a note box | The session, then the researchers. |
| `literature/overview.md`, `seeds.md`, `ratings.yaml` | The field in a few paragraphs; your seed papers; your rating of papers | Surveys write the overview; the researchers write the seeds and the ratings. |

**How decisions flow.** You never ask the agents for anything in the middle of their work. You answer the latest debrief, tick its lines, and write in its note box, in the Space or in an editor; you may also edit `project.md`, `conventions.md` or the draft directly. The next `session.py start` prints, and records in `sessions/S<n>/received.md`, everything written since the previous session started; the session applies the ticked lines first, asks any question left unanswered, and then proposes its brief. An unticked line is not applied. An unanswered question that still matters is asked again in the next debrief.

**What "established" means.** A claim is *established* when a `result` environment of `draft.tex` names its card (`\card{CL-S2-1}`). Only the researchers decide what enters the draft, by ticking a line such as "Copy Result 1 of note S2 into the draft, as a result" or by editing it. `check` refuses a result whose claim has no confirming review of a supporting derivation or computation (or a verification by a researcher, reported in a debrief); such a claim goes in a `conjecture` environment instead.


## Setting up your harness

A session runs on its own for hours, so a few minutes of setup before the first one saves interruptions later.

**With every harness:**

- Launch the harness from the workspace folder, after the installer has finished. A harness reads the workspace's settings when it starts, so restart it after you add a harness or upgrade the workspace.
- Stay logged in to Hugging Face (`hf auth login`; the installer logs you in if needed). If the environment variable `HF_TOKEN` is set, the scripts use it instead of your login.
- When a script fails, the coordinator stops and shows you the error instead of working around it. Fix the cause, or run the command yourself in a terminal, and then let the coordinator continue. Do not ask it to redo the script's work with git or the Hub by hand: the scripts keep the record consistent.
- On macOS, the scripts check the Hub's certificates against the system file `/etc/ssl/cert.pem`, because a sandbox blocks the usual check through the keychain. If your network inspects encrypted traffic with a certificate installed in your keychain, set `SSL_CERT_FILE` to a file that includes it.

**Claude Code** reads `CLAUDE.md`, a one-line import of `AGENTS.md`. Skills are slash commands.

- Accept the trust prompt for the folder on first launch. It turns on the workspace's settings, including the literature tools.
- Claude Code's sandbox can stay on. The workspace's `.claude/settings.json` lets commands reach the Hub and PyPI, which the scripts need. One setting is yours to add, in `~/.claude/settings.json`: the scripts run through uv, which writes its cache outside the workspace, so the sandbox must allow that folder. Merge this into your existing settings:

  ```json
  { "sandbox": { "filesystem": { "allowWrite": ["~/.cache/uv"] } } }
  ```

  Without it, no workspace script can run in the sandbox, and uv stops with "Failed to initialize cache". If you set `UV_CACHE_DIR`, allow that folder instead.
- Do not let the agent run the workspace scripts outside the sandbox, and do not exclude them from it (`sandbox.excludedCommands`). The scripts live in the workspace, which the agent can edit, so they would let anything the agent writes there run unsandboxed.

**Codex CLI** reads `AGENTS.md`. Skills are `$name` (`$session-run`).

- Accept the project-trust prompt on first launch. Otherwise Codex ignores `.codex/config.toml`, which gives commands the network access the scripts need and starts the literature tools.

**OpenCode** reads `AGENTS.md`. Skills are slash commands.

- The workspace's `opencode.json` lets the agent run commands, edit files and search the web without asking, so that a session can work on its own. OpenCode does not confine those commands to the workspace.
- Dispatching custom sub-agents has depended on the OpenCode version ([opencode #29616](https://github.com/anomalyco/opencode/issues/29616)); `AGENTS.md` explains the fallback.

**Pi** reads `AGENTS.md`. Skills are slash commands from `.pi/prompts/`.

- It installs `pi-subagents` and `pi-web-access` on first launch.

A workspace rendered for several harnesses opens in any of them without running anything again. `AGENTS.md` holds the method and one short section per harness.


## What a workspace looks like

```
project.md            the question, goal, approach, next steps (the researchers')
conventions.md        notation, units, signs
draft.tex             the draft paper (the researchers'); references.bib is generated from the paper cards
project.toml          method version, Hub repositories, people
.physics-hive/        copy of the method: prompts, renderer, scripts, templates, Space app
sessions/S12/         received.md, brief.md, log.md, note.tex (to read), debrief.md (to answer)
claims/               one card per claim or dead end
derivations/          D-S12-3.summary.md (one page) + D-S12-3.tex (full LaTeX) + reviews
computations/         C-S12-1.md (one page) + .py + .out + reviews
critiques/            strategic critiques
literature/           overview.md, one card per paper (P-<arXiv id>.md), seeds.md, ratings.yaml
INDEX.md              generated: one line per card, artefact, paper and session (git-ignored)
```

**Cards** are the record of results. A claim is one assertion about the physics, in one sentence, that a derivation or a computation can check; a dead end records an obstacle or a refutation. A card can be corrected during the session that wrote it and never changes afterwards; everything that happens to it later is a new file that names it (an artefact that supports it, a review, a dead end that refutes it, a claim that supersedes it). The scripts compute each claim's status (`working`, `established`, `refuted`, `revised`) and evidence, and flag as *needs re-check* every card that depends on a refuted or revised one. IDs embed the session number (`CL-S12-2`), so parallel sessions never collide.


## Skills

| Skill | What it does |
|---|---|
| `/session-run` | Runs one session: start, apply the ticked lines, a brief you confirm, autonomous work within a budget, note and debrief, end (and merge, in a shared space). |
| `/survey` | Literature: expands from the seed papers and the papers rated high, along citations (INSPIRE, arXiv), writes paper cards and updates the overview. Usable in any session. |
| `/research-plan` | Drafts an approach and next steps, which the session offers as tick lines. |
| `/derive <target>` | Analytical derivation in LaTeX with a one-page summary, by a fresh-context sub-agent. |
| `/compute <target>` | Symbolic and numerical computation (SymPy, NumPy), with both paths compared. |
| `/review <artefact>` | Blind, test-based review: dimensions, limits, symmetries and spot checks first, then located remarks with a severity. |
| `/critique` | Strategic critique of the overall state. |

## Scripts

The deterministic work is done by scripts in `.physics-hive/scripts/`, which the skills call with `uv run`: `regen.py` (rebuild `INDEX.md` and `references.bib`), `check.py` (validate cards, references, immutability, the draft's results, notes and debriefs), `session.py` (start, save, status, next ID, record an answer or a tick given in the terminal, brief, end, abort), `pdf.py` (compile the draft or a note), `export_trace.py`, `literature.py` (arXiv and INSPIRE search, citations, sources; also an MCP server), and `hubgit.py`.


## Where the project is going

- **Several researchers.** Colleagues can already sign in to a space and write in its debriefs, and a second operator can join with `--mode join`, but nobody has worked this way yet. Two parts are still built for one person: a debrief has one answer per question, and two sessions that edit the same researcher file at the same time (`draft.tex`, `conventions.md`, `literature/overview.md`) conflict when they merge.
- **Agents in the cloud.** Agents run only on the operator's machine. Sessions could run on Hugging Face infrastructure, or be started from the Space.
- **The Ask page.** A read-only assistant in the Space that answers questions about the project and cites the files it read.
- **Publishing the record.** At the end of a project, make the record public with the results. Traces first need their secrets removed, since a transcript contains a token as soon as an agent prints the environment, and there is no step that does this yet.

Current limitations:

- Model diversity between authors and reviewers is not enforced. Every card and trace records the models used, and the reviewer benchmark (`bench/reviewer/`) measures how often each reviewer configuration catches planted errors and raises false alarms.
- Trace export is complete for OpenCode and Claude Code, best effort for Codex and Pi.
- Workspaces created with Physics Intern are not supported.
