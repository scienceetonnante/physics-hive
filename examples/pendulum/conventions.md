# Conventions

<!--
Notation, units, sign conventions, metric signature, normalisations. Agents
read this file before every derivation and computation, and may edit it when
the work fixes a convention; every change they make is shown as a diff in their
session's debrief. Free text. It may start empty: write the conventions you
already know you want, and the sessions add the others.
-->

## Simple pendulum

- $L$: length of the rod; $g$: gravitational acceleration; $M$: mass (drops out of the period; the letter $m$ is kept for the elliptic parameter below).
- $\theta(t)$: angle of the rod from the downward vertical, in radians. The equation of motion is $\ddot\theta + \omega_0^2 \sin\theta = 0$.
- $\omega_0 = \sqrt{g/L}$; $T_0 = 2\pi/\omega_0 = 2\pi\sqrt{L/g}$ is the small-oscillation period.
- $\theta_0 \in (0, \pi)$: the amplitude, i.e. the maximum angle reached, in radians.
- $T(\theta_0)$: the exact period at amplitude $\theta_0$. Expansions in the amplitude are written $T = T_0\,(1 + c_2\,\theta_0^2 + c_4\,\theta_0^4 + \dots)$.

## Elliptic integrals

- $K(k) = \int_0^{\pi/2} \frac{d\phi}{\sqrt{1 - k^2 \sin^2\phi}}$ is the complete elliptic integral of the first kind, written with the **modulus** $k$.
- Some libraries take the **parameter** $m = k^2$ instead (for instance `scipy.special.ellipk(m)` and `mpmath.ellipk(m)`). Say which one is used whenever a library is called.
