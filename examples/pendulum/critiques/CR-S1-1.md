---
id: CR-S1-1
kind: critique
filed: 2026-11-24
status: resolved
---
## Summary
Filed critiques/CR-S1-1.md. 5 findings, all minor. The state supports stopping: the goal of `project.md` is reached in the record.

## Result
The goal asks for the coefficient of the $\theta_0^2$ correction, derived analytically and checked against a numerical evaluation of the exact period (complete elliptic integral) at several amplitudes. CL-S1-1 ($c_2 = 1/16$) has both. Derivation D-S1-1 obtains it from the elliptic-integral form and again by Poincaré–Lindstedt. Computation C-S1-2 was briefed without access to D-S1-1. It obtains $c_2$ symbolically by two routes and evaluates the exact period at 13 amplitudes from 0.01 to 3 rad, by three evaluations of $K$ and by a direct ODE integration that agree to $10^{-14}$. It also recovers $c_2$ from the ODE data alone to $3\times10^{-9}$. Each artefact has a confirming blind review with substantive tests of its own (quadrature, ODE runs, a hypergeometric series, a re-run of the script). Every flag is dispositioned in the log, and the parallel dispatch and the missing ID C-S1-1 are explained there. Nothing the goal asks for is missing. What remains is to bring the result into the lead's view and to ask what comes next.

1. **CL-S1-1 is still `working`, and the goal is reached only in the record.** The claim becomes established only when the lead ticks it into `draft.tex`. It passes the conditions of `check` (supporting artefacts with confirming reviews, nothing refuted). Resolve by putting a tick line in the debrief that copies the result of the note into the draft as a `result`. Its footnote should say "derivation D-S1-1 and independent computation C-S1-2, each confirmed by a blind review", which is robust evidence in the sense of the method. A second tick line can offer the body of `D-S1-1.tex` as an appendix.
2. **`project.md` has no Approach and no Next steps, and this session answers its whole goal.** Without an answer from the lead, the next session has no brief. Resolve by asking in the debrief whether the project ends here or what the lead wants next. Say that no answer means the project is considered complete. Do not draft a new direction without the lead.
3. **The artefacts contain more than CL-S1-1 states, and the note must not present the extra as separate results.** C-S1-2 and both reviews confirm $c_4 = 11/3072$, the exact period $T = 4\sqrt{L/g}\,K(\sin(\theta_0/2))$, and the accuracy of the second-order formula (relative error $-3.6\times10^{-3}$ at 1 rad, $-5.9\times10^{-2}$ at 2 rad, $-0.39$ at 3 rad). The note names a card for each result, and CL-S1-1 covers only $c_2$. Resolve by telling the writer to give these as context under the result of CL-S1-1, not as results of their own. If you want $c_4$ to be a result, it needs its own claim card and a review that names that card in `supports`.
4. **One notation in C-S1-2.md departs from `conventions.md`.** Line 51 writes $K(m) = \pi/2 + \pi m/8 + \dots$, a series in the parameter $m = k^2$. `conventions.md` defines $K$ with the modulus $k$, so a reader of the note would take $K(m)$ as $K$ at modulus $m$, and the series would then be wrong. The artefact itself is clear in context and needs no change. Resolve by asking the writer to write the series in the modulus ($K(k) = \tfrac{\pi}{2}(1 + k^2/4 + 9k^4/64 + \dots)$), or to say explicitly that the argument is the parameter.
5. **No paper card exists, so nothing can be cited.** $c_2 = 1/16$ is a classical result. The C-S1-2 reviewer compared the coefficients with "standard values" from memory, not from a source in the workspace. Resolve by telling the writer not to add any `\cite` and not to suggest that the result is new. If the lead wants the draft to cite the classical source, a short `/survey` in a later session can add the paper card. That can be one line in the question of finding 2.

## Flags
- (none)

## Findings
1. CL-S1-1 is `working` until the lead ticks it into the draft. Add a debrief tick line that copies the note's result into `draft.tex` as a `result`, with the evidence footnote (D-S1-1 and the independent C-S1-2, each confirmed by a blind review: robust). Optionally, add a second line offering D-S1-1 as an appendix.
2. `project.md` lists no next step, and the goal is answered. Ask the lead in the debrief whether the project ends or continues, and say that no answer means it is complete.
3. $c_4$, the exact period formula and the accuracy table appear in the artefacts but have no card of their own. Instruct the writer to present them as context under CL-S1-1. If any of them should become a result, write a card for it and dispatch a review that names that card.
4. C-S1-2.md line 51 writes $K(m)$ for a series in the parameter, against the modulus convention of `conventions.md`. Instruct the writer to use the modulus form, or to label the argument as the parameter.
5. There are no paper cards. Instruct the writer to add no citation and to make no claim of novelty. If the lead wants a reference, offer a short `/survey` for a later session.

## Resolution
1. Resolved: the S1 debrief offers a tick line that copies the result of note S1 into `draft.tex` as a `result` naming CL-S1-1, with the evidence footnote, and a second line that adds D-S1-1 as an appendix.
2. Resolved: the S1 debrief asks the lead whether the project ends here or what comes next, and says that no answer means the project is considered complete.
3. Resolved: the writer is told to present $c_4$, the exact period formula and the accuracy table as context under the result of CL-S1-1, not as results of their own. No card is written for them, since the goal of `project.md` asks only for $c_2$.
4. Resolved: the writer is told to write series of $K$ in the modulus $k$, following `conventions.md`. C-S1-2 is left unchanged.
5. Resolved: the writer is told to add no citation and to claim no novelty. The debrief offers a later `/survey` for the classical reference as a tick line.
