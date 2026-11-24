# Contributing to PhysicsHive

This file says how to set up a development copy, how to check a change, the rules the project follows, and how to release. [DOCUMENTATION.md](DOCUMENTATION.md) is the developer reference; [ROADMAP.md](ROADMAP.md) lists what is open.


## Where to find what

| Path | What it is |
|---|---|
| `commons/` | The method, independent of any harness: `workspace-doc.md` (the body of `AGENTS.md`), the sub-agent roles in `agents/`, the skills in `skills/`, the templates of a new workspace, and the renderer `render.py`. |
| `hosts/<host>/` | The glue for one harness (`claude`, `codex`, `opencode`, `pi`): `host.toml`, its section of `AGENTS.md`, and its settings files in `extras/`. |
| `scripts/` | The workspace scripts: cards and views, validation, the session lifecycle, Hub operations, trace export, PDFs, literature tools, and `init.py`, which creates, joins and upgrades workspaces. |
| `space/` | The Space, a FastAPI app. |
| `tests/` | The test suite, and two live scripts for the Hub (`hub_e2e.py`, `clean_hub.py`). |
| `bench/reviewer/` | The reviewer benchmark. |
| `.claude/skills/investigate-run/` | The audit skill, which writes a post-mortem of a workspace's sessions. |
| `design/` | The design document, notes, the schematic and the source of the explainer animation. |
| `examples/` | A real workspace after one session. |
| `docs/` | The user guides. |
| `install.sh`, `init-physics-hive.sh` | The installer (downloads a release) and the development launcher (uses this clone). |
| `.github/` | The test workflow, which runs the render and the tests on every push to `master` and every pull request; an issue template for problem reports; a pull request template with a checklist. |

Every workspace gets a copy of `commons/`, `hosts/`, `scripts/`, `space/` and `VERSION` in its `.physics-hive/` folder. These are the source of truth. Workspaces are snapshots: to change one, upgrade it or render it again, rather than editing its copy.


## A development copy

You need git, [uv](https://docs.astral.sh/uv/), Python 3.11 or later, and at least one harness to run real sessions.

```bash
git clone https://github.com/scienceetonnante/physics-hive && cd physics-hive
./init-physics-hive.sh --mode local --harness claude --dir /tmp/try-hive
```

`./init-physics-hive.sh` takes the same options as the installer, and uses the method as it is in your clone, uncommitted changes included. To move an existing test workspace to the method as it is now in your clone, run `./init-physics-hive.sh --dir <workspace> --upgrade`. To try the unreleased `master` branch on another machine without a clone, set `PHYSICS_HIVE_VERSION=master` before `sh` in the installer's command.

To create shared spaces from your clone with a dedicated token for the Space, put `PHYSICS_HIVE_SPACE_TOKEN=hf_...` in the `.env` at the root of the clone (it is git-ignored); see [the Space's token](docs/shared-spaces.md#the-spaces-token).


## Checking a change

After editing `commons/`, `hosts/` or `scripts/`, render a workspace for every harness and read the output:

```bash
python3 commons/render.py --hosts=claude,codex,opencode,pi --target=/tmp/render-all
```

Run the tests:

```bash
uv run --no-project --with pytest --with httpx --with-requirements space/requirements.txt --with "mcp>=1.12,<2" pytest -q tests/
```

`tests/hub_e2e.py` runs the shared-mode flow live on scratch repositories under your Hugging Face account and deletes them at the end (`uv run tests/hub_e2e.py`). It is manual and not collected by pytest.

For a change to the prompts, tests are not enough: run a few sessions on a test problem, in a fresh local workspace or a scratch shared space, and audit them with the `investigate-run` skill (in Claude Code, from this repository). See [Validation workflow](DOCUMENTATION.md#validation-workflow).


## Rules

- **Scope.** PhysicsHive is for research that people steer. Features for autonomous runs, where nobody steers, belong in [Physics Intern](https://github.com/huggingface/physics-intern).
- **Traceability.** Keep the record complete enough to publish at the end of a project: every result must stay traceable to who produced it (agent and model, or person), how, and with which method version.
- **Skill bodies stay harness-neutral.** OpenCode and Pi also read other harnesses' skill folders, so a skill must read the same everywhere: no tool names, harness paths or placeholders in `commons/skills/`. Harness-specific text goes in `hosts/<host>/section.md` or the agent files.
- **Deterministic work goes in scripts.** IDs, views, validation, what a session receives from the leads, git and Hub operations belong in `scripts/`, called by the skills; prompts keep the judgment. When the card format, the debrief format or a script's contract changes, update `commons/workspace-doc.md`, the affected roles and skills, the templates in `commons/templates/`, the Space, and `investigate-run` together.
- **Keep the skills simple.** The goal is a robust system that works on new problems. Skill prompts should be as short as they can be while still effective.
- **Bump `VERSION`** when a change to the method should be distinguishable in workspaces. It is stamped into `AGENTS.md` and recorded in each workspace's `project.toml`.
- **Update the documentation** after any major change: `README.md`, the guides in `docs/`, `DOCUMENTATION.md`, `CLAUDE.md` and, when it changes what is open, `ROADMAP.md`. The documents are written in plain, literal English, with complete sentences.

`CLAUDE.md` holds the same rules for a coding agent working on this repository.

To report a problem, open an issue on GitHub; its template asks for the version, the harness, the mode and the full error. For a security problem, follow [SECURITY.md](SECURITY.md) instead.


## Releasing

Users run `install.sh` from GitHub. It downloads the latest release, a git tag `v<VERSION>`, and runs that release's `scripts/init.py`. To release:

1. Bump `VERSION`, set `version` and `date-released` in `CITATION.cff` to the new version and the release date, and commit.
2. `git tag v<VERSION>`
3. `git push origin master v<VERSION>`

`install.sh` is always taken from `master`, but it runs whichever release it downloads. Keep it compatible with older releases: it relies only on `scripts/init.py` taking the options the user passes.
