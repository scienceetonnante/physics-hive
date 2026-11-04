---
name: finalize
description: Write answer.md, the final answer to the question of project.md, from the results in draft.tex, with a fresh-context finalizer sub-agent. For the end of the project, not the end of a session.
agent: finalizer
arguments_hint: "[emphasis, optional]"
---

Write the final answer. The `finalizer` sub-agent reads `project.md`, the draft, `INDEX.md` and the cards and artefacts behind the draft's results, and writes `answer.md`.

## Steps

1. **Check before dispatching.** The results of `draft.tex` should carry the answer, and `INDEX.md` should show no flag on them (refuted, revised, needs re-check). If the answer depends on conjectures or working claims, tell the operator (or, under `/autoresearch`, log it): `/finalize` will still write an honest partial answer.

2. **Dispatch the `finalizer` sub-agent** (see the dispatch syntax for your harness in AGENTS.md), with any emphasis inline.

3. **Integrate** (AGENTS.md §6): read the return block, disposition every flag in the session log (a suggestion of further checks may become one more `/review` or `/critique`), log the dispatch, run regen and commit: `[S<n>] finalize: <one-line summary>`. Present the headline result.
