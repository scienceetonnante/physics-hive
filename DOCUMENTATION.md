# PhysicsIntern — Developer Documentation

This document is for people who work on the PhysicsIntern method itself: the prompts, the renderer, the workspace scripts, the Space, the plugins and the audit skill. For installing and using PhysicsIntern, see [README.md](README.md). The design behind the card-based format and shared spaces is in `design/DESIGN-shared-spaces.md`.

## Contents

1. [What this repo is](#what-this-repo-is)
2. [Repo layout](#repo-layout)
3. [Architecture](#architecture)
4. [The render pipeline](#the-render-pipeline)
5. [The workspace format](#the-workspace-format)
6. [The workspace scripts](#the-workspace-scripts)
7. [Sessions and the Hub](#sessions-and-the-hub)
8. [The init script](#the-init-script)
9. [Authoring agents](#authoring-agents)
10. [Authoring skills](#authoring-skills)
11. [Host glue](#host-glue)
12. [The Space](#the-space)
13. [Literature tools](#literature-tools)
14. [The reviewer benchmark](#the-reviewer-benchmark)
15. [Distribution: plugins](#distribution-plugins)
16. [Tests](#tests)
17. [Design choices worth remembering](#design-choices-worth-remembering)
18. [Adding a host, an agent or a skill](#adding-a-host-an-agent-or-a-skill)
19. [Auditing a run: investigate-run](#auditing-a-run-investigate-run)
20. [Validation workflow](#validation-workflow)


## What this repo is

This repo holds the **method**: the prompts that turn an AI coding harness (Claude Code, Codex CLI, OpenCode, Pi) into a research coordinator with fresh-context sub-agents; the renderer that writes them in each harness's format; the **workspace scripts** that do the deterministic work (computing views, validating, opening and closing sessions, Hub operations, trace export); the **Space** app for browser-only reviewers; the plugin bootstraps; and the audit skill used to improve all of this from real runs.

The harness provides tool-use loops, sub-agent dispatch, shell, web search and slash commands; we do not rebuild those. Research content (cards, derivations, sessions) is produced inside workspaces, never here.


## Repo layout

```
physics-intern/
├── README.md, DOCUMENTATION.md, CLAUDE.md
├── VERSION                       method version, copied into every workspace
├── init-physics-intern.sh        thin launcher: uv run scripts/init.py
├── commons/                      host-agnostic method
│   ├── render.py                 renderer (stdlib only)
│   ├── workspace-doc.md          body of AGENTS.md
│   ├── agents/                   8 sub-agent roles (surveyor, planner, deriver, computer,
│   │                             reviewer, critic, finalizer, writer)
│   ├── skills/                   10 skill workflows (session-run, survey, research-plan, derive,
│   │                             compute, review, critique, finalize, write-up, autoresearch)
│   └── templates/                problem.md, plan.md, conventions.md, seeds.md, gitignore
├── hosts/<host>/                 harness glue: host.toml, section.md, extras/ (settings files)
├── scripts/                      workspace scripts (uv inline dependencies)
│   ├── cards.py                  library: load a workspace, compute status, evidence, re-check flags
│   ├── regen.py, check.py        generated views; validation
│   ├── session.py                start, status, next, brief, end, abort
│   ├── promote.py, propose.py    promotion records; proposal pull requests for the lead's files
│   ├── hub.py, hubgit.py         Hub operations; git with the Hub token
│   ├── export_trace.py           harness records → trace.jsonl
│   ├── literature.py             arXiv / INSPIRE / Semantic Scholar CLI and MCP server
│   ├── init.py                   create, join, refresh, upgrade
│   └── common.py                 git helpers, the active-session file
├── space/                        the Space app (Gradio), deployed by init --mode create
├── bench/reviewer/               reviewer benchmark: cases with planted errors, runner
├── plugins/<host>/               authored files of the plugin bootstraps
├── build-*plugin.sh              assemble the publishable plugin repos
├── tests/                        pytest suite; hub_e2e.py (live, manual)
├── .claude/skills/investigate-run/   the audit skill (repo-level)
├── design/                       design documents
└── workspaces/, problems/, references/, results/   sample runs and benchmark corpus (git-ignored)
```


## Architecture

Four layers, each with one job:

- **`commons/`** carries the substance of the method, written once: the workspace doc (what the coordinator does), the role prompts, the skill workflows, the skeletons of a new workspace. Skill bodies contain no harness-specific values.
- **`hosts/<host>/`** carries the glue for one harness: where its files go, the shape of its agent frontmatter, its tool names, its section of `AGENTS.md` (dispatch syntax, tool discipline), and its settings files.
- **`commons/render.py`** writes the harness files of a workspace for one or several harnesses. It is the only code that knows both sides.
- **`scripts/`** does the deterministic work inside a workspace, so that models are left only with judgment: `regen` and `check`, the session lifecycle, Hub operations, trace export, the literature tools.

**The method copy.** `scripts/init.py` copies `commons/`, `hosts/`, `scripts/`, `space/` and `VERSION` into a committed `.physics-intern/` folder in every workspace, and records the version in `project.toml`. Harness files are rendered from that copy (`.physics-intern/commons/render.py`), the scripts run from it (`uv run .physics-intern/scripts/…`), and the Space imports `cards.py` from it. So every operator and the Space use exactly the same prompts and scripts, the prompts that produced a result sit in the git history next to it, and an upgrade is one replacement of the folder (`init.py --upgrade`, a pull request in shared mode). `check` refuses session changes that touch it.


## The render pipeline

```bash
python3 commons/render.py --hosts=claude,opencode --target=<workspace>
```

For each selected host, in a fixed order (claude, codex, opencode, pi):

1. **Clean** the host's previously rendered agent and skill folders, so that removed files do not linger.
2. **Render the agents**: one file per `commons/agents/<name>.md`, with the manifest (`name`, `description`, `capabilities`, `output_pattern`) projected onto the host's frontmatter, capabilities mapped to tool names through `tools_map`. Codex roles are TOML (`developer_instructions` is a multi-line basic string, so backslashes are escaped and the result is checked by a TOML round trip).
3. **Render the skills**: Claude Code, Codex and OpenCode get `<skills_dir>/<name>/SKILL.md` (Claude adds `argument-hint`); Pi gets a stub in `.pi/skills/<name>/SKILL.md` and the workflow in `.pi/prompts/<name>.md` with the Pi preamble prepended.
4. **Copy the host extras** (`hosts/<host>/extras/<path>` → `<workspace>/<path>`): `.claude/settings.json` and `.mcp.json`, `.codex/config.toml`, `opencode.json`, `.pi/settings.json`.

Then, once:

5. **Render `AGENTS.md`**: a stamp line with the method version (`<!-- Rendered from the PhysicsIntern method 0.2.0 … -->`), then `commons/workspace-doc.md` with `{{harness_names}}` and `{{harness_sections}}` filled from each selected host's `section.md`. When Claude Code is selected, `CLAUDE.md` is the single line `@AGENTS.md`.

The renderer is stdlib-only (Python 3.11+, `tomllib`). Placeholders are `{{key}}`; an unknown placeholder raises. Skill bodies are substituted with an empty context, so a harness-specific placeholder in a skill fails the render.

**Why skill bodies are harness-neutral.** OpenCode also reads `.claude/skills/` and `.agents/skills/`, keeping the first copy of each skill name, and Pi reads `.agents/skills/`. Identical bodies make it irrelevant which copy a harness picks, and OpenCode, which lists skills as slash commands, then shows each skill once. Everything harness-specific lives in the harness's section of `AGENTS.md` and in its agent files, which no other harness reads (verified with `opencode debug skill`, `opencode debug agent` and Pi's RPC `get_commands`).


## The workspace format

The authoritative description, as agents see it, is `commons/workspace-doc.md`. The computations are in `scripts/cards.py`. In summary:

**Cards** (`claims/<id>.md`): YAML header `id`, `kind` (`claim`, `question`, `dead-end`), `statement`, `depends_on`, `produced_by` (`{kind: agent, model, operator}` or `{kind: human, user}`), `session`, `supersedes` (claims), `refutes` (dead ends), `answers` (claims and dead ends); free prose body. Never edited after creation.

**Artefacts**: `derivations/D-S<n>-<k>.summary.md` + `.tex`; `computations/C-S<n>-<k>.md` + `.py` + `.out` (+ text data files). The summary header holds `id`, `kind` and `supports` (the claims it supports), and no authorship, for blind review.

**Reviews**: `derivations/<target>_R-S<n>-<k>.md` (or in `computations/`), header `id`, `kind: review`, `target`, `supports`, `claim` (the statement reviewed), `verdict`, `by: {kind: agent}`, `session`, `date`. **Human verifications** are reviews in `feedback/` with `id: R-<user>-<timestamp>` and `by: {kind: human, user}`, with or without an artefact `target`.

**Feedback** (`feedback/`): reactions (`kind: reaction`, `target`, `value`, `by`, `date`, the comment as body; the latest per person and target counts), human reviews, and promotion records (`kind: promotion`, `target`, `by`, `date`, `session`, the reason as body).

**Paper cards** (`literature/P-<arXiv id>.md`), survey summaries (`literature/survey-S<n>.md`), critiques (`critiques/CR-S<n>-<k>.md`), and session folders (`sessions/S<n>/brief.md` with `goal`, `budget`, `merge`, `starts_from`; `log.md`; `report.md` with `stop_reason`, `dispatches` and fixed sections).

**IDs** embed the session (`CL-S12-2`, `D-S12-3`, `D-S3-2_R-S12-1`); items written outside a session carry the author and a UTC timestamp (`CL-alice-20261005T141233`); paper cards use the arXiv identifier.

**What is computed** (never stored):

| | Rule |
|---|---|
| Claim status | `refuted` if a dead end refutes it; else `revised` if a claim supersedes it; else `established` if a valid promotion record names it (in shared mode, by a lead); else `working`. |
| Question status | `answered` if a claim or dead end names it in `answers`; else `open`. |
| Evidence of a claim | Every artefact whose summary names it in `supports`, or that a review attaches by naming it in `supports`; with the reviews of that artefact that concern the claim (they name it, or name nothing while the artefact names it). Plus human verifications without an artefact target. |
| Needs re-check | The refuted or revised cards in the transitive closure of `depends_on`. |
| Promotion rule (`promotion_problems`) | Shared mode: the author is a human in `leads`. Always: the card is a claim, neither refuted nor revised, with at least one confirmed piece of evidence (an artefact with a confirming review for the claim, or a confirming human verification). |

**Generated views** (git-ignored): `INDEX.md` (one line per item, grouped by status) and `research_log.md` (Open Questions, Working Claims, Established Results, Dead Ends, Answered Questions, then the session reports' main sections). Both are deterministic: regenerating gives identical files.


## The workspace scripts

All run with `uv run .physics-intern/scripts/<script>` from a workspace, with PEP 723 inline dependencies (PyYAML; `huggingface_hub` for those that talk to the Hub). They print what they did and fail with one `ERROR:` line rather than guess; the skills tell the coordinator to stop and report such failures.

| Script | Role |
|---|---|
| `cards.py` | Library, no side effects: `Workspace` (loading, `status`, `evidence`, `needs_recheck`, `current_reactions`), `promotion_problems`, front-matter helpers. Imported by every other script and by the Space. |
| `regen.py` | Writes `INDEX.md` and `research_log.md`. |
| `check.py` | Validates headers, ID formats, references and their kinds, cycles, artefact authorship, reviews, feedback. With a base commit (default: the active session's), also: no file in `claims/`, `feedback/`, `derivations/`, `computations/` or paper cards edited or deleted; `.physics-intern/` untouched; in shared mode the lead's files and `project.toml` untouched by a session; other sessions' folders untouched; new IDs belong to the session; new promotion records follow the rule (and are refused inside shared sessions). |
| `session.py` | `start`, `status`, `next <prefix>` / `next review <artefact>` (next free ID, counting IDs already mentioned in the session's briefs and log), `brief`, `end [--no-merge]`, `abort`. State in `.active-session` (JSON, git-ignored). |
| `promote.py` | Records a promotion. Local: `--by-agent` for the coordinator. Shared: run by a lead, checked against the latest `main` in a temporary worktree, committed to `main` through the API. |
| `propose.py` | Opens a pull request that changes one lead's file (`create_commit(create_pr=True)`). |
| `hub.py` | Create and join, the session pull request lifecycle, sources sync, promotions, proposals, upgrades. |
| `hubgit.py` | Runs a git command with the Hub token passed in a header (for leads' own pushes). |
| `export_trace.py` | Collects the harness's record of a session: OpenCode's SQLite store (sessions, messages, parts in the window), Claude Code's JSONL files including sub-agent transcripts; Codex rollouts and Pi sessions as raw files, best effort. Returns the models found. |
| `literature.py` | Literature tools; see below. |
| `init.py` | Create, join, refresh, upgrade; see below. |

**`session.py start` waiting list.** Open questions; cards that need a re-check; human cards, reactions, verifications and promotions added since the last commit that added a session report; the `Proposed plan changes` of reports added since `plan.md` last changed; working claims proposed for promotion; and in shared mode, other open session pull requests (with the `starts_from` of their brief) and pull request comments since the last report. It also refuses to start when the harness files were rendered from another method version than the one on `main` (it re-renders and asks for a harness restart), when the checkout is dirty, or when a session is already active.


## Sessions and the Hub

A shared space is five private repositories in one organisation: the workspace (dataset), `-traces`, `-sources`, `-chat-debug` (datasets) and `-space` (Space). Research files are not stored in the Space repo, because every push to a Space rebuilds the app.

**Session lifecycle in shared mode** (`scripts/hub.py`):

1. `start`: fetch `main`; refuse if local `main` has unpushed commits; `create_pull_request` (a draft; its number is the session number); rename it `[S<n>] (brief pending) by <user>`; `git checkout -B session/S<n> origin/main`; download paper sources.
2. `brief`: commit the brief; push to `refs/pr/<n>`; rename the pull request `[S<n>] <goal>`; replace its description with the brief.
3. `end`: rebase on `origin/main` if it moved (stop on conflict, branch unchanged); `check` against `origin/main`; force-push to `refs/pr/<n>`; upload sources; export the trace and upload `S<n>/trace.jsonl` and `S<n>/meta.json`; mark the draft ready; merge (one retry after a fresh rebase); record the merge commit in `meta.json`; reset the checkout to the new `main`.

**Hub behaviours this relies on**, verified on scratch repositories before writing `session.py end`: a pull request is the ref `refs/pr/<n>` and accepts pushes and force-pushes of a rebased branch; a draft cannot be merged until `change_discussion_status(..., "open")`; **merging squashes** the pull request into one commit titled `<title> (#<n>)`, so session commits do not keep their SHAs on `main` (they stay reachable through `refs/pr/<n>`, and `meta.json` lists them with the merge commit); `create_commit(create_pr=True)` opens a ready pull request; small binary files push fine over plain git, and new repositories come with a `.gitattributes` routing many extensions to LFS, which `create` removes so that workspaces stay plain git.

**Authentication.** Git gets the token of `hf auth login` through `GIT_CONFIG_COUNT`/`http.<endpoint>/.extraHeader` for each command; it is never written to `.git/config`.

**Traces.** `meta.json` holds the session, pull request, operator, harness, declared model, models found in the trace, method version, start and end, the session's commits and the ref that keeps them, the merge commit, and a note when the export was partial.


## The init script

`scripts/init.py` (launched by `init-physics-intern.sh` and by the plugins) asks, each with a default and a flag: the mode (`--mode local|create|join`), the harnesses (`--harness`, a tick list with installed ones ticked), the folder (`--dir`), and for create the organisation and name (`--org`, `--name`), for join the repository (`--repo`). `--yes` never asks; `--list-harnesses` and `--list-orgs` print choices for the plugins.

- **local / create**: refuse a non-empty folder (except `problem.md`) and a workspace in the earlier format; copy the method; write `project.toml`, the skeletons, the card folders and the committed `.gitignore`; render; first commit; regen. **create** then creates the repositories, fetches the Hub's initial commit and builds on it (dropping its `.gitattributes`), pushes, and deploys the Space (`space/` from the method copy, with the variables `PHYSICS_INTERN_WORKSPACE` and `CHAT_DEBUG`, and the secret `HF_TOKEN` set to the creator's token unless `--space-token none`). A personal namespace is accepted with a warning, for trying shared mode alone.
- **join**: clone into an empty folder, then render the selected harnesses from the clone's method copy.
- **inside a workspace**: render the selected harnesses plus those already rendered (to add one or refresh); `--upgrade` replaces the method copy with the running script's copy (a commit in local mode, a pull request for a lead in shared mode).


## Authoring agents

Source: `commons/agents/<name>.md`, YAML frontmatter + Markdown body.

```yaml
---
name: deriver
description: Perform an analytical derivation … (shown to the coordinator at dispatch time)
capabilities: [file_read, file_write, glob]
output_pattern: derivations/D-S<n>-<k>.summary.md
---
```

`capabilities` come from `{file_read, file_write, file_edit, shell, glob, grep, web_search, web_fetch, literature}` and are mapped per host. `literature` lists the literature MCP server's tools in Claude Code's allowlist (an explicit `tools:` list hides MCP tools otherwise) and maps to the shell for Pi, which has no MCP. `output_pattern` is emitted as Pi's `output:`; `false` for the reviewer, whose path is given at dispatch.

Every role body follows the same contract: what you receive and read (and what you must not read); your artefact(s), with their header and sections; behaviour; the **return block** `## Summary` / `## Result` / `## Flags` (with `- (none)` when empty), identical at the top of the artefact and in the final reply (the planner and the writer return it in the reply only); constraints (write only your files; never cards, the session folder or the lead's files). Artefact headers carry no authorship.

Codex roles are TOML, so a body must not contain `"""`.


## Authoring skills

Source: `commons/skills/<name>.md`.

```yaml
---
name: derive
description: Analytical derivation …
agent: deriver                 # omit for skills that run in the coordinator's context
arguments_hint: <target claim or question>
top_level_cli: false           # optional, Pi only: hide from Pi's top-level commands
---
```

The body is the coordinator's workflow for that skill: get the IDs (`session.py next`), write the brief or assemble the dispatch context, dispatch (pointing to the harness section of `AGENTS.md` for the syntax), integrate (cards, log, regen, commit `[S<n>] …`), next dispatch. **Bodies must stay harness-neutral**: no tool names, no harness paths, no placeholders. Keep them as short as they can be while effective.


## Host glue

`hosts/<host>/host.toml`:

- `name`, `display_name` (used in `AGENTS.md`), `agents_dir`, `agent_ext`, `skills_dir`, optionally `prompts_dir` (Pi).
- `agent_frontmatter_order`, `[agent_extra_fields]` (Pi: `thinking = "high"`; OpenCode: `mode = "subagent"`), `agent_body_prefix` (Claude: a heading), `agent_format = "toml"` (Codex).
- `skills_layout` (`nested` by default; `pi` for the stub + prompt layout), `skill_argument_hint` (Claude).
- `[tools_map]` (capability → tool; informational for Codex and OpenCode, which have no per-role allowlist, but it must be complete).
- `[file_backed]`: `section = "section.md"` (the harness's part of `AGENTS.md`: name for `--harness`, how skills are invoked, tool discipline, dispatch syntax with an example, how to pass the model ID), and for Pi `preamble` and `skill_stub_template`.

`hosts/<host>/extras/` holds settings files copied verbatim: Claude `.mcp.json` and `.claude/settings.json` (permissions, and only the `literature` MCP server approved through `enabledMcpjsonServers`, which takes effect once the folder's trust prompt is accepted); Codex `.codex/config.toml` (workspace-write sandbox with network access, web search, the `literature` MCP server with a long startup timeout); OpenCode `opencode.json` (permissions, the MCP server with a 180-second timeout); Pi `.pi/settings.json` (`pi-subagents`, `pi-web-access`).


## The Space

`space/` is a Gradio app deployed as a private Space by `init --mode create` (`hub.deploy_space`): `backend.py` (workspace access, the views, every write; no Gradio), `chat.py` (the explainer), `app.py` (the page only), `README.md` (Space metadata: Gradio SDK version, Python 3.12, OAuth with the `inference-api` scope) and `requirements.txt`. `tests/test_space_backend.py` covers the backend and the chat tools in local mode.

- **Data.** It downloads `main` at its current commit with the `HF_TOKEN` secret (one cache folder per commit), on page load when older than two minutes, on Refresh and after each write, and imports `cards`, `regen`, `check` and `promote` from the snapshot's `.physics-intern/scripts/` (restoring `sys.path` and `sys.modules` afterwards), so that status, evidence and the promotion rule are computed by the workspace's own method version.
- **Identity.** Hugging Face OAuth; the signed-in user is recorded inside every file the Space writes. Leads are `[people] leads` of `project.toml`.
- **Writes** are new files with unique names (user and timestamp), committed to `main` with the Space token, after the workspace's own `check` has accepted them on a copy: reactions, question and claim cards, human verifications, and promotions (leads only, after `promotion_problems`, committed with `parent_commit` set to the commit they were checked on). The lead's files are edited in a text editor with a rendered preview: a lead's save is a commit to `main`, anyone else's is a proposal pull request (titled `Proposal: <file> (by <user>)`), and a save is refused if the file changed on `main` since the editor loaded it. Leads can merge open proposals; session pull requests are never listed as proposals.
- **Explainer chat.** A lightweight open model through inference providers (`[models] chat`, `openai/gpt-oss-20b` by default), called with the reader's own OAuth token so that costs are attributed, never with the Space token; four read-only tools (open a card, an artefact's summary, full material or reviews, a paper card; search the index), at most six rounds of tool calls; a note lists what it read; a button sends the last question to the question-card form. Conversations are not stored, except in debug mode (`CHAT_DEBUG=1`), where each exchange becomes a file of the `chat_debug` dataset behind a visible banner (the Space token must then also be able to write that dataset).
- **Local development**: `PHYSICS_INTERN_LOCAL=<workspace> PHYSICS_INTERN_LOCAL_USER=<name> python space/app.py` reads and writes a local folder instead of the Hub.


## Literature tools

`scripts/literature.py` is both a CLI and an MCP server (`literature.py mcp`, stdio, tool names with underscores), so that it works in every harness: `search-inspire`, `search-arxiv`, `references`, `citations` (INSPIRE when the paper is a core INSPIRE record, Semantic Scholar otherwise), `download` (arXiv LaTeX source preferred, PDF otherwise, extracted into `literature/sources/<id>/` with links, absolute and `..` paths skipped), `card` (a paper-card skeleton with the header filled; only the card goes to stdout, so it can be redirected into `literature/P-<id>.md`), and `search-cards` (keyword search over paper cards, survey summaries and card statements). Papers are named by arXiv identifier (with or without version, old or new style, or a paper-card ID) or `insp:<INSPIRE record>`. Every command takes `--json`; errors are one `ERROR:` line. arXiv requests are spaced by 3 seconds, also across runs; `SEMANTIC_SCHOLAR_API_KEY` raises the Semantic Scholar rate limit. Claude Code, Codex and OpenCode get the server through their extras; Pi has no MCP support, and the surveyor role says how to call the CLI instead. `init` installs the script's dependencies once (skipped when `PHYSICS_INTERN_NO_WARMUP` is set), so that the harnesses' first start of the server fits in their startup timeout. In shared mode, sources are synced with the `-sources` dataset at session start and end.


## The reviewer benchmark

`bench/reviewer/` measures each reviewer configuration (harness and model, with the method's reviewer prompt) on planted-error cases: the catch rate (planted errors refuted) and the false-alarm rate (correct work refuted). Each case is an artefact in the exact format a reviewer receives, with a `case.toml` giving the label, the claim, and for planted cases the error, its location and expected severity. `verify_cases.py` checks every correct case by an independent route (SymPy, numerical integration, exact diagonalisation) and shows that each planted result fails the same check. `run.py` creates a fresh workspace per case and configuration, runs the harness non-interactively as the reviewer (Claude Code with an explicit tool allowlist, Codex in its workspace sandbox with network, OpenCode with `--auto`), and scores the review files; `--dry-run` uses a fake reviewer to test the pipeline. Results go to `bench/reviewer/results/` (git-ignored). See `bench/reviewer/README.md`. Real runs call models and cost money.


## Distribution: plugins

The plugins bootstrap a workspace from inside a harness. They carry the whole method (vendored by the build scripts: every host, the scripts, the Space app, `VERSION`), because a workspace created with one harness may be opened with any other, and joiners render from the workspace's copy. They do not install the method's skills globally.

| Harness | Authored files | Build | Command |
|---|---|---|---|
| Claude Code | `plugins/claude/` (marketplace, `plugin.json`, `skills/init-physics-intern/SKILL.md`, `scripts/plugin-init.sh`) | `build-plugin.sh` → `physics-intern-claude-plugin` | `/physics-intern:init-physics-intern` |
| Codex CLI | `plugins/codex/` (marketplace under `.agents/plugins/`, `plugin.json`, the skill with `agents/openai.yaml` making it user-only, `scripts/plugin-init.sh`) | `build-codex-plugin.sh` → `physics-intern-codex-plugin` | `$physics-intern:init-physics-intern` |
| OpenCode | `plugins/opencode/` (`install.sh`, the global command, `scripts/plugin-init.sh`) | `build-opencode-plugin.sh` → `physics-intern-opencode-plugin` | `/init-physics-intern` |

The command asks the init questions in the chat (the harness is known) and runs `plugin-init.sh` once with the answers as flags; `plugin-init.sh` is a uv launcher for the vendored `scripts/init.py`. In Claude Code, `${CLAUDE_PLUGIN_ROOT}` is only available in an expansion-time `` !`…` `` block, so the command prints the initializer's path that way; Codex exposes `${PLUGIN_ROOT}` to model-issued shell commands; OpenCode's kit sits at a fixed path under `${XDG_CONFIG_HOME:-~/.config}/opencode/physics-intern/`. After the bootstrap, the user restarts the harness in the workspace so that its skills load.

Publishing: bump `version` in the plugin manifests (Claude, Codex), rebuild, commit and push the built tree to the plugin repo (the OpenCode repo must be public). Never hand-edit a built plugin. Local test: `bash build-plugin.sh /tmp/out` then `claude --plugin-dir /tmp/out/plugin` in a folder outside this repo; for Codex, `codex plugin marketplace add /tmp/out`; for OpenCode, `XDG_CONFIG_HOME=/tmp/cfg bash /tmp/out/install.sh`.


## Tests

```bash
uv run --no-project --with pytest --with pyyaml --with huggingface_hub --with gradio --with "mcp>=1.12,<2" pytest -q tests/
```

Without `gradio`, the test that builds the Space's page is skipped.

- `tests/test_cards.py`: status precedence, evidence (artefacts, attached artefacts, human verifications), propagation of needs re-check, deterministic regeneration, the promotion rule, and the check rules (headers, references, cycles, immutability against a base, lead's files and foreign IDs in shared sessions, promotions in sessions).
- `tests/test_local_flow.py`: a local workspace end to end through the real scripts: init, adding a harness, two sessions, reserved IDs, a review, a promotion, and a refused edit of an existing card.
- `tests/test_export_trace.py`: the trace exporter on a fake OpenCode store and fake Claude Code transcripts.
- `tests/test_space_backend.py`, `tests/test_literature.py`, `tests/test_reviewer_bench.py`: the Space's backend in local mode, the literature tools without network, the benchmark in dry-run mode (and the shape of every case).
- `tests/ACCEPTANCE.md` maps each acceptance test of the design's build plan to how it is checked, and gives the steps of those that need real agents.
- `tests/hub_e2e.py` (manual, live, not collected by pytest): creates scratch repositories under your account and runs the shared-mode flow with two operators: parallel sessions adding evidence to the same claim, a rebase, merges, a promotion refused for a non-lead and accepted for the lead, a proposal, an abort. It deletes the repositories at the end. `uv run tests/hub_e2e.py [--keep]`.


## Design choices worth remembering

- **Research files and harness files are separated.** Harness files are rendered locally from the method copy and git-ignored; only research content and the method copy are shared.
- **The method is copied into each workspace**, so that every participant runs the same prompts and the prompts sit in history next to the results.
- **One file per item, never edited.** Status and evidence are computed by `regen`, so parallel sessions add files and never edit the same file; their pull requests do not conflict.
- **Deterministic work is done by scripts, not prompts.** IDs (`session.py next`), views, validation, the pull request lifecycle, uploads. Models keep the judgment.
- **Sessions with briefs, not a fixed pipeline.** A brief can name a plan item, an open question, a doubt, a re-check, papers to read. The pipeline survives only in `/autoresearch` for benchmarks.
- **Sessions merge without a lead; promotion needs one.** A merge makes nothing established. Requiring a lead on every merge would make the lead the bottleneck.
- **Draft pull requests as claims.** Unique numbers without a shared counter, and the open sessions are visible.
- **A branch in the checkout, not a worktree.** Harness files are git-ignored and the harness runs in the checkout; one checkout holds at most one session.
- **Blind review.** Reviewers get the artefact and the claim's statement, never who produced it nor earlier verdicts; tests with a clear outcome come before opinions, and "no issue found" is a respected outcome.
- **Fresh context and second opinions.** No single verdict changes direction; a refutation becomes a dead-end card only after a second, independent review agrees.
- **Do not over-engineer the skills.** Prompts as short as they can be while effective; the audit skill catches drift.


## Adding a host, an agent or a skill

**A host** is a folder `hosts/<host>/` with `host.toml`, `section.md` and optional `extras/`. Then add it to `HOST_ORDER` in `commons/render.py`, to `HARNESSES` and `RENDER_MARKS` in `scripts/init.py` and `scripts/common.py`, to `detect_harness()` and to an exporter in `scripts/export_trace.py` if its record format is known. Render a workspace for it together with another harness and check that neither picks up the other's files.

**An agent** is one file in `commons/agents/`; **a skill** is one file in `commons/skills/` (its agent must exist). Add the skill to the list in `commons/workspace-doc.md` §6 and to the table in `README.md`. Render for every host before committing:

```bash
python3 commons/render.py --hosts=claude,codex,opencode,pi --target=/tmp/render-all
```


## Auditing a run: investigate-run

`.claude/skills/investigate-run/SKILL.md` is a repo-level skill that audits a workspace and its session record (harness JSONL, OpenCode's SQLite store, or the trace in the traces dataset for shared sessions) and writes a post-mortem to `/tmp/audit-<workspace>.md`. It detects the workspace format: for card-based workspaces it audits ten promises (coordinator only, valid immutable cards, robust evidence behind promotions, blind test-based review, review after every artefact, the integration loop, edit scope, return schema, session discipline, scripts not bypassed); legacy workspaces keep their rules. Update it when the method's contract changes.


## Validation workflow

1. Edit the source (`commons/`, `hosts/`, `scripts/`, `space/`).
2. Run the tests, and render a workspace for every host and read the result.
3. Run a benchmark problem in a fresh local workspace (often `/autoresearch`), or a shared session on a scratch space.
4. Audit it with `investigate-run`, and compare with earlier audits in `results/`.
5. Commit the source change together with any audit-rule change.

Changes reach a workspace only through its method copy: new workspaces get the current version; existing ones get it with `init.py --upgrade`.
