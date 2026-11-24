---
name: session-run
description: Run one research session from start to end - open it, apply what the lead ticked, ask their unanswered questions, propose a brief, work autonomously within the budget, stop, have the note written, write the debrief, and close it (in shared mode the session's pull request is merged). Use when the contributor wants to start a session of work.
arguments_hint: "[what to work on, optional]"
---

Run one session from start to end. The contributor's part is: start it, answer open questions if they want, and confirm the brief. The lead's part is to read the note and answer the debrief later. One person can be both the lead and the contributor. Everything else is your job. The scripts do the git and Hub bookkeeping; you never do it by hand, and when a script fails you stop and report its message instead of improvising.

## 1. Start

```
uv run .physics-hive/scripts/session.py start --harness <your harness> --model <your model id>
```

It first commits the lead's uncommitted edits of their files as theirs and, in shared mode, pushes them to `main`.

If `project.md` has no title or goal yet, it refuses: ask the contributor for the question and the goal, write them in `project.md` (the question in one line as its title, the goal under `## Goal`), show them to the contributor, and run `start` again. It also refuses when the checkout has uncommitted changes that are not the lead's, or when a session is already active; tell the contributor why and stop (`session.py status` shows the active session; `session.py abort` abandons it).

It prints the session ID, the contributor's name to put in cards, and **what the lead sent since the previous session started**: per debrief, the answers, the lines ticked (to apply) and not ticked (not applied), and the note; their edits of `project.md`, `conventions.md` and `draft.tex`, with diffs; changed ratings; and the first next step of `project.md`. Then the *Handoff* of the earlier session, the cards that need a re-check, and the draft's flags. Read all of it: it is the lead's instruction for this session.

## 2. Apply

Apply every ticked line, exactly as written (AGENTS.md §5 and, for copies into the draft, §8). Make one commit per debrief, with the message `[S<n>] apply the lines ticked in the S<m> debrief`. Run `check.py` before committing a change to the draft; if a ticked result cannot be copied, copy nothing and keep the reason for your debrief. A line that is not ticked is not applied. Notes and answers that ask for something are inputs to the brief, not changes to apply.

## 3. Questions

If the start output lists questions without an answer, show them to the contributor, and wait. If they answer, record each answer in the debrief it belongs to with `session.py answer <S> <n> <their words>` (and `session.py tick <S> <k>` for lines they ask you to tick, which you then apply like the others). If they say to go on, go on: an assumption whose question says that no answer means agreement stands; any other question that still matters goes again in your debrief.

## 4. Brief

Propose a brief to the contributor:

- **Goal and why**: by default the first next step of `project.md`; or the step or one-line brief the contributor gives. Say what the session will try and why it matters now, in one or two sentences, taking the lead's notes and answers into account.
- **Budget**: a number of dispatches, 20 by default.
- **Stop conditions**: the goal is reached; the budget is spent; no progress, meaning 4 dispatches in a row that added nothing towards the goal (no new claim or dead end, no review that confirms or refutes, no new paper cards); or the work shows that `project.md` should change.

In shared mode, if another open session (listed at start) works on the same step, say so and let the contributor decide. When the contributor confirms, possibly with changes, write `sessions/S<n>/brief.md`:

```markdown
---
session: S12
goal: '<one sentence>'
budget: 20
starts_from: [CL-S3-2]
---
## Goal
## Why
## Plan of work
## Stop conditions
```

Then run `session.py brief`. It commits the brief (and `received.md`) and, in shared mode, copies it to the pull request. From now on, do not ask the contributor anything until the end.

## 5. Work

Work towards the goal with `/survey`, `/derive`, `/compute`, `/review`, `/critique` and `/research-plan`, following AGENTS.md: every derivation and computation is reviewed, the integration loop runs after every return (cards, log, regen, commit), a refutation gets a second opinion before you act on it, and `/critique` runs every few changes of state. You may edit `conventions.md` when the work fixes a convention.

Keep the log current. Each dispatch gets a numbered line, so that the count survives a context clear:

```
Dispatch 7/20: /review D-S12-3 (D-S12-3_R-S12-1) → refuted: a cross term is dropped at eq. (14)
```

When the work shows that the approach or the next steps should change, note it in the log and continue; it becomes tick lines in your debrief. When a claim's evidence looks robust (AGENTS.md §3), note it; it becomes a line offering to copy it into the draft.

## 6. Stop

Stop at the first stop condition. Before stopping for lack of progress, record the obstacle as a dead-end card if there is one. If the work shows that `project.md` should change, stop and say so in the debrief, with the change as a tick line; do not edit it beyond removing finished steps.

If the session finished a next step of `project.md`, remove it from *Next steps*, in its own commit: `[S<n>] project.md: remove the finished step`. The debrief lists this change.

## 7. Note, debrief, handoff

1. **The note.** Dispatch the `writer` sub-agent (see the dispatch syntax for your harness in AGENTS.md) with, inline: the session ID, the output path `sessions/S<n>/note.tex`, and the claim cards of this session that the note should present as results (the others it may mention as working). It reads the brief, the log and the artefacts itself. Read its return and the note; if the note misstates a result, dispatch the writer again with what to fix, rather than editing the note yourself. Commit it: `[S<n>] note`.
2. **The debrief.** Write `sessions/S<n>/debrief.md` (AGENTS.md §7; the template is `.physics-hive/commons/templates/debrief.md`): the summary, then the questions, the tick lines and the empty note box. Number the questions from 1. Refer to results by their number in the note ("Result 1 of note S12") and by card. Keep it to one screen.
3. **The handoff.** End `sessions/S<n>/log.md` with `## Handoff`: what the next session needs that the lead does not (open threads, requirements for later briefs, deferred flags, approaches set aside and why).

Run regen, then commit the debrief and the log: `[S<n>] debrief and handoff`.

## 8. End

Run `session.py end`. It writes *Changed by this session* in the debrief from git, runs `check`, and in shared mode pushes the branch to the pull request, uploads the trace, marks the pull request ready and merges it, rebasing on `main` first if needed.

If `check` reports errors in files of this session (a malformed header, a `\card` naming no card, a debrief question without an answer line), fix them, commit, and run `session.py end` again. For any other failure, such as a rebase conflict or a Hub error, stop and give the contributor the script's message.

Finish by telling the contributor, in a few lines, why the session stopped, what it found, and that the note and the debrief are waiting for the lead (in shared mode, on the Review page of the Space). In local mode, tell them that `uv run .physics-hive/scripts/serve.py`, run in a terminal in this folder, opens the Space on it, where the lead can read the note and answer the debrief.
