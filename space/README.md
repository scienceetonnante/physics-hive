---
title: Physics Hive
emoji: ⚛️
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
hf_oauth: true
pinned: false
---

<!-- When the Space is deployed, its title becomes "[Physics Hive] <project>" and its short_description the question
of project.md (scripts/hub.py, space_card). Each session start updates the description if the question changed. -->

# PhysicsHive Space

This Space is the browser view of one PhysicsHive shared space: a private research workspace where agents
run sessions in a terminal and the researcher follows and steers them from here. Sign in with your Hugging
Face account (you must be a member of the organisation that owns the project).

- **Review** (the page the Space opens on): the debriefs of the sessions, newest first; an open one is marked *Awaiting your response* until you answer in it. The session's findings come first, each with what supports it and whether it is in the draft; your response stays in view on the right. Answer the questions, tick the lines you accept,
  and write anything else in the note box; the next session applies what you ticked.
- **Project**: `project.md` (the question, goal, approach and next steps) and `conventions.md`, each with an
  editor.
- **Draft**: `draft.tex`, the best current state of the research, rendered like an arXiv HTML paper, with an
  editor beside a preview and the PDF. A claim is established when a result of the draft names it.
- **Sessions**: one line per session; each opens its note, rendered the same way.
- **Literature**: the overview of the field, then the papers by topic with why each matters; rate them from
  their menu, and the next survey follows your ratings.

Saving commits the file to the workspace repository with this Space's token and names you in the commit.
The Space applies nothing by itself. The research files live in the workspace dataset, not in this Space.

Configuration (set by `init-physics-hive` when it creates the space): the variable
`PHYSICS_HIVE_WORKSPACE` (org/name of the workspace dataset) and the secret `HF_TOKEN` (a token that can
read and write the workspace: the one in `PHYSICS_HIVE_SPACE_TOKEN` on the creator's machine, else the
creator's login token).

For development, run the app on a local workspace folder:
`PHYSICS_HIVE_LOCAL=/path/to/workspace PHYSICS_HIVE_LOCAL_USER=<name> uvicorn app:app --reload`.
