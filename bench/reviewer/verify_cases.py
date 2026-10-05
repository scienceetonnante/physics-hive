# /// script
# requires-python = ">=3.11"
# dependencies = ["sympy>=1.12", "numpy>=1.26", "scipy>=1.11"]
# ///
"""Check the physics of the benchmark cases, independently of the artefacts.

For each pair, the result of the correct case is re-derived or tested by a route different
from the one in the artefact, and the result of the planted case is shown to fail the same
test. Run it after editing or adding a case:

  uv run bench/reviewer/verify_cases.py
"""

from __future__ import annotations

import numpy as np
import sympy as sp
from scipy.integrate import quad, solve_ivp
from scipy.special import ai_zeros

failures = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}")
    if not ok:
        failures.append(name)


def kapitza() -> None:
    """Equation of motion from the Lagrangian, then direct integration of the full equation."""
    t, a, w, l, g, m = sp.symbols("t a omega l g m", positive=True)
    th = sp.Function("theta")(t)
    x, y = l * sp.sin(th), a * sp.cos(w * t) - l * sp.cos(th)
    L = m / 2 * (sp.diff(x, t) ** 2 + sp.diff(y, t) ** 2) - m * g * y
    eom = sp.diff(sp.diff(L, sp.diff(th, t)), t) - sp.diff(L, th)
    thdd = sp.solve(eom, sp.diff(th, t, 2))[0]
    expected = -(g / l) * sp.sin(th) + (a * w**2 / l) * sp.cos(w * t) * sp.sin(th)
    check("kapitza: equation of motion (4)", sp.simplify(thdd - expected) == 0)

    def deviation(ratio: float, omega: float = 200.0) -> tuple[float, float]:
        """Max |theta - pi| and slow angular frequency, for g = l = 1 and a^2 w^2 = ratio g l."""
        amp = np.sqrt(ratio) / omega
        rhs = lambda tt, s: [s[1], (-1 + amp * omega**2 * np.cos(omega * tt)) * np.sin(s[0])]
        ts = np.linspace(0, 60, 60001)
        sol = solve_ivp(rhs, [0, 60], [np.pi + 0.01, 0.0], t_eval=ts, rtol=1e-10, atol=1e-12,
                        max_step=2 * np.pi / omega / 30)
        psi = sol.y[0] - np.pi
        spectrum = np.abs(np.fft.rfft(psi - psi.mean()))
        freqs = 2 * np.pi * np.fft.rfftfreq(len(ts), ts[1] - ts[0])
        low = freqs < 20  # the slow motion only
        return float(np.max(np.abs(psi))), float(freqs[low][np.argmax(spectrum[low])])

    unstable, _ = deviation(1.5)
    check("kapitza: a^2 w^2 = 1.5 g l is unstable (the planted claim says stable)", unstable > 1, f"max |theta - pi| = {unstable:.2f}")
    stable, omega_slow = deviation(4.0)
    check("kapitza: a^2 w^2 = 4 g l is stable", stable < 0.05, f"max |theta - pi| = {stable:.3f}")
    bin_width = 2 * np.pi / 60  # frequency resolution of the spectrum over 60 time units
    check("kapitza: slow frequency at a^2 w^2 = 4 g l is 1 (correct; planted predicts sqrt(3))",
          abs(omega_slow - 1.0) <= bin_width, f"measured {omega_slow:.3f}, spectral resolution {bin_width:.3f}")


def anharmonic() -> None:
    """Exact diagonalisation in a large basis, then the lambda^2 coefficient by extrapolation."""
    n = 80
    adag = np.diag(np.sqrt(np.arange(1, n)), -1)
    x = (adag + adag.T) / np.sqrt(2)
    h0, x4 = np.diag(np.arange(n) + 0.5), np.linalg.matrix_power(x, 4)
    c2 = lambda lam: (np.linalg.eigvalsh(h0 + lam * x4)[0] - 0.5 - 0.75 * lam) / lam**2
    estimate = 2 * c2(5e-4) - c2(1e-3)  # removes the term linear in lambda
    check("anharmonic: c2 = -21/8 from diagonalisation (planted: -9/4)", abs(estimate + 21 / 8) < 1e-3, f"{estimate:.5f}")


def sphere() -> None:
    """Image solution: equipotential surface, zero charge, and the two limits of the force."""
    q, R, d, e0, gam, s = sp.symbols("q R d epsilon_0 gamma s", positive=True)
    qp, b = -q * R / d, R**2 / d
    surface = q / sp.sqrt(R**2 + d**2 - 2 * R * d * sp.cos(gam)) + qp / sp.sqrt(R**2 + b**2 - 2 * R * b * sp.cos(gam))
    check("sphere: grounded images give zero potential on the sphere", sp.simplify(surface) == 0)
    force = q / (4 * sp.pi * e0) * (qp / (d - b) ** 2 - qp / d**2)
    claim = -q**2 * R**3 * (2 * d**2 - R**2) / (4 * sp.pi * e0 * d**3 * (d**2 - R**2) ** 2)
    planted = claim / R**2
    check("sphere: force (10)", sp.simplify(force - claim) == 0)
    alpha = 4 * sp.pi * e0 * R**3  # polarisability of a conducting sphere
    dipole = -2 * alpha * q**2 / (4 * sp.pi * e0) ** 2 / d**5
    check("sphere: far field equals the induced-dipole force", sp.limit(claim / dipole, d, sp.oo) == 1)
    check("sphere: planted force fails the far-field limit", sp.limit(planted / dipole, d, sp.oo) != 1)
    plane = -q**2 / (16 * sp.pi * e0 * s**2)  # image force of a plane at distance s
    check("sphere: near field equals the plane image force", sp.limit(claim.subs(d, R + s) / plane, s, 0) == 1)


def square_well() -> None:
    """Numerical quadrature of the Mayer function, and the low-temperature behaviour."""
    b0 = 2 * np.pi / 3
    closed = lambda kT, lam=1.5: b0 * (1 - (lam**3 - 1) * np.expm1(1 / kT))
    planted = lambda kT, lam=1.5: b0 * (1 - (lam**3 - 1) * np.expm1(-1 / kT))
    for kT in (0.5, 1.0, 3.0):
        numeric = b0 - 2 * np.pi * quad(lambda r: np.expm1(1 / kT) * r**2, 1, 1.5)[0]  # u = -1 in the well
        check(f"square well: closed form at kT = {kT}", abs(numeric - closed(kT)) < 1e-12 * abs(numeric))
    check("square well: B2 < 0 at low T, as for any attractive well (planted stays > b0)",
          closed(0.3) < 0 and planted(0.3) > b0)
    boyle = 1 / np.log(1.5**3 / (1.5**3 - 1))
    check("square well: B2 vanishes at the Boyle temperature", abs(closed(boyle)) < 1e-12, f"kT_B = {boyle:.4f} eps")


def orbit_clock() -> None:
    """Christoffel symbols from the metric, and the rate directly from the line element."""
    t, r, th, ph, rs, c = sp.symbols("t r theta phi r_s c", positive=True)
    coords = (t, r, th, ph)
    metric = sp.diag(-(1 - rs / r) * c**2, 1 / (1 - rs / r), r**2, r**2 * sp.sin(th) ** 2)
    inv = metric.inv()
    gamma = lambda a, b, cc: sp.simplify(sum(inv[a, k] * (sp.diff(metric[k, b], coords[cc]) + sp.diff(metric[k, cc], coords[b])
                                                         - sp.diff(metric[b, cc], coords[k])) for k in range(4)) / 2)
    omega2 = sp.simplify(-gamma(1, 0, 0) / gamma(1, 3, 3).subs(th, sp.pi / 2))
    check("orbit clock: Omega^2 = GM/r^3", sp.simplify(omega2 - c**2 * rs / (2 * r**3)) == 0)
    rate2 = sp.simplify((1 - rs / r) - r**2 * omega2 / c**2)  # from ds^2 with dr = 0
    check("orbit clock: (dtau/dt)^2 = 1 - 3 r_s/(2r) from the line element", sp.simplify(rate2 - (1 - 3 * rs / (2 * r))) == 0)
    planted2 = (1 - rs / r) * (1 - rs / (2 * r))
    check("orbit clock: rate vanishes at the photon sphere r = 3 r_s/2 (planted gives 2/9 for the square)",
          rate2.subs(r, 3 * rs / 2) == 0 and planted2.subs(r, 3 * rs / 2) == sp.Rational(2, 9))


def bouncer() -> None:
    """WKB levels against the exact levels, which are the zeros of the Airy function."""
    exact = -ai_zeros(4)[0]
    wkb = np.array([(1.5 * np.pi * (n - 0.25)) ** (2 / 3) for n in range(1, 5)])
    planted = np.array([(1.5 * np.pi * (n + 0.5)) ** (2 / 3) for n in range(0, 4)])
    check("bouncer: WKB levels within 1% of the exact ones", bool(np.all(np.abs(wkb / exact - 1) < 0.01)),
          ", ".join(f"{w:.4f}/{e:.4f}" for w, e in zip(wkb, exact)))
    check("bouncer: planted ground state is far off", abs(planted[0] / exact[0] - 1) > 0.2, f"{planted[0]:.4f}")
    E, m, g, hbar, z, n = sp.symbols("E m g hbar z n", positive=True)
    action = sp.integrate(sp.sqrt(2 * m * (E - m * g * z)), (z, 0, E / (m * g)))
    level = sp.solve(sp.Eq(action, (n - sp.Rational(1, 4)) * sp.pi * hbar), E)[0]
    claim = (hbar**2 * m * g**2 / 2) ** sp.Rational(1, 3) * (sp.Rational(3, 2) * sp.pi * (n - sp.Rational(1, 4))) ** sp.Rational(2, 3)
    check("bouncer: levels (10) from the quantisation condition (7)", sp.simplify(level / claim) == 1)


for verify in (kapitza, anharmonic, sphere, square_well, orbit_clock, bouncer):
    verify()
print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed.")
raise SystemExit(1 if failures else 0)
