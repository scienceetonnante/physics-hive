---
id: CL-S1-1
kind: claim
statement: 'The period of the simple pendulum released from rest at angle $\theta_0$ (in radians) is $T = 2\pi\sqrt{L/g}\,\left(1 + \tfrac{1}{16}\theta_0^2 + O(\theta_0^4)\right)$, so the coefficient of the $\theta_0^2$ correction is $a = 1/16$.'
depends_on: []
produced_by: {kind: agent, model: claude-opus-5-5, operator: dlouapre}
session: S1
supersedes: []
---
The ideal pendulum of `conventions.md`: point mass on a massless rigid rod of length $L$, uniform gravity $g$, no friction, equation of motion $\theta'' + \omega_0^2 \sin\theta = 0$. The amplitude $\theta_0$ is the angle from the downward vertical at which the pendulum is at rest, $0 < \theta_0 < \pi$, in radians. The coefficient $1/16$ refers to this measure of the amplitude: it holds for any measure equal to $\theta_0 + O(\theta_0^3)$, but it is $1/4$ in $k^2 = \sin^2(\theta_0/2)$ and $1/8$ in $1 - \cos\theta_0$.

Derivation D-S1-1 obtains $a = 1/16$ by two routes that share only the equation of motion: the exact period $T = (4/\omega_0) K(k)$, with modulus $k = \sin(\theta_0/2)$, expanded in $k$; and a Lindstedt–Poincaré expansion of the equation of motion. The first route also shows that the remainder is $O(\theta_0^4)$, since $T/T_0$ is analytic and even in $\theta_0$ for $|\theta_0| < \pi$.

Computation C-S1-1 obtains the same value independently: three symbolic routes (SymPy), and two numerical paths, the exact period through the elliptic integral (mpmath and SciPy) and a direct integration of the equation of motion, from which the fitted coefficient is $0.0625000000026 \pm 3.5\times10^{-10}$. Each artefact has a confirming blind review.

The correction is positive: the restoring torque $\sin\theta$ is weaker than $\theta$, so large swings are slower. At $\theta_0 = 0.5$ rad the correction is about 1.6 %.
