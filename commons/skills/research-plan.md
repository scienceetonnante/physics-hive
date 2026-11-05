---
name: research-plan
description: Draft an approach and next steps for the project with a fresh-context planner sub-agent. The draft goes in the session folder; you offer it to the researcher as tick lines in your debrief, and project.md changes only when they tick them.
agent: planner
arguments_hint: "[feedback or scope hints, optional]"
---

Draft or revise the approach and the next steps. The `planner` sub-agent reads `project.md`, the cards, the literature overview, the notes and the handoffs of earlier sessions, and writes a draft. `project.md` is the researcher's: the draft reaches it only through lines they tick.

## Steps

1. **Collect the inputs**: what the researcher asked for (their answers and notes, from `received.md`), and any scope hint from the operator.

2. **Dispatch the `planner` sub-agent** (see the dispatch syntax for your harness in AGENTS.md) with, inline: the session ID, the inputs above, and the output path `sessions/S<n>/plan.md`.

3. **Integrate** (AGENTS.md §6):
   - Read the return block (the planner returns it in its reply only).
   - Turn the draft into tick lines for your debrief: one to set the approach (if it changes), one per next step to add (in order), one per next step to remove (with its reason). Proposed conventions become a question or a tick line too. Approaches set aside, with their reasons, go in the *Handoff* of the log.
   - Disposition every flag in the session log, log the dispatch, run regen and commit: `[S<n>] research-plan: <one-line summary>`.
   - Under `/autoresearch`, apply the draft to `project.md` yourself and log the decision as a skipped gate.
