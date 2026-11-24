---
session: S1
goal: 'Find the coefficient of the θ₀² correction to the small-oscillation period of the simple pendulum, derived analytically and checked against a numerical evaluation of the exact period for several amplitudes.'
budget: 20
starts_from: []
---
## Goal

Find the period T of the simple pendulum (point mass on a massless rigid rod, no friction, uniform gravity) to first non-trivial order in the amplitude θ₀: the coefficient c in T = 2π√(L/g) (1 + c θ₀² + O(θ₀⁴)). Derive c analytically, and check it against a numerical evaluation of the exact period (complete elliptic integral) at several amplitudes.

## Why

This is the goal of `project.md`, which lists no next step yet. The contributor asked to proceed with it as the session's brief.

## Plan of work

1. Fix the notation in `conventions.md` (angle, amplitude, small-oscillation period, elliptic-integral convention), so that the derivation and the computation use the same symbols.
2. `/derive` the coefficient c analytically (claim CL-S1-1), then `/review` the derivation.
3. `/compute` independently: the series of the exact period, and a numerical evaluation of the exact period at several amplitudes, compared with the second-order formula, including a check that the residual scales as θ₀⁴. Then `/review` the computation.
4. `/critique` the state before ending.

No literature survey is planned: the goal does not depend on it.

## Stop conditions

- The goal is reached: c is derived, the derivation and an independent computation are each confirmed by a blind review.
- The budget of 20 dispatches is spent (about 6 are expected).
- No progress: 4 dispatches in a row that add nothing towards the goal.
- The work shows that `project.md` should change.
