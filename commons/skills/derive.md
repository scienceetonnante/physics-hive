---
name: derive
description: Analytical derivation of a target claim or question, by a fresh-context deriver sub-agent that works only from a brief file. Produces a LaTeX derivation and a one-page summary; you then write the claim card.
agent: deriver
arguments_hint: <target claim or question>
---

Run an analytical derivation. The `deriver` sub-agent works only from the brief you write; you dispatch it and integrate its result.

## Steps

1. **Get the IDs.** Run `session.py next D` for the artefact (for example `D-S12-3`) and `session.py next CL` to reserve the ID of the claim card the result will support (for example `CL-S12-4`). If the derivation is meant to support an existing card (a re-check), use that card's ID instead.

2. **Write the brief** at `derivations/.briefs/<artefact id>.md`. Include only:
   - the target, stated concretely;
   - the reserved card ID, to be written in `supports` in the summary header;
   - the established cards the deriver may use, by ID and statement;
   - a pointer to `conventions.md`;
   - the paper cards and sources (`literature/sources/…`) that bear on the target, by path;
   - earlier artefacts whose results are load-bearing inputs, by path, not restated;
   - when re-deriving after a refutation, the dead-end card by path, and nothing else about the earlier attempt.

   **No steering, no priors**: do not signal an expected answer or a preferred method.

3. **Dispatch the `deriver` sub-agent** with the brief path and the artefact ID (see the dispatch syntax for your harness in AGENTS.md). It writes `derivations/<id>.tex` and `derivations/<id>.summary.md`.

4. **Integrate** (AGENTS.md §6):
   - Read the return block.
   - Write the claim card with the reserved ID, stating what was actually derived (which may differ from the target), with `depends_on` naming the cards the derivation relied on. If the derivation reached nothing, write a dead-end card describing the obstacle instead and leave the reserved ID unused.
   - Disposition every flag in the session log and log the dispatch.
   - Run regen and commit: `[S<n>] derive(<id>): <one-line summary>`.

5. **Next dispatch is `/review <id>`**, unless the integration surfaced a reason to defer it (record the reason in the log).
