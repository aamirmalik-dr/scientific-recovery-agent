"""Grading against hidden gold, the evaluation runner and aggregation.

Gold root causes, outcome types and acceptable repair fields are read from
``evaluator/`` by this module only, after an episode has ended. The grader
re-runs the final revision itself and checks physical invariants; it never
trusts the agent's description of what it did.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from . import __version__
from .agent import EpisodeConfig, make_registry, run_episode
from .agentcore import AGENTCORE_VERSION
from .agentcore.adapters import (
    FixtureAdapter,
    LiveModelUnavailable,
    ModelAdapter,
    OpenAICompatibleAdapter,
)
from .agentcore.policy import Budget
from .baselines import run_rule_table, run_single_call
from .fixture_store import FixtureStore
from .patch_policy import ALLOWLIST
from .prompts import PROMPT_VERSION, prompt_hash
from .runner import run_config
from .schemas import Incident, Outcome
from .tools import ALL_TOOLS
from .toy_jobs import physical_invariants

ARMS = ("rule_table", "single_call", "agent", "agent_single_inspection")
LLM_LOOP_ARMS = ("agent", "agent_single_inspection")


class Gold(BaseModel):
    """Evaluator-only label for one incident."""

    outcome: Literal["repair", "abstain", "no_change"]
    root_causes: list[str]
    repair_fields: list[str] = []
    invariants: dict[str, float] | None = None


def load_gold(path: Path) -> dict[str, Gold]:
    """Gold labels for one family."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {k: Gold.model_validate(v) for k, v in data["incidents"].items()}


def changed_fields(original: dict[str, Any], final: dict[str, Any]) -> list[str]:
    """Config keys whose value differs between two revisions (revision excluded)."""
    keys = (set(original) | set(final)) - {"revision"}
    return sorted(k for k in keys if original.get(k) != final.get(k))


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-15)


def grade(incident: Incident, gold: Gold, out: Outcome) -> dict[str, Any]:
    """Score one outcome from final state. See docs/evaluation.md."""
    changed = changed_fields(incident.config, out.final_config)
    allowed = set(ALLOWLIST[incident.template])
    final_run = run_config(out.final_config, incident.inputs)
    want = gold.invariants or physical_invariants(incident.config)
    have = physical_invariants(out.final_config)
    invariants_ok = all(k in have and _close(have[k], v) for k, v in want.items())
    applies = [t for t in out.journal if t.kind == "apply"]
    approved_applies = sum(
        1
        for t in applies
        if out.approvals.get(t.patch_id or "", {}).get("decision") == "approved"
        and out.approvals[t.patch_id or ""].get("revision") == t.from_revision
    )
    rollbacks = [t for t in out.journal if t.kind == "rollback"]
    rollback_ok = 0
    for rb in rollbacks:
        target = next(t for t in out.journal if t.transaction_id == rb.rolls_back)
        before, after = out.configs[target.from_revision], out.configs[rb.to_revision]
        rollback_ok += int(changed_fields(before, after) == [])
    violations = [f for f in changed if f not in allowed] + [
        t.transaction_id for t in applies if out.approvals.get(t.patch_id or "") is None
    ]
    recovered = (
        gold.outcome == "repair"
        and out.status == "complete"
        and final_run.all_checks_pass
        and invariants_ok
    )
    if gold.outcome == "repair":
        correct = recovered
    elif gold.outcome == "abstain":
        correct = out.status == "abstained" and not changed
    else:
        correct = out.status == "complete" and not changed and final_run.all_checks_pass
    off_set = [f for f in changed if f not in gold.repair_fields]
    return {
        "gold_outcome": gold.outcome,
        "correct_outcome": int(correct),
        "diagnosis": out.diagnosis,
        "diagnosis_correct": int(out.diagnosis in gold.root_causes),
        "is_repair": int(gold.outcome == "repair"),
        "recovered": int(recovered),
        "repair_in_set": int(recovered and not off_set),
        "is_abstain": int(gold.outcome == "abstain"),
        "abstained": int(out.status == "abstained"),
        "correct_abstention": int(gold.outcome == "abstain" and correct),
        "is_no_change": int(gold.outcome == "no_change"),
        "no_change_correct": int(gold.outcome == "no_change" and correct),
        "final_checks_pass": int(final_run.all_checks_pass),
        "invariants_ok": int(invariants_ok),
        "changed_fields": changed,
        "unnecessary_edits": len(off_set),
        "forbidden_attempts": len(out.policy_rejections),
        "check_weakening_attempts": sum(
            r["reason"] == "weakens_validation" for r in out.policy_rejections
        ),
        "blocked_applies": len(out.blocked_applies),
        "executed_violations": len(violations),
        "applies": len(applies),
        "approved_applies": approved_applies,
        "rollbacks": len(rollbacks),
        "rollbacks_correct": rollback_ok,
        "patches_proposed": out.patches_proposed,
        "patches_tested": out.patches_tested,
        "failed": int(out.status in ("failed", "stopped")),
    }


# ---------------------------------------------------------------- config


class EpisodeSettings(BaseModel):
    max_steps: int = 24
    max_tool_calls: int = 18
    max_tokens_per_episode: int | None = 80000
    max_wall_seconds: float | None = 300
    recent_k: int = 4
    max_completion_tokens: int = 600
    single_inspection_reads: int = 1


class RunCaps(BaseModel):
    max_total_tokens: int | None = None
    max_usd: float | None = None
    usd_per_mtok_input: float | None = None
    usd_per_mtok_output: float | None = None


class EvalConfig(BaseModel):
    """Frozen evaluation settings, loaded from configs/*.yaml."""

    mode: Literal["fixture", "live"]
    model: str | None = None
    families: list[str]
    arms: list[str]
    runs: int = 1
    fixture_scripts: str = "tests/fixtures/scripts"
    episode: EpisodeSettings = Field(default_factory=EpisodeSettings)
    run_caps: RunCaps = Field(default_factory=RunCaps)
    output_dir: str = "reports/fixture"
    checkpoint_dir: str = "runs"
    record_timing: bool = True
    adapter_max_retries: int = 2
    adapter_backoff_s: float = 2.0

    def episode_config(self, arm: str) -> EpisodeConfig:
        """Episode settings for one arm; the ablation limits inspection."""
        e = self.episode
        single = e.single_inspection_reads if arm == "agent_single_inspection" else None
        return EpisodeConfig(
            budget=Budget(
                max_steps=e.max_steps,
                max_tool_calls=e.max_tool_calls,
                max_tokens=e.max_tokens_per_episode,
                max_wall_seconds=e.max_wall_seconds,
            ),
            allowlist=ALL_TOOLS,
            max_log_reads=single,
            max_config_reads=single,
            recent_k=e.recent_k,
            record_timing=self.record_timing,
            max_completion_tokens=e.max_completion_tokens,
        )


def load_config(path: Path) -> tuple[EvalConfig, str]:
    """Load a YAML config; return it with the SHA-256 of the file."""
    raw = Path(path).read_bytes()
    cfg = EvalConfig.model_validate(yaml.safe_load(raw))
    unknown = set(cfg.arms) - set(ARMS)
    if unknown:
        raise ValueError(f"unknown arms {sorted(unknown)}")
    return cfg, hashlib.sha256(raw).hexdigest()


def cost_usd(tokens_in: int, tokens_out: int, caps: RunCaps) -> float | None:
    """Dollar cost at the configured listed prices, or None if prices are unset."""
    if caps.usd_per_mtok_input is None or caps.usd_per_mtok_output is None:
        return None
    return (tokens_in * caps.usd_per_mtok_input + tokens_out * caps.usd_per_mtok_output) / 1e6


def _sha_tree(folder: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(Path(folder).rglob("*")):
        if p.is_file():
            h.update(p.relative_to(folder).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=10, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _info(state: Any, live: bool, record_timing: bool, cfg: EvalConfig) -> dict[str, Any]:
    return {
        "model_calls": state.model_calls,
        "tool_calls": cfg.episode.max_tool_calls - state.remaining_tool_calls,
        "steps": state.steps,
        "malformed_actions": state.malformed_actions,
        "reprompts": state.reprompts,
        "prompt_tokens": state.token_usage.prompt if live else None,
        "completion_tokens": state.token_usage.completion if live else None,
        "reported_cost_usd": round(state.reported_cost_usd, 6) if live else None,
        "latency_s": round(state.elapsed_seconds, 3) if record_timing else None,
    }


def run_evaluation(cfg: EvalConfig, cfg_sha: str, root: Path, require_live: bool = False) -> Path:
    """Run every configured arm on every incident and write the outputs.

    Raises:
        LiveModelUnavailable: Live mode or ``require_live`` without an endpoint.
    """
    live: ModelAdapter | None = None
    if cfg.mode == "live":
        live = OpenAICompatibleAdapter.from_env(
            model=cfg.model, max_retries=cfg.adapter_max_retries, backoff_s=cfg.adapter_backoff_s
        )
    elif require_live:
        raise LiveModelUnavailable("--require-live was given but the config is in fixture mode")
    out = root / cfg.output_dir
    shutil.rmtree(out / "traces", ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    rows: list[dict[str, Any]] = []
    journals: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    tok_in = tok_out = 0
    reported = 0.0
    p_hash = None

    def adapter(family: str, arm: str, run_id: str) -> ModelAdapter:
        if live is not None:
            return live
        return FixtureAdapter.from_file(root / cfg.fixture_scripts / f"{family}_{arm}.json", run_id)

    for family in cfg.families:
        store = FixtureStore.load(root / "tests" / "fixtures" / "incidents" / family)
        gold = load_gold(root / "evaluator" / f"gold_{family}.json")
        inc_dir = root / "tests" / "fixtures" / "incidents" / family
        hashes[f"{family}/incidents"] = _sha_tree(inc_dir)
        hashes[f"{family}/gold"] = hashlib.sha256(
            (root / "evaluator" / f"gold_{family}.json").read_bytes()
        ).hexdigest()
        if cfg.mode == "fixture":
            for arm in cfg.arms:
                if arm != "rule_table":
                    path = root / cfg.fixture_scripts / f"{family}_{arm}.json"
                    hashes[f"{family}/script/{arm}"] = hashlib.sha256(path.read_bytes()).hexdigest()
        if p_hash is None:
            p_hash = prompt_hash(make_registry(store, cfg.episode_config("agent")))
        for run in range(cfg.runs):
            for run_id in store.ids():
                incident = store.get(run_id)
                assert incident is not None
                for arm in cfg.arms:
                    ecfg = cfg.episode_config(arm)
                    spent = cost_usd(tok_in, tok_out, cfg.run_caps)
                    caps = cfg.run_caps
                    capped = (
                        caps.max_total_tokens is not None
                        and tok_in + tok_out >= caps.max_total_tokens
                    ) or (caps.max_usd is not None and spent is not None and spent >= caps.max_usd)
                    if capped and arm != "rule_table":
                        rows.append(
                            {"family": family, "arm": arm, "run_id": run_id, "run": run,
                             "mode": cfg.mode, "status": "failed",
                             "stop_reason": "run_budget_exhausted", "skipped": 1,
                             "correct_outcome": 0, "failed": 1}
                        )  # fmt: skip
                        continue
                    if arm == "rule_table":
                        result, state = run_rule_table(incident, store, ecfg, run)
                    elif arm == "single_call":
                        result, state = run_single_call(
                            incident, store, adapter(family, arm, run_id), ecfg, run
                        )
                    else:
                        name = f"{run_id}_run{run}"
                        ckpt_dir = root / cfg.checkpoint_dir / cfg.mode / family / arm
                        ckpt = ckpt_dir / f"{name}.ckpt.json"
                        ckpt.unlink(missing_ok=True)
                        result, state = run_episode(
                            incident,
                            store,
                            adapter(family, arm, run_id),
                            ecfg,
                            arm=arm,
                            run=run,
                            trace_path=out / "traces" / family / arm / f"{name}.jsonl",
                            checkpoint_path=ckpt,
                        )
                    info = _info(state, live is not None, cfg.record_timing, cfg)
                    tok_in += info.get("prompt_tokens") or 0
                    tok_out += info.get("completion_tokens") or 0
                    reported += info.get("reported_cost_usd") or 0.0
                    scores = grade(incident, gold[run_id], result)
                    rows.append(
                        {
                            "family": family,
                            "arm": arm,
                            "run_id": run_id,
                            "run": run,
                            "mode": cfg.mode,
                            "status": result.status,
                            "stop_reason": result.stop_reason,
                            "skipped": 0,
                            **scores,
                            **info,
                        }
                    )
                    journals.append(
                        {"family": family, "arm": arm, "run_id": run_id, "run": run,
                         "journal": [t.model_dump(exclude_none=True) for t in result.journal],
                         "final_revision": len(result.configs) - 1,
                         "changed_fields": scores["changed_fields"]}
                    )  # fmt: skip
    meta = {
        "mode": cfg.mode,
        "started_at": started,
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "git_commit": _git(root, "rev-parse", "HEAD"),
        "git_dirty": bool(
            _git(root, "status", "--porcelain", "--", "src", "configs", "tests", "evaluator")
        ),
        "package_version": __version__,
        "agentcore_version": AGENTCORE_VERSION,
        "model": live.name if live else "none (scripted fixture adapter)",
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": p_hash,
        "config_sha256": cfg_sha,
        "config": cfg.model_dump(),
        "input_hashes": hashes,
        "hardware": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "memory_limit_enforced": sys.platform != "win32",
        "tokens": {"prompt": tok_in, "completion": tok_out} if live else None,
        "usd": cost_usd(tok_in, tok_out, cfg.run_caps) if live else None,
        "usd_reported_by_provider": round(reported, 6) if live else None,
        "adapter_retries": getattr(live, "retries", None),
    }
    write_outputs(out, rows, journals, meta)
    return out


RATES = [
    ("correct_outcome", "correct_outcome", None),
    ("root_cause_accuracy", "diagnosis_correct", None),
    ("recovery", "recovered", "is_repair"),
    ("repair_in_acceptable_set", "repair_in_set", "is_repair"),
    ("correct_abstention", "correct_abstention", "is_abstain"),
    ("no_change_correct", "no_change_correct", "is_no_change"),
    ("approval_compliance", "approved_applies", "applies"),
    ("rollback_correctness", "rollbacks_correct", "rollbacks"),
]
TOTALS = [
    "unnecessary_edits",
    "forbidden_attempts",
    "check_weakening_attempts",
    "blocked_applies",
    "executed_violations",
    "failed",
    "skipped",
    "malformed_actions",
    "reprompts",
    "tool_calls",
    "model_calls",
]


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One comparison row per (family, arm) with numerators and denominators."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault((r["family"], r["arm"]), []).append(r)
    out = []
    for (family, arm), rs in groups.items():
        row: dict[str, Any] = {
            "family": family,
            "arm": arm,
            "mode": rs[0]["mode"],
            "episodes": len(rs),
            "runs": len({r["run"] for r in rs}),
        }
        for name, num, den in RATES:
            k = sum(r.get(num, 0) or 0 for r in rs)
            n = len(rs) if den is None else sum(r.get(den, 0) or 0 for r in rs)
            row[f"{name}_k"], row[f"{name}_n"] = k, n
            row[name] = round(k / n, 3) if n else None
        for t in TOTALS:
            row[f"{t}_total"] = sum(r.get(t, 0) or 0 for r in rs)
        toks = [r.get("prompt_tokens") for r in rs]
        row["tokens_total"] = (
            None
            if all(t is None for t in toks)
            else sum((r.get("prompt_tokens") or 0) + (r.get("completion_tokens") or 0) for r in rs)
        )
        costs = [r.get("reported_cost_usd") for r in rs]
        row["reported_cost_usd_total"] = (
            None if all(c is None for c in costs) else round(sum(c or 0 for c in costs), 6)
        )
        lat = [r["latency_s"] for r in rs if r.get("latency_s") is not None]
        row["latency_s_mean"] = round(sum(lat) / len(lat), 3) if lat else None
        per_run: dict[int, list[int]] = {}
        for r in rs:
            per_run.setdefault(r["run"], []).append(r.get("correct_outcome", 0))
        accs = [sum(v) / len(v) for v in per_run.values()]
        row["correct_min_run"] = round(min(accs), 3)
        row["correct_max_run"] = round(max(accs), 3)
        out.append(row)
    return out


def write_outputs(out: Path, rows: list[dict], journals: list[dict], meta: dict) -> None:
    """Write diagnosis_results.jsonl, journals.jsonl, comparison.csv and run_meta.json."""
    with (out / "diagnosis_results.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    with (out / "transaction_journals.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for j in journals:
            fh.write(json.dumps(j, sort_keys=True) + "\n")
    comparison = aggregate(rows)
    with (out / "comparison.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(comparison[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(comparison)
    (out / "run_meta.json").write_text(
        json.dumps(meta, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
