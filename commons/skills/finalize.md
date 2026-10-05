---
name: finalize
description: Write answer.md, the final answer to problem.md, from the established claims, with a fresh-context finalizer sub-agent. For the end of the project, not the end of a session.
agent: finalizer
arguments_hint: "[emphasis, optional]"
---

Write the final answer. The `finalizer` sub-agent reads the problem, the generated views and the cards and artefacts behind the established claims, and writes `answer.md`.

## Steps

1. **Check before dispatching.** The established claims in `INDEX.md` should carry the answer, and none of them should need a re-check. If the answer depends on working claims, tell the operator (or, in a session that cannot ask, say it in the report): `/finalize` will still write an honest partial answer.

2. **Dispatch the `finalizer` sub-agent** (see the dispatch syntax for your harness in AGENTS.md), with any emphasis inline.

3. **Integrate** (AGENTS.md §5): read the return block, disposition every flag in the session log (a suggestion of further checks may become one more `/review` or `/critique`), log the dispatch, run regen and commit: `[S<n>] finalize: <one-line summary>`. Present the headline result.
