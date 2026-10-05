---
name: write-up
description: Assemble the established claims into a LaTeX document compiled to PDF (write-up/write-up.tex and .pdf), with a fresh-context writer sub-agent. Each statement in the document names the card it comes from.
agent: writer
arguments_hint: "[audience, length or emphasis, optional]"
---

Write the project up. The `writer` sub-agent reads the established claims and the artefacts behind them, writes `write-up/write-up.tex`, and compiles it.

## Steps

1. **Check before dispatching.** There should be established claims, and none of them should need a re-check. If they do, say so to the operator (or in the report) before going on.

2. **Dispatch the `writer` sub-agent** (see the dispatch syntax for your harness in AGENTS.md), with the audience, length or emphasis inline.

3. **Integrate** (AGENTS.md §5): read the return block, disposition every flag in the session log, log the dispatch, run regen and commit `write-up/write-up.tex` and `write-up/write-up.pdf`: `[S<n>] write-up: <one-line summary>`.
