# PhysicsIntern project

In this repo we develop and maintain the core methodology and skills for PhysicsIntern, a framework for using AI agents to conduct physics research.

- **For user-facing context** (what PhysicsIntern is, local workspaces and shared spaces on the Hub, install/launch, plugins, skills, what a workspace looks like): see [`README.md`](README.md).
- **For developer documentation** (repo layout, render pipeline, workspace format, workspace scripts, sessions and the Hub, init script, agent/skill authoring contracts, host glue, the Space, literature tools, reviewer benchmark, plugins, tests, the audit workflow): see [`DOCUMENTATION.md`](DOCUMENTATION.md).
- **For the design** of the card-based format and shared spaces: see `design/DESIGN-shared-spaces.md`.

When the user asks a "how does this work" question, decide which doc fits before answering — if they're using PhysicsIntern, read `README.md`; if they're editing the methodology, read `DOCUMENTATION.md`. Most methodology-edit tasks are covered there in detail.

## Rules

- **Maintenance.** Update this file CLAUDE.md, README.md, DOCUMENTATION.md after any major change.
- **Do not over-engineer the skills.** The goal is a robust system that works on new problems. Skill prompts should be as simple as possible while still being effective. Avoid complex, verbose, or ad-hoc instructions that aren't essential to the core methodology.
- **Source of truth.** `commons/` (host-agnostic prompts, renderer, templates), `hosts/<host>/` (harness glue: `host.toml`, `section.md`, settings extras), `scripts/` (workspace scripts), `space/` (the Space app), and `VERSION`. Every workspace gets a copy of these in `.physics-intern/`; rendered workspaces (e.g. under `workspaces/`) are snapshots — upgrade or re-render rather than backporting edits.
- **Skill bodies stay harness-neutral.** OpenCode and Pi also read other harnesses' skill folders, so a skill must read the same everywhere: no tool names, harness paths or placeholders in `commons/skills/`. Harness-specific text goes in `hosts/<host>/section.md` or the agent files.
- **Deterministic work goes in scripts.** IDs, views, validation, git and Hub operations belong in `scripts/`, called by the skills; prompts keep the judgment. When the card format or a script's contract changes, update `commons/workspace-doc.md`, the affected roles and skills, and `investigate-run` together.
- **Render and test before committing.** After editing `commons/`, `hosts/` or `scripts/`, run `python3 commons/render.py --hosts=claude,codex,opencode,pi --target=<tmpdir>` and read the output, and run the tests: `uv run --no-project --with pytest --with httpx --with-requirements space/requirements.txt --with "mcp>=1.12,<2" pytest -q tests/`. `tests/hub_e2e.py` runs the shared-mode flow live on scratch repos under your account (manual).
- **Bump `VERSION`** when a change to the method should be distinguishable in workspaces (it is stamped into `AGENTS.md` and recorded in `project.toml`).
- **Host plugins.** `plugins/claude/`, `plugins/codex/`, and `plugins/opencode/` hold the authored files for the per-host bootstraps; `build-plugin.sh`, `build-codex-plugin.sh`, and `build-opencode-plugin.sh` assemble the publishable `physics-intern-<host>-plugin` repos by vendoring the whole method (`commons/`, every host, `scripts/`, `space/`, `VERSION`). The bootstrap command asks the init questions in the chat and runs `scripts/init.py` with flags. Claude and Codex are marketplace plugins (`/physics-intern:init-physics-intern` / `$physics-intern:init-physics-intern`); OpenCode has **no marketplace and plugins can't ship commands**, so it ships a global `/init-physics-intern` command file + a vendored kit installed by `plugins/opencode/install.sh`. Edit methodology in the source of truth and rebuild — never hand-edit a built plugin. See [`DOCUMENTATION.md`](DOCUMENTATION.md#distribution-plugins).

## Development skills

The `investigate-run` skill (`.claude/skills/investigate-run/SKILL.md`) audits an existing PhysicsIntern workspace (card-based or legacy format) and produces a post-mortem of the research process — strengths, weaknesses, methodology adherence, areas for improvement. See [`DOCUMENTATION.md`](DOCUMENTATION.md#auditing-a-run-investigate-run) for when and how to use it.
