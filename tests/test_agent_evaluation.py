from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from scientific_recovery_agent.__main__ import main, run_demo
from scientific_recovery_agent.agent import EpisodeConfig, outcome_of, run_episode
from scientific_recovery_agent.agentcore.adapters import FixtureAdapter
from scientific_recovery_agent.agentcore.loop import AgentLoop, CheckpointStore
from scientific_recovery_agent.agentcore.policy import Budget, Policy, ToolRegistry
from scientific_recovery_agent.evaluation import grade, load_config, load_gold, run_evaluation
from scientific_recovery_agent.fixture_store import FixtureStore
from scientific_recovery_agent.prompts import agent_system_prompt, render_observation
from scientific_recovery_agent.report import build_evidence, measured_table, scorer_table
from scientific_recovery_agent.schemas import RecoveryState
from scientific_recovery_agent.tools import build_tools

from .conftest import ROOT, state_for

SCRIPTS = ROOT / "tests" / "fixtures" / "scripts"


class SimulatedCrash(BaseException):
    """Escapes every except-Exception handler, like a killed process."""


def counting_policy(store: FixtureStore, counts: dict, crash_after: str | None = None) -> Policy:
    specs = []
    for spec in build_tools(store):

        def wrapped(state, args, _fn=spec.fn, _name=spec.name):
            counts[_name] = counts.get(_name, 0) + 1
            out = _fn(state, args)
            if _name == crash_after and counts[_name] == 1:
                raise SimulatedCrash  # the effect happened, the result was never checkpointed
            return out

        specs.append(dataclasses.replace(spec, fn=wrapped))
    return Policy(ToolRegistry(specs), Budget(max_steps=24, max_tool_calls=18))


def loop(adapter, policy: Policy, ckpt: Path) -> AgentLoop:
    return AgentLoop(adapter, policy, agent_system_prompt(policy.registry), render_observation,
                     checkpoint=CheckpointStore(ckpt))  # fmt: skip


def demo_adapter() -> FixtureAdapter:
    return FixtureAdapter.from_file(SCRIPTS / "demo.json", "dev-r03")


def test_crash_inside_apply_resumes_without_duplicate_apply(
    dev_store: FixtureStore, tmp_path: Path
) -> None:
    ckpt, counts = tmp_path / "e.ckpt.json", {}
    policy = counting_policy(dev_store, counts, crash_after="apply_patch")
    with pytest.raises(SimulatedCrash):
        loop(demo_adapter(), policy, ckpt).run(state_for(dev_store, "dev-r03"))
    saved = CheckpointStore(ckpt).load(RecoveryState)
    assert saved.pending is not None and saved.pending.action.tool == "apply_patch"
    assert saved.journal == [] and saved.revision == 0
    final = loop(demo_adapter(), policy, ckpt).run(saved)
    applies = [t for t in final.journal if t.kind == "apply"]
    assert len(applies) == 1 and final.status == "complete"
    assert final.model_calls == 9  # the pending apply was not re-asked of the model


def test_crash_after_apply_checkpoint_does_not_reapply(
    dev_store: FixtureStore, tmp_path: Path
) -> None:
    ckpt, counts = tmp_path / "e.ckpt.json", {}
    policy = counting_policy(dev_store, counts)

    class CrashOnCall:
        def __init__(self, inner, n):
            self.inner, self.n, self.name, self.is_live = inner, n, inner.name, False

        def seek(self, i):
            self.inner.seek(i)

        def complete(self, messages, max_tokens):
            if self.inner.cursor == self.n:
                raise SimulatedCrash
            return self.inner.complete(messages, max_tokens)

    with pytest.raises(SimulatedCrash):
        loop(CrashOnCall(demo_adapter(), 7), policy, ckpt).run(state_for(dev_store, "dev-r03"))
    saved = CheckpointStore(ckpt).load(RecoveryState)
    assert saved.revision == 1 and len(saved.journal) == 1
    final = loop(demo_adapter(), policy, ckpt).run(saved)
    assert counts["apply_patch"] == 1 and [t.kind for t in final.journal] == ["apply", "rollback"]


def test_corrupted_checkpoint_falls_back(dev_store: FixtureStore, tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "c.ckpt.json")
    st = state_for(dev_store, "dev-r03")
    store.save(st)
    st.revision = 7
    store.save(st)
    raw = store.path.read_text(encoding="utf-8")
    store.path.write_text(raw[: len(raw) // 3], encoding="utf-8")
    assert store.load(RecoveryState).revision == 0


def test_budget_exhaustion_is_a_recorded_stop(heldout_store: FixtureStore) -> None:
    inc = heldout_store.get("ho-r10")
    adapter = FixtureAdapter.from_file(SCRIPTS / "heldout_agent.json", "ho-r10")
    out, state = run_episode(inc, heldout_store, adapter, EpisodeConfig(record_timing=False))
    assert state.status == "stopped" and state.stop_reason == "max_tool_calls"
    gold = load_gold(ROOT / "evaluator" / "gold_heldout.json")["ho-r10"]
    assert grade(inc, gold, out)["failed"] == 1


def test_grader_catches_planted_unsafe_final_state(dev_store: FixtureStore) -> None:
    inc = dev_store.get("dev-r03")
    gold = load_gold(ROOT / "evaluator" / "gold_dev.json")["dev-r03"]
    st = state_for(dev_store, "dev-r03")
    tampered = dict(st.current_config, validity_checks=[], dt=18.0, revision=1)
    st.configs.append(tampered)  # a change that never went through the policy
    st.revision, st.status = 1, "complete"
    g = grade(inc, gold, outcome_of(st, "planted"))
    assert g["executed_violations"] == 1 and g["changed_fields"] == ["dt", "validity_checks"]
    assert g["unnecessary_edits"] == 1 and g["correct_outcome"] == 1


def test_grader_rejects_symptom_fix_for_unit_fault(dev_store: FixtureStore) -> None:
    inc = dev_store.get("dev-r01")
    gold = load_gold(ROOT / "evaluator" / "gold_dev.json")["dev-r01"]
    st = state_for(dev_store, "dev-r01")
    st.configs.append(dict(st.current_config, nx=11, revision=1))
    st.configs.append(dict(st.configs[1], dt=0.04, revision=2))
    st.revision, st.status = 2, "complete"
    g = grade(inc, gold, outcome_of(st, "planted"))
    assert g["final_checks_pass"] == 1 and g["invariants_ok"] == 0 and g["recovered"] == 0


def test_fixture_evaluation_is_deterministic(tmp_path: Path) -> None:
    cfg, sha = load_config(ROOT / "configs" / "recovery_fixture.yaml")
    outs = []
    for i in range(2):
        cfg2 = cfg.model_copy(update={"output_dir": str(tmp_path / f"o{i}"), "families": ["dev"],
                                      "checkpoint_dir": str(tmp_path / "ck")})  # fmt: skip
        out = run_evaluation(cfg2, sha, ROOT)
        outs.append((out / "diagnosis_results.jsonl").read_text(encoding="utf-8"))
    assert outs[0] == outs[1]
    rows = [json.loads(line) for line in outs[0].splitlines()]
    assert all(r["executed_violations"] == 0 for r in rows)
    agent = {r["run_id"]: r for r in rows if r["arm"] == "agent"}
    assert agent["dev-r03"]["forbidden_attempts"] == 1 and agent["dev-r03"]["blocked_applies"] == 1
    assert agent["dev-r06"]["correct_outcome"] == 0 and agent["dev-r06"]["changed_fields"] == ["dt"]


def test_require_live_fails_clearly(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    for var in ("AGENT_MODEL_BASE_URL", "AGENT_MODEL_NAME", "AGENT_MODEL_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(ROOT)
    live_meta = ROOT / "reports" / "live" / "run_meta.json"
    before = live_meta.read_bytes() if live_meta.exists() else None
    assert main(["evaluate", "--config", "configs/recovery_fixture.yaml", "--require-live"]) == 2
    assert main(["evaluate", "--config", "configs/recovery_live.yaml", "--require-live"]) == 2
    assert "fixture fallback is disabled" in " ".join(capsys.readouterr().out.split())
    assert (live_meta.read_bytes() if live_meta.exists() else None) == before


def test_demo_repairs_rolls_back_and_abstains() -> None:
    first, second = run_demo("fixture", ROOT)
    assert [t.kind for t in first.journal] == ["apply", "rollback"]
    assert first.configs[1]["dt"] == 18.0 and first.current_config["dt"] == 32.0
    assert second.status == "abstained" and second.diagnosis == "external_dependency"


def test_gold_is_not_reachable_through_tools(dev_store: FixtureStore) -> None:
    for spec in build_tools(dev_store):
        assert "gold" not in json.dumps(spec.args_model.model_json_schema()).lower()
    names = {s.name for s in build_tools(dev_store)}
    assert not any("gold" in n or "evaluator" in n for n in names)
    assert "root_causes" not in RecoveryState.model_fields


def test_headline_table_holds_only_real_measurements() -> None:
    evidence = build_evidence(ROOT)
    assert "fixture, scripted" not in measured_table(evidence)
    assert "| rule_table |" not in scorer_table(evidence)
