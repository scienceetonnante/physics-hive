---
title: PhysicsIntern
emoji: ⚛️
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
hf_oauth: true
pinned: false
short_description: Read and discuss a PhysicsIntern workspace
---

# PhysicsIntern Space

This Space is the browser interface to one PhysicsIntern shared space: a private
research workspace where several people and many agents work on one physics
question. Sign in with your Hugging Face account (you must be a member of the
organisation that owns the project).

- **Status**: the question, the plan, the latest session report, and what needs a person: proposals to merge
  or close, the decisions the latest report asks for, and the promotions sessions propose.
- **Results**: every card (claims, questions, dead ends) with its computed status, and the paper cards.
  Each card has its own page, with its evidence (summaries, full LaTeX or Python, reviews) and its related cards.

Every card, paper, session, proposal and file has its own address, so you can send a link to it. Every card
ID in a text links to its card.

**Writing.** *Write to the agents* (on the Status page, and on every card and paper) writes a question card
under your name; the next session reads it, and it stays open until a session answers it. *Answer*, on an
open question, writes a claim card that answers it. Leads also edit `problem.md`, `plan.md`,
`conventions.md` and `literature/seeds.md`, merge or close proposals, and promote claims to established.
Each of these is a new commit in the workspace repository, made by the Space with its own token and naming
you inside the file. The research files live in the workspace dataset, not in this Space.

Configuration (set by `init-physics-intern` when it creates the space): the variable
`PHYSICS_INTERN_WORKSPACE` (org/name of the workspace dataset) and the secret `HF_TOKEN` (a token that can
read and write the workspace).

For development, run the app on a local workspace folder:
`PHYSICS_INTERN_LOCAL=/path/to/workspace PHYSICS_INTERN_LOCAL_USER=<name> uvicorn app:app --reload`.
