"""C-S1-1: coefficient a in T(theta0) = T0 (1 + a theta0^2 + O(theta0^4)) for the simple pendulum.

Conventions (conventions.md): theta'' + w0^2 sin(theta) = 0, released from rest at theta0,
T0 = 2 pi / w0. We work with w0 = 1, so T0 = 2 pi. Elliptic modulus k = sin(theta0/2),
parameter m = k^2; scipy.special.ellipk and mpmath.ellipk both take m.

Exact period (energy conservation, see section 0 below):
    T = 4 K(k) / w0,   so   T/T0 = (2/pi) K(k)   with K written with the modulus k.

Run from the workspace root:
    uv run --with sympy --with numpy --with scipy python computations/C-S1-1.py
"""

import csv
from pathlib import Path

import mpmath as mp
import numpy as np
import sympy as sp
from scipy.integrate import solve_ivp
from scipy.special import ellipk as sc_ellipk

HERE = Path(__file__).resolve().parent
mp.mp.dps = 40

# ---------------------------------------------------------------------------
# 0. The exact period, and a numerical check that the elliptic form is right
# ---------------------------------------------------------------------------
# Energy (w0 = 1): theta'^2/2 - cos(theta) = -cos(theta0)
#   => T = 4 * int_0^theta0 dtheta / sqrt(2 (cos theta - cos theta0)).
# cos(theta) - cos(theta0) = 2 (k^2 - sin^2(theta/2)); substituting
# sin(theta/2) = k sin(phi) turns it into T = 4 K(k).
print("=" * 78)
print("0. Exact period: energy integral vs 4 K(k), w0 = 1 (mpmath, 40 digits)")
print("=" * 78)
for th0 in ["0.001", "0.1", "0.5", "1.0", "2.0", "3.0"]:
    th0 = mp.mpf(th0)
    # cos(theta) - cos(theta0) = 2 sin((theta0+theta)/2) sin((theta0-theta)/2). With theta = theta0 - u^2
    # this avoids the cancellation at the turning point and removes the 1/sqrt endpoint singularity.
    T_energy = 4 * mp.quad(lambda u: 2 * u / mp.sqrt(4 * mp.sin(th0 - u ** 2 / 2) * mp.sin(u ** 2 / 2)),
                           [0, mp.sqrt(th0)])
    T_ellip = 4 * mp.ellipk(mp.sin(th0 / 2) ** 2)
    print(f"theta0 = {mp.nstr(th0, 4):>6}:  T_energy = {mp.nstr(T_energy, 25)}"
          f"  4K = {mp.nstr(T_ellip, 25)}  rel diff = {mp.nstr(abs(T_energy / T_ellip - 1), 3)}")

# ---------------------------------------------------------------------------
# 1. Symbolic path
# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("1. Symbolic (SymPy)")
print("=" * 78)
th, m, phi = sp.symbols("theta0 m phi", positive=True)
N = 8  # series order in theta0 (exclusive)

# 1a. Series of (2/pi) K(m) with SymPy's elliptic_k (parameter convention), m = sin^2(theta0/2).
ratio_ellip = 2 / sp.pi * sp.elliptic_k(sp.sin(th / 2) ** 2)
ser_a = sp.series(ratio_ellip, th, 0, N).removeO()
print("1a. (2/pi) elliptic_k(sin^2(theta0/2)) =", sp.series(ratio_ellip, th, 0, N))

# 1b. Independent: expand the integrand of K in m and integrate term by term over phi.
integrand_ser = sp.series(1 / sp.sqrt(1 - m * sp.sin(phi) ** 2), m, 0, 4).removeO()
K_ser = sp.expand(sp.integrate(integrand_ser, (phi, 0, sp.pi / 2)))
ratio_m = sp.expand(2 / sp.pi * K_ser)
print("1b. (2/pi) K(m) from term-by-term integration =", ratio_m, "+ O(m^4)")
coeff_general = [sp.binomial(2 * n, n) ** 2 / sp.Integer(16) ** n for n in range(4)]
print("    check against ((2n)!/(2^{2n} n!^2))^2:", coeff_general,
      "match =", all(sp.simplify(ratio_m.coeff(m, n) - coeff_general[n]) == 0 for n in range(4)))
ser_b = sp.series(ratio_m.subs(m, sp.sin(th / 2) ** 2), th, 0, N).removeO()
print("    substituted m = sin^2(theta0/2):", ser_b)

# 1c. Independent of the period integral: Lindstedt-Poincare on theta'' + sin(theta) = 0.
#     tau = w t, theta(tau) = eps cos(tau) + eps^3 th3(tau) + ..., w^2 = 1 + eps^2 w2 + ...
#     The eps^3 equation is th3'' + th3 = R(tau); removing the secular cos(tau) term fixes w2.
tau, eps, w2 = sp.symbols("tau epsilon omega2")
th1 = sp.cos(tau)
# w^2 theta'' + theta - theta^3/6 + ... = 0  at order eps^3:
# th3'' + th3 + w2 th1'' - th1^3/6 = 0  =>  R = -(w2 th1'' - th1^3/6)
R = -(w2 * sp.diff(th1, tau, 2) - th1 ** 3 / 6)
secular = sp.integrate(sp.expand(R) * sp.cos(tau), (tau, 0, 2 * sp.pi)) / sp.pi
w2_val = sp.solve(sp.Eq(secular, 0), w2)[0]
omega = sp.sqrt(1 + eps ** 2 * w2_val)
ser_c = sp.series(2 * sp.pi / omega / (2 * sp.pi), eps, 0, 4).removeO()
print("1c. Lindstedt-Poincare: w2 =", w2_val, "; T/T0 =", ser_c, "+ O(eps^4)")
print("    (eps and theta0 differ at O(eps^3), which changes T/T0 only at O(theta0^4))")

a_sym = ser_a.coeff(th, 2)
b_sym = ser_a.coeff(th, 4)
c_sym = ser_a.coeff(th, 6)
print()
print("a (from 1a) =", a_sym, " (from 1b) =", ser_b.coeff(th, 2),
      " (from 1c) =", ser_c.coeff(eps, 2))
print("theta0^4 coefficient (1a) =", b_sym, " (1b) =", ser_b.coeff(th, 4))
print("theta0^6 coefficient (1a) =", c_sym, " (1b, needs m^3 term, included) =", ser_b.coeff(th, 6))
assert a_sym == ser_b.coeff(th, 2) == ser_c.coeff(eps, 2) == sp.Rational(1, 16)
assert b_sym == ser_b.coeff(th, 4) == sp.Rational(11, 3072)
print("LaTeX:  T = T_0\\left(" + sp.latex(sp.expand(ser_a), order="rev-lex") + " + O(\\theta_0^{8})\\right)")
print("LaTeX:  a = " + sp.latex(a_sym))
print("LaTeX:  \\frac{2}{\\pi}K(m) = " + sp.latex(ratio_m, order="rev-lex") + " + O(m^4)")

a_ex = float(a_sym)
b_ex = float(b_sym)
c_ex = float(c_sym)

# ---------------------------------------------------------------------------
# 2. Numerical paths
# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("2. Numerical: exact period via K (mpmath, SciPy) and via ODE integration")
print("=" * 78)


def ratio_mp(th0):
    """T/T0 = (2/pi) K, mpmath, parameter m = sin^2(theta0/2)."""
    th0 = mp.mpf(th0)
    return 2 / mp.pi * mp.ellipk(mp.sin(th0 / 2) ** 2)


def ratio_sc(th0):
    return 2 / np.pi * sc_ellipk(np.sin(th0 / 2) ** 2)


def period_ode(th0, rtol=1e-13, atol=1e-15):
    """Period from integrating theta'' + sin(theta) = 0 (w0 = 1), from rest at theta0.

    Rescaled u = theta/theta0 so tolerances do not depend on the amplitude:
    u'' = -sin(theta0 u)/theta0, u(0) = 1, u'(0) = 0.
    T = time between the first two downward zero crossings of u (t = T/4 and t = 5T/4).
    No elliptic-integral formula is used.
    """
    def rhs(t, y):
        return [y[1], -np.sin(th0 * y[0]) / th0]

    def cross(t, y):
        return y[0]
    cross.direction = -1

    t_end = 1.6 * 2 * np.pi * (1 + th0 ** 2)  # comfortably past 5T/4
    sol = solve_ivp(rhs, (0.0, t_end), [1.0, 0.0], method="DOP853",
                    rtol=rtol, atol=atol, events=cross, dense_output=False)
    tz = sol.t_events[0]
    assert len(tz) >= 2, (th0, tz)
    return tz[1] - tz[0], 4 * tz[0]


amps = [1e-3, 2e-3, 5e-3, 1e-2, 2e-2, 5e-2, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
ode_amps = {1e-3, 1e-2, 5e-2, 0.1, 0.2, 0.5, 1.0}
rows = []
hdr = (f"{'theta0':>8} {'T/T0 (mpmath, 40 dig)':>26} {'SciPy - mpmath':>15} "
       f"{'ODE - mpmath':>13} {'(T/T0-1)/theta0^2':>20} {'minus a':>12}")
print(hdr)
for th0 in amps:
    r_mp = ratio_mp(th0)
    r_sc = ratio_sc(th0)
    if th0 in ode_amps:
        T_full, T_quarter4 = period_ode(th0)
        r_ode = T_full / (2 * np.pi)
        d_ode = r_ode - float(r_mp)
        d_ode_s = f"{d_ode:13.2e}"
    else:
        r_ode, T_quarter4, d_ode_s = float("nan"), float("nan"), f"{'-':>13}"
    g = (r_mp - 1) / mp.mpf(th0) ** 2
    rows.append(dict(theta0=th0, ratio_mpmath=mp.nstr(r_mp, 30), ratio_scipy=repr(float(r_sc)),
                     ratio_ode=repr(float(r_ode)), g_mpmath=mp.nstr(g, 25),
                     g_scipy=repr(float((r_sc - 1) / th0 ** 2)),
                     g_ode=repr(float((r_ode - 1) / th0 ** 2))))
    print(f"{th0:8.3g} {mp.nstr(r_mp, 22):>26} {float(r_sc) - float(r_mp):15.2e} {d_ode_s} "
          f"{mp.nstr(g, 16):>20} {float(g) - a_ex:12.4e}")

with open(HERE / "C-S1-1.periods.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print("wrote C-S1-1.periods.csv")

print()
print("ODE consistency: full period vs 4 x quarter period, and tolerance sensitivity")
for th0 in sorted(ode_amps):
    Tf, Tq = period_ode(th0)
    Tf_loose, _ = period_ode(th0, rtol=1e-11, atol=1e-13)
    print(f"  theta0 = {th0:6.3g}: T_full/T0 = {Tf / (2 * np.pi):.15f}, "
          f"(T_full - 4 T_quarter)/T0 = {(Tf - Tq) / (2 * np.pi):.1e}, "
          f"tol 1e-13 vs 1e-11: {(Tf - Tf_loose) / (2 * np.pi):.1e}")

print()
print("ODE-only estimate of a: (T_ode/T0 - 1)/theta0^2")
for th0 in sorted(ode_amps):
    Tf, _ = period_ode(th0)
    g = (Tf / (2 * np.pi) - 1) / th0 ** 2
    print(f"  theta0 = {th0:6.3g}: {g:.12f}   (minus a: {g - a_ex:.3e};"
          f"  g - a - b theta0^2: {g - a_ex - b_ex * th0 ** 2:.3e})")

# ---------------------------------------------------------------------------
# 3. Extract a from the numbers
# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("3. Extract a from the numbers")
print("=" * 78)

# 3a. Limit of g(theta0) = (T/T0 - 1)/theta0^2 by Richardson extrapolation (g = a + b x + c x^2 + ...).
print("3a. Richardson extrapolation of g(theta0) = (T/T0-1)/theta0^2 in x = theta0^2 (mpmath values)")
h0 = mp.mpf("0.2")
hs = [h0 / 2 ** j for j in range(6)]
gs = [(ratio_mp(h) - 1) / h ** 2 for h in hs]
table = [gs]
for lev in range(1, 5):
    prev = table[-1]
    fac = mp.mpf(4) ** lev  # x halves by 4 each step
    table.append([(fac * prev[i + 1] - prev[i]) / (fac - 1) for i in range(len(prev) - 1)])
for lev, col in enumerate(table):
    print(f"  level {lev}: " + "  ".join(mp.nstr(v, 18) for v in col[-2:]))
a_rich = table[-1][-1]
print(f"  Richardson limit: a = {mp.nstr(a_rich, 25)},  minus 1/16 = {mp.nstr(a_rich - mp.mpf(1) / 16, 3)}")

# 3b. Least-squares polynomial fit of T/T0 - 1 in x = theta0^2 at small amplitudes (double precision).
print()
print("3b. Least-squares fit of T/T0 - 1 = a x + b x^2 + ... (x = theta0^2), no constant term")


def fit(th_arr, y_arr, deg):
    x = th_arr ** 2
    A = np.vstack([x ** p for p in range(1, deg + 1)]).T
    coef, res, rank, sv = np.linalg.lstsq(A, y_arr, rcond=None)
    resid = y_arr - A @ coef
    dof = max(len(y_arr) - deg, 1)
    s2 = resid @ resid / dof
    cov = s2 * np.linalg.inv(A.T @ A)
    return coef, np.sqrt(np.diag(cov)), np.max(np.abs(resid))


th_fit = np.linspace(0.05, 0.5, 25)
y_sc = np.array([ratio_sc(t) - 1 for t in th_fit])
y_mp = np.array([float(ratio_mp(t) - 1) for t in th_fit])
fit_results = {}
for label, y in [("SciPy K", y_sc), ("mpmath K (rounded to double)", y_mp)]:
    print(f"  data: {label}, 25 amplitudes in [0.05, 0.5] rad")
    for deg in (2, 3, 4, 5):
        coef, err, rmax = fit(th_fit, y, deg)
        fit_results[(label, deg)] = (coef, err)
        print(f"    degree {deg}: a = {coef[0]:.14f} +/- {err[0]:.1e}  (minus 1/16: {coef[0] - a_ex:+.1e}),"
              f"  b = {coef[1]:.10f} +/- {err[1]:.1e} (minus 11/3072: {coef[1] - b_ex:+.1e}),"
              f"  max resid {rmax:.1e}")

# Fit on ODE data only, so that a is extracted without any elliptic integral.
th_fit_ode = np.linspace(0.05, 0.5, 25)
y_ode = np.array([period_ode(t)[0] / (2 * np.pi) - 1 for t in th_fit_ode])
print("  data: ODE periods (no elliptic integral), 25 amplitudes in [0.05, 0.5] rad")
for deg in (2, 3, 4, 5):
    coef, err, rmax = fit(th_fit_ode, y_ode, deg)
    fit_results[("ODE", deg)] = (coef, err)
    print(f"    degree {deg}: a = {coef[0]:.12f} +/- {err[0]:.1e}  (minus 1/16: {coef[0] - a_ex:+.1e}),"
          f"  b = {coef[1]:.8f} +/- {err[1]:.1e}, max resid {rmax:.1e}")

# The data are deterministic, so the least-squares standard error underestimates the truncation bias.
# Error estimate: the larger of the standard error and the change of a from degree 4 to degree 5.
for label in ("SciPy K", "ODE"):
    a5, e5 = fit_results[(label, 5)][0][0], fit_results[(label, 5)][1][0]
    a4 = fit_results[(label, 4)][0][0]
    err = max(e5, abs(a5 - a4))
    print(f"  adopted ({label}, degree 5): a = {a5:.13f} +/- {err:.1e}  "
          f"(|a - 1/16| / error = {abs(a5 - a_ex) / err:.2f})")

# ---------------------------------------------------------------------------
# 4. Accuracy of the truncated formula T0 (1 + a theta0^2)
# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("4. Relative error of T0(1 + theta0^2/16) and of T0(1 + theta0^2/16 + 11 theta0^4/3072)")
print("=" * 78)
print(f"{'theta0':>7} {'deg':>6} {'T/T0 exact':>20} {'rel err, order 2':>17} {'-(11/3072)th^4':>15}"
      f" {'rel err, order 4':>17} {'small-angle T0':>15}")
acc_rows = []
for th0 in [0.1, 0.2, 0.5, 1.0]:
    r = ratio_mp(th0)
    t2 = 1 + mp.mpf(1) / 16 * mp.mpf(th0) ** 2
    t4 = t2 + mp.mpf(11) / 3072 * mp.mpf(th0) ** 4
    e2 = t2 / r - 1
    e4 = t4 / r - 1
    e0 = 1 / r - 1
    acc_rows.append(dict(theta0=th0, ratio_exact=mp.nstr(r, 20), relerr_order2=mp.nstr(e2, 6),
                         relerr_order4=mp.nstr(e4, 6), relerr_T0=mp.nstr(e0, 6)))
    print(f"{th0:7.2f} {float(th0) * 180 / np.pi:6.1f} {mp.nstr(r, 16):>20} {float(e2):17.3e}"
          f" {-b_ex * th0 ** 4:15.3e} {float(e4):17.3e} {float(e0):15.3e}")
with open(HERE / "C-S1-1.truncation.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(acc_rows[0].keys()))
    w.writeheader()
    w.writerows(acc_rows)
print("wrote C-S1-1.truncation.csv")
print("(relative error = T_truncated / T_exact - 1; negative means the formula underestimates T;")
print(" -(11/3072) theta0^4 is the leading-order prediction of the order-2 error; last column: T0 alone)")

# ---------------------------------------------------------------------------
# 5. Sanity checks
# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("5. Sanity checks")
print("=" * 78)
# Known closed form at theta0 = pi/2: K(1/sqrt 2) = Gamma(1/4)^2 / (4 sqrt(pi)).
r_half = ratio_mp(mp.pi / 2)
r_half_cf = 2 / mp.pi * mp.gamma(mp.mpf(1) / 4) ** 2 / (4 * mp.sqrt(mp.pi))
T_ode_half, _ = period_ode(np.pi / 2)
print(f"theta0 = pi/2: (2/pi)K = {mp.nstr(r_half, 20)}, Gamma(1/4)^2/(2 pi^(3/2)) = {mp.nstr(r_half_cf, 20)},"
      f" ODE = {T_ode_half / (2 * np.pi):.15f}")
# theta0 -> 0 limit and monotonicity.
print(f"theta0 = 1e-8: T/T0 - 1 = {mp.nstr(ratio_mp('1e-8') - 1, 6)} (expected theta0^2/16 = 6.25e-18)")
grid = [mp.mpf(i) / 100 * mp.pi for i in range(1, 100)]
vals = [ratio_mp(x) for x in grid]
print("T/T0 increasing on (0, pi):", all(vals[i + 1] > vals[i] for i in range(len(vals) - 1)))
print(f"theta0 = pi - 1e-6: T/T0 = {mp.nstr(ratio_mp(mp.pi - mp.mpf('1e-6')), 8)} (diverges logarithmically as theta0 -> pi;"
      f" (2/pi) ln(8/(pi - theta0)) = {mp.nstr(2 / mp.pi * mp.log(8 / mp.mpf('1e-6')), 8)})")
# Convention trap: passing the modulus k instead of the parameter m would give a linear term.
th_s = 0.01
wrong = 2 / np.pi * sc_ellipk(np.sin(th_s / 2)) - 1
print(f"Convention trap at theta0 = 0.01: ellipk(k) instead of ellipk(k^2) gives (T/T0-1)/theta0^2 = "
      f"{wrong / th_s ** 2:.4f} instead of {float((ratio_mp(th_s) - 1) / th_s ** 2):.6f}")
print("Dimensions: T0 = 2 pi sqrt(L/g) carries time; T/T0 is a function of the angle theta0 only,"
      " so a is a pure number (per rad^2).")
