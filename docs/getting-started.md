# Getting started

This guide takes you through a first session: first in a local workspace, which needs no Hugging Face account and is the quickest way to try the method, then in a shared space on the Hub. For what the files are, see [The workspace](workspace.md); for the web app, see [The Space](the-space.md).

The people on a project have two roles. A **lead** sets the question and makes the decisions, by writing in `project.md`, in the debriefs and in the draft. A **contributor** runs the sessions in a terminal. One person can be both, and so far one person always has been. If you try PhysicsHive alone, you are both.


## Before you start

- **git**, and **[uv](https://docs.astral.sh/uv/)**, which runs the scripts with their dependencies. The installer offers to install uv if it is missing. Nothing else needs installing by hand.
- **At least one harness**, installed and logged in to its model provider: [Claude Code](https://claude.com/claude-code) (`claude`), [Codex CLI](https://github.com/openai/codex) (`codex`), [OpenCode](https://opencode.ai) (`opencode`) or [Pi](https://pi.dev) (`pi`). Read [Setting up your harness](harness-setup.md) before the first session; with Claude Code, one setting is yours to add.
- **For a shared space**, a Hugging Face account and membership of the organisation that will own the space. Private repositories under a personal account cannot be shared, so a team needs one organisation (one per team, not per project). To try a shared space alone, choose your own account as the owner. The installer logs you in if needed.
- **Optional**: a TeX distribution with `latexmk` (TeX Live or MacTeX), to compile the notes and the draft to PDF on your machine. The Space compiles them itself.
- **Optional**: `SEMANTIC_SCHOLAR_API_KEY` in your environment, which raises the rate limit of the citation lookups for papers that INSPIRE does not cover.

Pick a question small enough for a first try. The example in [`examples/pendulum/`](../examples/pendulum/) used a textbook question (the period of a pendulum to second order in the amplitude), which one session answered.


## A first session in a local workspace

### 1. Create the workspace

In a new, empty folder:

```bash
curl -LsSf https://raw.githubusercontent.com/scienceetonnante/physics-hive/master/install.sh | sh -s -- --mode local
```

The installer checks for git and uv, downloads the latest release of PhysicsHive into a temporary folder, and runs its init script. It asks:

- which harnesses you will use on this machine: a tick list, with those it finds installed already ticked;
- the folder for the workspace (the current folder by default; it must be empty, or hold only a `project.md`);
- the question of the project in one line, and its goal: the question in full, and what would count as an answer. You may press Enter to leave either for later, but a session needs both to start.

It then writes the workspace: `project.md` with your question and goal, `conventions.md`, `draft.tex`, `literature/seeds.md`, the empty record folders, a copy of the method in `.physics-hive/`, the files your harnesses read, and a first git commit. It prints the next steps. Nothing stays installed on your machine: the workspace keeps its own copy of the method.

### 2. Write the question and the goal, if you left them

Open `project.md` in your editor. Write the question in one line as its title (`# ...`) and the goal under `## Goal`. *Approach* and *Next steps* can wait. If you have papers to start from, list their arXiv identifiers in `literature/seeds.md`. You may also leave all this to the coordinator: it asks for the question and the goal when they are missing.

### 3. Launch the harness and start the session

In the workspace folder, launch your harness (`claude`, `codex`, `opencode` or `pi`) and run `/session-run` (in Codex, `$session-run`). You may add what to work on after the command; otherwise the coordinator proposes a brief from `project.md`, by default its first next step.

Before it works on its own, the coordinator talks to you:

1. It runs `session.py start`. If the question or the goal is missing, it asks you for them and writes them into `project.md`.
2. It applies the lines you ticked in earlier debriefs (none, the first time).
3. If an earlier debrief has a question you did not answer, it shows it and waits. Answer, or tell it to go on.
4. It proposes a **brief**: the goal of the session and why, a budget in dispatches (20 by default; a dispatch is one sub-agent run, such as one derivation or one review), and the stop conditions. Confirm it or change it.

From then on the method asks you nothing until the end. (With Claude Code, this needs a permission mode in which it edits files without asking; see [Setting up your harness](harness-setup.md#claude-code). Otherwise it stops at each file edit to ask for your approval.) It works with sub-agents (literature, derivations, computations, blind reviews, critiques) and stops at the first of: the goal is reached; the budget is spent; four dispatches in a row add nothing; or the work shows that `project.md` should change.

While it works, you can follow it in `sessions/S1/log.md`, which has one line per dispatch (`Dispatch 3/20: /review D-S1-1 ... → confirmed ...`). If a script fails, the coordinator stops and shows you the error rather than working around it; see [the FAQ](faq.md#a-script-failed-what-do-i-do).

### 4. What you get at the end

The coordinator tells you, in a few lines, why the session stopped and what it found. The session folder `sessions/S1/` then holds:

- `note.tex`, the note: two to four pages of LaTeX, written by a fresh sub-agent for a reader who was not there. Compile it with `uv run .physics-hive/scripts/pdf.py S1` (this needs `latexmk`), or read it in the Space (step 5).
- `debrief.md`, the debrief: a summary, what the session changed in your files, its questions, and the lines it asks you to tick.
- `received.md` (what the session received from you), `brief.md`, and `log.md`, which ends with a *Handoff* for the next session.

The results themselves are in the record: cards in `claims/`, artefacts and their reviews in `derivations/` and `computations/`, critiques in `critiques/`, paper cards in `literature/`.

### 5. Answer the debrief

In your editor, open `sessions/S1/debrief.md`:

- write your answer under each question, after `> **Answer:**`;
- tick the lines you accept, by changing `- [ ]` into `- [x]`;
- write anything else for the next session after `> **Note:**`.

To do the same in a browser, with the note rendered, run the Space on your folder: `uv run .physics-hive/scripts/serve.py` in the workspace, then open the address it prints. In local mode, the Space writes your edits into the files without committing them.

You do not need to commit anything. The next `session.py start` commits your edits as yours.

### 6. The next session

Run `/session-run` again. It prints what you wrote since the previous session started, applies the ticked lines first, asks any question you left open, and proposes the next brief. An unticked line is not applied; a question you did not answer and that still matters comes back in the next debrief.


## A first session in a shared space

A shared space puts the workspace on the Hugging Face Hub, with a private web app, the Space, in which the leads read the notes and answer the debriefs. [Shared spaces](shared-spaces.md) explains how it works in detail.

### 1. Create the space

In a new, empty folder:

```bash
curl -LsSf https://raw.githubusercontent.com/scienceetonnante/physics-hive/master/install.sh | sh
```

If no Hugging Face token is found, the installer logs you in first (paste a token, or sign in in the browser); the token is saved as `hf auth login` saves it, and must be able to write to the organisation that will own the space. It then asks:

- what to do: create a shared space (the default), join one, or start a local workspace;
- which harnesses you will use on this machine;
- the folder (the current folder by default);
- the owner: one of your organisations, or, listed last, your own account (only you can then see the project);
- the project name (the folder's name by default);
- the question and the goal, as in local mode;
- whether to give the Space your Hugging Face token, so that it can save your answers and edits. It does not ask this when `PHYSICS_HIVE_SPACE_TOKEN` is set; see [the Space's token](shared-spaces.md#the-spaces-token).

It then creates four private dataset repositories and a private Space, all named after the project (for example `our-lab/physics-hive-x-correction`), pushes the first commit, and prints:

- the Space's own address, such as `https://our-lab-physics-hive-x-correction.hf.space`. Open the Space there rather than on huggingface.co: at its own address it signs you in within the same tab;
- the command a second contributor runs to join the space.

The Space builds its app on the Hub before it can open, the first time.

### 2. Before the first session

If you left the question or the goal for later, write them in the Space, on the *Project* page: the question as the title of `project.md`, the goal under *Goal*. A save in the Space is a commit on the Hub, where the session reads them. (An edit in your local checkout also works: the next session start commits it as yours and pushes it; see [Editing files outside the Space](shared-spaces.md#editing-files-outside-the-space).) If you have papers to start from, list them on the *Literature* page, which has an editor for `literature/seeds.md`.

### 3. Run the session

Launch your harness in the workspace folder and run `/session-run`, as in local mode. In a shared space, the session also:

- claims a session number by opening a draft pull request on the workspace repository (its number is the session number, `S1`), and puts your checkout on the branch `session/S1`;
- tells you if another open session works on the same step, and lets you decide;
- at the end, pushes its branch, uploads its trace to the `-traces` dataset, and merges the pull request into `main`. A merge adds to the record and endorses nothing: what the leads endorse is what they put in the draft.

### 4. Answer in the Space

Open the Space. The *Review* page shows the session waiting for your response: its note on the left, and your response on the right (the questions, the lines to tick, a note box). Save, then run `/session-run` again. [The Space](the-space.md) describes every page.


## Stopping a session

A session ends by itself, with its note and its debrief, at the first of its stop conditions. `/session-run` has no step for ending early at your request with a note and a debrief; to get a shorter session, give it a smaller budget when you confirm the brief.

To stop it anyway, interrupt the harness. The session stays active in the checkout: `uv run .physics-hive/scripts/session.py status` says so, and no other session can start there. You can then ask the coordinator to carry on, or abandon the session:

```bash
uv run .physics-hive/scripts/session.py abort
```

- In a **local workspace**, `abort` deletes the session's folder if nothing in it was committed. Files of the folder that were committed stay in `sessions/S<n>/`, and the session's commits (cards, artefacts) stay in the history of your branch.
- In a **shared space**, `abort` closes the session's pull request on the Hub; nothing is merged into `main`. If the checkout has no uncommitted changes, it moves back to the latest `main`; otherwise the changes stay, with a warning. The branch `session/S<n>` stays in the checkout, and the brief, if it was confirmed and pushed to the pull request, stays on the Hub with the closed pull request. The session's number is not used again.


## How long it takes, and what it costs

A session is bounded by its budget of dispatches (20 by default), not by time. The design aims at sessions of a few hours. In the example in [`examples/pendulum/`](../examples/pendulum/), session S1 used 5 dispatches out of the 10 its brief allowed, and took about 35 minutes with Claude Code.

What a session costs is what your harness's model provider charges for the tokens it uses: the coordinator, and every sub-agent it dispatches. The repository holds no cost figure. In a shared space, the trace's `meta.json` records the tokens each model used; a local workspace records none, so there your harness's own usage display is the place to look. See [the FAQ](faq.md#what-does-it-cost-to-run).


## Every question has a flag

To run the installer without questions, pass the answers as flags after `sh -s --`:

```bash
curl -LsSf https://raw.githubusercontent.com/scienceetonnante/physics-hive/master/install.sh | sh -s -- \
    --mode create --org our-lab --name x-correction --harness claude \
    --question "<the question in one line>" --goal "<the goal>" --yes
```

| Flag | Meaning |
|---|---|
| `--mode create\|join\|local` | create a shared space (the default), join one, or start a local workspace |
| `--harness claude,codex,opencode,pi` | the harnesses to render, comma-separated |
| `--dir PATH` | the folder (default: the current folder) |
| `--org ORG`, `--name NAME` | create: the owner (an organisation or your own account) and the project name |
| `--repo ORG/NAME` | join: the workspace repository |
| `--question TEXT`, `--goal TEXT` | create and local: written into `project.md` |
| `--space-token env\|mine\|none` | create: which token the Space holds (see [Shared spaces](shared-spaces.md#the-spaces-token)) |
| `--yes` | ask nothing; use the defaults for anything not given |
| `--upgrade` | inside a workspace: move it to the downloaded release (see [Shared spaces](shared-spaces.md#upgrading-a-workspace)) |

`PHYSICS_HIVE_VERSION`, set before `sh`, picks another release (a tag such as `v0.6.0`) or a branch (`master`).


## Later

- **Add a harness, or refresh the harness files**: `uv run .physics-hive/scripts/init.py --harness codex` inside the workspace. It renders from the workspace's own copy of the method. Restart your harness afterwards, since it reads the workspace's settings when it starts.
- **Stop a session in the middle**: see [Stopping a session](#stopping-a-session).
- **Move to a newer release of the method**: run the installer inside the workspace with `--upgrade`. See [Upgrading a workspace](shared-spaces.md#upgrading-a-workspace).
