from __future__ import annotations

from pathlib import Path

import pytest

from scientific_recovery_agent.agent import EpisodeConfig, new_state
from scientific_recovery_agent.fixture_store import FixtureStore
from scientific_recovery_agent.schemas import RecoveryState

ROOT = Path(__file__).resolve().parents[1]
INCIDENTS = ROOT / "tests" / "fixtures" / "incidents"


@pytest.fixture(scope="session")
def dev_store() -> FixtureStore:
    return FixtureStore.load(INCIDENTS / "dev")


@pytest.fixture(scope="session")
def heldout_store() -> FixtureStore:
    return FixtureStore.load(INCIDENTS / "heldout")


def state_for(store: FixtureStore, run_id: str, calls: int = 18) -> RecoveryState:
    inc = store.get(run_id)
    assert inc is not None
    cfg = EpisodeConfig()
    st = new_state(inc, "test", cfg)
    st.remaining_tool_calls = calls
    return st
