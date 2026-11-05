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

This repo holds the **method**: the prompts that turn an AI coding harness (Claude Code, Codex CLI, OpenCode, Pi) into a research coordinator with fresh-context sub-agents; the renderer that writes them in each harness's format; the **workspace scripts** that do the deterministic work (computing views, validating, opening and closing sessions, what a session receives from the researcher, Hub operations, trace export, PDFs); the **Space** app where the researcher reads and answers in a browser; the plugin bootstraps; and the audit skill used to improve all of this from real runs.

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
│   │                             reviewer, critic, finalizer, writer of the note)
│   ├── skills/                   9 skill workflows (session-run, survey, research-plan, derive,
│   │                             compute, review, critique, finalize, autoresearch)
│   └── templates/                project.md, conventions.md, draft.tex, seeds.md, gitignore (written by
│                                 init); note.tex and debrief.md (the shapes sessions follow)
├── hosts/<host>/                 harness glue: host.toml, section.md, extras/ (settings files)
├── scripts/                      workspace scripts (uv inline dependencies)
│   ├── cards.py                  library: load a workspace, compute status, evidence, re-check flags
│   ├── human.py                  library: project.md, debriefs, the draft, ratings; what a session receives
│   ├── regen.py, check.py        INDEX.md and references.bib; validation
│   ├── session.py                start, status, next, answer, tick, brief, end, abort
│   ├── pdf.py                    compile the draft or a note to PDF
│   ├── hub.py, hubgit.py         Hub operations; git with the Hub token
│   ├── export_trace.py           harness records → trace.jsonl
│   ├── literature.py             arXiv / INSPIRE / Semantic Scholar CLI and MCP server
│   ├── init.py                   create, join, refresh, upgrade
│   └── common.py                 git helpers, the active-session file
├── space/                        the Space app (FastAPI pages, LaTeX converter), deployed by init --mode create
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
- **`scripts/`** does the deterministic work inside a workspace, so that models are left only with judgment: `regen` and `check`, the session lifecycle and what a session receives from the researcher, Hub operations, trace export, PDFs, the literature tools.

**The method copy.** `scripts/init.py` copies `commons/`, `hosts/`, `scripts/`, `space/` and `VERSION` into a committed `.physics-intern/` folder in every workspace, and records the version in `project.toml`. Harness files are rendered from that copy (`.physics-intern/commons/render.py`), the scripts run from it (`uv run .physics-intern/scripts/…`), and the Space imports the scripts from it. So every operator and the Space use exactly the same prompts and scripts, the prompts that produced a result sit in the git history next to it, and an upgrade is one replacement of the folder (`init.py --upgrade`, a pull request in shared mode). `check` refuses session changes that touch it.


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

5. **Render `AGENTS.md`**: a stamp line with the method version (`<!-- Rendered from the PhysicsIntern method 0.4.2 … -->`), then `commons/workspace-doc.md` with `{{harness_names}}` and `{{harness_sections}}` filled from each selected host's `section.md`. When Claude Code is selected, `CLAUDE.md` is the single line `@AGENTS.md`.

The renderer is stdlib-only (Python 3.11+, `tomllib`). Placeholders are `{{key}}`; an unknown placeholder raises. Skill bodies are substituted with an empty context, so a harness-specific placeholder in a skill fails the render.

**Why skill bodies are harness-neutral.** OpenCode also reads `.claude/skills/` and `.agents/skills/`, keeping the first copy of each skill name, and Pi reads `.agents/skills/`. Identical bodies make it irrelevant which copy a harness picks, and OpenCode, which lists skills as slash commands, then shows each skill once. Everything harness-specific lives in the harness's section of `AGENTS.md` and in its agent files, which no other harness reads (verified with `opencode debug skill`, `opencode debug agent` and Pi's RPC `get_commands`).


## The workspace format

The authoritative description, as agents see it, is `commons/workspace-doc.md`. The computations are in `scripts/cards.py` and `scripts/human.py`. The design is `design/DESIGN-shared-spaces.md`. In summary, a workspace has two layers.

**The human view** is a few files the researcher reads and writes:

- `project.md`: `# <the question in one line>`, then `## Goal`, `## Approach`, `## Next steps` (a numbered list; a session takes the first, and removes it from the list when it finishes it). `parse_project` reads it; `session.py start` refuses while the title or the goal is missing.
- `conventions.md`: free text; agents may edit it.
- `draft.tex`: the draft paper. A `result` or `conjecture` environment names its claim card with `\card{CL-…}` (several cards may be named, separated by commas). `parse_draft` reads the environments, ignoring LaTeX comments.
- `sessions/S<n>/note.tex`: the note, written by the writer role in the LaTeX subset of the design (section 7).
- `sessions/S<n>/debrief.md`: plain Markdown with fixed markers: a summary, `#### Changed by this session` (filled by `session.py end`), questions `**Question N.** …` each followed by a blockquote `> **Answer:** …`, tick lines `- [ ] …` / `- [x] …`, and `#### Anything else for the next session` with `> **Note:** …`. `parse_debrief` reads it; `set_answer`, `set_ticks`, `set_note` and `set_changed` write back into it, keeping the rest; `debrief_problems` lists what is malformed.
- `literature/overview.md` (written by surveys, `## <Topic>` headings), `literature/seeds.md` and `literature/ratings.yaml` (paper card ID → high, medium, low, not relevant; written only by the researcher, through the Space).

**The record** is everything else:

- **Cards** (`claims/<id>.md`): YAML header `id`, `kind` (`claim` or `dead-end`), `statement`, `depends_on`, `produced_by` (`{kind: agent, model, operator}` or `{kind: human, user}`), `session`, `supersedes` (claims), `refutes` (dead ends); free prose body. There are no question cards: questions reach agents through debriefs. A card is edited only during the session that wrote it (`check` compares with the session's base) and never afterwards. A statement is one sentence; `check` warns above 300 characters.
- **Artefacts**: `derivations/D-S<n>-<k>.summary.md` + `.tex`; `computations/C-S<n>-<k>.md` + `.py` + `.out` (+ text data files). The summary header holds `id`, `kind` and `supports`, and no authorship, for blind review.
- **Reviews**: `derivations/<target>_R-S<n>-<k>.md` (or in `computations/`), header `id`, `kind: review`, `target`, `supports`, `claim`, `verdict`, `by`, `session`, `date`. `by` is `{kind: agent}` for a blind review, or `{kind: human, user}` for a verification by the researcher, which a session writes when a debrief reports it.
- **Paper cards** (`literature/P-<arXiv id>.md`) with `why`, `topic` and `rating` (the agent's estimate) besides the bibliographic fields; **critiques** (`critiques/CR-S<n>-<k>.md`); and **session folders**: `received.md` (front matter `session`, `started`, `base`, `previous`, and `debriefs`: per debrief read, the answers, ticked lines and note received; body: the text `session.py start` printed), `brief.md` (`goal`, `budget`, `starts_from`), `log.md` (ending with `## Handoff`), and `plan.md` when `/research-plan` ran.

**IDs** embed the session (`CL-S12-2`, `D-S12-3`, `D-S3-2_R-S12-1`); paper cards use the arXiv identifier.

**What is computed** (never stored):

| | Rule |
|---|---|
| Claim status | `refuted` if a dead end refutes it; else `revised` if a claim supersedes it; else `established` if a `result` environment of `draft.tex` names it; else `working`. |
| Evidence of a claim | Every artefact whose summary names it in `supports`, or that a review attaches by naming it in `supports`; with the reviews of that artefact that concern the claim (they name it, or name nothing while the artefact names it). A human verification is one of these reviews. |
| Needs re-check | The refuted or revised cards in the transitive closure of `depends_on`. |
| Result rule (`result_problems`) | A result of the draft names a claim that is neither refuted nor revised, with at least one supporting artefact that has a confirming review. |
| Draft flags | Cards named in the draft that are refuted, revised, missing, need a re-check, or (for results) have no confirmed evidence. |
| Debrief state | *Open* until a session's `received.md` lists it; then *closed*, "read by S<m>". |
| What a session receives (`human.received`) | Per debrief: everything, if no session has read it; otherwise the answers, ticks and note that differ from what earlier sessions recorded as received. Plus the researcher's edits of `project.md`, `conventions.md` and `draft.tex` since the previous session started (commits whose subject does not start with `[S<n>]`, and uncommitted changes), changed ratings, and the first next step. |
| Changed by this session (`human.changed_by_session`) | Per human file, the line counts and subjects of the session's own `[S<n>]` commits since its base (`[S<n>] apply the lines ticked in the S<m> debrief` reads "as you ticked in S<m>"), the diff of `conventions.md`, and the diff of the session's own edits of `draft.tex` (its commits other than apply commits, at most 60 changed lines). |

**Generated files** (git-ignored): `INDEX.md` (claims grouped by status with their evidence and place in the draft, dead ends, the draft's results and flags, artefacts, papers with their BibTeX key and ratings, sessions with their debrief state) and `references.bib` (one entry per paper card; keys `<first author's family name><year>`, and when two papers share a key the one recorded first keeps it and the others get `b`, `c`, …; each entry carries `paperid`). Both are deterministic.


## The workspace scripts

All run with `uv run .physics-intern/scripts/<script>` from a workspace, with PEP 723 inline dependencies (PyYAML; `huggingface_hub` for those that talk to the Hub). They print what they did and fail with one `ERROR:` line rather than guess; the skills tell the coordinator to stop and report such failures.

| Script | Role |
|---|---|
| `cards.py` | Library, no side effects: `Workspace` (loading, `status`, `in_draft`, `evidence`, `needs_recheck`, `draft_flags`), `result_problems`, front-matter helpers. Imported by every other script and by the Space. |
| `human.py` | Library: the parsers and writers of the human files, `History` (git access to a checkout), `received` and `format_received`, `received_record`, `previous_start`, `read_by`, `handoff`, `changed_by_session`. Stdlib and PyYAML only. |
| `regen.py` | Writes `INDEX.md` and `references.bib`. |
| `check.py` | Validates headers, ID formats, references and their kinds, cycles, artefact authorship, reviews, paper cards and ratings, the draft (`draft_problems`), the `\card` names of notes, and debriefs. With a base commit (default: the active session's): no record file edited or deleted; `.physics-intern/` and `project.toml` untouched; and for the paths the session changed itself (its `[S<n>]` commits and uncommitted changes, `common.session_paths`), no other session's folder, no seeds or ratings, new IDs that belong to the session. Problems in the draft are errors only when the session changed the draft and named the card at fault itself; problems in a debrief are errors for the session's own debrief. |
| `session.py` | `start`, `status`, `next <prefix>` / `next review <artefact>`, `answer <S> <n|note> <text>`, `tick <S> <k>…`, `brief`, `end [--no-merge]`, `abort`. State in `.active-session` (JSON, git-ignored). |
| `pdf.py` | `build_pdf(tex, bib, name)` compiles in a temporary folder with `latexmk` (dropping `\bibliography` when nothing is cited, since BibTeX fails then); the CLI writes `draft.pdf` or `sessions/S<n>/note.pdf`. |
| `hub.py` | Create and join, the session pull request lifecycle, other open sessions, sources sync, upgrades. |
| `hubgit.py` | Runs a git command with the Hub token passed in a header (for the researcher's own pushes). |
| `export_trace.py` | Collects the harness's record of a session: OpenCode's SQLite store, Claude Code's JSONL files including sub-agent transcripts; Codex rollouts and Pi sessions as raw files, best effort. Returns the models found. |
| `literature.py` | Literature tools; see below. |
| `init.py` | Create, join, refresh, upgrade; see below. |

**`session.py start`.** Refuses when a session is active, when `project.md` has no title or goal, or when the checkout has uncommitted changes; in local mode it first commits the researcher's uncommitted edits of their own files (`project.md`, `conventions.md`, `draft.tex`, seeds, ratings, debriefs) as "Researcher's edits", and refuses only for other files. It also refuses when the harness files were rendered from another method version (it re-renders and asks for a restart). It then opens the session (shared: the pull request and the branch), computes what the session receives (from the previous session's `received.md` base), writes `sessions/S<n>/received.md`, and prints it, followed by the *Handoff* of each session whose debrief it reads in full, the cards that need a re-check, the draft's flags, other open sessions (shared), and the questions without an answer.

**`session.py answer` and `tick`** write what the researcher said in the terminal into a debrief, commit it as theirs (a message without the session prefix, so that `check` does not count it as the session's), and add it to the active session's `received.md`, so that no later session receives it again.

**`session.py end`** needs `note.tex` and `debrief.md`. It writes *Changed by this session* into the debrief (a commit `[S<n>] debrief: changed by this session`), runs `check`, and in shared mode does the Hub steps below (after rebasing, so the section is computed against the latest `main`).


## Sessions and the Hub

A shared space is five private repositories in one organisation, named by `hub.repo_names`: the workspace `physics-hive-<name>` (dataset), `physics-hive-<name>-traces`, `-sources`, `-chat-debug` (datasets) and the Space `physics-hive-<name>` (the Hub keeps datasets and Spaces apart, so the workspace and the Space share the name; the Space shows the project as `<name>`). Research files are not stored in the Space repo, because every push to a Space rebuilds the app. The Space's card on the Hub is titled `[Physics Hive] <name>` and its `short_description` is the question of `project.md`, cut between words to the Hub's 60 characters (`hub.space_card`, written into the Space's `README.md` at deploy); `open_session` updates it when the question has changed, which restarts the Space, and only warns if it cannot.

**Session lifecycle in shared mode** (`scripts/hub.py`):

1. `start`: fetch `main`; refuse if local `main` has unpushed commits; `create_pull_request` (a draft; its number is the session number); rename it `[S<n>] (brief pending) by <user>`; `git checkout -B session/S<n> origin/main`; download paper sources.
2. `brief`: commit the brief and `received.md`; push to `refs/pr/<n>`; rename the pull request `[S<n>] <goal>`; replace its description with the brief.
3. `end`: rebase on `origin/main` if it moved (stop on conflict, branch unchanged); write *Changed by this session* and run `check` against `origin/main`; force-push to `refs/pr/<n>`; upload sources; export the trace and upload `S<n>/trace.jsonl` and `S<n>/meta.json`; mark the draft ready; merge (one retry after a fresh rebase); record the merge commit in `meta.json`; reset the checkout to the new `main`.

**Hub behaviours this relies on**, verified on scratch repositories before writing `session.py end`: a pull request is the ref `refs/pr/<n>` and accepts pushes and force-pushes of a rebased branch; a draft cannot be merged until `change_discussion_status(..., "open")`; **merging squashes** the pull request into one commit titled `<title> (#<n>)`, so session commits do not keep their SHAs on `main` (they stay reachable through `refs/pr/<n>`, and `meta.json` lists them with the merge commit); `create_commit(create_pr=True)` opens a ready pull request; small binary files push fine over plain git, and new repositories come with a `.gitattributes` routing many extensions to LFS, which `create` removes so that workspaces stay plain git.

**Authentication.** Git gets the token of `hf auth login` through `GIT_CONFIG_COUNT`/`http.<endpoint>/.extraHeader` for each command; it is never written to `.git/config`. The Space holds its own copy of a token, the secret `HF_TOKEN`, set by `create`. It is the token in the environment variable `PHYSICS_INTERN_SPACE_TOKEN`; if the variable is not set, `init.py` looks for it in the `.env` at the root of the method repository, which exists only when it runs from a clone of the repository (plugins do not ship one). Failing both, it is the creator's login token. `hub.space_secret` checks a dedicated token with `whoami` before anything is created, and `deploy_space` warns if it cannot read the new workspace. `--space-token env|mine|none` overrides the default. The README lists the permissions to give a dedicated Space token.

**Traces.** `meta.json` holds the session, pull request, operator, harness, declared model, models found in the trace, method version, start and end, the session's commits and the ref that keeps them, the merge commit, and a note when the export was partial.


## The init script

`scripts/init.py` (launched by `init-physics-intern.sh` and by the plugins) asks, each with a default and a flag: the mode (`--mode local|create|join`), the harnesses (`--harness`, a tick list with installed ones ticked), the folder (`--dir`), and for create the owner and name (`--org`, `--name`; the owner is one of your organisations or, listed last, your own account), for join the repository (`--repo`). `--yes` never asks; `--list-harnesses` and `--list-orgs` (the organisations, then your account) print choices for the plugins.

- **local / create**: refuse a non-empty folder (except `project.md`) and a workspace in the earlier format; copy the method; write `project.toml`, the skeletons (`project.md`, `conventions.md`, `draft.tex`, `literature/seeds.md`), the record folders and the committed `.gitignore`; render; first commit; regen. **create** then creates the repositories, fetches the Hub's initial commit and builds on it (dropping its `.gitattributes`), pushes, and deploys the Space (`space/` from the method copy, with the variables `PHYSICS_INTERN_WORKSPACE` and `CHAT_DEBUG`, and the secret `HF_TOKEN`, chosen as described under *Authentication* above). A personal namespace is accepted with a warning, for trying shared mode alone.
- **join**: clone into an empty folder, then render the selected harnesses from the clone's method copy.
- **inside a workspace**: render the selected harnesses plus those already rendered (to add one or refresh); `--upgrade` replaces the method copy with the running script's copy (a commit in local mode, a pull request in shared mode). It refuses a workspace of the 0.3 format (`problem.md` without `project.md`), which this method does not convert.


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

Every role body follows the same contract: what you receive and read (and what you must not read); your artefact(s), with their header and sections; behaviour; the **return block** `## Summary` / `## Result` / `## Flags` (with `- (none)` when empty), identical at the top of the artefact and in the final reply (the surveyor, the planner and the writer, whose files the researcher or the coordinator reads as they are, return it in the reply only); constraints (write only your files; never cards, the session folder or the researcher's files). Artefact headers carry no authorship.

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

`space/` is a small FastAPI app that serves plain HTML pages, deployed as a private Docker Space by `init --mode create` (`hub.deploy_space`): `backend.py` (workspace access, the data of every page, every write; no web code), `app.py` (the routes, Markdown rendering and the forms), `latex.py` (a converter from the LaTeX subset of notes and the draft to HTML), `latex.css`, `templates/` (Jinja pages; `base.html` holds the style), `Dockerfile` (Python, git, `latexmk` and a small TeX Live), `README.md` (Space metadata: Docker SDK, port 7860, OAuth) and `requirements.txt`. `tests/test_space_backend.py` covers the backend, the Hub store and the pages.

- **Pages** (design, section 14). `/` *Latest*: the debriefs, newest first; open ones as forms (an answer box per question, a checkbox per tick line, the note box; one Save per debrief), closed ones folded to one line ("read by S3 on …") but still editable, since the next session receives what changes. An open debrief carries the label *active*, and the page is titled *Latest session debrief*. `/project`: `project.md` and `conventions.md`. `/draft`: the draft with a contents column, the draft's flags, a PDF button and `/draft/edit` (the source beside a preview that `/preview` re-renders as you type). `/sessions`: one row per session (the title and the first sentence of the abstract of its note); `/note/<S>` renders a note, with its PDF and source. `/literature`: the overview, then the papers grouped by the overview's topics, each with its `why` and a rating menu; then the seeds. Record pages: `/card/<id>`, `/paper/<id>`, `/session/<S>` (what it received, its brief, cards, artefacts, log), `/file/<path>`. Editors: `/edit/<path>` for `project.md`, `conventions.md`, `literature/seeds.md` and any debrief (raw Markdown); *Discard my changes* returns to the page the file is shown on.
- **Rendering.** Markdown is rendered on the server with `markdown-it-py` (raw HTML and HTML comments are not shown); LaTeX by `latex.py`; math by MathJax 3 in the browser (`\(…\)`, `\[…\]` and equation environments, numbered with `tags: 'ams'`). In Markdown, every existing card, paper, artefact and session ID and every workspace path in a code span becomes a link; a session ID opens its note. In LaTeX, `\card{…}` links to the card page, a citation's entry links to its paper card (through `paperid` in `references.bib`), and in the draft a result whose card is refuted, revised or in doubt carries a warning.
- **Data.** In the deployed Space, `HubStore` keeps a bare git clone of the workspace (token passed in a header), fetches `main` on a page view when the last load is older than two minutes, on *Load the latest version* and after each write, and checks out each commit in its own git worktree (the last three are kept), so that pages read a fixed state and `human.received` can read the history. The method's modules (`cards`, `common`, `human`, `regen`, `check`, `pdf`) are imported from the snapshot's `.physics-intern/scripts/` (restoring `sys.path` and `sys.modules` afterwards), so everything is computed by the workspace's own method version. `references.bib` is rendered in memory, never written.
- **Writes.** The researcher's answers, ticks and note (`save_debrief`, which re-reads the debrief and refuses if it changed since the form was loaded), edits of their files (`save_file`; a draft that adds a result the workspace's `check` refuses is not saved), and ratings (`rate`, which rewrites `literature/ratings.yaml`). Each is one commit to `main` through the Hub API with `parent_commit` set to the commit the page was built from, with the signed-in user in the message. The Space applies nothing.
- **Identity.** Hugging Face sign-in (`attach_huggingface_oauth`, `parse_huggingface_oauth`). On huggingface.co the Space runs in a sandboxed frame that may not navigate the whole page (a `target="_top"` link does nothing) and in which browsers block the sign-in cookie, so when the page is framed the sign-in links open a new tab, as the Hub's OAuth documentation advises. The Hub's sign-in pages send `Cross-Origin-Opener-Policy: same-origin`, which cuts the link between the two tabs, so they cannot talk to each other: the new tab lands on `/signed-in` (signed in, with a button to close the tab), and the framed page asks `/whoami` every two seconds for five minutes and reloads once the sign-in shows. In a browser that keeps cookies out of frames (Safari by default), the framed page never sees the sign-in, and the researcher works in the new tab. Opening the Space at its own address (`https://<org>-physics-hive-<name>.hf.space`, printed by `create`) avoids the frame altogether. Anyone signed in (a member of the organisation, since the Space is private) may write. Forms carry a token tied to the session, so that another site cannot post them.
- **Local mode**: `PHYSICS_INTERN_LOCAL=<workspace> PHYSICS_INTERN_LOCAL_USER=<name> uvicorn app:app --reload` in `space/` reads a local folder and writes files into it without committing; the next `session.py start` commits them as the researcher's.
- **The LaTeX converter** (`latex.py`) handles the subset agents are told to use, documented in its docstring; anything else is rendered as text and listed in `Rendered.problems`. The design proposed LaTeXML; the Space uses this converter for both the preview and the saved page, because it is fast enough to run on every view, has no system dependency, and keeps the preview and the page identical. If notes need more than the subset, LaTeXML can replace it behind the same `render` function.


## Literature tools

`scripts/literature.py` is both a CLI and an MCP server (`literature.py mcp`, stdio, tool names with underscores), so that it works in every harness: `search-inspire`, `search-arxiv`, `references`, `citations` (INSPIRE when the paper is a core INSPIRE record, Semantic Scholar otherwise), `download` (arXiv LaTeX source preferred, PDF otherwise, extracted into `literature/sources/<id>/` with links, absolute and `..` paths skipped), `card` (a paper-card skeleton with the header filled; only the card goes to stdout, so it can be redirected into `literature/P-<id>.md`), and `search-cards` (keyword search over paper cards, the literature overview and card statements). The card skeleton has empty `why`, `topic` and `rating` fields, which the surveyor fills. Papers are named by arXiv identifier (with or without version, old or new style, or a paper-card ID) or `insp:<INSPIRE record>`. Every command takes `--json`; errors are one `ERROR:` line. arXiv requests are spaced by 3 seconds, also across runs; `SEMANTIC_SCHOLAR_API_KEY` raises the Semantic Scholar rate limit. Claude Code, Codex and OpenCode get the server through their extras; Pi has no MCP support, and the surveyor role says how to call the CLI instead. `init` installs the script's dependencies once (skipped when `PHYSICS_INTERN_NO_WARMUP` is set), so that the harnesses' first start of the server fits in their startup timeout. In shared mode, sources are synced with the `-sources` dataset at session start and end.


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
uv run --no-project --with pytest --with httpx --with-requirements space/requirements.txt --with "mcp>=1.12,<2" pytest -q tests/
```

Without `fastapi` and `httpx`, the test of the Space's pages is skipped.

- `tests/test_cards.py`: status precedence (the draft's results make claims established), evidence (artefacts, attached artefacts, human verifications), propagation of needs re-check, deterministic regeneration, stable BibTeX keys, the result rule, and the check rules (headers, references, cycles, immutability against a base and corrections within a session, session rules applied only to the session's own commits, the draft blamed on the session only for what it did, notes and debriefs).
- `tests/test_human.py`: `project.md`, parsing and writing back debriefs, the draft's environments, what a session receives (in full, then only what changed after a session recorded it), and *Changed by this session*.
- `tests/test_local_flow.py`: the acceptance test of phase A, through the real scripts: init, then three local sessions in which the researcher only edits debriefs and `project.md` in an editor. Each decision is applied by the session after it; a result copied into the draft shows as established; an unreviewed result is refused by `check`; a question answered in the terminal is recorded as the researcher's; an edited card is refused at the end.
- `tests/test_space_backend.py`: the Space's backend in local mode, the Hub store against a local git repository with a fake API, and every page and form through a test client.
- `tests/test_latex.py`: the LaTeX converter on a real note and a sample draft.
- `tests/test_space_token.py`: which token `create` stores in the Space (`PHYSICS_INTERN_SPACE_TOKEN`, the login token, or none), with a fake Hub client.
- `tests/test_export_trace.py`, `tests/test_literature.py`, `tests/test_reviewer_bench.py`: the trace exporter, the literature tools without network, the benchmark in dry-run mode.
- `tests/ACCEPTANCE.md` maps each acceptance test of the design's build plan to how it is checked, and gives the steps of those that need real agents.
- `tests/hub_e2e.py` (manual, live, not collected by pytest): creates scratch repositories under your account and runs the shared-mode flow with two operators: parallel sessions adding evidence to the same claim, a rebase, merges, a debrief answered through the API and received by the next session, an abort. It deletes the repositories at the end. `uv run tests/hub_e2e.py [--keep]`.


## Design choices worth remembering

- **Two layers.** The record is complete and for agents; the human view is a handful of files for the researcher (`project.md`, `conventions.md`, the draft, one note and one debrief per session, the literature overview). The same document never serves both readers.
- **The researcher decides through files, at session boundaries.** Answers, ticks and notes in a debrief take effect when the next session starts; agents never change the meaning of what the researcher wrote, and every change they make to a human file is listed in their debrief, from git.
- **What a session receives is computed, not remembered.** From git and the files: everything written since the previous session started, minus what earlier sessions recorded as received in their `received.md`. A note written while a session runs reaches the session after; a tick is never applied twice.
- **Established means: in the draft as a result.** The researcher decides what enters the draft; `check` keeps the bar (a confirming review of a supporting artefact). Sessions merge without the researcher, because a merge endorses nothing.
- **Research files and harness files are separated.** Harness files are rendered locally from the method copy and git-ignored; only research content and the method copy are shared.
- **The method is copied into each workspace**, so that every checkout and the Space run the same prompts, and the prompts sit in history next to the results.
- **One file per item, never edited once its session ends.** Status and evidence are computed by `regen`, so parallel sessions add files and never edit the same file. The human files are the exception, edited by the researcher and, as ticked, by sessions.
- **Deterministic work is done by scripts, not prompts.** IDs (`session.py next`), views, validation, what a session receives, the debrief's *Changed by this session*, the pull request lifecycle, uploads, PDFs. Models keep the judgment.
- **Draft pull requests as claims.** Unique numbers without a shared counter, and the open sessions are visible.
- **A branch in the checkout, not a worktree.** Harness files are git-ignored and the harness runs in the checkout; one checkout holds at most one session.
- **Blind review.** Reviewers get the artefact and the claim's statement, never who produced it nor earlier verdicts; tests with a clear outcome come before opinions, and "no issue found" is a respected outcome.
- **Fresh context and second opinions.** The note is written by a fresh writer, for a reader who was not there; no single verdict changes direction; a refutation becomes a dead-end card only after a second, independent review agrees.
- **Do not over-engineer the skills.** Prompts as short as they can be while effective; the audit skill catches drift.


## Adding a host, an agent or a skill

**A host** is a folder `hosts/<host>/` with `host.toml`, `section.md` and optional `extras/`. Then add it to `HOST_ORDER` in `commons/render.py`, to `HARNESSES` and `RENDER_MARKS` in `scripts/init.py` and `scripts/common.py`, to `detect_harness()` and to an exporter in `scripts/export_trace.py` if its record format is known. Render a workspace for it together with another harness and check that neither picks up the other's files.

**An agent** is one file in `commons/agents/`; **a skill** is one file in `commons/skills/` (its agent must exist). Add the skill to the list in `commons/workspace-doc.md` §6 and to the table in `README.md`. Render for every host before committing:

```bash
python3 commons/render.py --hosts=claude,codex,opencode,pi --target=/tmp/render-all
```


## Auditing a run: investigate-run

`.claude/skills/investigate-run/SKILL.md` is a repo-level skill that audits a workspace and its session record (harness JSONL, OpenCode's SQLite store, or the trace in the traces dataset for shared sessions) and writes a post-mortem to `/tmp/audit-<workspace>.md`. It detects the workspace format: for card-based workspaces it audits ten promises (coordinator only, valid immutable cards, robust evidence behind promotions or, from method 0.4, behind the draft's results, blind test-based review, review after every artefact, the integration loop, edit scope, return schema, session discipline, scripts not bypassed), plus, from 0.4, the researcher's attention (the size and content of notes and debriefs, and whether ticked lines were applied exactly once); legacy workspaces keep their rules. Update it when the method's contract changes.


## Validation workflow

1. Edit the source (`commons/`, `hosts/`, `scripts/`, `space/`).
2. Run the tests, and render a workspace for every host and read the result.
3. Run a benchmark problem in a fresh local workspace (often `/autoresearch`), or a shared session on a scratch space.
4. Audit it with `investigate-run`, and compare with earlier audits in `results/`.
5. Commit the source change together with any audit-rule change.

Changes reach a workspace only through its method copy: new workspaces get the current version; existing ones get it with `init.py --upgrade`.
