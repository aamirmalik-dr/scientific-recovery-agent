"""Command line: demo, evaluate and report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from .agent import EpisodeConfig, run_episode
from .agentcore.adapters import FixtureAdapter, LiveModelUnavailable, OpenAICompatibleAdapter
from .evaluation import load_config, run_evaluation
from .fixture_store import FixtureStore
from .report import write_reports
from .runner import run_config
from .schemas import RecoveryState

ROOT = Path.cwd()
INCIDENTS = Path("tests/fixtures/incidents/dev")
DEMO_SCRIPT = Path("tests/fixtures/scripts/demo.json")
DEMO_RUNS = ("dev-r03", "dev-r05")


def _short(obj: Any, n: int = 64) -> str:
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 3] + "..."


def _result_text(tool: str, out: dict[str, Any] | None) -> str:
    out = out or {}
    if tool == "inspect_log":
        return f"{len(out.get('lines', []))} of {out.get('total_lines')} lines"
    if tool == "test_patch":
        failed = [k for k, v in out.get("checks", {}).items() if not v]
        return "all checks pass" if out.get("all_checks_pass") else f"FAILED {failed}"
    if tool == "request_approval":
        return f"simulated: {out.get('decision')}"
    if tool in ("apply_patch", "rollback"):
        t = out.get("transaction", {})
        rev = f"{t.get('from_revision')} -> {t.get('to_revision')}"
        return f"{t.get('transaction_id')}: revision {rev}"
    return _short(out, 48)


def steps_table(state: RecoveryState) -> Table:
    """One row per tool call: what was asked, what happened, the model's summary."""
    t = Table(title=f"{state.run_id}: {state.alert}")
    for col in ("#", "tool", "arguments", "result", "model summary"):
        t.add_column(col, overflow="fold")
    for h in state.history:
        res = (
            _result_text(h.action.tool, h.result.output)
            if h.result.ok
            else f"REFUSED {h.result.error.code}: {_short(h.result.error.message, 50)}"
        )
        t.add_row(str(h.step), h.action.tool, _short(h.action.arguments, 56), res,
                  _short(h.summary, 46))  # fmt: skip
    return t


def checks_table(store: FixtureStore, state: RecoveryState) -> Table:
    """Validity checks of every revision, re-run here, plus the field diff."""
    inc = store.get(state.run_id)
    assert inc is not None
    t = Table(title="Revisions, re-run on a temporary copy")
    t.add_column("revision")
    t.add_column("change")
    t.add_column("exit")
    names = None
    rows = []
    for rev, cfg in enumerate(state.configs):
        o = run_config(cfg, inc.inputs)
        names = names or list(o.checks)
        tx = next((x for x in state.journal if x.to_revision == rev), None)
        change = f"{tx.field}: {tx.old_value} -> {tx.new_value} ({tx.kind})" if tx else "original"
        code = "timeout" if o.timed_out else str(o.exit_code)
        rows.append(
            [str(rev), change, code] + ["pass" if o.checks.get(n) else "FAIL" for n in names]
        )
    for n in names or []:
        t.add_column(n)
    for r in rows:
        t.add_row(*r)
    return t


def run_demo(mode: str, root: Path, console: Console | None = None, model: str | None = None):
    """Unstable-diffusion repair with apply and rollback, then a principled abstention."""
    store = FixtureStore.load(root / INCIDENTS)
    live = OpenAICompatibleAdapter.from_env(model=model) if mode == "live" else None
    states = []
    for run_id in DEMO_RUNS:
        inc = store.get(run_id)
        assert inc is not None
        adapter = live or FixtureAdapter.from_file(root / DEMO_SCRIPT, run_id)
        _, state = run_episode(inc, store, adapter, EpisodeConfig(record_timing=False))
        states.append(state)
        if console:
            console.print(steps_table(state))
            console.print(checks_table(store, state))
            console.print(f"status: {state.status}, diagnosis: {state.diagnosis}\n")
    if console:
        label = "scripted fixture replies, no model" if live is None else live.name
        console.print(f"Mode: {mode} ({label}). Approvals are simulated.")
    return states


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m scientific_recovery_agent``."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="scientific_recovery_agent", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("demo", help="repair, roll back, then abstain, on two dev incidents")
    p.add_argument("--mode", choices=("fixture", "live"), default="fixture")
    p.add_argument("--model", help="model id for live mode; overrides AGENT_MODEL_NAME")
    p = sub.add_parser("evaluate", help="run every arm on every incident of a config")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--require-live", action="store_true", help="fail unless a live model is set")
    sub.add_parser("report", help="regenerate evidence files and README tables from saved outputs")
    args = parser.parse_args(argv)
    console = Console(width=170)
    try:
        if args.cmd == "demo":
            run_demo(args.mode, ROOT, console, args.model)
        elif args.cmd == "evaluate":
            cfg, sha = load_config(args.config)
            if args.require_live and cfg.mode != "live":
                raise LiveModelUnavailable("--require-live needs a config with mode: live")
            out = run_evaluation(cfg, sha, ROOT, require_live=args.require_live)
            console.print(f"wrote {out.relative_to(ROOT).as_posix()}/")
        elif args.cmd == "report":
            ev = write_reports(ROOT)
            modes = {k: "pending" if v == "pending" else "saved" for k, v in ev["modes"].items()}
            console.print(f"wrote reports/evidence.json and reports/evidence.md; {modes}")
    except LiveModelUnavailable as exc:
        console.print(f"[red]live model unavailable:[/red] {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
