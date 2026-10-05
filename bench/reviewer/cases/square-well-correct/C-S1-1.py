"""Second virial coefficient of a gas of square-well molecules.

Pair potential (conventions.md): u(r) = +inf for r < sigma, u(r) = -epsilon for
sigma < r < lambda*sigma, and u(r) = 0 for r > lambda*sigma, with epsilon > 0.

    B2(T) = -2 pi * integral_0^inf f(r) r^2 dr,   f(r) = exp(-u(r)/kT) - 1 (Mayer function).

Symbolic path: piecewise integration with SymPy, compared with the closed form.
Numerical path: adaptive quadrature of the Mayer function with SciPy, for sigma = 1,
epsilon = 1 and lambda = 1.5, at several temperatures.
"""

import numpy as np
import sympy as sp
from scipy.integrate import quad

r, sigma, lam, eps, kT = sp.symbols("r sigma lambda epsilon kT", positive=True)

# Value of the potential on each interval. Beyond lambda*sigma, u = 0 and f = 0.
U_CORE = sp.oo
U_WELL = -eps  # inside the well of depth epsilon
PIECES = [(U_CORE, 0, sigma), (U_WELL, sigma, lam * sigma)]


def mayer(u):
    return sp.exp(-u / kT) - 1


# ----- symbolic path -----
B2 = -2 * sp.pi * sum(sp.integrate(mayer(u) * r**2, (r, lo, hi)) for u, lo, hi in PIECES)
b0 = 2 * sp.pi * sigma**3 / 3  # hard-sphere value
closed_form = b0 * (1 - (lam**3 - 1) * (sp.exp(eps / kT) - 1))

print("B2 =", sp.simplify(B2))
print("B2 - closed form =", sp.simplify(B2 - closed_form))
print("closed form, LaTeX:", sp.latex(closed_form))
print()

# ----- numerical path -----
SIGMA, LAM, EPS = 1.0, 1.5, 1.0
u_well = float(U_WELL.subs(eps, EPS))


def mayer_num(rv, kTv):
    if rv < SIGMA:
        return -1.0
    if rv < LAM * SIGMA:
        return np.expm1(-u_well / kTv)
    return 0.0


def b2_num(kTv):
    core = quad(lambda rv: mayer_num(rv, kTv) * rv**2, 0, SIGMA)[0]
    well = quad(lambda rv: mayer_num(rv, kTv) * rv**2, SIGMA, LAM * SIGMA)[0]
    return -2 * np.pi * (core + well)


b2_sym = sp.lambdify(kT, B2.subs({sigma: SIGMA, lam: LAM, eps: EPS}))
b0_num = 2 * np.pi * SIGMA**3 / 3
print(f"sigma = {SIGMA}, epsilon = {EPS}, lambda = {LAM}; b0 = 2 pi sigma^3/3 = {b0_num:.12f}")
print("  kT/eps   B2 symbolic        B2 numerical       relative diff   B2/b0")
worst = 0.0
for kTv in (0.5, 1.0, 2.0, 5.0, 20.0, 100.0):
    s, n = float(b2_sym(kTv)), b2_num(kTv)
    rel = abs(s - n) / abs(s)
    worst = max(worst, rel)
    print(f"  {kTv:6.1f}   {s:16.12f}   {n:16.12f}   {rel:.1e}         {s / b0_num:.6f}")
print(f"largest relative difference: {worst:.1e}")
print()

# ----- sanity checks -----
print("check: B2 -> b0 as T -> infinity:", sp.simplify(sp.limit(B2, kT, sp.oo) - b0) == 0)
print("check: B2 = b0 at every T when lambda = 1 (no well):", sp.simplify(B2.subs(lam, 1) - b0) == 0)
