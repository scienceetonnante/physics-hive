---
id: CL-S1-2
kind: claim
statement: 'To the next order, the period of the simple pendulum released from rest at angle $\theta_0$ (in radians) is $T = 2\pi\sqrt{L/g}\,\left(1 + \tfrac{1}{16}\theta_0^2 + \tfrac{11}{3072}\theta_0^4 + O(\theta_0^6)\right)$.'
depends_on: [CL-S1-1]
produced_by: {kind: agent, model: claude-opus-5-5, operator: dlouapre}
session: S1
supersedes: []
---
A by-product of the work on CL-S1-1, which it extends by one order; the session brief only asked for the $\theta_0^2$ coefficient. Same setting and same measure of the amplitude as CL-S1-1. Unlike $1/16$, the coefficient $11/3072$ changes under any reparametrisation $\theta_0 \to \theta_0 + O(\theta_0^3)$ of the amplitude.

In the record, the evidence is computation C-S1-1 with its confirming review. C-S1-1 obtains $11/3072$ from two symbolic series of the exact period, and from least-squares fits of numerically evaluated periods, both through the elliptic integral and by integrating the equation of motion (fitted $b = 0.0035807290$, against $11/3072 = 0.0035807292$). Derivation D-S1-1 also contains the value (its Eq. 15, from the elliptic-integral route only), but no review has examined D-S1-1 against this statement, so it is not attached as evidence.

Its practical use is the error of the order-2 formula: $T_0(1 + \theta_0^2/16)$ underestimates the exact period by about $(11/3072)\,\theta_0^4$, that is $2.2\times10^{-4}$ at $\theta_0 = 0.5$ rad and $3.6\times10^{-3}$ at $1$ rad (C-S1-1). The next coefficient, $173/737280$ for $\theta_0^6$, appears in C-S1-1 and was reproduced by both reviews, but it has no card.
