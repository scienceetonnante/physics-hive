---
id: CL-S1-1
kind: claim
statement: 'The period of the simple pendulum at amplitude $\theta_0$ is $T = T_0\,(1 + \theta_0^2/16 + O(\theta_0^4))$ with $T_0 = 2\pi\sqrt{L/g}$, so $c_2 = 1/16$.'
depends_on: []
produced_by: {kind: agent, model: claude-opus-5-5, operator: dlouapre}
session: S1
supersedes: []
refutes: []
---
This answers the goal of `project.md`: the coefficient of the $\theta_0^2$ correction to the small-oscillation period.

Derivation D-S1-1 obtains it in two ways. First, energy conservation gives the exact period $T(\theta_0) = 4\sqrt{L/g}\,K(\sin(\theta_0/2))$, with $K$ written with the modulus $k$ (see `conventions.md`); expanding $K$ and $k = \sin(\theta_0/2)$ gives $T/T_0 = 1 + \theta_0^2/16 + 11\,\theta_0^4/3072 + O(\theta_0^6)$. Second, a Poincaré–Lindstedt calculation on $\sin\theta \approx \theta - \theta^3/6$ gives the same $c_2$.

Assumptions: point mass, massless rigid rod, no friction, uniform gravity, planar motion, libration ($0 < \theta_0 < \pi$), $\theta_0$ in radians. The next coefficient $c_4 = 11/3072$ is stated by D-S1-1 but is not the subject of this card.
