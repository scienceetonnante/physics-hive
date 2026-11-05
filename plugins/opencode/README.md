# PhysicsHive — OpenCode bootstrap

Set up a **PhysicsHive** research workspace from inside OpenCode: a new shared space on the Hugging Face Hub, a shared space you join, or a local workspace on your machine.

PhysicsHive lets a small team of scientists use AI coding agents to work together on one problem in theoretical physics or mathematics. The researchers write the question and the goal in `project.md`. Agents then work in bounded sessions: they read the literature, derive and compute in fresh-context sub-agents, review each result blindly, and record results as cards whose status and evidence are computed by scripts. Each session comes back with a short LaTeX note and a one-page debrief, which the researchers answer; what they decide to keep goes into a shared LaTeX draft. In a shared space, every session ends in a pull request, and the researchers read and answer in a browser through the project's private Space.

## Install

OpenCode has no plugin marketplace, and its plugins can register only tools and hooks, not commands. So this ships as a **global command and a kit**, copied into your OpenCode configuration by an installer:

```
git clone https://github.com/huggingface/physics-hive-opencode-plugin
cd physics-hive-opencode-plugin
./install.sh
```

It copies the `/init-physics-hive` command and the kit (the method and its scripts) into `${XDG_CONFIG_HOME:-~/.config}/opencode/`. Restart OpenCode afterwards so that the command registers; run `git pull && ./install.sh` to upgrade. The scripts run through [uv](https://docs.astral.sh/uv/); install it once (`curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`). For shared spaces, log in to the Hub once with `hf auth login`.

## Use

In an empty folder:

```
opencode
> /init-physics-hive
```

The agent asks what to do (create a shared space, join one, or start a local workspace), which other harnesses the folder should also work with, where, for a new space the organisation and the project name or for joining the repository, and for a new workspace the question of the project and its goal. It then runs the initializer once (OpenCode may ask you to approve the shell command).

Then:

1. If you left the question or the goal for later, write them in `project.md`: on the Space's *Project* page in a shared space, in your editor in a local workspace. Seed papers go on the Space's *Literature* page, or in `literature/seeds.md`.
2. **Exit and restart OpenCode in the workspace folder**, so that `AGENTS.md`, the skills (`.opencode/skills/`), the sub-agent roles and `opencode.json` load.
3. Run **`/session-run`**.

## What it sets up

- `.physics-hive/` — a committed copy of the method (prompts, renderer, scripts, Space app), so that everyone on a project runs the same version.
- `project.toml`, `project.md`, `conventions.md`, `draft.tex`, `literature/seeds.md`, and the folders for cards, artefacts and sessions.
- The harness files rendered from the method copy (`AGENTS.md`, `.opencode/`, `opencode.json`, and those of any other harness you chose), which are git-ignored and personal to each checkout.
- For a shared space: the private workspace, traces, sources and chat-debug datasets and the Space, in your organisation.
  The Space gets a copy of your login token as its secret `HF_TOKEN`, or the token in `PHYSICS_HIVE_SPACE_TOKEN` if that variable is set when you start the harness. A dedicated token needs only read and write access to the repositories of your organisation, and *Make calls to Inference Providers* for the Space's future assistant.

## Notes

- **Custom sub-agent dispatch has depended on the OpenCode version.** Some builds only accepted the built-in `explore` and `general` roles (opencode issue #29616). If yours cannot dispatch the method's roles, the workspace's `AGENTS.md` explains the fallback.
- The installer only adds the `/init-physics-hive` command globally. The method's skills and sub-agent roles live in each workspace, not in your other projects.
- This repository is a build artefact. The source of truth is upstream, assembled here by `build-opencode-plugin.sh`; edit upstream, not here.
