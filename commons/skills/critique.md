---
name: critique
description: Strategic critique of the overall research state by a fresh-context critic sub-agent - drift from the brief and the approach, viability, coherence of established claims, fragile foundations, unreviewed evidence.
agent: critic
arguments_hint: "[focus, optional]"
---

Run a strategic critique. The `critic` sub-agent reads `INDEX.md`, `project.md` and the session brief, spot-checks artefacts, and files findings. Findings are proposals; you disposition each one.

## Steps

1. **Get the ID** with `session.py next CR` (for example `CR-S12-1`).

2. **Collect one-line summaries of earlier critiques**: for each `critiques/CR-*.md`, its date and headline finding. This prevents repetition without passing earlier analyses.

3. **Dispatch the `critic` sub-agent** (see the dispatch syntax for your harness in AGENTS.md) with the critique ID, the session ID, the one-line summaries and any focus, inline.

4. **Integrate** (AGENTS.md §6):
   - Read the return block.
   - Disposition each finding in the critique's `## Resolution` (resolve, dismiss or defer, with a reason) and update its `status:` field (`resolved`, `partially resolved` or `deferred`). Do not act on a finding that would change direction before a second opinion (AGENTS.md §6).
   - Findings that call for work become dispatches in this session, or next steps offered as tick lines in your debrief. A finding about a card written in this session is fixed by correcting that card (AGENTS.md §3).
   - Disposition general flags in the session log, log the dispatch, run regen and commit: `[S<n>] critique(<id>): <one-line summary>`.
