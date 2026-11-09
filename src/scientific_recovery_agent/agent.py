"""Run one recovery episode and turn its state into a gradeable outcome."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from .agentcore.adapters import ModelAdapter
from .agentcore.loop import AgentLoop, CheckpointStore
from .agentcore.policy import Budget, Policy, ToolRegistry
from .agentcore.trace import TraceWriter
from .fixture_store import FixtureStore
from .prompts import agent_system_prompt, render_observation
from .schemas import Incident, Outcome, RecoveryState
from .tools import ALL_TOOLS, ToolLimits, build_tools


class EpisodeConfig(BaseModel):
    """Per-arm episode settings."""

    budget: Budget = Budget(max_steps=24, max_tool_calls=18, max_tokens=80000)
    allowlist: tuple[str, ...] = ALL_TOOLS
    max_log_reads: int | None = None
    max_config_reads: int | None = None
    recent_k: int = 4
    record_timing: bool = True
    max_completion_tokens: int = 600
    job_timeout_s: float = 30.0

    def limits(self) -> ToolLimits:
        """Tool-level limits for this arm."""
        return ToolLimits(self.max_log_reads, self.max_config_reads, self.job_timeout_s)


def make_registry(store: FixtureStore, cfg: EpisodeConfig) -> ToolRegistry:
    """Registry over ``store`` restricted to the allowlist."""
    return ToolRegistry(build_tools(store, cfg.limits()), allowlist=cfg.allowlist)


def new_state(incident: Incident, arm: str, cfg: EpisodeConfig, run: int = 0) -> RecoveryState:
    """Fresh state with revision 0 of the incident's config. No gold data."""
    return RecoveryState(
        episode_id=f"{arm}:{incident.run_id}:run{run}",
        run_id=incident.run_id,
        template=incident.template,
        alert=incident.alert,
        configs=[incident.config],
        remaining_tool_calls=cfg.budget.max_tool_calls,
    )


def outcome_of(state: RecoveryState, arm: str) -> Outcome:
    """Gradeable record of a finished state."""
    return Outcome(
        run_id=state.run_id,
        arm=arm,
        status=state.status,
        stop_reason=state.stop_reason,
        diagnosis=state.diagnosis,
        final_config=state.current_config,
        configs=state.configs,
        journal=state.journal,
        approvals={k: v.model_dump() for k, v in state.approvals.items()},
        policy_rejections=state.policy_rejections,
        blocked_applies=state.blocked_applies,
        patches_proposed=len(state.proposed_patches),
        patches_tested=len(state.validation_results),
    )


def run_episode(
    incident: Incident,
    store: FixtureStore,
    adapter: ModelAdapter,
    cfg: EpisodeConfig,
    arm: str = "agent",
    run: int = 0,
    trace_path: Path | None = None,
    checkpoint_path: Path | None = None,
    resume: bool = False,
) -> tuple[Outcome, RecoveryState]:
    """Run (or resume from a checkpoint) one recovery episode."""
    registry = make_registry(store, cfg)
    ckpt = CheckpointStore(checkpoint_path) if checkpoint_path else None
    state = ckpt.load(RecoveryState) if (resume and ckpt) else None
    if state is None:
        state = new_state(incident, arm, cfg, run)
    loop = AgentLoop(
        adapter,
        Policy(registry, cfg.budget),
        agent_system_prompt(registry),
        render_observation,
        checkpoint=ckpt,
        trace=TraceWriter(trace_path, cfg.record_timing) if trace_path else None,
        recent_k=cfg.recent_k,
        max_completion_tokens=cfg.max_completion_tokens,
    )
    state = loop.run(state)
    return outcome_of(state, arm), state
