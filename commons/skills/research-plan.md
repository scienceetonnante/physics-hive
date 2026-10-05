---
name: research-plan
description: Draft the research strategy with a fresh-context planner sub-agent. In local mode it writes plan.md and you present it to the operator; in shared mode it drafts a proposal that becomes a pull request for the lead, and plan.md on main is never written by agents.
agent: planner
arguments_hint: "[feedback or scope hints, optional]"
---

Draft or revise the plan. The `planner` sub-agent reads the problem, the current plan, the cards, the survey summaries and the plan-change proposals of earlier sessions, and writes a draft.

## Steps

1. **Collect the plan-change proposals.** `session.py start` (or `session.py status`) lists the `## Proposed plan changes` of session reports merged since `plan.md` last changed. Add any feedback from the operator.

2. **Dispatch the `planner` sub-agent** (see the dispatch syntax for your harness in AGENTS.md) with, inline: the proposals and feedback, and the path to write:
   - local mode: `plan.md`;
   - shared mode: `sessions/S<n>/plan-proposal.md`.

3. **Integrate** (AGENTS.md §5):
   - Read the return block (the planner returns it in its reply only).
   - Disposition every flag in the session log. Proposed conventions or sanity checks go to the operator in local mode (you may then edit `conventions.md` or `problem.md`), and to the report in shared mode.
   - Log the dispatch, run regen and commit: `[S<n>] research-plan: <one-line summary>`.
   - **Shared mode:** open the proposal for the lead:
     ```
     uv run .physics-intern/scripts/propose.py plan.md --from sessions/S<n>/plan-proposal.md --title "[S<n>] Plan proposal: <one line>"
     ```
     It opens a pull request that touches only `plan.md`, which the lead merges, edits or closes. Record its number in the log and in the report. Do not wait for the lead.
   - **Local mode, interactive:** present the plan to the operator and wait for approval before working from it. Under `/autoresearch`, log the decision instead.
