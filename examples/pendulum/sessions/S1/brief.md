---
session: S1
goal: 'Find the coefficient a of the θ₀² correction in T = 2π√(L/g)(1 + a θ₀² + O(θ₀⁴)) for the simple pendulum, derived analytically and checked against a numerical evaluation of the exact period at several amplitudes.'
budget: 10
starts_from: []
---
## Goal

Find the coefficient a of the θ₀² correction to the period of the simple pendulum (point mass on a massless rigid rod, no friction, uniform gravity), T = 2π√(L/g)(1 + a θ₀² + O(θ₀⁴)), where θ₀ is the amplitude in radians. Derive a analytically, and check it against a numerical evaluation of the exact period (complete elliptic integral) at several amplitudes.

## Why

This is the whole goal of `project.md`. Nothing has been done yet, and the target is small enough to be reached in one session.

## Plan of work

1. Fix the conventions in `conventions.md`: θ measured from the downward vertical, θ₀ the amplitude in radians, ω₀ = √(g/L), T₀ = 2π/ω₀, and the elliptic modulus k = sin(θ₀/2), with the parameter m = k² that SciPy's `ellipk` takes stated explicitly.
2. `/derive` D-S1-1: the coefficient a, analytically, by two independent analytic routes inside the same artefact if feasible. Supports the reserved card CL-S1-1.
3. `/compute` C-S1-1, independent of the derivation and dispatched in parallel with it: the series of the exact period, symbolically, and the exact period evaluated numerically at several amplitudes, with the coefficient extracted from the data. Also supports CL-S1-1.
4. `/review` each artefact blindly, then one `/critique`.
5. No literature survey unless the work needs a reference: the result is textbook material and the check asked for is numerical.

Budget: 10 dispatches.

## Stop conditions

- The coefficient is derived and confirmed by both reviewed artefacts.
- The budget of 10 dispatches is spent.
- No progress: 4 dispatches in a row that add nothing towards the goal.
- The work shows that `project.md` should change.
