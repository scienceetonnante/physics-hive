---
name: session-run
description: Run one research session from start to end - open it, propose a brief to the operator, work autonomously within the budget, stop, write the report, and close it (in shared mode the session's pull request is merged). Use when the operator wants to start a session of work.
arguments_hint: "[what to work on, optional]"
---

Run one session from start to end. The operator's part is three things: start it, confirm the brief, and read the report. Everything else is your job. The scripts do the git and Hub bookkeeping (the pull request, the commits pushed to it, the trace upload, the merge); you never do it by hand, and when a script fails you stop and report its message instead of improvising.

## 1. Start

Run:

```
uv run .physics-intern/scripts/session.py start --harness <your harness> --model <your model id>
```

It refuses to start when `problem.md` does not state a question yet, when the checkout has uncommitted changes, or when a session is already active; tell the operator why and stop (`session.py status` shows the active session; `session.py abort` abandons it).

It prints the session ID (for example `S12`), the operator name to put in cards, and what is waiting for the agents: open question cards, needs re-check flags, reactions, human verifications, promotions and human-written cards since the last session, pull request comments (shared mode), plan-change proposals that the plan has not taken in yet, and the briefs of other open sessions.

## 2. Brief

Propose a brief to the operator, starting from what is waiting and from the operator's request if they gave one:

- **Goal and why**: what the session will try, in one or two sentences, and why it matters now. A goal may come from a plan item, an open question card, a doubtful reaction, a needs re-check flag, a set of papers to read, or the operator's idea.
- **Budget**: a number of dispatches, 20 by default.
- **Stop conditions**: the goal is reached; the budget is spent; no progress, meaning 4 consecutive dispatches without a new claim card, a new dead-end card, a refutation or a promotion proposal; or the work shows that `problem.md` should change.
- **Starting cards**: the cards the session starts from.
- **Merge**: `auto` (the session merges on its own at the end; the default) or `ask` (you show the report and wait for the operator's yes). Local mode has no merge.

If another open session's brief names one of the same cards, say so and let the operator decide; do not refuse. If plan-change proposals are pending, offer to dispatch `/research-plan` during the session.

When the operator confirms, possibly with changes, write `sessions/S<n>/brief.md`:

```markdown
---
session: S12
goal: '<one sentence>'
budget: 20
merge: auto
starts_from: [CL-S3-2, Q-alice-20261005T141233]
---
## Goal
## Why
## Plan of work
## Stop conditions
```

Then run `session.py brief`. It commits the brief and, in shared mode, copies it to the pull request. From now on, do not ask the operator anything until the report.

## 3. Work

Work towards the goal with `/survey`, `/derive`, `/compute`, `/review`, `/critique` and `/research-plan`, following AGENTS.md: every derivation and computation is reviewed, the integration loop runs after every return (cards, log, regen, commit), a refutation gets a second opinion before you act on it, and `/critique` runs every few changes of state. Literature work is allowed at any point.

Keep the log current. Each dispatch gets a numbered line, so that the count survives a context clear:

```
Dispatch 7/20: /review D-S12-3 (D-S12-3_R-S12-1) → refuted: a cross term is dropped at eq. (14)
```

When the work shows that the plan should change, note it in the log and continue; do not edit `plan.md` in shared mode. When a claim looks ready to be established (AGENTS.md §3), note it in the log; it becomes a promotion proposal in the report.

## 4. Stop

Stop at the first stop condition. Before stopping for lack of progress, record the obstacle as a dead-end card if there is one. If the work shows that `problem.md` should change, stop and explain why in the report; do not edit it.

## 5. Report

Write `sessions/S<n>/report.md`:

```markdown
---
session: S12
stop_reason: goal reached        # or: budget spent | no progress | problem.md should change
dispatches: 14
---
## Found
## Refuted
## Left open
## Why the session stopped
## Proposed plan changes
## Proposed promotions
- CL-S3-2: <its evidence: which artefacts, which confirming reviews, which independent routes>
## Needs a human decision
```

Write `(none)` under an empty section. Run regen, then commit the report.

## 6. End

- **Local mode.** Show the operator the report's headline. If it proposes promotions, ask which ones to record, record them with `promote.py <card> --by-agent --reason "<evidence>"`, and commit. Then run `session.py end`, which runs `check` and closes the session.
- **Shared mode.** If the brief says `merge: ask`, show the report and wait for the operator's yes; if they decline, run `session.py end --no-merge`, which leaves the pull request open for them. Otherwise run `session.py end`. It runs `check`, pushes the branch to the pull request, uploads the trace, marks the pull request ready and merges it, rebasing on `main` first if other sessions were merged in the meantime.
- If `check` reports errors in files of this session (usually a malformed header), fix them, commit, and run `session.py end` again. For any other failure, such as a rebase conflict or a Hub error, stop and give the operator the script's message.

Finish by telling the operator why the session stopped, what it found, and what needs a human decision.
