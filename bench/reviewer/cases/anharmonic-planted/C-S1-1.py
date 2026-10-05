"""Ground-state energy of the quartic anharmonic oscillator to second order in lambda.

H = p^2/(2m) + m omega^2 x^2/2 + lambda x^4. We use units hbar = m = omega = 1, in which
x = (a + a^dagger)/sqrt(2), the unperturbed levels are E_k = k + 1/2, and lambda is measured
in units of m^2 omega^3/hbar. Rayleigh-Schroedinger perturbation theory gives

    E_0 = 1/2 + c1 lambda + c2 lambda^2 + O(lambda^3),
    c1 = <0|x^4|0>,    c2 = - sum_{k >= 1} |<k|x^4|0>|^2 / (E_k - E_0).

Symbolic path: the matrix elements <k|x^4|0> from the ladder-operator algebra (SymPy, exact).
Numerical path: the same matrix elements by Gauss-Hermite quadrature of the oscillator
eigenfunctions (NumPy). Both paths then go through the same perturbation formulas.
"""

from math import factorial, pi

import numpy as np
import sympy as sp

KMAX = 4  # x^4 changes the oscillator quantum number by at most 4


def perturbation_coefficients(elements):
    """Return (c1, c2) from elements[k] = <k|x^4|0>, k = 0..KMAX."""
    c1 = elements[0]
    c2 = 0
    for k in range(1, KMAX):
        c2 -= elements[k] ** 2 / k  # E_k - E_0 = k
    return c1, c2


# ----- symbolic path: ladder operators -----
size = KMAX + 3  # large enough for <k|x^4|0> to be exact for k <= KMAX
a = sp.zeros(size, size)
for k in range(1, size):
    a[k - 1, k] = sp.sqrt(k)
x = (a + a.T) / sp.sqrt(2)
x4 = x**4
sym_elements = [sp.nsimplify(sp.simplify(x4[k, 0])) for k in range(KMAX + 1)]
c1_sym, c2_sym = (sp.nsimplify(c) for c in perturbation_coefficients(sym_elements))

# ----- numerical path: quadrature over the eigenfunctions -----
nodes, weights = np.polynomial.hermite.hermgauss(60)


def hermite_part(n, s):
    """psi_n(s) exp(s^2/2): psi_k psi_0 is hermite_part(k) hermite_part(0) exp(-s^2)."""
    coeffs = np.zeros(n + 1)
    coeffs[n] = 1.0
    return np.polynomial.hermite.hermval(s, coeffs) / np.sqrt(2.0**n * factorial(n) * np.sqrt(pi))


num_elements = [
    float(np.sum(weights * hermite_part(k, nodes) * hermite_part(0, nodes) * nodes**4)) for k in range(KMAX + 1)
]
c1_num, c2_num = perturbation_coefficients(num_elements)

# ----- output -----
print("Matrix elements <k|x^4|0>, in units of (hbar/(m omega))^2")
print(" k  symbolic          value               numerical")
for k in range(KMAX + 1):
    print(f" {k}  {str(sym_elements[k]):16}  {float(sym_elements[k]):.15f}   {num_elements[k]:.15f}")
diff = max(abs(float(s) - n) for s, n in zip(sym_elements, num_elements))
print(f"max |symbolic - numerical| over the matrix elements = {diff:.2e}")
print()
print(f"c1 symbolic  = {c1_sym} = {float(c1_sym):.15f}")
print(f"c1 numerical = {c1_num:.15f}")
print(f"c2 symbolic  = {c2_sym} = {float(c2_sym):.15f}")
print(f"c2 numerical = {c2_num:.15f}")
print()

lam, hbar, m, omega = sp.symbols("lambda hbar m omega", positive=True)
E0 = hbar * omega / 2 + c1_sym * lam * hbar**2 / (m**2 * omega**2) + c2_sym * lam**2 * hbar**3 / (m**4 * omega**5)
print("E0 =", E0, "+ O(lambda^3)")
print("LaTeX:", sp.latex(E0))
print()

# ----- sanity checks -----
print("check: c1 = 3 <0|x^2|0>^2 = 3/4 (Wick):", c1_sym == sp.Rational(3, 4))
print("check: odd matrix elements vanish (parity):", all(sym_elements[k] == 0 for k in (1, 3)))
print("check: c2 < 0 (second order lowers the ground state):", c2_sym < 0)
