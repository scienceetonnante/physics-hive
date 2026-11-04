---
name: compute
description: Symbolic and numerical computation for a target claim, by a fresh-context computer sub-agent that works only from a brief file. SymPy and NumPy by default, with both paths run together when feasible and any disagreement flagged. You then write the claim card.
agent: computer
arguments_hint: <target claim or quantity>
---

Run a symbolic and numerical computation. The `computer` sub-agent writes a script, runs it and captures its output; you write the brief and integrate the result.

## Steps

1. **Get the IDs.** Run `session.py next C` for the artefact (for example `C-S12-1`) and `session.py next CL` to reserve the ID of the claim card the result will support. If the computation is meant to support existing cards (an independent second route, a re-check), use their IDs instead; a computation may support several cards.

2. **Write the brief** at `computations/.briefs/<artefact id>.md`. Include only:
   - the target claim or quantity, stated concretely;
   - the card ID(s) to write in `supports` in the summary header;
   - the established cards it may use, by ID and statement;
   - a pointer to `conventions.md`;
   - the paper cards, sources and earlier artefacts that are load-bearing inputs, by path;
   - earlier data files it may reuse (`computations/<id>.<name>.csv`), by path.

   **No steering, no priors**: do not signal an expected answer. When the computation is an independent check of a derivation, give the statement to check, not the derivation's intermediate steps.

3. **Dispatch the `computer` sub-agent** with the brief path and the artefact ID (see the dispatch syntax for your harness in AGENTS.md). It writes `computations/<id>.py`, `.out`, any data files, and the summary `computations/<id>.md`.

4. **Integrate** (AGENTS.md §6):
   - Read the return block.
   - Write the claim card with the reserved ID (or none, if the computation supports existing cards), stating what was actually computed. If the symbolic and numerical paths disagree, do not write a claim; record the disagreement as a flag disposition, and in your debrief if it needs the researcher.
   - Disposition every flag in the session log and log the dispatch.
   - Run regen and commit: `[S<n>] compute(<id>): <one-line summary>`. The commit includes the script, its output and its data files.

5. **Next dispatch is `/review <id>`**, unless the integration surfaced a reason to defer it.
