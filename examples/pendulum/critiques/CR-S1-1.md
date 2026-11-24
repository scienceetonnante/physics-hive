---
id: CR-S1-1
kind: critique
filed: 2026-11-09
status: resolved
---
## Summary
Filed critiques/CR-S1-1.md. 6 findings.

## Result
1. **The goal of project.md is met in the record, but nothing is established, and project.md has no next step.** The evidence for CL-S1-1 matches what the goal asks for: an analytic derivation by two routes (D-S1-1) and a numerical check against the complete elliptic integral at twelve amplitudes, plus a direct integration of the equation of motion (C-S1-1). Each artefact has a confirming blind review. The draft is empty, though, so CL-S1-1 is still a working claim. Resolve: in the debrief, offer a tick line that copies the CL-S1-1 result into the draft (evidence: robust). Optionally offer D-S1-1 as an appendix. Ask whether the project is complete or what comes next. Do not call the claim "established" in the note or the debrief.
2. **The statements depend on θ₀ being the angular amplitude in radians, and they do not say so.** a = 1/16 holds for any amplitude measure equal to θ₀ + O(θ₀³). It becomes 1/4 in k² = sin²(θ₀/2) and 1/8 in 1 − cos θ₀. The θ₀⁴ coefficient 11/3072 changes even under θ₀ → θ₀ + O(θ₀³). Resolve: in the writer's dispatch, require each result block to define θ₀ and T₀ explicitly. No new work is needed.
3. **C-S1-1.md writes K(m), where conventions.md writes K(k).** The numbers are right. But if a note copied "(2/π)K(sin²(θ₀/2))" and a reader took K in the modulus notation of conventions.md, the formula would give a = 0. Resolve: the writer's dispatch should require T = (4/ω₀)K(k) with k = sin(θ₀/2). Leave C-S1-1.md as it is.
4. **Two card bodies are out of date.** CL-S1-1 still says C-S1-1 "is planned". CL-S1-2 says that 173/737280 "has not been checked by a second artefact", but both reviews reproduced it. Resolve: correct both bodies in place before `session.py end`.
5. **CL-S1-2 contains CL-S1-1 but has `depends_on: []`.** If CL-S1-1 were ever refuted, CL-S1-2 would not be flagged as needs re-check. Resolve: set `depends_on: [CL-S1-1]` before the session ends.
6. **In the record, CL-S1-2 rests on one artefact.** The full evidence is stronger: the reviewer confirmed it by three independent routes, and D-S1-1 also contains the value, but D-S1-1 is not attached to CL-S1-2. Resolve: if CL-S1-2 is offered for the draft, describe its evidence as it stands in the record. A /review of D-S1-1 against the statement of CL-S1-2 would attach a second artefact, but it is only worth a dispatch if the researcher wants the θ₀⁴ term in the draft.

## Flags
- Findings 4 and 5 must be applied before `session.py end`, because cards cannot change after their session.
- No candidate refutation, and no earlier work needs redoing.

## Findings

1. **The goal of `project.md` is met in the record, but nothing is established yet, and `project.md` has no next step.**
   The goal asks for the θ₀² coefficient, "derived analytically and checked against a numerical evaluation of the exact period (complete elliptic integral) for several amplitudes". D-S1-1 derives a = 1/16 by two analytic routes: the elliptic integral expanded in k, and Lindstedt–Poincaré. It also bounds the remainder rigorously (Eq. 11 of the derivation). C-S1-1 evaluates the elliptic integral with mpmath and SciPy at twelve amplitudes from 10⁻³ to 1 rad. It also integrates the equation of motion directly, which does not use the formula T = 4K/ω₀ at all, and extracts a from the data. Each artefact has a confirming blind review, and both reviewers ran their own independent checks. I found no gap in this evidence, and the values agree with the known series.
   The draft is empty, however, so CL-S1-1 is a working claim. It becomes established only when the researcher ticks a line that copies it into `draft.tex`. Both reviews use "established" in its everyday sense ("CL-S1-1 is established by this computation"). The note and the debrief should not repeat that word. `project.md` has no Approach and no Next steps, so the session has no step to remove.
   *To resolve:* in the debrief, offer a tick line that copies the CL-S1-1 result of the note into the draft as a result. Describe its evidence as robust: a derivation with two analytic routes and an independent computation with symbolic, elliptic-integral and equation-of-motion paths, each confirmed by a blind review. Optionally, offer a tick line that adds the body of `D-S1-1.tex` as an appendix, as §8 of AGENTS.md suggests. Ask the researcher whether the project is complete or what should come next.

2. **The statements are correct only with θ₀ defined as the angular amplitude in radians, and the statements themselves do not say so.**
   `conventions.md` fixes θ₀ as the largest angle of the rod from the downward vertical, in radians, and every artefact follows it. Nothing is wrong in the record. But the coefficient depends on which amplitude variable is used:
   - a = 1/16 holds for any amplitude measure equal to θ₀ + O(θ₀³), such as the arc length or the horizontal displacement divided by L.
   - The same expansion has coefficient 1/4 in k² = sin²(θ₀/2). This is the variable of the elliptic series in both artefacts, so a reader of the note could easily confuse the two.
   - The coefficient is 1/8 in 1 − cos θ₀ (the release height divided by L), and (π/180)²/16 when θ₀ is in degrees (C-S1-1 already notes the degree case).
   - The θ₀⁴ coefficient 11/3072 of CL-S1-2 is more sensitive: it changes even under θ₀ → θ₀ + O(θ₀³). By my own arithmetic, which no artefact has checked, it becomes 25/1024 when the amplitude variable is sin θ₀.

   The statements of CL-S1-1 and CL-S1-2 say only "at amplitude θ₀". Once a block of the note is copied into the draft, its reader will not have `conventions.md` beside it.
   *To resolve:* in the writer's dispatch, require each result block to define θ₀ (the largest angle of the rod from the downward vertical, in radians) and T₀ = 2π√(L/g) (the full small-oscillation period). No new derivation or computation is needed.

3. **The notation for K in `C-S1-1.md` differs from `conventions.md`.**
   `conventions.md` writes the complete elliptic integral with the modulus, K(k), and notes that SciPy and mpmath take the parameter m = k². D-S1-1 and the header comment of `C-S1-1.py` follow this. `C-S1-1.md`, however, writes "(2/π)K(m) with m = sin²(θ₀/2)" in its Result section and displays "(2/π)K(m) = 1 + m/4 + …" in its Results section. The `.out` file prints the same. The numbers are right: the code passes m to every `ellipk` call, and the review checked this. The risk is in the note. If it copies this notation, and a reader takes K in the modulus notation of `conventions.md`, then K(sin²(θ₀/2)) = (π/2)(1 + θ₀⁴/64 + …) gives a = 0. This is the very error that `conventions.md` was written to prevent.
   *To resolve:* in the writer's dispatch, require the note to write T = (4/ω₀)K(k) with k = sin(θ₀/2), as in `conventions.md`, and to mention m = k² only where it talks about code. Do not edit `C-S1-1.md`, which is a sub-agent's artefact.

4. **The bodies of CL-S1-1 and CL-S1-2 are out of date, and cards cannot change once the session ends.**
   The last sentence of CL-S1-1 says "Computation C-S1-1 is planned as an independent check". C-S1-1 has since returned and been confirmed, and it is the second leg of the robust evidence. CL-S1-2 says that the θ₀⁶ coefficient 173/737280 "has not been checked by a second artefact". In fact, both reviews reproduced it in their own checks: D-S1-1_R-S1-1 in its Result section and its hand-evaluation row, and C-S1-1_R-S1-1 by a direct expansion of the energy integral. It is still true that no card states this coefficient. The note writer may read these cards.
   *To resolve:* before `session.py end`, correct both bodies in place, which is allowed for cards of the current session. In CL-S1-1, name C-S1-1 and its review as evidence. In CL-S1-2, say that both reviews reproduced 173/737280 and that no claim records it.

5. **CL-S1-2 contains CL-S1-1 but does not declare the dependency.**
   The statement of CL-S1-2 includes the θ₀²/16 term. If CL-S1-1 were ever refuted or revised, CL-S1-2 would be wrong too. With `depends_on: []`, however, `regen` would not mark it as needs re-check.
   *To resolve:* set `depends_on: [CL-S1-1]` in CL-S1-2 before the session ends. The stakes are low, since both claims are well checked.

6. **In the record, CL-S1-2 rests on a single artefact.**
   CL-S1-2 is a by-product, but it is accounted for: the C-S1-1 brief asked for the θ₀⁴ coefficient, and the log disposes of the D-S1-1 flag about it. It is therefore not unexplained work. Its evidence in the record is C-S1-1 with one confirming review.
   The full evidence is stronger. The reviewer of C-S1-1 confirmed 11/3072 by three routes that the computation does not use: Gauss's AGM formula at 60 digits, a direct expansion of the energy integral, and a 30-digit Taylor integration of the equation of motion. D-S1-1 also obtains 11/3072 (its Eq. 15), and its reviewer marked that equation as passing. That review, however, supports only CL-S1-1.
   *To resolve:* if the debrief offers CL-S1-2 for the draft, describe its evidence as it stands in the record: one computation confirmed by a blind review, plus a derivation that contains the value but is not attached to the claim. To attach a second artefact, run one /review of D-S1-1 against the statement of CL-S1-2. The log shows four dispatches before this critique, out of a budget of 10, so there is room. The goal of `project.md` does not need it, and I would spend the dispatch only if the researcher wants the θ₀⁴ term in the draft.

**Areas with no finding.**
- Unexplained work: none. The log records why D-S1-1 and C-S1-1 were dispatched in parallel before either review, and it accounts for CL-S1-2.
- Viability: the brief's approach reached its goal in four dispatches.
- Coherence: the two claims agree with each other and with the known series.
- Re-check flags: no card is flagged as needs re-check.
- Unreviewed evidence: every artefact cited as evidence has a confirming review.
- Steering: the briefs did not signal the expected value of a.

## Resolution

1. Resolved. The debrief offers a tick line copying CL-S1-1 into the draft as a result, with its evidence described as robust, a tick line offering D-S1-1 as an appendix, and a question on what comes next. The note and the debrief do not call the claim established.
2. Resolved. Both card statements now say that θ₀ is the angle of release from rest, in radians, and the CL-S1-1 body says how the coefficient changes with the measure of the amplitude. The writer's dispatch requires every result block to define θ₀ and T₀.
3. Resolved. The writer's dispatch requires the exact period to be written T = (4/ω₀)K(k) with k = sin(θ₀/2), in the modulus notation of conventions.md. C-S1-1.md is left as it is.
4. Resolved. Both card bodies corrected in place.
5. Resolved. CL-S1-2 now has depends_on: [CL-S1-1].
6. Deferred. The session's goal is reached and the brief says to stop there. The debrief offers CL-S1-2 for the draft with its evidence as it stands in the record (one computation with a confirming review). The handoff notes that a /review of D-S1-1 against CL-S1-2 would attach a second artefact if the researcher wants the θ₀⁴ term in the draft.

