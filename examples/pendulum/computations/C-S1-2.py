"""C-S1-2: independent check of the second-order period correction of the simple pendulum.

Target: T(theta0) = T0 (1 + c2 theta0^2 + c4 theta0^4 + ...), T0 = 2 pi sqrt(L/g); is c2 = 1/16?

Conventions (conventions.md): EOM  theta'' + omega0^2 sin(theta) = 0, omega0 = sqrt(g/L),
theta0 = maximum angle; K(k) written with the MODULUS k.
Library conventions used below:
  - sympy.elliptic_k(m)      : PARAMETER m = k^2
  - scipy.special.ellipk(m)  : PARAMETER m = k^2
  - mpmath.ellipk(m)         : PARAMETER m = k^2
  - the AGM route below       : takes k' = sqrt(1 - k^2), K(k) = pi / (2 AGM(1, k'))
All periods are reported as the dimensionless ratio T/T0 (equivalently omega0 = 1, T0 = 2 pi).

Run from the workspace root:
  uv run --with sympy --with numpy --with scipy python computations/C-S1-2.py
"""

from pathlib import Path
import csv

import numpy as np
import sympy as sp
import mpmath as mp
from scipy.special import ellipk
from scipy.integrate import solve_ivp

HERE = Path(__file__).resolve().parent
OUT_CSV = HERE / "C-S1-2.periods.csv"

mp.mp.dps = 40
rng = np.random.default_rng(12345)

print("=" * 78)
print("C-S1-2  simple pendulum: second-order amplitude correction to the period")
print("=" * 78)

# ---------------------------------------------------------------------------
# SYMBOLIC PATH
# ---------------------------------------------------------------------------
print("\n## SYMBOLIC PATH\n")

th, th0, phi, k, w0, t = sp.symbols("theta theta_0 phi k omega_0 t", positive=True)
m = sp.symbols("m", positive=True)

# S1. Energy integral from the EOM.
# Multiply theta'' + w0^2 sin(theta) = 0 by theta' and integrate:
#   theta'^2/2 - w0^2 cos(theta) = const = -w0^2 cos(theta0)  (theta' = 0 at theta = theta0)
thetadot_sq = 2 * w0**2 * (sp.cos(th) - sp.cos(th0))
# Check: d/dt of the energy vanishes on the EOM.
thf = sp.Function("theta")(t)
E = sp.Rational(1, 2) * thf.diff(t) ** 2 - w0**2 * sp.cos(thf)
dE = sp.diff(E, t).subs(thf.diff(t, 2), -w0**2 * sp.sin(thf))
print("S1  dE/dt on the equation of motion simplifies to:", sp.simplify(dE))
print("    theta'^2 =", sp.latex(thetadot_sq))
# By symmetry of the motion, T = 4 * int_0^theta0 dtheta / sqrt(theta'^2).

# S2. Substitution sin(theta/2) = k sin(phi), k = sin(theta0/2), maps the quarter-period
# integral onto int_0^{pi/2} dphi / sqrt(1 - k^2 sin^2 phi) / w0.
theta_of_phi = 2 * sp.asin(k * sp.sin(phi))
cos_th0 = 1 - 2 * k**2  # cos(theta0) with k = sin(theta0/2)
integrand_theta = 1 / sp.sqrt(2 * w0**2 * (sp.cos(theta_of_phi) - cos_th0))
jac = sp.diff(theta_of_phi, phi)
integrand_phi = integrand_theta * jac
target_phi = 1 / (w0 * sp.sqrt(1 - k**2 * sp.sin(phi) ** 2))
ratio = sp.simplify(sp.trigsimp(integrand_phi / target_phi))
print("S2  [dtheta/dphi / sqrt(theta'^2)] / [1/(w0 sqrt(1-k^2 sin^2 phi))] simplifies to:", ratio)
# Numerical spot check of the same identity, in case simplify is fragile.
f_chk = sp.lambdify((k, phi, w0), integrand_phi / target_phi, "mpmath")
spot = [f_chk(mp.mpf(kk), mp.mpf(pp), mp.mpf(ww))
        for kk, pp, ww in zip(rng.uniform(0.05, 0.99, 6), rng.uniform(0.01, 1.55, 6), rng.uniform(0.3, 3, 6))]
print("    spot values of that ratio at 6 random (k, phi, w0):", [mp.nstr(s, 18) for s in spot])
print("    => T = (4/omega_0) K(k), k = sin(theta_0/2);  T/T0 = (2/pi) K(sin(theta_0/2))")

# S3. Series of K in the parameter m = k^2, by term-by-term integration of the integrand.
NMAX = 5  # keep m^0..m^4  -> theta0^8 accuracy
s = sp.symbols("s")
binom_series = sp.series((1 - m * s) ** sp.Rational(-1, 2), m, 0, NMAX).removeO()
K_series_m = 0
for n in range(NMAX):
    coeff = binom_series.coeff(m, n)  # polynomial in s = sin^2 phi
    term = sp.integrate(coeff.subs(s, sp.sin(phi) ** 2), (phi, 0, sp.pi / 2))
    K_series_m += sp.simplify(term) * m**n
K_series_m = sp.expand(K_series_m)
print("\nS3  K as a series in the parameter m = k^2 (term-by-term integration):")
print("    K =", sp.latex(K_series_m), "+ O(m^5)")
# Cross-check against SymPy's own elliptic_k (which takes the parameter m).
K_sympy = sp.series(sp.elliptic_k(m), m, 0, NMAX).removeO()
print("    difference with sympy.elliptic_k(m).series (parameter m):", sp.simplify(K_series_m - K_sympy))
# Closed-form coefficients: pi/2 * [binom(2n,n)/4^n]^2
closed = sum(sp.pi / 2 * (sp.binomial(2 * n, n) / 4**n) ** 2 * m**n for n in range(NMAX))
print("    difference with pi/2 * sum [binom(2n,n)/4^n]^2 m^n:", sp.simplify(K_series_m - closed))

# S4. T/T0 = (2/pi) K(m = sin^2(theta0/2)), expanded in theta0.
ORDER = 10  # through theta0^8
TT0_expr = (2 / sp.pi) * K_series_m.subs(m, sp.sin(th0 / 2) ** 2)
TT0_series = sp.series(TT0_expr, th0, 0, ORDER).removeO()
TT0_series = sp.expand(TT0_series)
c = {j: sp.nsimplify(TT0_series.coeff(th0, j)) for j in range(0, ORDER, 1)}
print("\nS4  T/T0 =", sp.latex(TT0_series), "+ O(theta_0^10)")
for j in (1, 3, 5, 7):
    assert c[j] == 0, f"odd coefficient c{j} nonzero"
c2_sym, c4_sym, c6_sym, c8_sym = c[2], c[4], c[6], c[8]
print(f"    c0 = {c[0]},  c2 = {c2_sym},  c4 = {c4_sym},  c6 = {c6_sym},  c8 = {c8_sym}")
print("    LaTeX: c_2 =", sp.latex(c2_sym), ", c_4 =", sp.latex(c4_sym),
      ", c_6 =", sp.latex(c6_sym), ", c_8 =", sp.latex(c8_sym))
# Check that truncating the m-series at m^4 does not affect theta0^8: m^5 ~ theta0^10.
TT0_direct = sp.series((2 / sp.pi) * sp.elliptic_k(sp.sin(th0 / 2) ** 2), th0, 0, 8).removeO()
print("    cross-check, series of (2/pi) elliptic_k(sin^2(theta0/2)) directly to theta0^6:",
      sp.latex(sp.expand(TT0_direct)))

# S5. Independent symbolic route that never uses an elliptic integral:
# Lindstedt-Poincare on the EOM with omega0 = 1, tau = omega t, initial data theta(0) = eps,
# theta'(0) = 0, so the maximum angle is exactly eps = theta0.
#   Omega theta_tau'' + sin(theta) = 0,  Omega = omega^2 = 1 + a2 eps^2 + a4 eps^4 + a6 eps^6
#   theta = eps cos tau + eps^3 y3 + eps^5 y5 + eps^7 y7
# Each y_j is a trig polynomial in cos(n tau); we represent it as a Laurent polynomial in
# z = exp(i tau) (cos n tau = (z^n + z^-n)/2, d^2/dtau^2 -> multiply z^n by -n^2).
print("\nS5  Lindstedt-Poincare from the equation of motion (no elliptic integral):")
z, eps = sp.symbols("z epsilon")
a2, a4, a6 = sp.symbols("a2 a4 a6")


def d2(expr):
    """Second tau-derivative of a Laurent polynomial in z = exp(i tau)."""
    expr = sp.expand(expr)
    return sp.expand(sum(-(n**2) * expr.coeff(z, n) * z**n for n in range(-15, 16)))


def solve_forced(f):
    """Solve y'' + y = -f for y even in tau with y(0) = 0; f must have no z^{+-1} term."""
    f = sp.expand(f)
    y = 0
    for n in range(-15, 16):
        cn = f.coeff(z, n)
        if cn == 0:
            continue
        assert abs(n) != 1, "secular term left in forcing"
        y += -cn / (1 - n**2) * z**n
    # add C cos tau so that y(tau=0) = y(z=1) = 0
    C = -y.subs(z, 1)
    return sp.expand(y + C * (z + 1 / z) / 2)


cos_tau = (z + 1 / z) / 2
Omega = 1 + a2 * eps**2 + a4 * eps**4 + a6 * eps**6
ys = {1: cos_tau}
sol_a = {}
for order in (3, 5, 7):
    theta_trunc = sum(eps**j * ys[j] for j in ys)
    y_new = sp.Symbol("Y")
    # residual of the EOM at this order, with the unknown y_order entering as y'' + y
    sin_series = sum((-1) ** q * theta_trunc ** (2 * q + 1) / sp.factorial(2 * q + 1) for q in range(4))
    res = sp.expand(Omega.subs(sol_a) * d2(theta_trunc) + sin_series)
    f = sp.expand(res.coeff(eps, order))
    # the y_order contribution at eps^order is (y'' + y), so y'' + y = -f
    a_unknown = {3: a2, 5: a4, 7: a6}[order]
    secular = sp.expand(f.coeff(z, 1))
    a_val = sp.solve(secular, a_unknown)[0]
    sol_a[a_unknown] = a_val
    f = sp.expand(f.subs(a_unknown, a_val))
    assert sp.simplify(f.coeff(z, 1)) == 0 and sp.simplify(f.coeff(z, -1)) == 0
    ys[order] = solve_forced(f)
    print(f"    order eps^{order}: secular condition gives {a_unknown} = {a_val}")
Omega_sol = Omega.subs(sol_a)
TT0_LP = sp.expand(sp.series(Omega_sol ** sp.Rational(-1, 2), eps, 0, 8).removeO())
print("    T/T0 = Omega^(-1/2) =", sp.latex(TT0_LP.subs(eps, th0)), "+ O(theta_0^8)")
print("    difference with the elliptic-integral series (through theta0^6):",
      sp.simplify(TT0_LP.subs(eps, th0) - sum(c[j] * th0**j for j in range(0, 7))))
c2_LP = TT0_LP.coeff(eps, 2)
c4_LP = TT0_LP.coeff(eps, 4)
print(f"    Lindstedt-Poincare: c2 = {c2_LP}, c4 = {c4_LP}")

# ---------------------------------------------------------------------------
# NUMERICAL PATH
# ---------------------------------------------------------------------------
print("\n## NUMERICAL PATH\n")
c2n, c4n = float(c2_sym), float(c4_sym)
amps = np.array([0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0])


def tt0_scipy(a):
    # scipy.special.ellipk takes the PARAMETER m = k^2
    return 2 / np.pi * ellipk(np.sin(a / 2) ** 2)


def tt0_mpmath(a):
    # mpmath.ellipk takes the PARAMETER m = k^2; 40 significant digits
    a = mp.mpf(a)
    return 2 / mp.pi * mp.ellipk(mp.sin(a / 2) ** 2)


def tt0_agm(a):
    # Pure NumPy arithmetic-geometric mean; K(k) = pi / (2 AGM(1, k')), k' = sqrt(1-k^2) = cos(a/2)
    x, y = 1.0, np.cos(a / 2)
    for _ in range(60):
        x, y = (x + y) / 2, np.sqrt(x * y)
    return 2 / np.pi * (np.pi / (2 * x))


def tt0_ode(a):
    """Direct integration of theta'' + sin(theta) = 0 (omega0 = 1), no elliptic function.

    Rescaled u = theta/theta0: u'' = -sin(theta0 u)/theta0, u(0) = 1, u'(0) = 0, so the tolerances
    are uniform in the amplitude. The first zero crossing of u (downwards) is a quarter period.
    """
    def rhs(_t, y):
        return [y[1], -np.sin(a * y[0]) / a]

    def hit_zero(_t, y):
        return y[0]
    hit_zero.terminal = True
    hit_zero.direction = -1
    sol = solve_ivp(rhs, (0.0, 50.0), [1.0, 0.0], method="DOP853",
                    rtol=1e-13, atol=1e-15, events=hit_zero, dense_output=False)
    tq = sol.t_events[0][0]
    # Also check the half period by symmetry: integrate on and locate u' = 0 (u = -1 turning point)

    def hit_turn(_t, y):
        return y[1]
    hit_turn.terminal = True
    hit_turn.direction = 1
    sol2 = solve_ivp(rhs, (0.0, 100.0), [1.0, 0.0], method="DOP853",
                     rtol=1e-13, atol=1e-15, events=hit_turn, first_step=1e-3)
    th_ = sol2.t_events[0]
    th_ = th_[th_ > 1e-6][0]
    T_q, T_h = 4 * tq, 2 * th_
    return T_q / (2 * np.pi), T_h / (2 * np.pi), sol2.y_events[0][-1][0]


rows = []
hdr = (f"{'theta0':>7} {'T/T0 mpmath':>22} {'scipy-mp':>10} {'AGM-mp':>10} {'ODE(1/4)-mp':>12} "
       f"{'ODE(1/2)-mp':>12} {'2nd-order relerr':>17} {'resid/th^4':>12}")
print("N1  T/T0 at each amplitude: mpmath (40 digits) as reference; differences of the other routes")
print("    relative error of the second-order formula = [T0(1 + theta0^2/16) - T]/T")
print(hdr)
for a in amps:
    ref = tt0_mpmath(a)
    ref_f = float(ref)
    sc = float(tt0_scipy(a))
    ag = float(tt0_agm(a))
    ode_q, ode_h, u_turn = tt0_ode(a)
    second = 1 + c2n * a**2
    relerr = (second - ref_f) / ref_f
    resid = ref - 1 - mp.mpf(c2n) * mp.mpf(a) ** 2  # high-precision residual
    resid_f = float(resid)
    rows.append(dict(theta0_rad=a, T_over_T0_mpmath=mp.nstr(ref, 20), T_over_T0_scipy=sc,
                     T_over_T0_agm=ag, T_over_T0_ode_quarter=ode_q, T_over_T0_ode_half=ode_h,
                     T_over_T0_second_order=second, relerr_second_order=relerr,
                     residual=resid_f, residual_over_theta0_4=resid_f / a**4,
                     ode_minus_mpmath=ode_q - ref_f))
    print(f"{a:7.3f} {mp.nstr(ref, 18):>22} {sc - ref_f:10.1e} {ag - ref_f:10.1e} {ode_q - ref_f:12.1e} "
          f"{ode_h - ref_f:12.1e} {relerr:17.6e} {resid_f / a**4:12.8f}")

with open(OUT_CSV, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    for r in rows:
        w.writerow(r)
print(f"\n    table written to {OUT_CSV.relative_to(HERE.parent)}")

# N2. Scaling of the residual T/T0 - 1 - theta0^2/16 at small amplitude
small = amps[amps <= 0.3]
res_small = np.array([r["residual"] for r in rows if r["theta0_rad"] <= 0.3])
slope, icpt = np.polyfit(np.log(small), np.log(res_small), 1)
print(f"\nN2  log-log slope of the residual vs theta0 on [{small[0]}, {small[-1]}]: {slope:.6f} (expect 4)")
print(f"    residual/theta0^4 -> {res_small[0] / small[0]**4:.10f} at theta0 = {small[0]}; "
      f"c4 = 11/3072 = {c4n:.10f}")
# same with the ODE data alone (no elliptic function)
ode_small = np.array([r["T_over_T0_ode_quarter"] for r in rows if r["theta0_rad"] <= 0.3])
res_ode = ode_small - 1 - small**2 / 16
okm = res_ode > 0
slope_ode = np.polyfit(np.log(small[okm]), np.log(res_ode[okm]), 1)[0]
print(f"    same slope from the ODE data alone: {slope_ode:.6f}")

# N3. c2 from the numerical data alone
print("\nN3  c2 extracted from numerical data alone")
print(f"    {'theta0':>7} {'(T/T0-1)/th^2 [mpmath]':>24} {'(T/T0-1)/th^2 [ODE]':>22}")
for r in rows:
    if r["theta0_rad"] <= 0.3:
        a = r["theta0_rad"]
        q_mp = (float(mp.mpf(r["T_over_T0_mpmath"]) - 1)) / a**2
        q_ode = (r["T_over_T0_ode_quarter"] - 1) / a**2
        print(f"    {a:7.3f} {q_mp:24.12f} {q_ode:22.12f}")
# Least-squares fit (T/T0 - 1)/theta0^2 = c2 + c4 th^2 + c6 th^4 on theta0 in [0.05, 0.5], ODE data only
sel = (amps >= 0.05) & (amps <= 0.5)
x = amps[sel] ** 2
yode = (np.array([r["T_over_T0_ode_quarter"] for r in rows])[sel] - 1) / x
A = np.vstack([np.ones_like(x), x, x**2]).T
coef_ode, *_ = np.linalg.lstsq(A, yode, rcond=None)
ymp = (np.array([float(mp.mpf(r["T_over_T0_mpmath"])) for r in rows])[sel] - 1) / x
coef_mp, *_ = np.linalg.lstsq(A, ymp, rcond=None)
print(f"    fit c2 + c4 th^2 + c6 th^4 on theta0 in [0.05, 0.5] ({sel.sum()} points):")
print(f"      ODE data   : c2 = {coef_ode[0]:.12f}, c4 = {coef_ode[1]:.8f}, c6 = {coef_ode[2]:.6f}")
print(f"      mpmath data: c2 = {coef_mp[0]:.12f}, c4 = {coef_mp[1]:.8f}, c6 = {coef_mp[2]:.6f}")
print(f"      exact      : c2 = {c2n:.12f}, c4 = {c4n:.8f}, c6 = {float(c6_sym):.6f}")
# Richardson on two smallest-but-not-too-small ODE points (removes the c4 term)
a1, a2_ = 0.05, 0.1
q1 = (rows[list(amps).index(a1)]["T_over_T0_ode_quarter"] - 1) / a1**2
q2 = (rows[list(amps).index(a2_)]["T_over_T0_ode_quarter"] - 1) / a2_**2
c2_rich = (q1 * a2_**2 - q2 * a1**2) / (a2_**2 - a1**2)
print(f"    Richardson from ODE at theta0 = {a1}, {a2_}: c2 = {c2_rich:.12f} (|err| = {abs(c2_rich - c2n):.1e})")

# N4. Truncated series vs exact (checks the symbolic coefficients numerically)
print("\nN4  truncated symbolic series vs mpmath exact, relative error")
ser_f = sp.lambdify(th0, TT0_series, "mpmath")
for a in (0.1, 0.5, 1.0, 2.0):
    ex = tt0_mpmath(a)
    s2 = 1 + mp.mpf(1) / 16 * mp.mpf(a) ** 2
    s4 = s2 + mp.mpf(11) / 3072 * mp.mpf(a) ** 4
    s8 = ser_f(mp.mpf(a))
    print(f"    theta0 = {a:4.1f}: order 2 {float((s2 - ex) / ex):10.3e}   order 4 {float((s4 - ex) / ex):10.3e}"
          f"   order 8 {float((s8 - ex) / ex):10.3e}")

# Limits
print("\nLimits")
print(f"    theta0 -> 0: T/T0 (mpmath, theta0 = 1e-8) - 1 = {mp.nstr(tt0_mpmath(1e-8) - 1, 6)}"
      f"  (expect theta0^2/16 = {1e-16 / 16:.3e})")
for a in (3.1, 3.14, 3.1415):
    ex = tt0_mpmath(a)
    # near the separatrix K(k) ~ ln(4/k'), k' = cos(theta0/2)
    approx = 2 / mp.pi * mp.log(4 / mp.cos(mp.mpf(a) / 2))
    print(f"    theta0 = {a}: T/T0 = {mp.nstr(ex, 10)}, (2/pi) ln(4/cos(theta0/2)) = {mp.nstr(approx, 10)}")

print("\nSUMMARY")
print(f"    symbolic (elliptic series):   c2 = {c2_sym}, c4 = {c4_sym}, c6 = {c6_sym}, c8 = {c8_sym}")
print(f"    symbolic (Lindstedt-Poincare): c2 = {c2_LP}, c4 = {c4_LP}")
print(f"    numerical (ODE fit)          : c2 = {coef_ode[0]:.12f}, c4 = {coef_ode[1]:.8f}")
print(f"    max |ODE - mpmath| over all amplitudes: {max(abs(r['ode_minus_mpmath']) for r in rows):.2e}")
print(f"    max |scipy - mpmath|: {max(abs(r['T_over_T0_scipy'] - float(mp.mpf(r['T_over_T0_mpmath']))) for r in rows):.2e}")
