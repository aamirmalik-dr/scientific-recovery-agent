from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scientific_recovery_agent.fixture_store import FixtureStore
from scientific_recovery_agent.runner import run_config
from scientific_recovery_agent.toy_jobs import physical_invariants

from .conftest import INCIDENTS


def test_clean_runs_pass_every_check(dev_store: FixtureStore, heldout_store: FixtureStore) -> None:
    for store, run_id in ((dev_store, "dev-r06"), (heldout_store, "ho-r10")):
        inc = store.get(run_id)
        out = run_config(inc.config, inc.inputs)
        assert out.exit_code == 0 and out.all_checks_pass and out.checks


def test_exit_zero_with_degraded_numerics_is_a_failure(heldout_store: FixtureStore) -> None:
    inc = heldout_store.get("ho-r08")  # marginally unstable, finishes normally
    out = run_config(inc.config, inc.inputs)
    assert out.exit_code == 0 and out.checks["finite"]
    assert not out.all_checks_pass and not out.checks["max_principle"]


def test_missing_dependency_exits_3_without_checks(dev_store: FixtureStore) -> None:
    inc = dev_store.get("dev-r05")
    out = run_config(inc.config, inc.inputs)
    assert out.exit_code == 3 and out.checks == {} and not out.all_checks_pass
    assert any("ImportError" in line for line in out.log_tail)


def test_corrupted_input_fails_checksum_and_backup_passes(dev_store: FixtureStore) -> None:
    inc = dev_store.get("dev-r04")
    bad = run_config(inc.config, inc.inputs)
    assert not bad.checks["input_checksum"] and not bad.checks["finite"]
    good = run_config(inc.config | {"initial_profile_source": "backup"}, inc.inputs)
    assert good.all_checks_pass


def test_runner_kills_a_job_that_exceeds_its_time_limit() -> None:
    out = run_config({"template": "_spin", "backend": "numpy"}, {}, timeout_s=2.0)
    assert out.timed_out and out.exit_code is None and not out.all_checks_pass
    assert out.elapsed_s < 15


def test_runner_never_touches_the_fixture_store(dev_store: FixtureStore) -> None:
    before = {p: p.read_bytes() for p in (INCIDENTS / "dev" / "dev-r03").rglob("*") if p.is_file()}
    inc = dev_store.get("dev-r03")
    run_config(inc.config | {"dt": 10.0}, inc.inputs)
    after = {p: p.read_bytes() for p in (INCIDENTS / "dev" / "dev-r03").rglob("*") if p.is_file()}
    assert before == after


def test_memory_limit_is_reported_honestly() -> None:
    out = run_config({"template": "gd2d", "backend": "missing"}, {}, timeout_s=10)
    assert out.memory_limit_enforced == (sys.platform != "win32")


def test_unit_fix_and_dt_compensation_differ_in_invariants(dev_store: FixtureStore) -> None:
    cfg = dev_store.get("dev-r01").config
    fixed = physical_invariants(cfg | {"diffusivity_units": "cm2/s"})
    compensated = physical_invariants(cfg | {"dt": 0.001})
    assert fixed["diffusivity_si"] == pytest.approx(1e-9)
    assert compensated["diffusivity_si"] == pytest.approx(1e-5)


def test_fixture_logs_are_real_solver_output(dev_store: FixtureStore) -> None:
    inc = dev_store.get("dev-r03")
    assert any("r=D*dt/dx^2=0.8" in line for line in inc.log_lines)
    meta = json.loads((Path(INCIDENTS) / "dev" / "dev-r03" / "meta.json").read_text())
    assert meta["template"] == "diffusion1d"
