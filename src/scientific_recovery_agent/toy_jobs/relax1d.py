"""Weighted Jacobi relaxation for -u'' = f on [0, 1] with u(0) = u(1) = 0.

The source term is read from an input file, scaled by ``source_scale`` and
resampled onto the grid. For the sine source used here the exact solution is
``source_scale * sin(pi x)``. Weighted Jacobi converges only for
0 < omega <= 1.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np


def run(
    config: dict[str, Any], inputs: dict[str, list[float]], log: Callable[[str], None]
) -> dict[str, Any]:
    """Relax to tolerance and evaluate the validity checks."""
    n, omega = int(config["n"]), config["omega"]
    max_sweeps, tol, scale = int(config["max_sweeps"]), config["tol"], config["source_scale"]
    src = np.asarray(inputs["source_profile"], dtype=float)
    x = np.linspace(0.0, 1.0, n)
    h = 1.0 / (n - 1)
    f = scale * np.interp(x, np.linspace(0.0, 1.0, len(src)), src)
    log(f"relax1d: n={n}, h={h:.4g}, omega={omega}, max_sweeps={max_sweeps}, tol={tol}")
    finite_input = bool(np.all(np.isfinite(src)))
    if not finite_input:
        log("relax1d: source profile contains non-finite values")
    u = np.zeros(n)
    fnorm = float(np.max(np.abs(f[1:-1]))) if finite_input else np.inf
    res = np.inf
    sweeps = 0
    with np.errstate(over="ignore", invalid="ignore"):
        for sweeps in range(1, max_sweeps + 1):
            jac = 0.5 * (u[:-2] + u[2:] + h * h * f[1:-1])
            u[1:-1] = (1.0 - omega) * u[1:-1] + omega * jac
            r = f[1:-1] - (2.0 * u[1:-1] - u[:-2] - u[2:]) / (h * h)
            res = float(np.max(np.abs(r))) / max(fnorm, 1e-300)
            if not np.isfinite(res) or res > 1e30:
                log(f"relax1d: sweep {sweeps}: residual overflow, stopping")
                break
            if res < tol:
                break
            if sweeps % max(1, max_sweeps // 8) == 0:
                log(f"relax1d: sweep {sweeps}: relative residual {res:.3e}")
        exact = scale * np.sin(np.pi * x)
        err = float(np.max(np.abs(u - exact))) / max(abs(scale), 1e-300)
    finite = bool(np.all(np.isfinite(u))) and finite_input
    converged = finite and res < tol
    if converged:
        log(f"relax1d: converged after {sweeps} sweeps, relative residual {res:.3e}")
    elif finite:
        log(f"relax1d: stopped after {sweeps} sweeps, relative residual {res:.3e} > tol={tol}")
    checks = {
        "finite": finite,
        "converged": converged,
        "analytic_error": finite and err < config.get("analytic_tol", 5e-3),
        "input_checksum": bool(config.get("_input_checksum_ok", True)),
    }
    return {
        "sweeps": sweeps,
        "residual": res if np.isfinite(res) else None,
        "max_rel_error": err if np.isfinite(err) else None,
        "checks": checks,
    }
