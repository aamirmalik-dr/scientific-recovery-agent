"""The finite patch allowlist: which config fields may change, and to what.

A patch sets one field to one value. Only numeric values inside a range or a
member of a fixed enumeration are accepted, never paths, commands or free
strings. Tolerances, validity checks, physical constants of the problem and
the backend are never patchable: a repair must fix the run, not the test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FieldRule:
    """Allowed values for one patchable field."""

    kind: str  # "float", "int" or "enum"
    low: float | None = None
    high: float | None = None
    choices: tuple[str, ...] = ()
    low_inclusive: bool = True

    def describe(self) -> str:
        """Human-readable rule, shown to the agent."""
        if self.kind == "enum":
            return "one of " + ", ".join(self.choices)
        bracket = "[" if self.low_inclusive else "("
        return f"{self.kind} in {bracket}{self.low}, {self.high}]"


ALLOWLIST: dict[str, dict[str, FieldRule]] = {
    "gd2d": {
        "learning_rate": FieldRule("float", 0.0, 0.1, low_inclusive=False),
        "momentum": FieldRule("float", 0.0, 0.95),
        "max_iter": FieldRule("int", 10, 50_000),
        "x0_units": FieldRule("enum", choices=("m", "cm", "mm")),
    },
    "diffusion1d": {
        "dt": FieldRule("float", 0.0, 100.0, low_inclusive=False),
        "nx": FieldRule("int", 11, 401),
        "diffusivity_units": FieldRule("enum", choices=("m2/s", "cm2/s", "mm2/s")),
        "initial_profile_source": FieldRule("enum", choices=("primary", "backup")),
    },
    "relax1d": {
        "omega": FieldRule("float", 0.0, 1.0, low_inclusive=False),
        "max_sweeps": FieldRule("int", 10, 100_000),
        "n": FieldRule("int", 11, 201),
        "source_profile_source": FieldRule("enum", choices=("primary", "backup")),
    },
}

PROTECTED_WORDS = ("tol", "check", "threshold", "valid", "backend", "template", "revision")
"""Fields containing these words are refused with a specific reason."""


class PatchRejected(ValueError):
    """The patch is outside the allowlist. ``reason`` is a short code."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


def check_patch(template: str, field: str, value: Any) -> Any:
    """Validate one proposed field change and return the normalised value.

    Raises:
        PatchRejected: For a protected field, a field outside the allowlist,
            a value of the wrong type or a value out of range.
    """
    rules = ALLOWLIST.get(template, {})
    if field not in rules:
        if any(w in field.lower() for w in PROTECTED_WORDS):
            raise PatchRejected(
                "weakens_validation",
                f"{field!r} is a tolerance, validity check or job identity field and is never "
                "patchable",
            )
        raise PatchRejected("field_not_allowlisted", f"{field!r} is not a patchable field")
    rule = rules[field]
    if rule.kind == "enum":
        if not isinstance(value, str) or value not in rule.choices:
            raise PatchRejected("value_not_allowed", f"{field} must be {rule.describe()}")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PatchRejected("wrong_type", f"{field} must be a number")
    if rule.kind == "int":
        if float(value) != int(value):
            raise PatchRejected("wrong_type", f"{field} must be an integer")
        value = int(value)
    value_f = float(value)
    assert rule.low is not None and rule.high is not None
    too_low = value_f < rule.low or (value_f == rule.low and not rule.low_inclusive)
    if too_low or value_f > rule.high:
        raise PatchRejected("out_of_range", f"{field} must be {rule.describe()}")
    return value if rule.kind == "int" else value_f


def describe_allowlist(template: str) -> dict[str, str]:
    """The allowlist for one template, as shown to the agent."""
    return {name: rule.describe() for name, rule in ALLOWLIST.get(template, {}).items()}
