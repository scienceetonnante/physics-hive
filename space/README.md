---
title: PhysicsIntern
emoji: ⚛️
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
hf_oauth: true
pinned: false
short_description: Read and answer a PhysicsIntern workspace
---

# PhysicsIntern Space

This Space is the browser view of one PhysicsIntern shared space: a private research workspace where agents
run sessions in a terminal and the researcher follows and steers them from here. Sign in with your Hugging
Face account (you must be a member of the organisation that owns the project).

- **Latest**: the debriefs of the sessions, newest first. Answer the questions, tick the lines you accept,
  and write anything else in the note box; the next session applies what you ticked. Below them, what the
  next session will receive.
- **Project**: `project.md` (the question, goal, approach, next steps, done steps, definition of done) and
  `conventions.md`, each with an editor.
- **Draft**: `draft.tex`, the best current state of the research, rendered like an arXiv HTML paper, with an
  editor beside a preview and the PDF. A claim is established when a result of the draft names it.
- **Sessions**: one line per session; each opens its note, rendered the same way.
- **Literature**: the overview of the field, then the papers by topic with why each matters; rate them from
  their menu, and the next survey follows your ratings.

Saving commits the file to the workspace repository with this Space's token and names you in the commit.
The Space applies nothing by itself. The research files live in the workspace dataset, not in this Space.

Configuration (set by `init-physics-intern` when it creates the space): the variable
`PHYSICS_INTERN_WORKSPACE` (org/name of the workspace dataset) and the secret `HF_TOKEN` (a token that can
read and write the workspace: the one in `PHYSICS_INTERN_SPACE_TOKEN` on the creator's machine, else the
creator's login token).

For development, run the app on a local workspace folder:
`PHYSICS_INTERN_LOCAL=/path/to/workspace PHYSICS_INTERN_LOCAL_USER=<name> uvicorn app:app --reload`.
