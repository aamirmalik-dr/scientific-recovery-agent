"""Heavy-ball gradient descent on a scaled Rosenbrock function.

f(x, y) = (1 - x)^2 + 10 (y - x^2)^2, minimum 0 at (1, 1). The starting
point is given in length units and converted to metres before the run.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

B = 10.0


def f(x: float, y: float) -> float:
    """Objective value."""
    return (1.0 - x) ** 2 + B * (y - x * x) ** 2


def grad(x: float, y: float) -> tuple[float, float]:
    """Analytic gradient."""
    return (-2.0 * (1.0 - x) - 4.0 * B * x * (y - x * x), 2.0 * B * (y - x * x))


def run(
    config: dict[str, Any], inputs: dict[str, list[float]], log: Callable[[str], None]
) -> dict[str, Any]:
    """Run the optimiser and evaluate its validity checks."""
    from . import UNIT_SCALE

    scale = UNIT_SCALE[config["x0_units"]]
    x, y = config["x0"][0] * scale, config["x0"][1] * scale
    lr, mom = config["learning_rate"], config["momentum"]
    max_iter, tol = int(config["max_iter"]), config["tol"]
    log(f"gd2d: start=({x:.6g}, {y:.6g}) m, learning_rate={lr}, momentum={mom}")
    log(f"gd2d: max_iter={max_iter}, tol={tol}")
    vx = vy = 0.0
    gnorm = math.inf
    finite = True
    it = 0
    for it in range(1, max_iter + 1):
        gx, gy = grad(x, y)
        gnorm = math.hypot(gx, gy)
        if not math.isfinite(gnorm) or gnorm > 1e12:
            finite = False
            log(f"gd2d: iteration {it}: gradient norm not finite (overflow), stopping")
            break
        if gnorm < tol:
            break
        vx, vy = mom * vx - lr * gx, mom * vy - lr * gy
        x, y = x + vx, y + vy
        if it % max(1, max_iter // 10) == 0:
            log(f"gd2d: iteration {it}: f={f(x, y):.6e} |grad|={gnorm:.3e}")
    converged = finite and gnorm < tol
    value = f(x, y) if finite else math.inf
    if converged:
        log(f"gd2d: converged after {it} iterations, |grad|={gnorm:.3e}")
    elif finite:
        log(f"gd2d: did not converge after {max_iter} iterations, |grad|={gnorm:.3e} > tol={tol}")
    checks = {
        "finite": finite and math.isfinite(value),
        "converged": converged,
        "residual": finite and value < 1e-8,
        "in_domain": finite and abs(x) < 10 and abs(y) < 10,
    }
    return {
        "iterations": it,
        "solution": [x, y] if finite else None,
        "objective": value if math.isfinite(value) else None,
        "grad_norm": gnorm if math.isfinite(gnorm) else None,
        "checks": checks,
    }
