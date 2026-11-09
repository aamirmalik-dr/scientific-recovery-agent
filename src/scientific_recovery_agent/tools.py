"""The ten bounded tools. Every one is a finite, typed operation.

No tool runs model-written code, touches the network or writes outside a
temporary job copy. The gold root causes and repair sets are not reachable
from here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .agentcore.policy import ToolFailure, ToolSpec
from .fixture_store import FixtureStore
from .patch_policy import PatchRejected, check_patch, describe_allowlist
from .runner import run_config
from .schemas import (
    ROOT_CAUSES,
    Approval,
    EvidenceRef,
    Patch,
    RecoveryState,
    RootCause,
    Validation,
)
from .toy_jobs import UNIT_SCALE
from .toy_jobs.diffusion1d import MAX_STEPS
from .transactions import TransactionError, apply, approval_token, patch_hash, patched, rollback

ALL_TOOLS = (
    "inspect_log",
    "read_config",
    "validate_config",
    "propose_patch",
    "test_patch",
    "request_approval",
    "apply_patch",
    "rollback",
    "finish",
    "abstain",
)
MAX_LOG_WINDOW = 200


@dataclass(frozen=True)
class ToolLimits:
    """Per-arm limits on inspection (the ablation sets both to 1)."""

    max_log_reads: int | None = None
    max_config_reads: int | None = None
    job_timeout_s: float = 30.0


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InspectLogArgs(_Args):
    run_id: str
    start_line: int = Field(ge=1, description="1-based, inclusive")
    end_line: int = Field(ge=1, description=f"inclusive, at most start_line + {MAX_LOG_WINDOW}")


class ReadConfigArgs(_Args):
    run_id: str
    keys: list[str] = Field(min_length=1, max_length=20)


class RunArgs(_Args):
    run_id: str


class ProposePatchArgs(_Args):
    run_id: str
    field: str = Field(min_length=1, max_length=60)
    new_value: float | int | str = Field(description="number or enumerated string, never a path")
    expected_revision: int = Field(ge=0)


class PatchArgs(_Args):
    patch_id: str


class ApplyArgs(_Args):
    patch_id: str
    approval_token: str = Field(min_length=1, max_length=40)


class RollbackArgs(_Args):
    transaction_id: str


class FinishArgs(_Args):
    diagnosis: RootCause
    summary: str = Field(min_length=1, max_length=500)


class AbstainArgs(_Args):
    reason: str = Field(min_length=1, max_length=400)
    diagnosis: RootCause = "other"


def diagnostics(config: dict[str, Any], inputs: dict[str, bytes]) -> dict[str, Any]:
    """Schema errors and diagnostics computable without running the job."""
    errors: list[str] = []
    out: dict[str, Any] = {}
    t = config.get("template")
    for field, rule in describe_allowlist(t).items():
        if field in config:
            try:
                check_patch(t, field, config[field])
            except PatchRejected:
                errors.append(f"{field}={config[field]!r} is outside {rule}")
    backend = config.get("backend", "numpy")
    out["backend"] = backend
    out["backend_available"] = backend == "numpy"
    source_field = {"diffusion1d": "initial_profile_source", "relax1d": "source_profile_source"}
    if t in source_field:
        name = f"{config[source_field[t]]}.csv"
        sums = json.loads(inputs["checksums.json"])
        ok = hashlib.sha256(inputs.get(name, b"")).hexdigest() == sums.get(name)
        out["selected_input"] = name
        out["input_checksum_ok"] = ok
        if not ok:
            errors.append(f"checksum mismatch for input {name}")
    if t == "diffusion1d":
        d = config["diffusivity"] * UNIT_SCALE[config["diffusivity_units"]]
        dx = config["length_m"] / (config["nx"] - 1)
        out["diffusivity_si"] = d
        out["stability_number_r"] = round(d * config["dt"] / dx**2, 6)
        out["steps"] = round(config["t_end_s"] / config["dt"])
        out["solver_step_limit"] = MAX_STEPS
        if out["steps"] > MAX_STEPS:
            errors.append(f"{out['steps']} steps exceed the solver limit of {MAX_STEPS}")
        if out["stability_number_r"] > 0.5:
            errors.append(f"stability number r={out['stability_number_r']} exceeds 0.5")
    if t == "gd2d":
        s = UNIT_SCALE[config["x0_units"]]
        out["x0_si"] = [config["x0"][0] * s, config["x0"][1] * s]
    out["schema_errors"] = errors
    return out


def build_tools(store: FixtureStore, limits: ToolLimits | None = None) -> list[ToolSpec]:
    """Tool specs bound to one fixture store."""
    limits = limits or ToolLimits()

    def incident(state: RecoveryState, run_id: str):
        if run_id != state.run_id:
            raise ToolFailure("not_found", f"this episode handles run {state.run_id} only")
        inc = store.get(run_id)
        if inc is None:
            raise ToolFailure("not_found", f"unknown run {run_id}")
        return inc

    def find_patch(state: RecoveryState, patch_id: str) -> Patch:
        p = next((x for x in state.proposed_patches if x.patch_id == patch_id), None)
        if p is None:
            raise ToolFailure("not_found", f"unknown patch {patch_id}")
        return p

    def inspect_log(state: RecoveryState, a: InspectLogArgs) -> dict[str, Any]:
        inc = incident(state, a.run_id)
        if limits.max_log_reads is not None and state.log_reads >= limits.max_log_reads:
            raise ToolFailure("budget_exhausted", "log inspection budget used up")
        if a.end_line < a.start_line or a.end_line - a.start_line > MAX_LOG_WINDOW:
            raise ToolFailure("out_of_range", f"window must be 1 to {MAX_LOG_WINDOW + 1} lines")
        n = len(inc.log_lines)
        if a.start_line > n:
            raise ToolFailure("out_of_range", f"the log has {n} lines")
        state.log_reads += 1
        end = min(a.end_line, n)
        state.inspected_evidence.append(EvidenceRef(kind="log", ref=f"{a.start_line}-{end}"))
        lines = [f"{i}: {inc.log_lines[i - 1]}" for i in range(a.start_line, end + 1)]
        return {"run_id": a.run_id, "total_lines": n, "lines": lines}

    def read_config(state: RecoveryState, a: ReadConfigArgs) -> dict[str, Any]:
        inc = incident(state, a.run_id)
        if limits.max_config_reads is not None and state.config_reads >= limits.max_config_reads:
            raise ToolFailure("budget_exhausted", "config read budget used up")
        unknown = [k for k in a.keys if k not in inc.visible_keys]
        if unknown:
            raise ToolFailure(
                "not_found", f"unknown or hidden keys {unknown}; readable: {inc.visible_keys}"
            )
        state.config_reads += 1
        state.inspected_evidence.append(EvidenceRef(kind="config", ref=",".join(a.keys)))
        cfg = state.current_config
        return {"revision": state.revision, "values": {k: cfg.get(k) for k in a.keys}}

    def validate_config(state: RecoveryState, a: RunArgs) -> dict[str, Any]:
        inc = incident(state, a.run_id)
        state.inspected_evidence.append(EvidenceRef(kind="validation", ref=f"r{state.revision}"))
        return {"revision": state.revision, **diagnostics(state.current_config, inc.inputs)}

    def propose_patch(state: RecoveryState, a: ProposePatchArgs) -> dict[str, Any]:
        incident(state, a.run_id)
        if a.expected_revision != state.revision:
            raise ToolFailure(
                "precondition_failed",
                f"stale revision: expected {a.expected_revision}, current is {state.revision}",
            )
        try:
            value = check_patch(state.template, a.field, a.new_value)
        except PatchRejected as exc:
            state.policy_rejections.append(
                {"step": state.steps, "field": a.field, "value": a.new_value, "reason": exc.reason}
            )
            raise ToolFailure("precondition_failed", f"{exc.reason}: {exc.message}") from None
        p = Patch(
            patch_id=f"P{len(state.proposed_patches) + 1}",
            run_id=a.run_id,
            field=a.field,
            old_value=state.current_config.get(a.field),
            new_value=value,
            expected_revision=state.revision,
            patch_hash=patch_hash(a.run_id, a.field, value, state.revision),
        )
        state.proposed_patches.append(p)
        return {"patch_id": p.patch_id, "field": p.field, "old_value": p.old_value,
                "new_value": p.new_value, "against_revision": p.expected_revision}  # fmt: skip

    def test_patch(state: RecoveryState, a: PatchArgs) -> dict[str, Any]:
        p = find_patch(state, a.patch_id)
        inc = incident(state, p.run_id)
        if p.expected_revision != state.revision:
            raise ToolFailure("precondition_failed", "patch targets a stale revision")
        outcome = run_config(
            patched(state.configs[p.expected_revision], p), inc.inputs, limits.job_timeout_s
        )
        state.validation_results[p.patch_id] = Validation(
            patch_id=p.patch_id,
            revision=state.revision,
            all_checks_pass=outcome.all_checks_pass,
            checks=outcome.checks,
            exit_code=outcome.exit_code,
            timed_out=outcome.timed_out,
        )
        return {"patch_id": p.patch_id, "ran_on": "temporary copy", **outcome.model_dump()}

    def request_approval(state: RecoveryState, a: PatchArgs) -> dict[str, Any]:
        p = find_patch(state, a.patch_id)
        v = state.validation_results.get(p.patch_id)
        reason = ""
        if v is None:
            reason = "patch has not been tested"
        elif not v.all_checks_pass:
            reason = "patched copy failed validity checks"
        elif p.expected_revision != state.revision or v.revision != state.revision:
            reason = "patch targets a stale revision"
        decision = "denied" if reason else "approved"
        token = approval_token(p, state.revision) if decision == "approved" else None
        state.approvals[p.patch_id] = Approval(
            patch_id=p.patch_id, decision=decision, revision=state.revision, token=token,
            reason=reason,
        )  # fmt: skip
        state.approval = decision
        out = {"simulated": True, "patch_id": p.patch_id, "decision": decision}
        return out | ({"approval_token": token} if token else {"reason": reason})

    def apply_patch(state: RecoveryState, a: ApplyArgs) -> dict[str, Any]:
        p = find_patch(state, a.patch_id)
        try:
            tx = apply(state, p, a.approval_token)
        except TransactionError as exc:
            state.blocked_applies.append(
                {"step": state.steps, "patch_id": p.patch_id, "reason": exc.reason}
            )
            raise ToolFailure("precondition_failed", f"{exc.reason}: {exc.message}") from None
        return {"transaction": tx.model_dump(exclude_none=True), "current_revision": state.revision}

    def do_rollback(state: RecoveryState, a: RollbackArgs) -> dict[str, Any]:
        try:
            tx = rollback(state, a.transaction_id)
        except TransactionError as exc:
            raise ToolFailure("precondition_failed", f"{exc.reason}: {exc.message}") from None
        return {"transaction": tx.model_dump(exclude_none=True), "current_revision": state.revision}

    def check_finish(state: RecoveryState, a: FinishArgs) -> None:
        if a.diagnosis == "no_fault":
            return
        original, current = state.configs[0], state.current_config
        keys = (set(original) | set(current)) - {"revision"}
        if all(original.get(k) == current.get(k) for k in keys):
            raise ToolFailure(
                "precondition_failed",
                "finish refused: the config is unchanged since revision 0, so the fault is not "
                "repaired. Apply a tested repair, or abstain if no allowlisted field can fix "
                "the cause.",
            )

    def finish(state: RecoveryState, a: FinishArgs) -> dict[str, Any]:
        state.diagnosis = a.diagnosis
        return {"diagnosis": a.diagnosis, "summary": a.summary, "revision": state.revision}

    def abstain(state: RecoveryState, a: AbstainArgs) -> dict[str, Any]:
        state.diagnosis = a.diagnosis
        return {"reason": a.reason, "diagnosis": a.diagnosis}

    return [
        ToolSpec("inspect_log", "Read log lines [start_line, end_line] of the failed run.",
                 InspectLogArgs, inspect_log),
        ToolSpec("read_config", "Read readable config keys at the current revision.",
                 ReadConfigArgs, read_config),
        ToolSpec("validate_config", "Schema errors and static diagnostics of the current revision.",
                 RunArgs, validate_config),
        ToolSpec("propose_patch", "Propose one allowlisted field change against a revision.",
                 ProposePatchArgs, propose_patch),
        ToolSpec("test_patch", "Run the job with the patch on a temporary copy; returns the "
                 "validity checks.", PatchArgs, test_patch),
        ToolSpec("request_approval", "Ask the simulated approver; it approves only a tested patch "
                 "whose checks all pass at the current revision.", PatchArgs, request_approval,
                 side_effect=True),
        ToolSpec("apply_patch", "Apply an approved patch; needs its approval token.", ApplyArgs,
                 apply_patch, side_effect=True),
        ToolSpec("rollback", "Undo the latest applied transaction.", RollbackArgs, do_rollback,
                 side_effect=True),
        ToolSpec("finish", "End with a root-cause label from: " + ", ".join(ROOT_CAUSES) + ".",
                 FinishArgs, finish, precheck=check_finish, terminal="complete"),
        ToolSpec("abstain", "End without repairing when the fault is outside what the patch "
                 "allowlist can fix.", AbstainArgs, abstain, terminal="abstained"),
    ]  # fmt: skip
