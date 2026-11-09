"""Original toy numerical jobs with explicit validity checks.

Each template exposes ``run(config, inputs, log) -> dict`` that returns the
solution summary and a ``checks`` mapping of check name to bool. A run is
valid only if every enabled check passes; finishing without an exception is
not enough.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import diffusion1d, gd2d, relax1d

Log = Callable[[str], None]


def _spin(config: dict[str, Any], inputs: dict[str, list[float]], log: Log) -> dict[str, Any]:
    """Test-only template that never finishes, used to prove the runner's time limit."""
    while True:
        pass


TEMPLATES: dict[str, Callable[[dict[str, Any], dict[str, list[float]], Log], dict[str, Any]]] = {
    "gd2d": gd2d.run,
    "diffusion1d": diffusion1d.run,
    "relax1d": relax1d.run,
    "_spin": _spin,
}

UNIT_SCALE = {
    "m": 1.0,
    "cm": 1e-2,
    "mm": 1e-3,
    "m2/s": 1.0,
    "cm2/s": 1e-4,
    "mm2/s": 1e-6,
}


class DependencyError(RuntimeError):
    """A required external backend is not available (cannot be patched)."""


def check_backend(config: dict[str, Any]) -> None:
    """Fail like a missing shared library when an unavailable backend is configured."""
    backend = config.get("backend", "numpy")
    if backend != "numpy":
        raise DependencyError(f"backend {backend!r} unavailable: lib{backend}.so.3 not found")


def physical_invariants(config: dict[str, Any]) -> dict[str, float]:
    """Physical quantities, in SI, that a valid repair must not change."""
    t = config["template"]
    if t == "gd2d":
        s = UNIT_SCALE[config["x0_units"]]
        return {"x0_si_0": config["x0"][0] * s, "x0_si_1": config["x0"][1] * s}
    if t == "diffusion1d":
        return {
            "diffusivity_si": config["diffusivity"] * UNIT_SCALE[config["diffusivity_units"]],
            "length_m": config["length_m"],
            "t_end_s": config["t_end_s"],
        }
    if t == "relax1d":
        return {"source_scale": config["source_scale"]}
    return {}
