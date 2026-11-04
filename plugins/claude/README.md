# PhysicsIntern — Claude Code plugin

Set up a **PhysicsIntern** research workspace from inside Claude Code: a local workspace on your machine, a new shared space on the Hugging Face Hub for a team, or a shared space you join.

PhysicsIntern is a method for using AI coding agents to do theoretical physics and mathematics research. The researcher writes the question and the goal in `project.md`. Agents then work in bounded sessions: they read the literature, derive and compute in fresh-context sub-agents, review each result blindly, and record results as cards whose status and evidence are computed by scripts. Each session comes back with a short LaTeX note and a one-page debrief, which the researcher answers; what they decide to keep goes into a shared LaTeX draft. In a shared space, every session ends in a pull request, and the researcher reads and answers in a browser through the project's private Space.

## Install

```
/plugin marketplace add huggingface/physics-intern-claude-plugin
/plugin install physics-intern@physics-intern-claude
```

Restart Claude Code afterwards so that the command registers. The scripts run through [uv](https://docs.astral.sh/uv/); install it once (`curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`). For shared spaces, log in to the Hub once with `hf auth login`.

## Use

In an empty folder:

```
claude
> /init-physics-intern
```

The agent asks what to do (local, create or join), which other harnesses the folder should also work with, where, and for a shared space the organisation and project name or the repository to join. It then runs the bundled initializer once; Claude Code asks for one approval, because the script writes `.claude/`, runs git and uses the network.

Then:

1. In a new workspace, write the question in one line as the title of `project.md` and the goal under *Goal* (and seed papers in `literature/seeds.md`).
2. **Exit and restart Claude Code in the workspace folder**, so that its skills and sub-agents load.
3. Run **`/session-run`**. For a benchmark run in a local workspace, `/autoresearch`.

## What it sets up

- `.physics-intern/` — a committed copy of the method (prompts, renderer, scripts, Space app), so that everyone on a project runs the same version.
- `project.toml`, `project.md`, `conventions.md`, `draft.tex`, `literature/seeds.md`, and the folders for cards, artefacts and sessions.
- The harness files rendered from the method copy (`AGENTS.md`, `CLAUDE.md`, `.claude/`, and those of any other harness you chose), which are git-ignored and personal to each checkout.
- For a shared space: the private workspace, traces, sources and chat-debug datasets and the Space, in your organisation.

## Notes

- The plugin only adds the `/init-physics-intern` command. The method's skills and sub-agents live in each workspace, not in your other projects.
- This repository is a build artefact. The source of truth is upstream, assembled here by `build-plugin.sh`; edit upstream, not here.
