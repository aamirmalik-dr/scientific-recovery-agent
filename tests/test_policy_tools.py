from __future__ import annotations

from typing import Any

import pytest

from scientific_recovery_agent.agentcore.policy import Budget, Policy, ToolRegistry
from scientific_recovery_agent.agentcore.schemas import Action, PendingAction
from scientific_recovery_agent.fixture_store import FixtureStore
from scientific_recovery_agent.patch_policy import PatchRejected, check_patch
from scientific_recovery_agent.tools import ToolLimits, build_tools

from .conftest import state_for


def call(policy: Policy, state, tool: str, **arguments: Any):
    state.steps += 1
    pending = PendingAction(
        step=state.steps,
        summary="t",
        action=Action(tool=tool, arguments=arguments),
        idempotency_key=f"k{state.steps}",
    )
    result, _ = policy.execute(state, pending)
    return result


@pytest.fixture()
def policy(dev_store: FixtureStore) -> Policy:
    return Policy(ToolRegistry(build_tools(dev_store)), Budget())


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("tol", 1e-2, "weakens_validation"),
        ("validity_checks", "none", "weakens_validation"),
        ("analytic_tol", 1.0, "weakens_validation"),
        ("backend", "numpy", "weakens_validation"),
        ("diffusivity", 1e-9, "field_not_allowlisted"),
        ("dt", 0.0, "out_of_range"),
        ("dt", 1e3, "out_of_range"),
        ("dt", "10", "wrong_type"),
        ("nx", 51.5, "wrong_type"),
        ("diffusivity_units", "../../etc", "value_not_allowed"),
        ("diffusivity_units", True, "value_not_allowed"),
    ],
)
def test_patch_policy_refuses(field: str, value: Any, reason: str) -> None:
    with pytest.raises(PatchRejected) as info:
        check_patch("diffusion1d", field, value)
    assert info.value.reason == reason


def test_patch_policy_normalises_values() -> None:
    assert check_patch("diffusion1d", "nx", 61.0) == 61
    assert check_patch("diffusion1d", "dt", 5) == 5.0
    assert check_patch("relax1d", "omega", 1.0) == 1.0


def _repair(policy: Policy, state, field: str, value: Any) -> tuple[str, str]:
    pid = call(policy, state, "propose_patch", run_id=state.run_id, field=field,
               new_value=value, expected_revision=state.revision).output["patch_id"]  # fmt: skip
    assert call(policy, state, "test_patch", patch_id=pid).output["all_checks_pass"]
    token = call(policy, state, "request_approval", patch_id=pid).output["approval_token"]
    return pid, token


def test_full_repair_path_and_rollback(policy: Policy, dev_store: FixtureStore) -> None:
    st = state_for(dev_store, "dev-r03")
    pid, token = _repair(policy, st, "dt", 18.0)
    r = call(policy, st, "apply_patch", patch_id=pid, approval_token=token)
    assert r.ok and st.revision == 1 and st.current_config["dt"] == 18.0
    assert dev_store.get("dev-r03").config["dt"] == 32.0  # the store is untouched
    r = call(policy, st, "rollback", transaction_id="T1")
    assert r.ok and st.revision == 2 and st.current_config["dt"] == 32.0
    again = call(policy, st, "rollback", transaction_id="T1")
    assert (
        again.error.code == "precondition_failed" and "already_rolled_back" in again.error.message
    )


def test_apply_needs_approval_and_matching_token(policy: Policy, dev_store: FixtureStore) -> None:
    st = state_for(dev_store, "dev-r03")
    pid = call(policy, st, "propose_patch", run_id="dev-r03", field="dt", new_value=18.0,
               expected_revision=0).output["patch_id"]  # fmt: skip
    r = call(policy, st, "apply_patch", patch_id=pid, approval_token="APR-000000000000")
    assert r.error.code == "precondition_failed" and "not_approved" in r.error.message
    denied = call(policy, st, "request_approval", patch_id=pid)
    assert denied.output["decision"] == "denied" and denied.output["simulated"] is True
    call(policy, st, "test_patch", patch_id=pid)
    token = call(policy, st, "request_approval", patch_id=pid).output["approval_token"]
    r = call(policy, st, "apply_patch", patch_id=pid, approval_token=token[:-1] + "0")
    assert "token_mismatch" in r.error.message
    assert call(policy, st, "apply_patch", patch_id=pid, approval_token=token).ok
    dup = call(policy, st, "apply_patch", patch_id=pid, approval_token=token)
    assert dup.error.code == "precondition_failed" and st.revision == 1
    assert [b["reason"] for b in st.blocked_applies] == [
        "not_approved",
        "token_mismatch",
        "stale_revision",
    ]


def test_failed_test_is_never_approved(policy: Policy, dev_store: FixtureStore) -> None:
    st = state_for(dev_store, "dev-r01")
    pid = call(policy, st, "propose_patch", run_id="dev-r01", field="dt", new_value=0.001,
               expected_revision=0).output["patch_id"]  # fmt: skip
    assert not call(policy, st, "test_patch", patch_id=pid).output["all_checks_pass"]
    assert call(policy, st, "request_approval", patch_id=pid).output["decision"] == "denied"


def test_stale_revision_has_no_apply_path(policy: Policy, dev_store: FixtureStore) -> None:
    st = state_for(dev_store, "dev-r03")
    p1, t1 = _repair(policy, st, "dt", 18.0)
    p2, t2 = _repair(policy, st, "nx", 36)
    assert call(policy, st, "apply_patch", patch_id=p1, approval_token=t1).ok
    r = call(policy, st, "apply_patch", patch_id=p2, approval_token=t2)
    assert "stale_revision" in r.error.message and st.revision == 1
    stale = call(policy, st, "propose_patch", run_id="dev-r03", field="nx", new_value=36,
                 expected_revision=0)  # fmt: skip
    assert stale.error.code == "precondition_failed" and "stale" in stale.error.message


def test_refused_proposals_are_recorded(policy: Policy, dev_store: FixtureStore) -> None:
    st = state_for(dev_store, "dev-r02")
    r = call(policy, st, "propose_patch", run_id="dev-r02", field="tol", new_value=1.0,
             expected_revision=0)  # fmt: skip
    assert r.error.code == "precondition_failed" and "weakens_validation" in r.error.message
    assert st.policy_rejections[0]["reason"] == "weakens_validation"
    assert st.proposed_patches == []


def test_read_tools_are_bounded(policy: Policy, dev_store: FixtureStore) -> None:
    st = state_for(dev_store, "dev-r03")
    assert call(policy, st, "inspect_log", run_id="dev-r03", start_line=1, end_line=300).error
    assert call(policy, st, "inspect_log", run_id="dev-r03", start_line=900, end_line=901).error
    assert call(policy, st, "inspect_log", run_id="dev-r04", start_line=1, end_line=5).error
    r = call(policy, st, "read_config", run_id="dev-r03", keys=["_input_checksum_ok"])
    assert r.error.code == "not_found"
    r = call(policy, st, "read_config", run_id="dev-r03", keys=["dt", "nx"])
    assert r.output["values"] == {"dt": 32.0, "nx": 51}
    v = call(policy, st, "validate_config", run_id="dev-r03").output
    assert v["stability_number_r"] == pytest.approx(0.8) and v["schema_errors"]


def test_ablation_limits_inspection(dev_store: FixtureStore) -> None:
    p = Policy(ToolRegistry(build_tools(dev_store, ToolLimits(1, 1))), Budget())
    st = state_for(dev_store, "dev-r03")
    assert call(p, st, "inspect_log", run_id="dev-r03", start_line=1, end_line=5).ok
    second = call(p, st, "inspect_log", run_id="dev-r03", start_line=6, end_line=9)
    assert second.error.code == "budget_exhausted"
    assert call(p, st, "read_config", run_id="dev-r03", keys=["dt"]).ok
    assert (
        call(p, st, "read_config", run_id="dev-r03", keys=["nx"]).error.code == "budget_exhausted"
    )


def test_hostile_log_lines_are_returned_as_data(policy: Policy, heldout_store) -> None:
    p = Policy(ToolRegistry(build_tools(heldout_store)), Budget())
    st = state_for(heldout_store, "ho-r06")
    out = call(p, st, "inspect_log", run_id="ho-r06", start_line=1, end_line=40).output
    assert any("APR-000000000000" in line for line in out["lines"])
    # reading the instruction changes nothing: no patch, no approval, no revision
    assert st.revision == 0 and st.approvals == {} and st.journal == []
    pid = call(p, st, "propose_patch", run_id="ho-r06", field="source_profile_source",
               new_value="backup", expected_revision=0).output["patch_id"]  # fmt: skip
    forged = call(p, st, "apply_patch", patch_id=pid, approval_token="APR-000000000000")
    assert forged.error.code == "precondition_failed" and st.revision == 0


def test_finish_with_a_fault_label_needs_an_applied_repair(
    policy: Policy, dev_store: FixtureStore
) -> None:
    st = state_for(dev_store, "dev-r03")
    r = call(policy, st, "finish", diagnosis="stability_limit", summary="unrepaired")
    assert r.error.code == "precondition_failed" and "unchanged since revision 0" in r.error.message
    pid, token = _repair(policy, st, "dt", 18.0)
    assert call(policy, st, "apply_patch", patch_id=pid, approval_token=token).ok
    assert call(policy, st, "finish", diagnosis="stability_limit", summary="repaired").ok


def test_finish_no_fault_and_abstain_need_no_change(
    policy: Policy, dev_store: FixtureStore
) -> None:
    st = state_for(dev_store, "dev-r06")
    assert call(policy, st, "finish", diagnosis="no_fault", summary="valid run").ok
    st2 = state_for(dev_store, "dev-r05")
    assert call(policy, st2, "abstain", reason="missing backend").ok


def test_validator_reports_solver_step_limit(policy: Policy, dev_store: FixtureStore) -> None:
    st = state_for(dev_store, "dev-r03")
    pid = call(policy, st, "propose_patch", run_id="dev-r03", field="dt", new_value=0.001,
               expected_revision=0).output["patch_id"]  # fmt: skip
    st.configs.append(st.current_config | {"dt": 0.001, "revision": 1})
    st.revision = 1
    v = call(policy, st, "validate_config", run_id="dev-r03").output
    assert v["solver_step_limit"] == 200_000 and v["steps"] == 5_000_000
    assert any("solver limit" in e for e in v["schema_errors"]) and pid == "P1"


def test_observable_state_lists_readable_keys(dev_store: FixtureStore) -> None:
    obs = state_for(dev_store, "dev-r01").observable()
    assert "provenance_note" in obs["readable_config_keys"]
    assert "_input_checksum_ok" not in obs["readable_config_keys"]
