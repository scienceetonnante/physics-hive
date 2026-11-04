---
name: review
description: Blind, test-based review of a derivation (D-…) or computation (C-…) against the statement of a claim, by a fresh-context reviewer sub-agent that is told nothing about who produced the work and never sees earlier reviews. Writes one review file next to the target.
agent: reviewer
arguments_hint: <artefact id> [claim id]
---

Run an independent review of an artefact. The `reviewer` sub-agent checks whether the artefact establishes a stated claim, runs tests with a clear outcome first, and writes its verdict (`confirmed`, `refuted` or `inconclusive`) in a new file next to the target.

## Steps

1. **Resolve the target and the claim.** The target is a derivation (`derivations/<id>.summary.md` and `.tex`) or a computation (`computations/<id>.md`, `.py`, `.out`). The claim under review is normally the card the artefact supports; for a re-check or to attach an existing artefact to a later card, it is that later card. Copy the claim's **statement** from its card.

2. **Get the output path** with `session.py next review <target id>` (for example `derivations/D-S3-2_R-S12-1.md`).

3. **Dispatch the `reviewer` sub-agent** (see the dispatch syntax for your harness in AGENTS.md) with, inline:
   - the target ID and its files;
   - the statement of the claim under review, and the card ID(s) to record in `supports`;
   - the output path and the session ID;
   - if useful as cross-checks, a few established statements (statements only) and a pointer to `conventions.md` and to the references the target cites.

   **Blind and without priors.** Do not pass the card's path, the model or operator that produced the work, or the name of a human author. Do not pass earlier verdicts, objections or framing. The reviewer reads the target directly.

4. **Integrate** (AGENTS.md §6):
   - Read the verdict and check that the review file exists.
   - A confirming review needs no card: `regen` counts it as evidence for the cards in `supports`.
   - On `refuted` or `inconclusive`, do not act yet. Dispatch a second `/review` of the same target, with no mention of the first. If the second also refutes, write a dead-end card that refutes the claim (and names the reason, such as the equation at fault); then decide whether a new `/derive` or `/compute` should attempt the corrected claim. If the two reviews disagree, record the disagreement in the log and seek a third, independent check (often a `/compute`).
   - Disposition every flag in the session log and log the dispatch.
   - Run regen and commit: `[S<n>] review(<review id>): <verdict, one line>`.
