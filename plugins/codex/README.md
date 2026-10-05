# PhysicsIntern — Codex CLI plugin

Set up a **PhysicsIntern** research workspace from inside Codex: a local workspace on your machine, a new shared space on the Hugging Face Hub for a team, or a shared space you join.

PhysicsIntern is a method for using AI coding agents to do theoretical physics and mathematics research. The lead scientist writes the question and its definition of done in `problem.md`. Agents then work in bounded sessions: they read the literature, derive and compute in fresh-context sub-agents, review each result blindly, and record results as cards whose status and evidence are computed by scripts. In a shared space, every session ends in a pull request, and reviewers follow the work in a browser through the project's private Space.

## Install

```
codex plugin marketplace add huggingface/physics-intern-codex-plugin
codex plugin add physics-intern@physics-intern-codex
```

Restart Codex afterwards so that the skill registers. The scripts run through [uv](https://docs.astral.sh/uv/); install it once (`curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`). For shared spaces, log in to the Hub once with `hf auth login`.

## Use

In an empty folder:

```
codex
> $physics-intern:init-physics-intern
```

The agent asks what to do (local, create or join), which other harnesses the folder should also work with, where, and for a shared space the organisation and project name or the repository to join. It then runs the bundled initializer once; Codex asks for one approval, because the script writes `.codex/`, runs git and uses the network.

Then:

1. In a new workspace, write the question in `problem.md` (and seed papers in `literature/seeds.md`).
2. **Exit and restart Codex in the workspace folder**, and accept the project-trust prompt on first launch, so that `AGENTS.md`, the skills, the sub-agent roles and `.codex/config.toml` load.
3. Run **`$session-run`**. For a benchmark run in a local workspace, `$autoresearch`.

## What it sets up

- `.physics-intern/` — a committed copy of the method (prompts, renderer, scripts, Space app), so that everyone on a project runs the same version.
- `project.toml`, `problem.md`, `plan.md`, `conventions.md`, `literature/seeds.md`, and the folders for cards, artefacts, sessions and feedback.
- The harness files rendered from the method copy (`AGENTS.md`, `.agents/skills/`, `.codex/`, and those of any other harness you chose), which are git-ignored and personal to each checkout. `.codex/config.toml` allows network access, which the session scripts need.
- For a shared space: the private workspace, traces, sources and chat-debug datasets and the Space, in your organisation.

## Notes

- The plugin only adds the user-invoked `$physics-intern:init-physics-intern` skill. The method's skills and sub-agent roles live in each workspace, not in your other projects.
- This repository is a build artefact. The source of truth is upstream, assembled here by `build-codex-plugin.sh`; edit upstream, not here.
