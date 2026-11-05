# PhysicsHive — Claude Code plugin

Set up a **PhysicsHive** research workspace from inside Claude Code: a new shared space on the Hugging Face Hub, a shared space you join, or a local workspace on your machine.

PhysicsHive lets a small team of scientists use AI coding agents to work together on one problem in theoretical physics or mathematics. The researchers write the question and the goal in `project.md`. Agents then work in bounded sessions: they read the literature, derive and compute in fresh-context sub-agents, review each result blindly, and record results as cards whose status and evidence are computed by scripts. Each session comes back with a short LaTeX note and a one-page debrief, which the researchers answer; what they decide to keep goes into a shared LaTeX draft. In a shared space, every session ends in a pull request, and the researchers read and answer in a browser through the project's private Space.

## Install

```
/plugin marketplace add huggingface/physics-hive-claude-plugin
/plugin install physics-hive@physics-hive-claude
```

Restart Claude Code afterwards so that the command registers. The scripts run through [uv](https://docs.astral.sh/uv/); install it once (`curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`). For shared spaces, log in to the Hub once with `hf auth login`.

## Use

In an empty folder:

```
claude
> /init-physics-hive
```

The agent asks what to do (create a shared space, join one, or start a local workspace), which other harnesses the folder should also work with, where, for a new space the organisation and the project name or for joining the repository, and for a new workspace the question of the project and its goal. It then runs the bundled initializer once; Claude Code asks for one approval, because the script writes `.claude/`, runs git and uses the network.

Then:

1. If you left the question or the goal for later, write them in `project.md`: on the Space's *Project* page in a shared space, in your editor in a local workspace. Seed papers go on the Space's *Literature* page, or in `literature/seeds.md`.
2. **Exit and restart Claude Code in the workspace folder**, so that its skills and sub-agents load.
3. Run **`/session-run`**.

## What it sets up

- `.physics-hive/` — a committed copy of the method (prompts, renderer, scripts, Space app), so that everyone on a project runs the same version.
- `project.toml`, `project.md`, `conventions.md`, `draft.tex`, `literature/seeds.md`, and the folders for cards, artefacts and sessions.
- The harness files rendered from the method copy (`AGENTS.md`, `CLAUDE.md`, `.claude/`, and those of any other harness you chose), which are git-ignored and personal to each checkout.
- For a shared space: the private workspace, traces, sources and chat-debug datasets and the Space, in your organisation.
  The Space gets a copy of your login token as its secret `HF_TOKEN`, or the token in `PHYSICS_HIVE_SPACE_TOKEN` if that variable is set when you start the harness. A dedicated token needs only read and write access to the repositories of your organisation, and *Make calls to Inference Providers* for the Space's future assistant.

## Notes

- The plugin only adds the `/init-physics-hive` command. The method's skills and sub-agents live in each workspace, not in your other projects.
- This repository is a build artefact. The source of truth is upstream, assembled here by `build-plugin.sh`; edit upstream, not here.
