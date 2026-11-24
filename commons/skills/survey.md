---
name: survey
description: Literature work by a fresh-context surveyor sub-agent - expand from the seed papers and the papers the lead rated high, along citations (INSPIRE, arXiv), write one paper card per useful paper, download sources, and update the overview of the field. Can be dispatched in any session, for the whole problem or for a narrower need.
agent: surveyor
arguments_hint: "[focus, optional]"
---

Run literature work. The `surveyor` sub-agent reads papers, writes paper cards and updates `literature/overview.md`; you pass it the focus and integrate what it found.

## Steps

1. **Check the inputs.** `project.md` must state the question. `literature/seeds.md` lists the lead's seed papers and `literature/ratings.yaml` their ratings; both may be empty.

2. **Dispatch the `surveyor` sub-agent** (see the dispatch syntax for your harness in AGENTS.md) with, inline:
   - the session ID;
   - the focus: the whole problem for a first survey, or the specific need of the current work (a result a derivation needs, a convention to pin down, papers the lead pointed to in a debrief);
   - the paper cards that already exist (from `INDEX.md`), so that it does not duplicate them.

   Do not put a long instruction in the dispatch; the role definition already says how to work, including how to use the ratings.

3. **Integrate** (AGENTS.md §6):
   - Read the return block.
   - Disposition every flag in the session log. A flag that calls for work becomes a dispatch in this session or a next step offered in your debrief; one that needs the lead's decision (two papers using opposite sign conventions, two readings of the question) becomes a question in your debrief.
   - Write no cards from the survey: its findings stay in the overview and the paper cards (AGENTS.md §3). A published result the work will rely on becomes a next step to check, and a claim once a derivation or computation has checked it.
   - Log the dispatch.
   - Run regen and commit: `[S<n>] survey: <N paper cards, one-line summary>`. Sources under `literature/sources/` are git-ignored; in shared mode `session.py end` uploads them to the sources dataset.
   - If the return reports a load-bearing disagreement between approaches, the approach needs a decision: dispatch `/research-plan`, and offer its approach in your debrief.
