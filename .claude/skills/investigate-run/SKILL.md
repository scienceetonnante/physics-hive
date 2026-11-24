---
name: investigate-run
description: Post-mortem analysis of a PhysicsHive workspace run (Claude Code, Pi, Codex, or OpenCode host). Reconstructs the trajectory from the session record — JSONL file(s) for Claude/Pi/Codex, the SQLite store for OpenCode, or the trace uploaded to the traces dataset of a shared space — audits methodology adherence against the workspace's own AGENTS.md and skill/agent prompts, checks commit discipline, flag dispositions and what the lead was asked to read, and assesses substantive quality. Produces a thorough evidence-anchored markdown report. Use after a workspace has been worked on to identify what went well, where the methodology slipped, and what prompts to improve.
context: fork
agent: general-purpose
arguments: [workspace_path, session_id]
---

# Investigate PhysicsHive Run

You are auditing a PhysicsHive workspace run. Four sources:

1. **The workspace** at `$workspace_path` — files, git history, and the method copy `.physics-hive/` the run operated under.
2. **The session record** — every prompt, response, and tool call from the run: a main-agent JSONL plus one JSONL per sub-agent for Claude Code, Pi and Codex; a **single SQLite database** (rows keyed by session, not files) for OpenCode. In a shared space, each session's record is also in the traces dataset. See *Host detection and session locations* below.
3. **The methodology contract** — the workspace's `AGENTS.md` and its rendered roles and skills (`.claude/agents/` and `.claude/skills/`, `.codex/agents/` and `.agents/skills/`, `.opencode/agents/` and `.opencode/skills/`, `.pi/agents/` and `.pi/prompts/`). These are the rules the run is audited against. The rendered files are git-ignored and may have been re-rendered since the run: the authoritative prompts are those of the method copy at the session's commits (`git show <commit>:.physics-hive/commons/skills/<name>.md`), and the stamp at the top of `AGENTS.md` gives the version the harness loaded. (Optional: the canonical sources in this repo's `commons/` and `hosts/<host>/`, for cross-reference.)
4. **Reference solution** (if available) — a known answer to the problem, documented in `references/`, for a calibration run. This is a quality check, not a methodology requirement: say honestly whether the run's results are correct, partially correct or wrong, but focus on the process.

## The workspace

A PhysicsHive workspace has `project.toml`, `project.md` and `.physics-hive/` at its root. Check this first: a folder without them, or with `problem.md`, `research_log.md` or `notes/flags.md` instead, was made by Physics Intern or an earlier version of the method, and this skill does not audit it. Say so and stop.

- **The human view**: `project.md` (the question as its title, then *Goal*, *Approach*, *Next steps*), `conventions.md`, `draft.tex`, and per session `sessions/S<n>/note.tex` and `debrief.md`; `literature/overview.md`, `seeds.md` and `ratings.yaml`.
- **The record**: cards in `claims/` (claims `CL-S<n>-<k>`, dead ends `DE-S<n>-<k>`); artefacts in `derivations/` (`D-S<n>-<k>.summary.md` and `.tex`) and `computations/` (`C-S<n>-<k>.md`, `.py`, `.out`), with their briefs in `.briefs/` and their reviews `<artefact>_R-S<m>-<j>.md`; critiques `critiques/CR-S<n>-<k>.md`; paper cards `literature/P-<id>.md`; and per session `received.md`, `brief.md`, `log.md` and, when `/research-plan` ran, `plan.md`.
- **Generated and git-ignored**: `INDEX.md` and `references.bib`. Regenerate them with `uv run .physics-hive/scripts/regen.py` rather than trusting a stale copy.
- **Decisions**: a claim is *established* when a `result` environment of `draft.tex` names its card (`\card{CL-…}`). There are no question cards: the lead decides through answers, ticks and notes in debriefs, and the next session applies the ticked lines.
- **Roles**: the lead sets the question, answers the debriefs and decides what enters the draft; the contributor runs sessions in a terminal and confirms the brief. One person can be both. Workspaces made before 0.6.0 say "researcher" and "operator", and their commits for the lead's edits start with "Researcher's" instead of "The lead's".
- **Harness and version**: the workspace may be rendered for several harnesses at once (one `AGENTS.md`, a one-line `CLAUDE.md`). The harness a session ran under is in the first line of its `log.md` (`Started … by <contributor> with <harness> (<model>).`), in `.active-session` while it runs, and in the trace's `meta.json`. The method version is in `project.toml` and `.physics-hive/VERSION`.
- **Shared mode** (`[hub]` filled in `project.toml`): each session is a pull request on the Hub. The squash merge leaves one commit per session on `main`; the per-dispatch commits stay on `refs/pr/<n>` (`git fetch origin refs/pr/<n>`). The traces dataset named in `[hub] traces` holds `S<n>/trace.jsonl` (the exported harness record) and `S<n>/meta.json` (the contributor, under the key `operator`; harness, models, method version, the session's commits, the merge commit, the tokens each model used in `tokens_by_model`, and the number of secrets replaced in the trace in `trace_redactions` and `trace_redactions_by_kind`). Download them with `hf download <traces repo> --repo-type dataset --include "S<n>/*" --local-dir /tmp/trace-S<n>`.

## The promises

Audit the run against these eleven promises.

1. **Coordinator only.** The coordinator dispatches sub-agents; it never performs substantive surveys, derivations, computations, reviews or critiques itself, and never writes the note.
2. **Cards are immutable and well-formed.** `uv run .physics-hive/scripts/check.py` passes (errors are findings; read its warnings too, e.g. "reserved ID never written"). Nothing in `claims/`, `derivations/` or `computations/` is edited or deleted after the session that created it; within that session, correcting a card in place is expected. Refutations are dead-end cards; revisions of earlier sessions' claims are superseding cards. A claim states one assertion about the physics in one sentence and comes from a derivation or a computation; the survey's findings stay in the overview and the paper cards. A literature summary written as a claim, or a superseding card that only fixes the wording of a card from the same session, is a finding.
3. **Robust evidence before the draft.** Every claim named by a `result` environment of `draft.tex` got there by a line the lead ticked (find the tick in the debrief named by the apply commit `[S<n>] apply the lines ticked in the S<m> debrief`) or by the lead's own edit, and the tick line said how robust its evidence was. A session that copies a result nobody ticked, or copies a result whose claim has no confirming review instead of offering it as a conjecture, fails. Note a result whose evidence comes from a single dispatch context (one artefact, whose internal cross-checks count as one), unless the tick line or the note says why only one approach is available.
4. **Blind, fresh-context review.** Reviewer dispatches pass the artefact, the claim's **statement**, the card IDs for `supports` and the output path — not the card's path, not the model or contributor, not earlier verdicts. Reviews start with tests that have a clear outcome (dimensions, limits, symmetries, numerical spot checks) and give each remark a location and a severity (*breaks the result*, *weakens it*, *cosmetic*). Reviewers do not read `claims/`, `sessions/`, `INDEX.md` or other reviews of the target. Critics receive only one-line summaries of earlier critiques.
5. **Review after derive and compute.** Every artefact has at least one review file `<id>_R-S<n>-<k>.md`, or the log records why the review was deferred.
6. **Integration loop.** After every return, the coordinator writes the cards, dispositions every flag in `sessions/S<n>/log.md`, logs the dispatch, runs regen, and makes **one commit** prefixed `[S<n>]` that bundles the artefact, the cards and the log. Sub-agents do not commit.
7. **Edit scope.** The coordinator writes `claims/`, the current session folder, the briefs and critique resolutions. It edits `conventions.md` only when the work fixes a convention; `project.md` only to apply ticked lines (one commit per debrief) or to remove the step its session finished; and `draft.tex` only to apply ticked lines or when a next step asks for it. It never edits another session's folder (debriefs included: the lead's answers are theirs, except through `session.py answer` and `tick`), `literature/seeds.md`, `literature/ratings.yaml`, artefacts or `.physics-hive/`.
8. **Return schema.** Both (8a) the artefact on disk and (8b) the reply the coordinator receives carry `## Summary` / `## Result` / `## Flags`, with empty flags written `- (none)`; the surveyor, the planner and the writer return the block in the reply only. Extra sections (e.g. `## Recommended next steps`) violate the schema. The two channels drift independently: usually the artefact is fine and the reply is prose. Flags are proposals; the coordinator records each disposition in the session log.
9. **Sessions.** `received.md` exists and was read: the ticked lines are applied before the brief, and unanswered questions were shown to the contributor before the brief. The brief (`goal`, `budget`) takes the first next step of `project.md` unless the contributor chose otherwise, and the contributor confirmed it before the first dispatch. The dispatch count stays within the budget, and the session stops at the first stop condition (goal reached, budget spent, four dispatches in a row without progress, `project.md` should change). The note was written by a dispatched `writer` sub-agent, is two to four pages, and names its results' cards. The debrief has a short summary, only the questions the lead alone can answer, concrete tick lines and an empty note box, and no process detail. The log ends with `## Handoff`. IDs come from `session.py next`, so there are no collisions or reused numbers.
10. **Scripts, not improvisation.** The session's pull request, pushes, trace upload, merge and *Changed by this session* go through `session.py`. A coordinator that pushes, merges, rebases or uploads by hand, edits `.active-session` or `received.md`, or writes *Changed by this session* itself, is a finding, even when the result looks fine.
11. **The lead's attention.** Count the words of the note and the debrief, the number of questions and tick lines, and how many of them were routine (adopt a convention, a threshold, a library) rather than decisions only the lead could take. The target is one note and one debrief per session that the lead can read and answer in a few minutes. Compare the debrief with what the note and the log say: a decision the session needed but did not ask, or a question it could have settled itself, is a finding.

## Inputs

- `$workspace_path` (required): path to the workspace directory (e.g. `workspaces/helmholtz-2`).
- `$session_id` (optional): UUID of the harness session. If omitted, auto-discover based on host (see below).

If `$ARGUMENTS` is empty, ask the user for the workspace path.

## Host detection and session locations

First detect which harness ran the session. A workspace is often rendered for several harnesses, so several of `.claude/`, `.codex/`, `.opencode/` and `.pi/` can exist at once: take the harness from the first line of the session's `log.md` or from the trace's `meta.json`, and use the matching location below.

- **Claude Code**: main-agent JSONL at `~/.claude/projects/<encoded>/<uuid>.jsonl`; the transcript of each sub-agent dispatched with the `Task` tool at `~/.claude/projects/<encoded>/<uuid>/subagents/*.jsonl`.
- **Pi**: **both main and sub-agent JSONLs live under `~/.pi/agent/sessions/`** — main-agent at `~/.pi/agent/sessions/<encoded>/<timestamp>_<uuid>.jsonl`, and per-sub-agent JSONLs **nested under a sibling dir with the same basename** (timestamp + uuid, no `.jsonl`): `~/.pi/agent/sessions/<encoded>/<timestamp>_<uuid>/<short-id>/run-N/session.jsonl` (one `<short-id>` subdir per dispatched sub-agent, `run-N` for retries). Audit both: the main agent shows orchestration decisions, the sub-agents show what each one actually did. A sibling `<encoded>/subagent-artifacts/` dir holds `<short-id>_<agent>_<n>_{input,output,meta}` triples — useful as a fast summary parallel to the JSONLs.
- **Codex**: sessions are **date-organised, not workspace-organised** — JSONLs live at `${CODEX_HOME:-~/.codex}/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl`. Discover the main-agent session by reading the first record of candidate files and matching `cwd` against the workspace absolute path. **Two schemas exist**: current Codex (`multi_agents_v2`) uses top-level `type=="response_item"` / `type=="event_msg"` / `type=="session_meta"` with `cwd` at `.payload.cwd`; older Codex builds use `item.type` tags (`SessionMeta`/`FunctionCall`/`EventMsg`) with `cwd` at `.item.cwd`. Sub-agent activity lives in **separate JSONL files** under the same date tree; linkage is the child UUID inside `close_agent.arguments.target` (current) or `CollabAgentSpawnBegin.child_thread_id` (older), which matches the child JSONL's filename suffix.
- **OpenCode**: there are **no JSONL files** — OpenCode keeps everything in one SQLite database at `${XDG_DATA_HOME:-~/.local/share}/opencode/opencode.db`. The trajectory lives across three tables: `session` (one row per main agent or sub-agent; `directory` = workspace abs path, `parent_id` = the dispatching main session for sub-agents, `agent` = `build` for the main agent or the role name for a sub-agent, plus `model`, `cost`, `tokens_*`), `message` (one row per turn, `data` JSON carries `role`/`modelID`/`tokens`/`finish`), and `part` (`data` JSON carries `type` ∈ `text`/`reasoning`/`tool`/`patch`/`step-start`/`step-finish`; tool parts hold `.tool`, `.state.status`, `.state.input`, `.state.output`, `.state.error`). **Discover by `session.directory`, not by project** — a single workspace re-initialised N times spawns N `project` rows for the same path, so `WHERE directory = '<abs path>'` is the only robust key. Expect **multiple main (`build`, `parent_id IS NULL`) sessions** per run (context clears, restarts) — the git commits are the canonical spine; union all main sessions for the directory and order by `time_created`.

The encoded path uses `/` → `-`. Claude Code drops the leading `/`; Pi preserves it with a leading `--` (verify by `ls ~/.pi/agent/sessions/`). Codex does not encode the workspace path into the filename at all — filter by `.payload.cwd` (current) / `.item.cwd` (older) instead. OpenCode does not use the filesystem for sessions at all — query the SQLite `session.directory` column.

In a shared space, when the contributor's machine is not available, use the trace from the traces dataset instead: `S<n>/trace.jsonl` wraps every record as `{"source", "record"}`, merging the main conversation and the sub-agent transcripts into one file; `source` says where each record came from (a harness file, or a table of OpenCode's database). Before the upload, `export_trace.py` replaced the secrets it recognised with markers such as `[REDACTED:huggingface-token]`: such markers are expected and are not a defect of the run, and their count is in `meta.json` (`trace_redactions`). A record that could not be written is replaced by a placeholder and counted in `trace_records_omitted`. The token counts per model (`tokens_by_model`) give the size of each session; quote them under *Run shape*.

### Auto-discovery snippet (bash)

```bash
WS="$workspace_path"
HOST=$(head -1 "$WS/sessions/S<n>/log.md" | grep -oE 'with (claude|codex|opencode|pi)' | cut -d' ' -f2)
case "$HOST" in
claude)
  ENCODED=$(echo "$WS" | sed 's|/|-|g')
  SESSION_DIR="$HOME/.claude/projects/${ENCODED}"
  if [ -n "$session_id" ]; then
    JSONL="${SESSION_DIR}/${session_id}.jsonl"
  else
    JSONL=$(ls -t "${SESSION_DIR}"/*.jsonl 2>/dev/null | head -1)
  fi
  SUBAGENT_LOGS="${JSONL%.jsonl}/subagents"   # one JSONL per Task dispatch
  ;;
pi)
  # Pi encodes the workspace path with `/` → `-` and a `--` wrap on each side
  # (e.g. `--Users-david-...-qec--`). Glob rather than reconstruct.
  WS_BASENAME=$(basename "$WS")
  SESSION_DIR=$(ls -d "$HOME/.pi/agent/sessions/"*"${WS_BASENAME}"* 2>/dev/null | head -1)
  JSONL=$(ls -t "${SESSION_DIR}"/*.jsonl 2>/dev/null | head -1)
  # Sub-agent JSONLs are nested under a sibling dir named after the full JSONL
  # basename (timestamp + uuid, no .jsonl extension):
  #   $SESSION_DIR/<timestamp>_<uuid>/<short-id>/run-N/session.jsonl
  SUBAGENT_LOGS="${JSONL%.jsonl}"
  ;;
codex)
  # Codex sessions are date-organised under ~/.codex/sessions/YYYY/MM/DD/
  # — not keyed by workspace. Filter all candidates by cwd, then pick the most
  # recently-modified. Current schema puts cwd at .payload.cwd; older at .item.cwd.
  SESSION_ROOT="${CODEX_HOME:-$HOME/.codex}/sessions"
  if [ -n "$session_id" ]; then
    JSONL=$(find "$SESSION_ROOT" -name "*${session_id}*.jsonl" 2>/dev/null | head -1)
  else
    matches=$(find "$SESSION_ROOT" -name "rollout-*.jsonl" 2>/dev/null | while read -r f; do
      cwd=$(head -1 "$f" 2>/dev/null | jq -r '.payload.cwd // .item.cwd // empty' 2>/dev/null)
      [ "$cwd" = "$WS" ] && echo "$f"
    done)
    JSONL=$(printf '%s\n' "$matches" | xargs ls -t 2>/dev/null | head -1)
  fi
  # Sub-agent JSONLs are discovered from spawn/close events in the main JSONL
  # (each carries a child UUID matching the per-child filename suffix).
  SUBAGENT_LOGS="$SESSION_ROOT"
  ;;
opencode)
  # OpenCode stores everything in one SQLite DB — there is no JSONL. Discovery
  # is a SQL query on session.directory, NOT filesystem globbing.
  OC_DB="${XDG_DATA_HOME:-$HOME/.local/share}/opencode/opencode.db"
  JSONL=""              # not applicable; use $OC_DB
  sqlite3 "$OC_DB" "SELECT count(*) FROM session WHERE directory='$WS';" 2>/dev/null
  ;;
esac
```

If `$JSONL` is missing or empty (or, for OpenCode, `$OC_DB` is absent or has no rows for `$WS`), use the trace from the traces dataset in a shared space; otherwise do the analysis from the workspace and git history alone, and note the gap in the report.

## Procedure

Execute in order. Use `jq`, `grep`, `git`, and `Read` liberally.

### Step 1 — Sanity checks and scope

- Confirm that `$workspace_path` is a PhysicsHive workspace (see *The workspace*) and find the harness of each session to audit.
- Read `AGENTS.md`, the role prompts and the skill prompts the run used — from the method copy at the session's commits, since the rendered files may have changed since. The audit's contract is what these say, not what this repo's current sources say; note any divergence.
- Size the transcript: `wc -l "$JSONL"` (Claude/Pi/Codex). For OpenCode, count rows instead: `sqlite3 "$OC_DB" "SELECT count(*) FROM part WHERE session_id IN (SELECT id FROM session WHERE directory='$WS');"`. If huge, plan to sample.
- Capture the run's shape: sessions, dispatches, artefacts and cards, commits, and the wall-clock from the first to the last record.

### Step 2 — Trajectory reconstruction

The schema differs by host — pick the right extractor.

**Claude Code.** Each line is an event with `.type` (`user`, `assistant`, …) and `.timestamp`. Tool calls are items of `.message.content[]` with `type=="tool_use"` (`id`, `name`, `input`) in assistant events; their results are items with `type=="tool_result"` (`tool_use_id`, `content`) in later user events. Sub-agent dispatches are `tool_use` items named `Task` (`Agent` in recent versions), with `input.subagent_type` (the role), `input.description` and `input.prompt`. Each sub-agent's own activity is in its file under `$SUBAGENT_LOGS`.

```bash
jq -c 'select(.type=="assistant") | .timestamp as $ts | .message.content[]? | select(.type=="tool_use") | {ts:$ts, id, name, input}' "$JSONL" > /tmp/calls.jsonl
jq -c 'select(.name=="Task" or .name=="Agent")' /tmp/calls.jsonl > /tmp/dispatches.jsonl
jq -c 'select(.type=="user") | .timestamp as $ts | .message.content[]? | select(.type=="tool_result") | {ts:$ts, id:.tool_use_id, content}' "$JSONL" > /tmp/results.jsonl
```

For each dispatch: capture `dispatch_ts`, the role, the prompt, and the result with the same ID (`return_ts` and the reply the coordinator integrated).

**Pi.** Tool calls are nested inside `message` events: `.message.content[].type == "toolCall"`. Sub-agent dispatches use `name == "subagent"`, with `.arguments.tasks[].agent` (e.g. `surveyor`, `deriver`), `.arguments.tasks[].task` (the dispatch brief) and `.arguments.tasks[].output` (the artefact path). The sub-agent's full activity log is **in its own JSONL**, not in the main-agent JSONL.

```bash
# Main-agent dispatches
jq -c 'select(.type=="message") | .message.content[]? | select(.type=="toolCall" and .name=="subagent")' "$JSONL" > /tmp/dispatches.jsonl

# Each sub-agent's journal: $SUBAGENT_LOGS/<short-id>/run-N/session.jsonl (run-1, run-2 for retries)
```

For each Pi `subagent` call: capture `dispatch_ts` (from the enclosing message), the agent name and the task body, and read the sub-agent's `session.jsonl` for its full trajectory and its structured return.

**Codex.** Two schemas exist — sniff before extracting:

```bash
jq -r '.type // .item.type' "$JSONL" 2>/dev/null | sort -u | head
```

If the top-level keys are `response_item` / `event_msg` / `session_meta` (lowercase tagged), the run is on **current Codex** (`multi_agents_v2`). If they're `SessionMeta` / `FunctionCall` / `EventMsg` (PascalCase under `.item.type`), it's an **older Codex build** — use the second `jq` below.

**Current schema.** Main-agent tool calls split across two `payload.type` values:

- `function_call` — used by `exec_command`, `spawn_agent`, `wait_agent`, `close_agent`, and a few others.
- `custom_tool_call` — used by `apply_patch` (a freeform Lark-grammar tool, distinct from `function_call`).

The tool inventory is essentially: `exec_command` (shell — Codex's **only file-read primitive**, used via `sed -n`, `cat`, `rg`, `ls`, `find`, `git`), `apply_patch` (the dedicated edit tool), and the `spawn_agent` / `wait_agent` / `close_agent` triple for sub-agent orchestration. **There is no native `read_file` / `edit_file` / `write_file` / `grep` / `glob`** — every file read is a shell call.

```bash
# All main-agent tool calls (both payload kinds)
jq -c 'select(.type=="response_item" and (.payload.type=="function_call" or .payload.type=="custom_tool_call"))
       | {ts:.timestamp, name:.payload.name, kind:.payload.type, args:.payload.arguments}' "$JSONL" > /tmp/calls.jsonl

# Sub-agent dispatch lifecycle (spawn / wait / close)
jq -c 'select(.type=="response_item" and .payload.type=="function_call"
              and (.payload.name=="spawn_agent" or .payload.name=="wait_agent" or .payload.name=="close_agent"))' "$JSONL" > /tmp/dispatches.jsonl

# For each close_agent, the child UUID locates the per-agent JSONL:
#   target=$(echo "$args" | jq -r '.target')
#   find "${CODEX_HOME:-$HOME/.codex}/sessions" -name "*${target}*.jsonl"
```

**Older schema.** Each line is `{timestamp, item}` with `item.type` in `FunctionCall` / `FunctionCallOutput` / `EventMsg`. Sub-agent dispatches appear as `EventMsg` items with `msg.type` in `CollabAgentSpawnBegin` / `CollabAgentSpawnEnd` etc., carrying the child `thread_id`:

```bash
jq -c 'select(.item.type=="FunctionCall") | {ts:.timestamp, name:.item.name, args:.item.arguments}' "$JSONL" > /tmp/calls.jsonl
jq -c 'select(.item.type=="EventMsg" and (.item.msg.type | startswith("CollabAgent")))' "$JSONL" > /tmp/dispatches.jsonl
```

**OpenCode.** No JSONL — query the SQLite store. Open it **read-only** (`mode=ro&immutable=1`) and parse the JSON columns with Python (sqlite3's CLI mangles multi-line JSON). The session tree is explicit: main sessions are `parent_id IS NULL`, sub-agents are `parent_id = <main session id>`, so linkage needs no UUID matching (unlike Codex). Sub-agent dispatches also appear in the **main** session as `part.data.type=="tool"` with `tool=="task"` — `state.input.subagent_type` is the role, `state.input.description` the task slug, and `state.status` is `completed` or `error` (OpenCode surfaces dispatch errors here).

```python
import sqlite3, json, os
WS = os.environ["WS"]
db = os.path.expanduser(os.environ.get("OC_DB", "~/.local/share/opencode/opencode.db"))
con = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True); con.row_factory = sqlite3.Row

sessions = list(con.execute(
    "SELECT id,parent_id,agent,title,model,cost,tokens_output,time_created "
    "FROM session WHERE directory=? ORDER BY time_created", (WS,)))
mains = [s for s in sessions if not s["parent_id"]]          # the build sessions (often >1)

def parts(sid):                                              # ordered trajectory for a session
    return [json.loads(r["data"]) for r in con.execute(
        "SELECT data FROM part WHERE session_id=? ORDER BY time_created", (sid,))]

def tools(sid):                                             # (tool, status, error) per tool call
    out = []
    for d in parts(sid):
        if d.get("type") == "tool":
            st = d.get("state", {}) or {}
            out.append((d.get("tool"), st.get("status"), st.get("error")))
    return out

def dispatches(main_id):                                    # Task calls made by a main session
    for d in parts(main_id):
        if d.get("type") == "tool" and d.get("tool") == "task":
            inp = (d.get("state", {}) or {}).get("input", {}) or {}
            yield inp.get("subagent_type"), inp.get("description"), (d.get("state") or {}).get("status")
```

The dispatch return the main agent integrates is the sub-agent session's **final assistant text** (the `## Summary` / `## Result` / `## Flags` block) — extract it as the last `part.data.type=="text"` of the child session. The **model** is `session.model` (JSON) or `message.data.modelID`; record it, because on OpenCode model quality dominates sub-agent reliability (see the empty-turn heuristic below). To map a child session to its artefact, match its `agent` + `title` (e.g. `deriver` / "derive D-S2-1 …") and the files written (`tool=="write"`/`"edit"` parts) against the committed artefacts.

For all hosts, for each sub-agent return:

- Wall-clock = `return_ts - dispatch_ts`.
- Was the return the canonical `## Summary` / `## Result` / `## Flags` block, or did it invent sections?
- Identify the coordinator's activity *between* this return and the next dispatch: which files were edited, which messages from the contributor came in, which questions it asked.

Produce a numbered trajectory table.

### Step 3 — Commit discipline

```bash
cd "$WS" && git log --all --pretty='%h %ai %s'
git status --porcelain
```

In shared mode, fetch `refs/pr/<n>` first: `main` holds one squash commit per session. For each dispatch from step 2: was there one `[S<n>]` commit after its return, before the next dispatch, that touched the expected artefact together with the cards and the log? Expected artefacts: `literature/P-*.md` and `literature/overview.md` for `/survey`, `derivations/D-S<n>-<k>.*` for `/derive`, `computations/C-S<n>-<k>.*` for `/compute`, the `_R-` file for `/review`, `critiques/CR-S<n>-<k>.md` for `/critique`, `sessions/S<n>/plan.md` for `/research-plan`, `sessions/S<n>/note.tex` for the writer. Build a table:

| Dispatch | Expected artefact | Commit? | Files left uncommitted |
|---|---|---|---|

Outside an active session, `git status` should be empty; any entry is a finding.

### Step 4 — The promises, one by one

For each promise, decide **pass / partial / fail** with specific evidence (promise 8 is split into 8a and 8b: twelve checks). Don't be charitable. Cite JSONL line numbers (or `jq` queries) and commit hashes. Mechanical checks:

- **1 (coordinator only)**: count the coordinator's tool calls by type. Flag any coordinator write or edit to `derivations/` or `computations/` (outside `.briefs/`), the findings of a critique, `literature/P-*.md`, `literature/overview.md` or `sessions/S<n>/note.tex`. Also scan the coordinator's text turns for inline derivations or substantive maths or code — heuristic: a text turn with several equations not framed as quoted sub-agent output. **Tool-count caveat**: raw tool counts are *not comparable across hosts* — Claude Code has dedicated `Read`/`Edit`/`Write`, Pi has structured `read`/`edit`/`write`, OpenCode has native `read`/`edit`/`write`/`bash`/`glob`/`grep` (so its counts *are* comparable to Claude/Pi), Codex has only `exec_command` + `apply_patch` (so every file read is a `sed -n` shell). For Codex, classify each `exec_command` by command stem (`sed`/`cat`/`rg`/`find`/`ls`/`git`/`mkdir`/`python`/`curl`) before counting. For OpenCode, the coordinator is itself an OpenCode session (`agent=='build'`); its tool parts are queried the same way as any other session. Report both the raw count and the normalised count of **logical operations** (file reads, file writes, sub-agent dispatches, commits, questions to the contributor).
- **2 (cards)**: run `uv run .physics-hive/scripts/check.py` on the final state, then once per session with that session's base (`--base <first parent of the session's first commit> --session S<n>`; in shared mode fetch `refs/pr/<n>` first). Every error is a finding; quote it. Immutability: `git log --diff-filter=MD --name-only --format='%h %s' -- claims derivations computations literature/P-*` (ignore `.briefs/`); each hit outside the session that created the file is a finding. IDs: every artefact's `supports` names a card that exists (`check.py` warns "reserved ID never written"; acceptable only when the log says the result was a dead end); no ID of session S<n> appears in another session's commits; IDs have no gaps that suggest hand counting.
- **3 (evidence before the draft)**: for each `result` environment of `draft.tex`, find the commit that added it (`git log -S'\card{CL-…}' --format='%h %s' -- draft.tex`), the tick or the lead's edit behind it, and the claim's evidence at that commit (`regen` and `check.py` on a worktree at that commit). Group the evidence by dispatch context.
- **4 (blind review)**: for every reviewer dispatch, check the prompt for a card path (`claims/…`), a model name, a contributor or human author, or an earlier verdict. Check the reviewer's own tool calls for reads of `claims/`, `sessions/`, `INDEX.md` or sibling reviews. Check that each review file has a `## Tests` table before its remarks, and that every remark has a location and one of the three severities. For `/critique`, check that only one-line summaries of earlier critiques were passed.
- **5 (review after artefacts)**: for every `D-S<n>-<k>` and `C-S<n>-<k>`, a sibling `_R-` file exists; otherwise the log says why the review was deferred.
- **6 (integration loop)**: from the table of step 3.
- **7 (edit scope)**: list the coordinator's writes and edits outside the allowed paths. For the human files, `git log --format='%h %s' -- project.md draft.tex conventions.md` shows, for sessions, only apply commits, removals of finished steps, convention fixes and draft edits that a next step asked for, each listed in that session's debrief under *Changed by this session*. For each apply commit, compare its diff with the ticked lines of the debrief it names, and with what `received.md` says the session received: a ticked line not applied, an unticked line applied, or a line applied twice is a finding. `uv run .physics-hive/scripts/session.py status` outside a session prints what the next session would receive; compare it with the lead's latest edits.
- **8a (artefact schema)**: every artefact (derivation and computation summaries, reviews, critiques) starts with its role's return block — `## Summary` / `## Result` / `## Flags` — followed by the sections its role declares (reviews: `## Tests` then `## Remarks`; critiques: `## Findings` then `## Resolution`). Extra sections are findings. Check with `grep -E '^## ' <artefact>`.
- **8b (reply schema)**: the sub-agent's **reply** — what the coordinator actually sees as the dispatch return — should *also* be the canonical block, not a narrative summary. Locations: Claude Code → the `tool_result` content of the `Task` call; Pi → the `subagent` tool's return body (also at the head of the sub-agent's `session.jsonl`); Codex → the `wait_agent` reply / `last_task_message`; OpenCode → the child session's **final `text` part** (mirrored in the parent's `task` tool `state.output`). Drift on 8b is **independent** of 8a, and it causes flags to be silently dropped, because the coordinator integrates from the reply, not the file.
- **9 (sessions)**: for each `sessions/S<n>/`: the brief has `goal` and `budget` and was confirmed by the contributor before the first dispatch (look for the confirmation in the record); the `Dispatch k/N` lines in `log.md` match the budget and the dispatches actually made in the record; the stop condition that applied first is the one the log gives; the writer was dispatched for the note, and the note names the cards of its results (compile it with `uv run .physics-hive/scripts/pdf.py S<n>` to count pages); the debrief passes `check.py` and contains what promise 9 asks.
- **10 (scripts bypassed)**: search the coordinator's shell calls for `git push`, `git rebase`, `git merge`, `hf upload`, `huggingface_hub` calls, or edits of `.active-session` or `received.md`, outside the scripts. Each is a finding, with the script failure that preceded it if any.
- **11 (attention)**: `wc -w` on the note's text and the debrief; count the questions (`grep -c '^\*\*Question'`) and the tick lines (`grep -c '^- \['`); classify each as routine or as a decision only the lead could take.

### Step 5 — Flag-disposition trace

For every sub-agent return that contained a `## Flags` block:

- Extract each flag (one bullet per flag).
- **Primary check**: is there a matching line in `sessions/S<n>/log.md`, in the form `[<skill> <artefact id>] <flag> → accepted / dismissed / deferred (one-line reason)`?
- Verify that the disposition matches what the coordinator did next, before the next dispatch:
  - **accepted** → a card, a follow-up dispatch, a question or a tick line in the debrief, or an entry in the *Handoff*.
  - **dismissed** → the reason in the log line is enough.
  - **deferred** → the reason names what it waits for, and the flag appears in the debrief (if it needs the lead) or the *Handoff* (if only the next session needs it).
- A flag with no line in the log is a finding ("silently dropped"), whatever the coordinator did afterwards.

### Step 6 — Prompt-vs-behaviour delta

Compare what the run's role prompts (`(.claude|.pi|.opencode)/agents/*.md`, `.codex/agents/*.toml`) and skill prompts (`(.claude/skills|.agents/skills|.opencode/skills)/*/SKILL.md`, `.pi/prompts/*.md`) *claim* against what actually happened:

- For each role's declared `tools:` list: did the sub-agent run any tool outside that list? (Possible — Claude Code may not strictly enforce.) **N/A for Codex and OpenCode**, whose roles carry no per-role tools allowlist (Codex is sandbox-scoped; OpenCode relies on the file-ownership prose) — skip this bullet for them.
- For each role's declared artefact structure: does the produced artefact use it? Mismatches are findings.
- For each role's "do not" constraints: any violations?
- For each role's instruction to report through `## Flags` rather than expand its scope: did a sub-agent silently expand its scope (read other artefacts, browse `references/`)?
- **Brief priors-leakage** (coordinator side): scan the dispatch briefs (`derivations/.briefs/`, `computations/.briefs/`, or the inline prompt) for explicit numeric targets ("This should give 16/25"), pre-stated sub-claim values ("Sub-claim: u_1 = 7"), or worked hints. The sub-agent is supposed to find those independently; pre-stating them defeats the cross-check. This is distinct from promise 4 (leaking earlier **reviews**): it leaks author-supplied **priors**. Flag it with the brief path or JSONL event and quote the offending line.

### Step 7 — Substantive quality (lighter pass)

- Do the results of `draft.tex` answer the question of `project.md`, or say how far they go? Does each result name its card, and does the draft state its assumptions?
- For each card named in the draft and the notes: does it exist, and do its supporting artefacts establish its statement (open the summary: does its task match the claim)?
- Reconcile the next steps of `project.md` with what the sessions did: finished steps were removed by the session that finished them; routes set aside have a stated reason in a note or a *Handoff*.
- Note any unresolved critique findings that bear on the results.
- If a reference solution exists, compare.

### Step 8 — Compile the report

Write to `/tmp/audit-<workspace-basename>.md`. Structure:

```markdown
# <Workspace> Run Post-Mortem

## Run shape
<wall-clock; sessions; dispatches; commits; artefacts and cards; headline judgement (results correct/partial/wrong)>

## Trajectory
<numbered list with timestamps, dispatch args, return summary, integration actions>

## Methodology adherence
<table: promise → pass/partial/fail with evidence>

## The lead's attention
<per session: words of the note and the debrief, questions and tick lines, how many were routine>

## Prompt-quality issues
<numbered findings; each with file:line, current text, observed behaviour, proposed fix>

## Workflow observations

### Per-dispatch wall-clock

| # | Skill | Agent | Dispatched at | Returned at | Duration | Artefact |
|---|---|---|---|---|---|---|

### Coordinator tool inventory

Report logical operations (comparable across hosts) and raw tool calls (host-dependent) separately.

| Logical operation | Count |
|---|---|
| Sub-agent dispatches | |
| File reads | |
| File writes/edits | |
| Commits | |
| Shell (other) | |
| Questions to the contributor | |

| Raw tool / command stem | Count | Notes |
|---|---|---|

### Backtracks, retries, recoveries
<list any: re-dispatches, apply_patch retries, `close_agent` thread-limit recoveries, clarifications asked of the contributor, sub-agent timeouts, and (OpenCode) **empty-turn dispatch failures** — sub-agent sessions that read their inputs but produced no artefact and were re-dispatched. Count the churn (e.g. "deriver dispatched 4× before D-S2-1 was written") and attribute it: a weak model is the usual cause, and the coordinator's detect-and-re-dispatch is the method recovering, not a defect.>

## Substantive quality
<short prose: does the draft answer the question of project.md; are artefacts well-formed>

## Recommended fixes (prioritised)
1. <highest impact, with specific files to edit>
2. ...
```

Then return a tight summary (under 800 words) to the caller covering:

- Headline verdict (substantive correctness + methodology score)
- Top 5 findings with evidence anchors
- Top 5 recommended fixes
- Anything systemic (e.g. one instruction that several roles ignore)

## Heuristics to bake in

- **"Did not commit per integration loop"** = no `[S<n>]` commit between a return and the next dispatch that touches both the expected artefact and the coordinator's integration edits (the cards, the session log).
- **"Flag silently dropped"** = a flag returned in a `## Flags` block has no line in the session log. Later incidental activity does not redeem it; the log line is the canonical record.
- **"Single-context result"** = a result of the draft whose supporting artefacts span ≤1 dispatch context, with no stated reason why only one approach is available. Several paths inside one artefact are still one context.
- **"Missing review"** = an artefact with no sibling `_R-` file and no reason in the log.
- **"Scope expansion"** = a sub-agent read a file outside its dispatch (check its read calls against what the dispatch named).
- **"Artefact schema drift"** (8a) = the artefact on disk contains sections outside its role's schema, or lacks the return block.
- **"Reply schema drift"** (8b) = the sub-agent's **reply** is narrative prose without `## Summary` / `## Result` / `## Flags` headers — even when the artefact on disk is canonical. Most common on Codex (`wait_agent` reply) and on long returns in Claude Code. It causes flags to be silently dropped, because the coordinator integrates from the reply, not the file.
- **"Brief priors-leakage"** = the coordinator's dispatch brief pre-states the expected answer numerically ("This should give 16/25") or names a sub-claim's value. Distinct from promise 4, which is about leaking earlier **reviews**.
- **"Empty-turn dispatch failure"** (OpenCode) = a sub-agent session (`part` rows show completed `read`s) that ends with a near-zero-output final assistant turn and **zero `write`/`edit` tool calls**, so no artefact lands on disk and the coordinator re-dispatches. Detect it as: child session with `tokens_output` ≈ a few hundred, no `tool=='write'`/`'edit'` parts, and a re-dispatch of the same role and target minutes later. It is a **model-reliability** signature (weak models stall after reading instead of writing), not a permissions or prompt bug — confirm `write` works elsewhere in the same run before blaming the configuration. Report the churn count and the model (`session.model`); the fix is "use a stronger model", not a prompt edit.
- **"Split run across sessions/projects"** (OpenCode) = the same workspace has several `project` rows (one per re-init) and/or several main (`build`) sessions (context clears, restarts). This is expected, not a finding — reconstruct by `session.directory` and treat the git commits as the canonical spine. Note it so that per-session wall-clocks aren't mistaken for the whole run.

## Constraints

- **Be evidence-anchored.** Cite file paths, line numbers, JSONL events, commit hashes. Findings without evidence are useless.
- **Don't be charitable.** A "soft" violation is still a violation; flag it as partial rather than passing.
- **Don't propose generic fixes** ("be more rigorous"). Propose specific edits to specific files with the current text and the replacement.
- **Stateless and idempotent** — runnable any time, on any workspace and session record. Do not edit the workspace, the session record, or any global files. Only write to `/tmp/audit-*.md`.
- **Honest about gaps.** If the session record is missing or truncated — a missing/truncated JSONL, or (OpenCode) an `opencode.db` with no rows for the workspace directory — say so and report only what the workspace + git can tell you.

## Tools required

`Read`, `Bash` (for `jq`, `grep`, `git`, `wc`, `ls`, and `sqlite3` + `python3` for the OpenCode store), `Write` (only to `/tmp/`).
