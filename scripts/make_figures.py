"""Draw the README figures from saved run outputs only.

Reads reports/live (v1, gpt-4.1-mini), reports/live_v2_gpt41mini (v2,
gpt-4.1-mini) and reports/live_v2_sonnet (v2, second model):
diagnosis_results.jsonl and transaction_journals.jsonl, plus the gold labels
in evaluator/. No model is called and nothing is estimated.

One figure, example_incident.png, also reruns the deterministic toy solver on
three configurations of the selected incident (revision 0, the agent's saved
final revision and the coarse-grid reference named in the incident's
provenance note) to recover the residual trajectory, which the evaluation
does not save. Running this script twice gives identical files.

Usage: python scripts/make_figures.py [--out docs/figures]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figure_style as fs  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from scientific_recovery_agent.fixture_store import FixtureStore  # noqa: E402
from scientific_recovery_agent.toy_jobs import relax1d  # noqa: E402

# (output dir, incident family, group label, second model?)
ROUNDS = [
    ("live", "heldout", "v1\nheld-out v1", False),
    ("live_v2_gpt41mini", "heldout_v2", "v2\nheld-out v2", False),
    ("live_v2_sonnet", "heldout_v2", "v2, second model\nheld-out v2", True),
]
SAMPLE = (
    "Live. v1 and v2: gpt-4.1-mini, 10 incidents x 2 runs.\n"
    "Second model: claude-sonnet-4.6, 10 incidents x 1 run (hatched)."
)
KEY = (
    "rule: rule table, no model.  single: one model call, then the same repair path.\n"
    "agent: iterative agent.  one-read: agent limited to one log read and one config read."
)
ARMS = ["rule_table", "single_call", "agent", "agent_single_inspection"]
ARM_TYPE = {
    "rule_table": "baseline",
    "single_call": "single",
    "agent": "agent",
    "agent_single_inspection": "ablation",
}
ARM_LABEL = {
    "rule_table": "rule",
    "single_call": "single",
    "agent": "agent",
    "agent_single_inspection": "one-read",
}
FIGURES = [
    "outcome_by_arm.png",
    "root_cause_and_recovery.png",
    "v2_incident_outcomes.png",
    "example_incident.png",
    "cost_vs_outcome.png",
]


def load(name: str) -> list[dict]:
    path = ROOT / "reports" / name / "diagnosis_results.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def journals(name: str) -> list[dict]:
    path = ROOT / "reports" / name / "transaction_journals.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def by_arm(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["arm"]].append(r)
    return out


def layout() -> list[tuple[float, str, bool, str]]:
    """Bar positions: (x, round dir, second model, arm)."""
    pos, x = [], 0.0
    for name, _, _, second in ROUNDS:
        present = by_arm(load(name))
        for arm in ARMS:
            if arm in present:
                pos.append((x, name, second, arm))
                x += 1
        x += 0.9
    return pos


def label_groups(ax, pos, y: float = -0.2) -> None:
    """Arm names as rotated ticks, round names centred under each group."""
    ax.set_xticks([p[0] for p in pos], [ARM_LABEL[p[3]] for p in pos], rotation=30, ha="right")
    for name, _, title, _ in ROUNDS:
        xs = [p[0] for p in pos if p[1] == name]
        if xs:
            ax.text(
                sum(xs) / len(xs),
                y,
                title,
                ha="center",
                va="top",
                fontsize=10,
                transform=ax.get_xaxis_transform(),
            )
    ax.set_xlim(pos[0][0] - 0.7, pos[-1][0] + 1.3)


def per_run_rate(rs: list[dict], key: str, den: str | None = None) -> list[float]:
    out = []
    for i in sorted({r["run"] for r in rs}):
        sub = [r for r in rs if r["run"] == i]
        n = sum(r[den] for r in sub) if den else len(sub)
        out.append(sum(r[key] for r in sub) / n if n else 0.0)
    return out


def rate_panel(ax, pos, key: str, den: str | None, ylabel: str) -> None:
    """Bars of k/n per arm and round, with per-run points and k/n labels."""
    for x, name, second, arm in pos:
        rs = by_arm(load(name))[arm]
        k = sum(r[key] for r in rs)
        n = sum(r[den] for r in rs) if den else len(rs)
        runs = per_run_rate(rs, key, den)
        ax.bar(x, k / n, width=0.7, **fs.bar_kwargs(ARM_TYPE[arm], second))
        if len(runs) > 1:
            fs.points(ax, x, runs)
        ax.text(x, max(k / n, *runs) + 0.03, f"{k}/{n}", ha="center", va="bottom", fontsize=10)
    ax.set_ylim(0, 1.18)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_ylabel(ylabel)


def outcome_by_arm(out: Path) -> None:
    fig, ax = plt.subplots(figsize=(fs.WIDTH, 5.6))
    pos = layout()
    rate_panel(ax, pos, "correct_outcome", None, "Share of episodes with the\ncorrect final state")
    label_groups(ax, pos, y=-0.2)
    ax.set_title(
        "Correct final state by arm (repaired, abstained or left unchanged as the gold label "
        "requires)\n"
        f"{SAMPLE}\nBars: all episodes. Points: individual runs.",
        loc="left",
        fontsize=11,
    )
    fig.text(0.01, 0.01, KEY, fontsize=10, color=fs.MUTED, va="bottom")
    fig.subplots_adjust(left=0.11, right=0.99, top=0.8, bottom=0.31)
    fs.save(fig, out / "outcome_by_arm.png")


def root_cause_and_recovery(out: Path) -> None:
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(fs.WIDTH, 8.4), sharex=True)
    pos = layout()
    rate_panel(top, pos, "diagnosis_correct", None, "Root-cause label\ncorrect (all episodes)")
    rate_panel(
        bottom, pos, "recovered", "is_repair", "Recovered with invariants\n(repair incidents)"
    )
    label_groups(bottom, pos, y=-0.3)
    top.set_title(
        "Root-cause accuracy (top) and invariant-preserving recovery (bottom) by arm\n"
        f"{SAMPLE}\nRecovery counts only the 8 repair incidents per run. Points: individual runs.",
        loc="left",
        fontsize=11,
    )
    fig.text(0.01, 0.01, KEY, fontsize=10, color=fs.MUTED, va="bottom")
    fig.subplots_adjust(left=0.12, right=0.99, top=0.86, bottom=0.21, hspace=0.12)
    fs.save(fig, out / "root_cause_and_recovery.png")


CATEGORIES = [
    ("correct final state", fs.OUTCOME["correct"], "ok"),
    ("wrong final state", fs.OUTCOME["wrong"], "wrong"),
    ("abstained, gold expects a repair", fs.OUTCOME["abstained"], "abst"),
    ("stopped on the 18-call cap", fs.OUTCOME["failed"], "cap"),
]


def category(r: dict) -> int:
    if r["correct_outcome"]:
        return 0
    if r["status"] == "abstained":
        return 2
    if r["status"] in ("stopped", "failed"):
        return 3
    return 1


def v2_incident_outcomes(out: Path) -> None:
    gold = json.loads((ROOT / "evaluator" / "gold_heldout_v2.json").read_text(encoding="utf-8"))
    incidents = sorted(gold["incidents"])
    cols = []
    for arm in ARMS:
        for run in (0, 1):
            cols.append(("live_v2_gpt41mini", arm, run, f"{ARM_LABEL[arm]} r{run + 1}"))
    for arm in ("rule_table", "single_call", "agent"):
        cols.append(("live_v2_sonnet", arm, 0, f"{ARM_LABEL[arm]} sonnet"))
    rows = {
        (name, r["arm"], r["run"], r["run_id"]): r
        for name in ("live_v2_gpt41mini", "live_v2_sonnet")
        for r in load(name)
    }
    fig, ax = plt.subplots(figsize=(fs.WIDTH, 6.6))
    for j, (name, arm, run, _) in enumerate(cols):
        for i, inc in enumerate(incidents):
            label, colour, short = CATEGORIES[category(rows[(name, arm, run, inc)])]
            ax.add_patch(
                plt.Rectangle((j, i), 1, 1, facecolor=colour, edgecolor="white", linewidth=2)
            )
            ax.text(
                j + 0.5,
                i + 0.5,
                short,
                ha="center",
                va="center",
                fontsize=10,
                color="white" if colour != fs.OUTCOME["abstained"] else fs.TEXT,
            )
    ax.set_xlim(0, len(cols))
    ax.set_ylim(len(incidents), 0)
    ax.set_xticks(
        [j + 0.5 for j in range(len(cols))],
        [c[3] for c in cols],
        fontsize=10,
        rotation=30,
        ha="right",
    )
    ax.set_yticks(
        [i + 0.5 for i in range(len(incidents))],
        [f"{inc}  {gold['incidents'][inc]['root_causes'][0]}" for inc in incidents],
    )
    ax.axvline(8, color=fs.EDGE, linewidth=1.5)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.legend(
        handles=[
            Patch(facecolor=c, edgecolor=fs.EDGE, label=f"{s}: {k}") for k, c, s in CATEGORIES
        ],
        loc="upper center",
        bbox_to_anchor=(0.42, -0.2),
        ncol=2,
        frameon=False,
    )
    ax.set_title(
        "Per-incident outcome, live, v2 held-out family heldout_v2 (10 incidents)\n"
        "Left of the line: gpt-4.1-mini, 2 runs per arm. Right: claude-sonnet-4.6, 1 run.\n"
        "Rows: incident and its gold root-cause label. r1, r2: run 1, run 2.",
        loc="left",
        fontsize=11,
    )
    fig.subplots_adjust(left=0.33, right=0.99, top=0.85, bottom=0.25)
    fs.save(fig, out / "v2_incident_outcomes.png")


TRAJ = re.compile(r"sweep (\d+): relative residual ([0-9.e+-]+)")
END = re.compile(r"(?:converged|stopped) after (\d+) sweeps, relative residual ([0-9.e+-]+)")


def select_example() -> str:
    """First heldout_v2 incident, in run-id order, that the gpt-4.1-mini agent got right twice."""
    rows = [r for r in load("live_v2_gpt41mini") if r["arm"] == "agent"]
    for inc in sorted({r["run_id"] for r in rows}):
        if all(r["correct_outcome"] for r in rows if r["run_id"] == inc):
            return inc
    raise SystemExit("no incident meets the selection rule")


def trajectory(config: dict, inputs: dict[str, list[float]]) -> tuple[list, list, dict]:
    """Rerun the deterministic solver and read its progress log back."""
    lines: list[str] = []
    result = relax1d.run(dict(config), inputs, lines.append)
    xs, ys = [], []
    for line in lines:
        m = TRAJ.search(line) or END.search(line)
        if m:
            xs.append(int(m.group(1)))
            ys.append(float(m.group(2)))
    return xs, ys, result["checks"]


def example_incident(out: Path) -> None:
    inc_id = select_example()
    store = FixtureStore.load(ROOT / "tests" / "fixtures" / "incidents" / "heldout_v2")
    inc = store.get(inc_id)
    assert inc is not None and inc.template == "relax1d", "the plot below is written for relax1d"
    src = [float(v) for v in inc.inputs["primary.csv"].decode().split(",") if v.strip()]
    inputs = {"source_profile": src}
    journal = next(
        j for j in journals("live_v2_gpt41mini") if j["arm"] == "agent" and j["run_id"] == inc_id
    )
    repaired = dict(inc.config)
    for t in journal["journal"]:
        repaired[t["field"]] = t["new_value"] if t["kind"] == "apply" else t["old_value"]
    reference = dict(inc.config, n=41)  # the coarse grid named in the provenance note
    runs = [
        (f"reference: coarse grid n = 41, max_sweeps {reference['max_sweeps']}", reference,
         fs.BASELINE, "o"),
        (f"revision 0 (fault): n = 121, max_sweeps {inc.config['max_sweeps']}", inc.config,
         fs.OUTCOME["wrong"], "s"),
        (f"agent repair, run 1: max_sweeps {repaired['max_sweeps']}", repaired, fs.AGENT, "D"),
    ]  # fmt: skip
    fig, ax = plt.subplots(figsize=(fs.WIDTH, 6.6))
    for label, cfg, colour, marker in runs:
        xs, ys, checks = trajectory(cfg, inputs)
        failed = [k for k, v in checks.items() if not v]
        status = "all checks pass" if not failed else "fails " + ", ".join(failed)
        ax.plot(xs, ys, color=colour, marker=marker, markeredgecolor=fs.EDGE, lw=1.6,
                label=f"{label} ({status})")  # fmt: skip
    ax.axhline(inc.config["tol"], color=fs.EDGE, linestyle="--", linewidth=1)
    ax.text(ax.get_xlim()[1], inc.config["tol"], " tol", va="center", ha="left", fontsize=10)
    ax.set_yscale("log")
    ax.set_xlabel("Jacobi sweep")
    ax.set_ylabel("Relative residual (log scale)")
    ax.grid(True, axis="both")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=1, frameon=False)
    ax.set_title(
        f"Example incident {inc_id}: relaxation residual before the fault, after the fault\n"
        "and after the agent's repair (gpt-4.1-mini, v2 live run 1).\n"
        "Selection: first heldout_v2 incident in run-id order where the gpt-4.1-mini agent\n"
        "reached the correct final state in both runs. Recomputed by rerunning the\n"
        "deterministic solver on each configuration; points are its progress log lines.",
        loc="left",
        fontsize=11,
    )
    fig.subplots_adjust(left=0.1, right=0.94, top=0.76, bottom=0.3)
    fs.save(fig, out / "example_incident.png")


MARKER = {"live": "o", "live_v2_gpt41mini": "s", "live_v2_sonnet": "D"}
LABEL_OFFSET = {
    ("live_v2_gpt41mini", "agent"): (-9, 8, "right"),
    ("live_v2_gpt41mini", "agent_single_inspection"): (9, -12, "left"),
}


def cost_vs_outcome(out: Path) -> None:
    fig, ax = plt.subplots(figsize=(fs.WIDTH, 6.0))
    for name, _, _, second in ROUNDS:
        for arm, rs in by_arm(load(name)).items():
            if arm == "rule_table":
                continue
            k, n = sum(r["correct_outcome"] for r in rs), len(rs)
            usd = sum(r.get("reported_cost_usd") or 0.0 for r in rs) / n
            colour = fs.arm_colour(ARM_TYPE[arm])
            ax.scatter(
                usd,
                k / n,
                s=110,
                marker=MARKER[name],
                facecolor="white" if second else colour,
                edgecolor=colour if second else fs.EDGE,
                linewidth=2.2 if second else 1.0,
                zorder=3,
            )
            dx, dy, ha = LABEL_OFFSET.get((name, arm), (9, -4, "left"))
            ax.annotate(
                f"{ARM_LABEL[arm]} {k}/{n}",
                (usd, k / n),
                xytext=(dx, dy),
                textcoords="offset points",
                fontsize=10,
                ha=ha,
            )
    ax.set_xscale("log")
    ax.set_xlim(0.0003, 0.2)
    ax.set_ylim(0.4, 1.08)
    ax.set_xlabel("Provider-reported USD per episode (log scale)")
    ax.set_ylabel("Share with the correct final state")
    ax.grid(True, axis="both")
    rounds = [
        Line2D([], [], marker=MARKER[name], color="white", markeredgecolor=fs.EDGE,
               markerfacecolor="white" if second else fs.MUTED, markersize=9,
               label=title.replace("\n", ", "))
        for name, _, title, second in ROUNDS
    ]  # fmt: skip
    arms = [
        Patch(facecolor=fs.arm_colour(ARM_TYPE[a]), edgecolor=fs.EDGE, label=ARM_LABEL[a])
        for a in ARMS[1:]
    ]
    ax.legend(
        handles=rounds + arms,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.13),
        ncol=3,
        frameon=False,
    )
    ax.set_title(
        "Correct final state against cost per episode, model arms only\n"
        f"{SAMPLE.replace(' (hatched)', ' (white-filled markers)')}\n"
        "The rule table (no model, 0 USD) scored 18/20 in v1, 16/20 in v2 and 8/10 with the "
        "second model.",
        loc="left",
        fontsize=11,
    )
    fig.subplots_adjust(left=0.1, right=0.97, top=0.82, bottom=0.27)
    fs.save(fig, out / "cost_vs_outcome.png")


def main(argv: list[str] | None = None) -> list[Path]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "figures")
    args = parser.parse_args(argv)
    fs.apply()
    args.out.mkdir(parents=True, exist_ok=True)
    outcome_by_arm(args.out)
    root_cause_and_recovery(args.out)
    v2_incident_outcomes(args.out)
    example_incident(args.out)
    cost_vs_outcome(args.out)
    return [args.out / f for f in FIGURES]


if __name__ == "__main__":
    for p in main():
        print(f"wrote {p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else p}")
