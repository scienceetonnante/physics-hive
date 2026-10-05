---
name: autoresearch
description: Local mode only. Drive the full pipeline (survey, plan, derive and review, finalize) autonomously in one session, without stopping for the operator, logging every decision taken in their place. For benchmark runs. Only the user invokes it.
arguments_hint: "[max-iterations=N] [max-derivations=N] [start-from=survey|plan|loop|finalize]"
top_level_cli: false
---

You work in **autoresearch mode**: drive the research pipeline from the current state to `answer.md` without pausing for the operator. This deliberately skips the points where the normal flow waits for a human. It suits benchmark problems whose shape is known in advance, where course correction is unlikely. It is not used in shared mode: if `project.toml` names a Hub repository, tell the operator to use `/session-run` and stop.

This skill runs in your own context and drives the loop; every step still dispatches its sub-agent with a fresh context.

Arguments:
- `max-iterations=N` — total dispatch budget. Default 30.
- `max-derivations=N` — combined `/derive` and `/compute` budget. Default 12.
- `start-from=survey|plan|loop|finalize` — where to start. Default: inferred from the files (no `literature/survey-S*.md`: survey; an empty `plan.md`: plan; otherwise the loop).

## Start

Run `session.py start --harness <your harness> --model <your model id>`. If it refuses because `problem.md` does not state a question yet, tell the operator and stop. Write `sessions/S<n>/brief.md` yourself (goal: answer `problem.md`; budget: `max-iterations`; `merge` does not apply) and run `session.py brief`. Do not ask for confirmation.

## Decisions taken without the operator

At every point where the normal flow would wait for the operator, decide and append a block to the session log under `## Decisions taken without the operator`:

```markdown
### <gate name>
- Decision: <what you decided>
- Reasoning: <why it was safe to go on>
- Would have asked: "<the question you would have put to the operator>"
- Inputs: <cards, artefacts, return lines the decision rests on>
```

Use these gate names exactly, so that audits can find them:

- `Post-survey gate` — going from `/survey` to `/research-plan`.
- `Framing gate` — committing to a reading of the question or a method when the survey reported a load-bearing disagreement; name the alternatives set aside and why.
- `Post-plan gate` — going from `/research-plan` to the first dispatch, and adopting proposed conventions or sanity checks.
- `Pre-strategy-change gate` — re-dispatching `/research-plan` for a change of strategy.
- `Refutation gate` — writing a dead-end card after a second review agreed on a refutation.
- `Promotion gate` — recording a promotion with `promote.py <card> --by-agent --reason "<evidence>"`.
- `Pre-finalize gate` — going to `/finalize`.

The blocks are committed with the integration step they belong to.

## Loop

```
counters: dispatches = 0, derivations = 0,
          changes_since_critique = 0, substantive_changes_since_critique = 0

survey:  /survey (whole problem) → integrate → Post-survey gate
plan:    /research-plan (writes plan.md) → integrate → Post-plan gate (and Framing gate if needed)
loop:    pick the next item from plan.md and the open work in INDEX.md
           /derive or /compute → integrate → /review → integrate
           on a refutation: second /review; if it agrees → Refutation gate → dead-end card
           when a claim has robust evidence (AGENTS.md §3) → Promotion gate → promote.py
           count every integrated return in changes_since_critique, and promotions and
           refutations in substantive_changes_since_critique
         run /critique when (substantive ≥ 1 and changes ≥ 2) or changes ≥ 6; reset both
         on a change of strategy: a second /critique, then Pre-strategy-change gate, then /research-plan
         stop the loop when the established claims carry the answer, or a budget is spent
finalize: /critique (final) → Pre-finalize gate → /finalize → integrate
```

## End

Write `sessions/S<n>/report.md` (format in `/session-run`), run regen, commit, and run `session.py end`. Then tell the operator:

- the outcome (completed, or which budget stopped the run) and the dispatches and derivations used;
- the artefacts produced, the established claims (one line each), the working claims still open, the dead ends added;
- the number of decisions taken without them, with a pointer to the session log;
- what to read first: `answer.md` and the decisions in the log, or, if the run stopped early, the card or artefact to look at.
