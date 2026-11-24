---
id: P-physics_0510206
kind: paper
title: 'An accurate formula for the period of a simple pendulum oscillating beyond the small angle regime'
authors: ['F. M. S. Lima', 'P. Arun']
year: 2006
arxiv: 'physics/0510206'
inspire: null
doi: '10.1119/1.2215616'
journal: 'Am. J. Phys. 74, 892'
why: 'A citable, peer-reviewed paper that states in one place the exact period $T = 4\sqrt{L/g}\,K(k)$ with modulus $k=\sin(\theta_0/2)$ and the second-order formula $T_2 = T_0(1+\theta_0^2/16)$, which it attributes to Bernoulli (1749).'
topic: 'Exact period and its expansion in the amplitude'
rating: high
session: S2
---
## Question

How the period of the simple pendulum grows with the amplitude, and which simple closed formula best approximates the exact period for amplitudes up to $90^\circ$, compared with experimental data.

## Method

Energy conservation gives $T = 2\sqrt2\sqrt{L/g}\int_0^{\theta_0} d\theta/\sqrt{\cos\theta-\cos\theta_0}$ (their Eq. 4). The substitutions $\cos\theta = 1-2\sin^2(\theta/2)$ and $\sin\varphi = \sin(\theta/2)/\sin(\theta_0/2)$ turn it into a complete elliptic integral of the first kind (their Eq. 5). The authors then approximate the integrand $\sqrt{1-k^2\sin^2\varphi}$ by a straight line between its end values, which gives a logarithmic formula. They compare its relative error with that of the small-angle period $T_0$, of Bernoulli's second-order formula, and of the Kidd–Fogg and Molina formulas, and with pendulum measurements (their own and two older data sets).

## Main result

- Exact period (their Eq. 5): $T = 4\sqrt{L/g}\int_0^{\pi/2} d\varphi/\sqrt{1-k^2\sin^2\varphi} = 4\sqrt{L/g}\,K(k)$, with $k \equiv \sin(\theta_0/2)$, equivalently $T = (2T_0/\pi)\,K(k)$.
- Second-order formula (their Eq. 11): $T_2 = T_0\,(1+\theta_0^2/16)$, "found by Bernoulli in 1749 from a perturbative analysis", which they call "perhaps the most famous formula for the large angle period". They state that its relative error exceeds 0.1% above $41^\circ$ and 0.5% above $60^\circ$. The paper states this formula but does not derive it.
- Their own approximation: $T_{\log} = -T_0 \ln a/(1-a)$ with $a = \cos(\theta_0/2)$, with relative error below 0.1% up to $74^\circ$.

I checked numerically (mpmath, outside the record) that $(2/\pi)K(\sin(\theta_0/2))$ minus $1+\theta_0^2/16$ gives a relative error of 0.094% at $41^\circ$ and 0.43% at $60^\circ$, consistent with their stated thresholds.

## Assumptions

Ideal simple pendulum: point mass on a massless rigid rod, no friction, uniform gravity, released from rest at $\theta_0$, with $|\theta_0| < \pi$.

## Conventions

Same as `conventions.md`: $\theta$ measured from the downward vertical, $T_0 = 2\pi\sqrt{L/g}$, and $K(k)$ written with the **modulus** $k = \sin(\theta_0/2)$ (not the parameter $m = k^2$). The mass is written $m$ (our $M$).

## Relevance

This is the best readable, peer-reviewed reference found for both formulas the project needs: the exact elliptic-integral period, with the same modulus convention as `conventions.md`, and the coefficient $c_2 = 1/16$. The attribution to Bernoulli (1749) is second-hand: the paper cites it to C. J. Smith, *A Degree Physics, Part I: The General Properties of Matter* (Edward Arnold, London, 1960), which I did not read. For the elliptic integral the paper cites Thornton and Marion, *Classical Dynamics of Particles and Systems*, 5th ed. (2004), pp. 155–158 and Appendix B, and Abramowitz and Stegun, p. 589. The published version is Am. J. Phys. 74, 892–895 (2006); I read the LaTeX source of the latest arXiv version, not the journal version, so equation numbers may differ slightly from the published text. Rating high for citation purposes; it adds nothing to the derivation itself.
