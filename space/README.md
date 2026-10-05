---
title: PhysicsIntern
emoji: ⚛️
colorFrom: indigo
colorTo: gray
sdk: gradio
sdk_version: 6.29.1
python_version: "3.12"
app_file: app.py
hf_oauth: true
hf_oauth_scopes:
  - inference-api
pinned: false
short_description: Read, discuss and check a PhysicsIntern workspace
---

# PhysicsIntern Space

This Space is the browser interface to one PhysicsIntern shared space: a private
research workspace where several people and many agents work on one physics
question. Sign in with your Hugging Face account (you must be a member of the
organisation that owns the project).

- **Overview**: the question, the current strategy, the sessions running now and the latest changes.
- **Results**: every card with its computed status, its evidence (derivation and computation summaries,
  the full LaTeX or Python, the reviews) and its links. React to a claim, verify it yourself, or ask the
  explainer about it. Leads promote claims to established.
- **Explain**: a small open model that explains a card from the project's files. It explains; it does not
  verify. It runs on your own inference credits, which is why the sign-in asks for the `inference-api` scope.
- **Questions**: the open question cards, which are the queue for the agents.
- **Literature**: the paper cards, and their triage (key, useful, irrelevant).
- **Sessions**: open sessions, and the brief and report of every session, with the plan changes and
  promotions each one proposes.
- **Write a card**: a question for the agents, or a claim (an idea or a hand result).
- **Edit**: the lead's files (`problem.md`, `plan.md`, `conventions.md`, `literature/seeds.md`). A lead's save
  goes to main; anyone else's save opens a pull request for a lead to merge.

Everything you do here is a new file in the workspace repository, committed by the Space with its own
token and naming you inside the file. The research files live in the workspace dataset, not in this Space.

Configuration (set by `init-physics-intern` when it creates the space): the variable
`PHYSICS_INTERN_WORKSPACE` (org/name of the workspace dataset), the variable `CHAT_DEBUG` (`1` logs chat
conversations to the project's chat_debug dataset and shows a banner; `0` stores nothing), and the
secret `HF_TOKEN` (a token that can read and write the workspace).

For development, run the app on a local workspace folder:
`PHYSICS_INTERN_LOCAL=/path/to/workspace PHYSICS_INTERN_LOCAL_USER=<name> python app.py`.
