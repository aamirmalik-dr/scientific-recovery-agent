"""Explicit (FTCS) 1D diffusion with zero Dirichlet boundaries.

The initial profile is read from an input file and resampled onto the grid.
For the sine-mode profile used here the exact solution is known, so the run
reports its error against it. The scheme is stable only for
r = D dt / dx^2 <= 0.5.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

MAX_STEPS = 200_000


def run(
    config: dict[str, Any], inputs: dict[str, list[float]], log: Callable[[str], None]
) -> dict[str, Any]:
    """Integrate to t_end and evaluate the validity checks."""
    from . import UNIT_SCALE

    d = config["diffusivity"] * UNIT_SCALE[config["diffusivity_units"]]
    length, nx, dt, t_end = config["length_m"], int(config["nx"]), config["dt"], config["t_end_s"]
    profile = np.asarray(inputs["initial_profile"], dtype=float)
    dx = length / (nx - 1)
    r = d * dt / dx**2
    steps = int(round(t_end / dt))
    log(f"diffusion1d: D={d:.4g} m2/s (from {config['diffusivity']} {config['diffusivity_units']})")
    log(f"diffusion1d: nx={nx}, dx={dx:.4g} m, dt={dt} s, steps={steps}, r=D*dt/dx^2={r:.4g}")
    if steps > MAX_STEPS:
        raise ValueError(f"{steps} steps exceeds the limit of {MAX_STEPS}")
    if r > 0.5:
        log(f"diffusion1d: WARNING stability number r={r:.4g} exceeds 0.5")
    x = np.linspace(0.0, length, nx)
    src = np.linspace(0.0, length, len(profile))
    u = np.interp(x, src, profile)
    finite_input = bool(np.all(np.isfinite(profile)))
    if not finite_input:
        log("diffusion1d: input profile contains non-finite values")
    u0_max, u0_min = float(np.nanmax(u)), float(np.nanmin(u))
    u[0] = u[-1] = 0.0
    with np.errstate(over="ignore", invalid="ignore"):
        for k in range(1, steps + 1):
            u[1:-1] = u[1:-1] + r * (u[2:] - 2.0 * u[1:-1] + u[:-2])
            if k % max(1, steps // 5) == 0:
                log(f"diffusion1d: step {k}/{steps}: max|u|={float(np.nanmax(np.abs(u))):.6g}")
        exact = np.sin(np.pi * x / length) * np.exp(-d * np.pi**2 * steps * dt / length**2)
        err = float(np.max(np.abs(u - exact)))
    finite = bool(np.all(np.isfinite(u))) and finite_input
    checks = {
        "finite": finite,
        "stable_step": r <= 0.5,
        "max_principle": finite and float(u.max()) <= u0_max + 1e-9 and float(u.min()) >= -1e-9,
        "analytic_error": finite and err < config.get("analytic_tol", 2e-3),
        "input_checksum": bool(config.get("_input_checksum_ok", True)),
    }
    log(f"diffusion1d: max abs error vs analytic = {err:.3e}")
    return {
        "r": r,
        "steps": steps,
        "max_error": err if np.isfinite(err) else None,
        "u_min0": u0_min,
        "checks": checks,
    }
