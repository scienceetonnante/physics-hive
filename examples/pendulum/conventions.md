# Conventions

<!--
Notation, units, sign conventions, metric signature, normalisations. Agents
read this file before every derivation and computation, and may edit it when
the work fixes a convention; every change they make is shown as a diff in their
session's debrief. Free text.
-->

## The simple pendulum

- A point mass m on a massless rigid rod of length L, in uniform gravity g, without friction. Motion in a vertical plane.
- θ is the angle of the rod from the downward vertical, in radians. The equation of motion is θ'' + ω₀² sin θ = 0.
- θ₀ > 0 is the amplitude, the largest value of |θ| during the motion, in radians. The pendulum is released from rest at θ = θ₀ (it oscillates, so 0 < θ₀ < π).
- ω₀ = √(g/L) is the small-oscillation angular frequency and T₀ = 2π/ω₀ = 2π√(L/g) the small-oscillation period.
- T(θ₀) is the exact period at amplitude θ₀. Corrections are written T = T₀ (1 + a θ₀² + O(θ₀⁴)).

## Elliptic integrals

- k = sin(θ₀/2) is the elliptic modulus; m = k² is the parameter.
- K(k) = ∫₀^{π/2} dφ / √(1 − k² sin²φ) is the complete elliptic integral of the first kind, written with the modulus k.
- SciPy's `scipy.special.ellipk(m)` and mpmath's `mpmath.ellipk(m)` both take the parameter m = k², not the modulus.
