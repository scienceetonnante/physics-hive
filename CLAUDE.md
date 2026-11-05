# PhysicsHive project

In this repo we develop and maintain PhysicsHive: the method, scripts and web app with which a small team of scientists steers AI agents on one problem in theoretical physics or mathematics, in a shared space on the Hugging Face Hub. So far it has been used by one person at a time. It was forked in November 2026 from Physics Intern (`../physics-intern`, `huggingface/physics-intern`), which remains the project for autonomous runs.

- **For user-facing context** (what PhysicsHive is, shared spaces on the Hub and local workspaces, install/launch, skills, what a workspace looks like, where the project is going): see [`README.md`](README.md).
- **For developer documentation** (repo layout, render pipeline, workspace format, workspace scripts, sessions and the Hub, init script, agent/skill authoring contracts, host glue, the Space, literature tools, reviewer benchmark, the installer and releases, tests, the audit workflow): see [`DOCUMENTATION.md`](DOCUMENTATION.md).
- **For the design** of the workspace format (the record and the human view: `project.md`, notes, debriefs, the draft) and of shared spaces: see `design/DESIGN-shared-spaces.md`.

When the user asks a "how does this work" question, decide which doc fits before answering — if they're using PhysicsHive, read `README.md`; if they're editing the methodology, read `DOCUMENTATION.md`. Most methodology-edit tasks are covered there in detail.

## Rules

- **Scope.** PhysicsHive is for research that people steer. Features for autonomous runs, where nobody steers, belong in Physics Intern, not here.
- **Traceability.** Keep the record complete enough to publish at the end of a project: every result must stay traceable to who produced it (agent and model, or person), how, and with which method version.
- **Maintenance.** Update this file CLAUDE.md, README.md, DOCUMENTATION.md after any major change.
- **Do not over-engineer the skills.** The goal is a robust system that works on new problems. Skill prompts should be as simple as possible while still being effective. Avoid complex, verbose, or ad-hoc instructions that aren't essential to the core methodology.
- **Source of truth.** `commons/` (host-agnostic prompts, renderer, templates), `hosts/<host>/` (harness glue: `host.toml`, `section.md`, settings extras), `scripts/` (workspace scripts), `space/` (the Space app), and `VERSION`. Every workspace gets a copy of these in `.physics-hive/`; rendered workspaces (e.g. under `workspaces/`) are snapshots — upgrade or re-render rather than backporting edits.
- **Skill bodies stay harness-neutral.** OpenCode and Pi also read other harnesses' skill folders, so a skill must read the same everywhere: no tool names, harness paths or placeholders in `commons/skills/`. Harness-specific text goes in `hosts/<host>/section.md` or the agent files.
- **Deterministic work goes in scripts.** IDs, views, validation, what a session receives from the researcher, git and Hub operations belong in `scripts/`, called by the skills; prompts keep the judgment. When the card format, the debrief format or a script's contract changes, update `commons/workspace-doc.md`, the affected roles and skills, the templates in `commons/templates/`, the Space, and `investigate-run` together.
- **Render and test before committing.** After editing `commons/`, `hosts/` or `scripts/`, run `python3 commons/render.py --hosts=claude,codex,opencode,pi --target=<tmpdir>` and read the output, and run the tests: `uv run --no-project --with pytest --with httpx --with-requirements space/requirements.txt --with "mcp>=1.12,<2" pytest -q tests/`. `tests/hub_e2e.py` runs the shared-mode flow live on scratch repos under your account (manual).
- **Bump `VERSION`** when a change to the method should be distinguishable in workspaces (it is stamped into `AGENTS.md` and recorded in `project.toml`).
- **Distribution.** Users run `install.sh` from GitHub; it downloads the latest release (a git tag `v<VERSION>`) and runs its `scripts/init.py`. To release: bump `VERSION`, commit, tag `v<VERSION>`, push the tag. `install.sh` is always taken from `master` but runs whichever release it downloads, so keep it compatible with older releases. To create a workspace from the development version, run `./init-physics-hive.sh` from this clone. See [`DOCUMENTATION.md`](DOCUMENTATION.md#distribution-the-installer-and-releases).

## Development skills

The `investigate-run` skill (`.claude/skills/investigate-run/SKILL.md`) audits an existing PhysicsHive workspace and produces a post-mortem of the research process — strengths, weaknesses, methodology adherence, areas for improvement. See [`DOCUMENTATION.md`](DOCUMENTATION.md#auditing-a-run-investigate-run) for when and how to use it.
