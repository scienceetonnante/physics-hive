---
name: autoresearch
description: Local mode only. Drive the full pipeline (survey, plan, derive and review, draft, finalize) autonomously in one session, without stopping for the operator, acting for the researcher and logging every decision taken in their place. For benchmark runs. Only the user invokes it.
arguments_hint: "[max-iterations=N] [max-derivations=N] [start-from=survey|plan|loop|finalize]"
top_level_cli: false
---

You work in **autoresearch mode**: drive the research from the current state to `answer.md` without pausing for the operator. You act for the researcher: you apply your own suggestions to `project.md` and `draft.tex` instead of offering them as tick lines, and you log each one as a gate you skipped. This suits benchmark problems whose shape is known in advance. It is not used in shared mode: if `project.toml` names a Hub repository, tell the operator to use `/session-run` and stop.

This skill runs in your own context and drives the loop; every step still dispatches its sub-agent with a fresh context.

Arguments:
- `max-iterations=N` — total dispatch budget. Default 30.
- `max-derivations=N` — combined `/derive` and `/compute` budget. Default 12.
- `start-from=survey|plan|loop|finalize` — where to start. Default: inferred from the files (no `literature/overview.md`: survey; no next steps in `project.md`: plan; otherwise the loop).

## Start

Run `session.py start --harness <your harness> --model <your model id>`. If it refuses because `project.md` has no title or goal yet, tell the operator and stop. Apply any ticked lines it prints, as `/session-run` does. Write `sessions/S<n>/brief.md` yourself (goal: answer the question of `project.md`; budget: `max-iterations`) and run `session.py brief`. Do not ask for confirmation.

## Decisions taken without the operator

At every point where the normal flow would wait for the researcher, decide and append a block to the session log under `## Decisions taken without the operator`:

```markdown
### <gate name>
- Decision: <what you decided>
- Reasoning: <why it was safe to go on>
- Would have asked: "<the question or the tick line you would have put in a debrief>"
- Inputs: <cards, artefacts, return lines the decision rests on>
```

Use these gate names exactly, so that audits can find them:

- `Post-survey gate` — going from `/survey` to `/research-plan`.
- `Framing gate` — committing to a reading of the question or a method when the survey reported a load-bearing disagreement; name the alternatives set aside and why.
- `Post-plan gate` — writing the planner's approach and next steps into `project.md`, and adopting proposed conventions.
- `Pre-strategy-change gate` — re-dispatching `/research-plan` for a change of strategy.
- `Refutation gate` — writing a dead-end card after a second review agreed on a refutation.
- `Draft gate` — copying a result into `draft.tex` (AGENTS.md §8); `check` must accept it. This is what makes a claim established.
- `Pre-finalize gate` — going to `/finalize`.

The blocks are committed with the integration step they belong to.

## Loop

```
counters: dispatches = 0, derivations = 0,
          changes_since_critique = 0, substantive_changes_since_critique = 0

survey:  /survey (whole problem) → integrate → Post-survey gate
plan:    /research-plan → integrate → Post-plan gate (and Framing gate if needed): write project.md
loop:    take the first next step of project.md
           /derive or /compute → integrate → /review → integrate
           on a refutation: second /review; if it agrees → Refutation gate → dead-end card
           when a claim has robust evidence (AGENTS.md §3) → Draft gate → copy it into draft.tex as a result
           when a step is finished, remove it from project.md
           count every integrated return in changes_since_critique, and results copied into
           the draft and refutations in substantive_changes_since_critique
         run /critique when (substantive ≥ 1 and changes ≥ 2) or changes ≥ 6; reset both
         on a change of strategy: a second /critique, then Pre-strategy-change gate, then /research-plan
         stop the loop when the draft's results carry the answer, or a budget is spent
finalize: /critique (final) → Pre-finalize gate → /finalize → integrate
```

## End

Dispatch the writer for `sessions/S<n>/note.tex`, write `sessions/S<n>/debrief.md` (its questions are those you would have asked; its tick lines are empty, since you applied your suggestions), end the log with its `## Handoff`, run regen, commit, and run `session.py end`. Then tell the operator:

- the outcome (completed, or which budget stopped the run) and the dispatches and derivations used;
- the artefacts produced, the results in the draft (one line each), the working claims still open, the dead ends added;
- the number of decisions taken without them, with a pointer to the session log;
- what to read first: `answer.md`, the note, and the decisions in the log, or, if the run stopped early, the card or artefact to look at.
