"""Build reports/evidence.json, reports/evidence.md and the README tables.

Everything is read from saved run outputs. A mode without saved outputs is
reported as "pending"; nothing is estimated.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

MODES = ("fixture", "live", "live_v2_gpt41mini", "live_v2_sonnet")
LIVE_MODES = {
    "live": "live v1, held-out v1",
    "live_v2_gpt41mini": "live v2, held-out v2",
    "live_v2_sonnet": "live v2, held-out v2, second model",
}
MARKERS = {
    "measured": ("<!-- measured-table:start -->", "<!-- measured-table:end -->"),
    "scorer": ("<!-- scorer-table:start -->", "<!-- scorer-table:end -->"),
}
SCRIPTED_NOTE = (
    "In fixture mode the single_call, agent and agent_single_inspection arms replay "
    "hand-written replies with planted failures. Those rows check the tools, policy and grader; "
    "they are not model results. The rule_table arm calls no model, so its rows are real "
    "measurements of that baseline."
)
LIMITATIONS = [
    "Six development and ten held-out incidents on three original toy solvers, written by the "
    "author together with the rule table. Useful for testing behaviour, too small to rank models.",
    "The rule table was written with knowledge of the fault types, so it is a strong scripted "
    "reference rather than a naive baseline.",
    "The simulated approver approves any tested patch whose checks pass; it does not model a "
    "human reviewer.",
    "The subprocess runner enforces a time limit everywhere and a memory limit only on POSIX.",
    "There is no production integration: no scheduler, cluster, file system or real code.",
]


def _num(v: str) -> Any:
    if v == "":
        return None
    try:
        f = float(v)
    except ValueError:
        return v
    return int(f) if f.is_integer() and "." not in v else f


def load_mode(reports: Path, mode: str) -> dict[str, Any] | None:
    """Saved outputs for one mode, or None if that mode has never run."""
    d = reports / mode
    if not (d / "run_meta.json").exists():
        return None
    meta = json.loads((d / "run_meta.json").read_text(encoding="utf-8"))
    with (d / "comparison.csv").open(encoding="utf-8") as fh:
        comparison = [{k: _num(v) for k, v in row.items()} for row in csv.DictReader(fh)]
    rows = [
        json.loads(line)
        for line in (d / "diagnosis_results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    keys = ("family", "arm", "run_id", "run", "status", "stop_reason", "gold_outcome")
    problems = [
        {k: r.get(k) for k in keys}
        | {
            "diagnosis": r.get("diagnosis"),
            "changed_fields": r.get("changed_fields"),
            "forbidden_attempts": r.get("forbidden_attempts"),
            "blocked_applies": r.get("blocked_applies"),
            "malformed_actions": r.get("malformed_actions"),
        }
        for r in rows
        if not r.get("correct_outcome")
        or r.get("forbidden_attempts")
        or r.get("blocked_applies")
        or r.get("malformed_actions")
        or r.get("unnecessary_edits")
    ]
    return {"meta": meta, "metrics": comparison, "problems": problems, "n_rows": len(rows)}


def build_evidence(root: Path) -> dict[str, Any]:
    """Assemble the evidence record from saved outputs."""
    evidence: dict[str, Any] = {"schema": "evidence-v1", "modes": {}}
    for mode in MODES:
        data = load_mode(root / "reports", mode)
        if data is None:
            evidence["modes"][mode] = "pending"
            continue
        m = data["meta"]
        evidence["modes"][mode] = {
            "mode": mode,
            "interpretation": SCRIPTED_NOTE if mode == "fixture" else "live model results",
            **{
                k: m.get(k)
                for k in (
                    "git_commit",
                    "git_dirty",
                    "model",
                    "agentcore_version",
                    "prompt_version",
                    "prompt_sha256",
                    "config_sha256",
                    "input_hashes",
                    "hardware",
                    "started_at",
                    "finished_at",
                    "memory_limit_enforced",
                )
            },
            "caps": {"episode": m["config"]["episode"], "run": m["config"]["run_caps"]},
            "cost": {
                "tokens": m["tokens"],
                "usd_at_listed_prices": m["usd"],
                "usd_reported_by_provider": m.get("usd_reported_by_provider"),
                "adapter_retries": m.get("adapter_retries"),
            },
            "metrics": data["metrics"],
            "episodes_needing_attention": data["problems"],
            "episodes": data["n_rows"],
        }
    done = [m for m in LIVE_MODES if evidence["modes"][m] != "pending"]
    evidence["limitations"] = LIMITATIONS + [
        (
            "Each live run is ten held-out incidents with one or two runs per arm at temperature "
            "0: "
            "an exploratory sample, not a ranking. v1 and v2 use different incident families, so "
            "their rows are not paired."
            if done
            else "No live model has been evaluated yet; live results are pending."
        )
    ]
    evidence["reproduce"] = {
        "fixture": "python -m scientific_recovery_agent evaluate --config "
        "configs/recovery_fixture.yaml && python -m scientific_recovery_agent report",
        "live": "python -m scientific_recovery_agent evaluate --config configs/recovery_live.yaml "
        "--require-live && python -m scientific_recovery_agent report",
        "live_v2_gpt41mini": "python -m scientific_recovery_agent evaluate --config "
        "configs/recovery_live_v2_gpt41mini.yaml --require-live",
        "live_v2_sonnet": "python -m scientific_recovery_agent evaluate --config "
        "configs/recovery_live_v2_sonnet.yaml --require-live",
    }
    return evidence


def _frac(row: dict[str, Any], name: str) -> str:
    k, n = row.get(f"{name}_k"), row.get(f"{name}_n")
    if not n:
        return "n/a"
    return f"{k}/{n}"


HEAD = (
    "| Mode | Family | Arm | Correct outcome | Root cause | Recovered | In repair set "
    "| Abstained correctly | No-change correct | Unnecessary edits | Refused proposals "
    "| Executed violations | Failures"
)


def _cells(label: str, r: dict[str, Any]) -> str:
    return (
        f"| {label} | {r['family']} | {r['arm']} | {_frac(r, 'correct_outcome')} "
        f"| {_frac(r, 'root_cause_accuracy')} | {_frac(r, 'recovery')} "
        f"| {_frac(r, 'repair_in_acceptable_set')} | {_frac(r, 'correct_abstention')} "
        f"| {_frac(r, 'no_change_correct')} | {r['unnecessary_edits_total']} "
        f"| {r['forbidden_attempts_total']} | {r['executed_violations_total']} "
        f"| {r['failed_total']}"
    )


def measured_table(evidence: dict[str, Any]) -> str:
    """Only real measurements: the no-model rule table and the live rows."""
    head = HEAD + " | Correct per run | Tool calls | Model calls | Tokens | USD |\n"
    head += "|---" * 18 + "|\n"
    lines = []
    fixture = evidence["modes"]["fixture"]
    if fixture != "pending":
        for r in fixture["metrics"]:
            if r["arm"] == "rule_table":
                lines.append(
                    _cells("no model", r) + f" | one run | {r['tool_calls_total']} | 0 | 0 | 0 |"
                )
    for mode, label in LIVE_MODES.items():
        live = evidence["modes"][mode]
        if live == "pending":
            lines.append(f"| {label}: pending |" + " |" * 17)
            continue
        model = str(live["model"]).split("/")[-1]
        for r in live["metrics"]:
            spread = (
                f"{r['correct_min_run']:.2f} to {r['correct_max_run']:.2f}"
                if r["runs"] > 1
                else "one run"
            )
            usd = r.get("reported_cost_usd_total") or 0.0
            lines.append(
                _cells(f"{label}, {model}", r) + f" | {spread} | {r['tool_calls_total']} "
                f"| {r['model_calls_total']} | {r['tokens_total'] or 0} "
                f"| {'0' if not r['model_calls_total'] else f'{usd:.4f}'} |"
            )
    return head + "\n".join(lines) + "\n"


def scorer_table(evidence: dict[str, Any]) -> str:
    """Scripted fixture rows: checks of tools, policy and grader, not model results."""
    head = HEAD + " | Blocked applies | Rollbacks correct |\n" + "|---" * 15 + "|\n"
    fixture = evidence["modes"]["fixture"]
    if fixture == "pending":
        return head + "| fixture: pending |" + " |" * 14 + "\n"
    lines = [
        _cells("fixture, scripted", r)
        + f" | {r['blocked_applies_total']} | {_frac(r, 'rollback_correctness')} |"
        for r in fixture["metrics"]
        if r["arm"] != "rule_table"
    ]
    return head + "\n".join(lines) + "\n"


def evidence_markdown(evidence: dict[str, Any]) -> str:
    """Human-readable evidence report."""
    out = ["# Evidence", "", "Generated from saved outputs by "
           "`python -m scientific_recovery_agent report`. Do not edit by hand.", ""]  # fmt: skip
    for mode in MODES:
        data = evidence["modes"][mode]
        out += [f"## {LIVE_MODES.get(mode, 'fixture (scripted)')} ({mode})", ""]
        if data == "pending":
            out += ["Pending. No saved outputs exist for this mode.", ""]
            continue
        c = data["cost"]
        out += [
            data["interpretation"],
            "",
            f"- Commit: `{data['git_commit']}` (working tree dirty: {data['git_dirty']})",
            f"- Model: {data['model']}; agentcore {data['agentcore_version']}",
            f"- Prompt: {data['prompt_version']}, sha256 `{(data['prompt_sha256'] or '')[:16]}`",
            f"- Config sha256: `{data['config_sha256'][:16]}`",
            f"- Run: {data['started_at']} to {data['finished_at']}",
            f"- Hardware: {data['hardware']['platform']}, Python {data['hardware']['python']}; "
            f"memory limit enforced: {data['memory_limit_enforced']}",
            f"- Episodes scored: {data['episodes']}",
            f"- Tokens: {c['tokens']}; USD at listed prices: {c['usd_at_listed_prices']}; "
            f"USD reported by provider: {c['usd_reported_by_provider']}; "
            f"adapter retries: {c['adapter_retries']}",
            "",
            "### Input hashes",
            "",
        ]
        out += [f"- {k}: `{v[:16]}`" for k, v in sorted(data["input_hashes"].items())]
        out += [
            "",
            "### Every wrong, refused or malformed episode",
            "",
            "| Family | Arm | Run | Rep | Gold | Status | Stop | Diagnosis | Changed | Refused "
            "| Blocked applies | Malformed |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        out += [
            f"| {p['family']} | {p['arm']} | {p['run_id']} | {p['run']} | {p['gold_outcome']} "
            f"| {p['status']} | {p['stop_reason']} | {p['diagnosis']} "
            f"| {', '.join(p['changed_fields'] or []) or '-'} | {p['forbidden_attempts']} "
            f"| {p['blocked_applies']} | {p['malformed_actions']} |"
            for p in data["episodes_needing_attention"]
        ]
        out.append("")
    out += [
        "## Measured results (no-model baseline and live model)",
        "",
        measured_table(evidence),
        "## Scorer checks (scripted replies, not model results)",
        "",
        scorer_table(evidence),
        "## Limitations",
        "",
    ]
    out += [f"- {x}" for x in evidence["limitations"]]
    out += ["", "## Reproduce", ""] + [f"- {k}: `{v}`" for k, v in evidence["reproduce"].items()]
    return "\n".join(out) + "\n"


def write_reports(root: Path, update_readme: bool = True) -> dict[str, Any]:
    """Write evidence.json and evidence.md and refresh the README tables."""
    evidence = build_evidence(root)
    reports = root / "reports"
    (reports / "evidence.json").write_text(
        json.dumps(evidence, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    (reports / "evidence.md").write_text(
        evidence_markdown(evidence), encoding="utf-8", newline="\n"
    )
    readme = root / "README.md"
    if update_readme and readme.exists():
        text = readme.read_text(encoding="utf-8")
        for key, table in (
            ("measured", measured_table(evidence)),
            ("scorer", scorer_table(evidence)),
        ):
            start, end = MARKERS[key]
            pattern = re.compile(re.escape(start) + ".*?" + re.escape(end), re.S)
            if pattern.search(text):
                block = f"{start}\n{table}{end}"
                text = pattern.sub(lambda _, b=block: b, text)
        readme.write_text(text, encoding="utf-8", newline="\n")
    return evidence
