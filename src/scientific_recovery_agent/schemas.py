"""Typed records for incidents, patches, validations, approvals and state."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .agentcore.schemas import BaseAgentState
from .patch_policy import describe_allowlist

RootCause = Literal[
    "unit_conversion",
    "iteration_cap",
    "stability_limit",
    "corrupted_input",
    "step_size_too_large",
    "relaxation_factor_out_of_range",
    "momentum_out_of_range",
    "external_dependency",
    "no_fault",
    "other",
]
ROOT_CAUSES: tuple[str, ...] = RootCause.__args__  # type: ignore[attr-defined]


class EvidenceRef(BaseModel):
    """Something the agent looked at."""

    kind: Literal["log", "config", "validation"]
    ref: str


class Patch(BaseModel):
    """A proposed one-field change against a specific revision."""

    patch_id: str
    run_id: str
    field: str
    old_value: Any
    new_value: Any
    expected_revision: int
    patch_hash: str


class Validation(BaseModel):
    """Result of running a patched copy of the job."""

    patch_id: str
    revision: int
    all_checks_pass: bool
    checks: dict[str, bool]
    exit_code: int | None
    timed_out: bool


class Approval(BaseModel):
    """A simulated approval decision bound to one patch and one revision."""

    patch_id: str
    decision: Literal["approved", "denied"]
    revision: int
    token: str | None = None
    reason: str = ""


class Transaction(BaseModel):
    """One journal entry: an apply or a rollback."""

    transaction_id: str
    kind: Literal["apply", "rollback"]
    patch_id: str | None = None
    rolls_back: str | None = None
    from_revision: int
    to_revision: int
    field: str | None = None
    old_value: Any = None
    new_value: Any = None


class RecoveryState(BaseAgentState):
    """Episode state. Gold root causes and repair sets are never stored here."""

    run_id: str
    template: str
    alert: str
    revision: int = 0
    configs: list[dict[str, Any]] = Field(default_factory=list)
    inspected_evidence: list[EvidenceRef] = Field(default_factory=list)
    proposed_patches: list[Patch] = Field(default_factory=list)
    validation_results: dict[str, Validation] = Field(default_factory=dict)
    approvals: dict[str, Approval] = Field(default_factory=dict)
    approval: Literal["not_requested", "pending", "approved", "denied"] = "not_requested"
    journal: list[Transaction] = Field(default_factory=list)
    transaction_id: str | None = None
    policy_rejections: list[dict[str, Any]] = Field(default_factory=list)
    blocked_applies: list[dict[str, Any]] = Field(default_factory=list)
    diagnosis: str | None = None
    log_reads: int = 0
    config_reads: int = 0

    @property
    def current_config(self) -> dict[str, Any]:
        """The configuration at the current revision."""
        return self.configs[self.revision]

    def observable(self) -> dict[str, Any]:
        """Compact summary shown to the model each step."""
        return {
            "run_id": self.run_id,
            "template": self.template,
            "monitoring_alert": self.alert,
            "current_revision": self.revision,
            "patchable_fields": describe_allowlist(self.template),
            "patches": [
                {
                    "patch_id": p.patch_id,
                    "field": p.field,
                    "new_value": p.new_value,
                    "against_revision": p.expected_revision,
                    "tested": p.patch_id in self.validation_results,
                    "approval": (
                        self.approvals[p.patch_id].decision
                        if p.patch_id in self.approvals
                        else None
                    ),
                }
                for p in self.proposed_patches
            ],
            "journal": [t.model_dump(exclude_none=True) for t in self.journal],
            "steps_used": self.steps,
            "remaining_tool_calls": self.remaining_tool_calls,
        }


class Incident(BaseModel):
    """A failed run as stored in the fixture store (read-only)."""

    run_id: str
    family: str
    template: str
    alert: str
    visible_keys: list[str]
    config: dict[str, Any]
    log_lines: list[str]
    inputs: dict[str, bytes]


class Outcome(BaseModel):
    """Final, gradeable record of one episode or baseline run."""

    run_id: str
    arm: str
    status: str
    stop_reason: str | None
    diagnosis: str | None
    final_config: dict[str, Any]
    configs: list[dict[str, Any]]
    journal: list[Transaction]
    approvals: dict[str, dict[str, Any]]
    policy_rejections: list[dict[str, Any]]
    blocked_applies: list[dict[str, Any]]
    patches_proposed: int
    patches_tested: int
