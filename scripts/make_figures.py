"""Draw the README figures from saved run outputs only.

Reads reports/live (v1, gpt-4.1-mini), reports/live_v2_gpt41mini (v2,
gpt-4.1-mini) and reports/live_v2_sonnet (v2, second model):
diagnosis_results.jsonl and transaction_journals.jsonl. Writes each figure to
docs/figures/ as SVG and as a 300 dpi PNG, plus figure_stats.json with every
plotted value and interval. No model is called and nothing is estimated.

Panel d of Figure 1 also reruns the deterministic toy solver on three
configurations of the selected incident (revision 0, the agent's saved final
revision and the coarse-grid reference named in the incident's provenance
note) to recover the residual trajectory, which the evaluation does not save.
Running this script twice gives byte-identical files.

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
import numpy as np  # noqa: E402
from matplotlib.ticker import LogLocator, MultipleLocator, NullFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from scientific_recovery_agent.fixture_store import FixtureStore  # noqa: E402
from scientific_recovery_agent.toy_jobs import relax1d  # noqa: E402

# (output dir, short label, long label, second model)
CONDITIONS = [
    ("live", "v1", "v1, gpt-4.1-mini", False),
    ("live_v2_gpt41mini", "v2", "v2, gpt-4.1-mini", False),
    ("live_v2_sonnet", "v2, Sonnet", "v2, claude-sonnet-4.6", True),
]
ARMS = ["rule_table", "single_call", "agent", "agent_single_inspection"]
ARM_TYPE = {
    "rule_table": "baseline",
    "single_call": "single",
    "agent": "agent",
    "agent_single_inspection": "ablation",
}
ARM_NAME = {
    "rule_table": "Rule table (no model)",
    "single_call": "Single call",
    "agent": "Agent",
    "agent_single_inspection": "Agent, one read",
}
STEMS = ["fig1_main", "figS1_cost_vs_outcome", "figS2_v1_to_v2"]
CLASSES = [
    ("correct", "Correct final state", "C"),
    ("wrong", "Wrong final state", "W"),
    ("abstained", "Abstained, repair expected", "A"),
    ("failed", "Stopped on the 18-call cap", "F"),
]
STATS: dict[str, dict] = {}


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


def classify(r: dict) -> str:
    if r["correct_outcome"]:
        return "correct"
    if r["status"] == "abstained":
        return "abstained"
    if r["status"] in ("stopped", "failed"):
        return "failed"
    return "wrong"


def rate(rows: list[dict], key: str, tag: str, den: str | None = None) -> tuple:
    k = sum(int(r[key]) for r in rows if (r[den] if den else True))
    n = sum(1 for r in rows if (r[den] if den else True))
    p, lo, hi = fs.wilson(k, n)
    STATS[tag] = {"k": k, "n": n, "rate": p, "wilson95": [lo, hi]}
    return p, lo, hi, k, n


def per_task(rows: list[dict], key: str) -> dict[str, float]:
    acc: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        acc[r["run_id"]].append(float(r[key] or 0.0))
    return {t: float(np.mean(v)) for t, v in acc.items()}


def paired(rows_a: list[dict], rows_b: list[dict], key: str, tag: str) -> tuple:
    a, b = per_task(rows_a, key), per_task(rows_b, key)
    tasks = sorted(set(a) & set(b))
    m, lo, hi = fs.paired_bootstrap([a[t] for t in tasks], [b[t] for t in tasks])
    STATS[tag] = {"mean_difference": m, "bootstrap95": [lo, hi], "n_tasks": len(tasks)}
    return m, lo, hi, len(tasks)


def unit_x(ax, step: float = 0.5) -> None:
    ticks = list(np.arange(0, 1 + 1e-9, step))
    ax.set_xlim(-0.04, 1.04)
    ax.spines["bottom"].set_bounds(0, 1)
    ax.set_xticks(ticks)
    ax.xaxis.set_minor_locator(MultipleLocator(0.1))
    fs.tidy_ticks(ax, "x")


def arm_rows() -> list[tuple[float, str, str, bool, str]]:
    """Row positions for arm x condition dot plots: (y, arm, cond, second, sublabel)."""
    rows, y = [], 0.0
    for arm in ARMS:
        for name, short, _, second in CONDITIONS:
            rows.append((y, arm, name, second, short))
            y += 1
        y += 0.6
    return rows


# Figure 1 -------------------------------------------------------------------


def panel_rates(fig, data, top: float) -> None:
    metrics = [
        ("correct_outcome", None, "Correct final state"),
        ("diagnosis_correct", None, "Root-cause label correct"),
        ("recovered", "is_repair", "Recovered with\ninvariants kept"),
    ]
    rows = arm_rows()
    height = (rows[-1][0] + 1) * 3.1
    left0, width, gap = 37.0, 23.0, 3.5
    for j, (key, den, title) in enumerate(metrics):
        ax = fs.axes_mm(fig, left0 + j * (width + gap), top, width, height)
        for y, arm, name, second, _ in rows:
            if arm not in data[name]:
                ax.text(0.5, y, "not run", ha="center", va="center", color=fs.MUTED)
                continue
            p, lo, hi, _, _ = rate(data[name][arm], key, f"{key}/{name}/{arm}", den)
            fs.dot_interval(ax, y, p, lo, hi, ARM_TYPE[arm], second)
        unit_x(ax)
        ax.set_ylim(rows[-1][0] + 0.6, -0.6)
        ax.set_yticks([r[0] for r in rows])
        if j == 0:
            ax.set_yticklabels([r[4] for r in rows])
            for arm in ARMS:
                ys = [r[0] for r in rows if r[1] == arm]
                ax.text(
                    -0.62,
                    (ys[0] + ys[-1]) / 2,
                    ARM_NAME[arm].replace(" (", "\n("),
                    ha="right",
                    va="center",
                    transform=ax.get_yaxis_transform(),
                )
        else:
            ax.set_yticklabels([])
        ax.set_title(title, fontsize=7)
        if j == 1:
            ax.set_xlabel("Fraction of episodes")
    fs.panel_label(fig, "a", 1.5, top - 6.0)


def panel_forest(fig, data, top: float) -> None:
    rows = []
    for name, _, label, second in CONDITIONS:
        for arm in ("agent", "agent_single_inspection"):
            if arm in data[name]:
                m, lo, hi, n = paired(
                    data[name][arm],
                    data[name]["single_call"],
                    "correct_outcome",
                    f"paired_vs_single_call/{name}/{arm}",
                )
                rows.append((f"{ARM_NAME[arm]}\n{label}", arm, second, m, lo, hi))
        paired(
            data[name]["agent"],
            data[name]["rule_table"],
            "correct_outcome",
            f"paired_vs_rule_table/{name}/agent",
        )
    ax = fs.axes_mm(fig, 141.0, top, 34.0, 38.0)
    for i, (_, arm, second, m, lo, hi) in enumerate(rows):
        fs.dot_interval(ax, i, m, lo, hi, ARM_TYPE[arm], second)
    fs.ref_line(ax, 0.0, "x")
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.set_ylim(len(rows) - 0.5, -1.1)
    ax.set_xlim(-0.78, 0.32)
    ax.spines["bottom"].set_bounds(-0.75, 0.3)
    ax.set_xticks([-0.75, -0.5, -0.25, 0, 0.25])
    ax.xaxis.set_minor_locator(MultipleLocator(0.05))
    fs.tidy_ticks(ax, "x")
    ax.set_xlabel("Paired difference vs single call\n(correct final state, fraction)")
    ax.text(-0.02, -0.95, "single call better", ha="right", va="center", color=fs.MUTED)
    ax.text(0.02, -0.95, "agent better", ha="left", va="center", color=fs.MUTED)
    fs.panel_label(fig, "b", 118.0, top - 6.0)


def panel_tiles(fig, data, top: float) -> None:
    cols = []
    for name, _, label, _second in CONDITIONS[1:]:
        model = label.split(", ")[1]
        for arm in ARMS:
            for run in sorted({r["run"] for r in data[name].get(arm, [])}):
                rs = {r["run_id"]: r for r in data[name][arm] if r["run"] == run}
                cols.append((f"{ARM_NAME[arm]}, run {run + 1}", (arm, model), rs))
    incs = sorted({q for *_, rs in cols for q in rs})
    pairs: dict[tuple, list[dict]] = defaultdict(list)
    for _, key, rs in cols:
        pairs[key].append(rs)
    ease = {
        q: float(np.mean([np.mean([rs[q]["correct_outcome"] for rs in v]) for v in pairs.values()]))
        for q in incs
    }
    incs.sort(key=lambda q: (-ease[q], q))
    tile_w, tile_h, head = 4.3, 3.1, 3.6
    left, marg_h = 37.0, 7.0
    n_mini = sum(1 for c in cols if c[1][1] == "gpt-4.1-mini")
    grid_h = len(cols) * tile_h + 2 * head
    width = len(incs) * tile_w
    ax = fs.axes_mm(fig, left, top + marg_h + 0.8, width, grid_h)
    fs.bare(ax)
    ys = []
    for i, (_, _, rs) in enumerate(cols):
        y0 = i * tile_h + (2 * head if i >= n_mini else head)
        ys.append(y0 + tile_h / 2)
        for j, q in enumerate(incs):
            key = classify(rs[q])
            ax.add_patch(
                fs.plt.Rectangle(
                    (j * tile_w, y0),
                    tile_w,
                    tile_h,
                    facecolor=fs.OUTCOME[key],
                    edgecolor="white",
                    linewidth=0.6,
                )
            )
            code = next(c for k, _, c in CLASSES if k == key)
            ax.text(
                j * tile_w + tile_w / 2,
                y0 + tile_h / 2 + 0.05,
                code,
                ha="center",
                va="center",
                color=fs.OUTCOME_TEXT[key],
            )
    for txt, y in (
        ("gpt-4.1-mini, 2 runs per arm", head * 0.55),
        ("claude-sonnet-4.6, 1 run per arm", n_mini * tile_h + head * 1.55),
    ):
        ax.text(0, y, txt, ha="left", va="center", color=fs.MUTED)
    ax.set_xlim(0, width)
    ax.set_ylim(grid_h, 0)
    ax.set_yticks(ys, [c[0] for c in cols])
    ax.set_xticks([(j + 0.5) * tile_w for j in range(len(incs))], [q[3:] for q in incs])
    ax.set_xlabel("Held-out v2 incident, easiest to hardest")
    mx = fs.axes_mm(fig, left, top, width, marg_h)
    mx.bar(
        [(j + 0.5) * tile_w for j in range(len(incs))],
        [ease[q] for q in incs],
        width=tile_w * 0.7,
        color=fs.MUTED,
        linewidth=0,
    )
    mx.set_xlim(0, width)
    mx.set_ylim(0, 1)
    mx.set_yticks([0, 1])
    fs.tidy_ticks(mx, "y")
    mx.set_xticks([])
    mx.spines["bottom"].set_visible(False)
    mx.set_ylabel("Correct\n(mean of 7 arms)", rotation=0, ha="right", va="center", labelpad=4)
    key = fs.axes_mm(fig, 2.0, top + marg_h + grid_h + 12.5, 95.0, 7.0)
    key.set_axis_off()
    key.legend(
        handles=fs.outcome_handles(
            [
                (k, f"{c}  {lab}")
                for k, lab, c in CLASSES
                if any(classify(rs[q]) == k for *_, rs in cols for q in incs)
            ]
        ),
        loc="center left",
        ncol=2,
        handlelength=1.0,
        columnspacing=1.2,
    )
    fs.panel_label(fig, "c", 1.5, top - 2.5)


TRAJ = re.compile(r"sweep (\d+): relative residual ([0-9.e+-]+)")
END = re.compile(r"(?:converged|stopped) after (\d+) sweeps, relative residual ([0-9.e+-]+)")


def select_example(data) -> str:
    """First heldout_v2 incident, in run-id order, that the gpt-4.1-mini agent got right twice."""
    rows = data["live_v2_gpt41mini"]["agent"]
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


def panel_example(fig, data, top: float) -> None:
    inc_id = select_example(data)
    store = FixtureStore.load(ROOT / "tests" / "fixtures" / "incidents" / "heldout_v2")
    inc = store.get(inc_id)
    assert inc is not None and inc.template == "relax1d", "panel d is written for relax1d"
    src = [float(v) for v in inc.inputs["primary.csv"].decode().split(",") if v.strip()]
    inputs = {"source_profile": src}
    journal = next(
        j for j in journals("live_v2_gpt41mini") if j["arm"] == "agent" and j["run_id"] == inc_id
    )
    repaired = dict(inc.config)
    for t in journal["journal"]:
        repaired[t["field"]] = t["new_value"] if t["kind"] == "apply" else t["old_value"]
    reference = dict(inc.config, n=41)  # the coarse grid named in the provenance note
    ax = fs.axes_mm(fig, 125.0, top + 1.0, 52.0, 44.0)
    # (label, config, colour, marker, label position in data units, alignment)
    lab_ref = "Reference\n(n = 41)"
    lab_rep = "Agent repair\n(sweep cap raised)"
    lab_rev = "Revision 0 (n = 121),\nstops at the cap"
    runs = [
        (lab_ref, reference, fs.MUTED, "o", (7.0, 2e-5), "left"),
        (lab_rep, repaired, fs.AGENT, "D", (27.0, 2e-2), "left"),
        (lab_rev, inc.config, fs.INK, "s", (22.0, 0.3), "left"),
    ]
    info = {}
    for label, cfg, colour, marker, (lx, ly), ha in runs:
        xs, ys, checks = trajectory(cfg, inputs)
        x = np.asarray(xs) / 1000
        y = np.asarray(ys)
        last = x == x[-1]
        if cfg is repaired:
            # the repaired run follows revision 0's trajectory up to the old cap; draw it from there
            keep = x >= inc.config["max_sweeps"] / 1000
            x, y = x[keep], y[keep]
            last = last[keep]
        ax.plot(x, y, color=colour, linewidth=1.0, zorder=2)
        ax.plot(
            x[~last],
            y[~last],
            linestyle="none",
            marker=marker,
            markersize=2.4,
            markerfacecolor=colour,
            markeredgecolor=colour,
            zorder=3,
        )
        failed = sorted(k for k, v in checks.items() if not v)
        info[label.replace("\n", " ")] = {
            "sweeps": xs[-1],
            "final_residual": ys[-1],
            "failed_checks": failed,
        }
        ax.plot(
            [x[-1]],
            [y[-1]],
            linestyle="none",
            marker="X" if failed else "o",
            markersize=5.5,
            markerfacecolor=colour if failed else "white",
            markeredgecolor=colour,
            markeredgewidth=1.0,
            zorder=6,
            clip_on=False,
        )
        ax.text(lx, ly, label, ha=ha, va="center", color=colour)
    STATS[f"example_incident/{inc_id}"] = {
        "selection": "first heldout_v2 incident in run-id order with the gpt-4.1-mini agent "
        "correct in both runs",
        "tol": inc.config["tol"],
        "max_sweeps_revision0": inc.config["max_sweeps"],
        "max_sweeps_repaired": repaired["max_sweeps"],
        "runs": info,
    }
    tol = inc.config["tol"]
    ax.axhline(tol, color=fs.INK, linewidth=0.6, linestyle=(0, (1, 1.5)), zorder=1)
    cap = inc.config["max_sweeps"] / 1000
    ax.axvline(cap, color=fs.MUTED, linewidth=0.6, linestyle=(0, (1, 1.5)), zorder=1)
    ax.set_yscale("log")
    ax.set_ylim(5e-7, 1.0)
    ax.yaxis.set_major_locator(LogLocator(base=10, numticks=12))
    ax.yaxis.set_minor_locator(LogLocator(base=10, subs=np.arange(2, 10) * 0.1, numticks=12))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xlim(0, None)
    ax.set_xlabel("Jacobi sweep (thousands)")
    ax.set_ylabel("Relative residual")
    ax.text(7.0, tol * 1.4, "tolerance", ha="left", va="bottom", color=fs.INK)
    ax.text(cap + 0.6, 2.5e-6, "revision 0\nsweep cap", ha="left", va="bottom", color=fs.MUTED)
    fs.panel_label(fig, "d", 108.0, top - 8.5)


def figure1(data, out: Path) -> list[Path]:
    fig = fs.figure(fs.FULL_WIDTH, 142)
    panel_rates(fig, data, top=9.0)
    panel_forest(fig, data, top=9.0)
    panel_tiles(fig, data, top=68.0)
    panel_example(fig, data, top=74.0)
    return fs.save(fig, out, "fig1_main")


# Supplementary --------------------------------------------------------------


def figure_s1(data, out: Path) -> list[Path]:
    fig = fs.figure(fs.FULL_WIDTH, 62)
    for j, (name, _, label, second) in enumerate(CONDITIONS):
        ax = fs.axes_mm(fig, 16 + j * 58, 10, 44, 38)
        handles = []
        markers = []
        for arm in ("single_call", "agent_single_inspection", "agent"):
            if arm not in data[name]:
                ax.text(
                    0.97,
                    0.03,
                    f"{ARM_NAME[arm]}: not run",
                    transform=ax.transAxes,
                    ha="right",
                    va="bottom",
                    color=fs.MUTED,
                )
                continue
            rs = data[name][arm]
            y, ylo, yhi, _, _ = rate(rs, "correct_outcome", f"correct_outcome/{name}/{arm}")
            cost = per_task(rs, "reported_cost_usd")
            tasks = sorted(cost)
            c, clo, chi = fs.paired_bootstrap([cost[t] for t in tasks], [0.0] * len(tasks))
            STATS[f"usd_per_episode/{name}/{arm}"] = {
                "mean": c,
                "bootstrap95": [clo, chi],
                "n_tasks": len(tasks),
            }
            t = ARM_TYPE[arm]
            ax.plot([clo, chi], [y, y], **fs.line_kw(t, second, width=0.8))
            ax.plot([c, c], [ylo, yhi], **fs.line_kw(t, second, width=0.8))
            markers.append((c, y, t))
        # markers after every interval; the larger ablation triangle above the agent diamond
        for c, y, t in sorted(markers, key=lambda m: ["single", "agent", "ablation"].index(m[2])):
            size = 3.0 if (t == "agent" and name == "live_v2_gpt41mini") else None
            ax.plot(
                [c], [y], **{**fs.marker_kw(t, second, size=size), "clip_on": False, "zorder": 4}
            )
        for arm in ("single_call", "agent", "agent_single_inspection"):
            if arm in data[name]:
                handles += fs.arm_handles([(ARM_NAME[arm], ARM_TYPE[arm], second)])
        ax.set_xscale("log")
        ax.set_xlim(2e-4, 0.2)
        ax.set_ylim(-0.02, 1.04)
        ax.spines["left"].set_bounds(0, 1)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1])
        fs.tidy_ticks(ax, "y")
        ax.set_xlabel("Provider-reported USD per episode")
        if j == 0:
            ax.set_ylabel("Correct final state (fraction)")
        else:
            ax.set_yticklabels([])
        ax.legend(handles=handles, loc="lower left")
        ax.set_title(label.replace(", ", "\n"))
        fs.panel_label(fig, "abc"[j], 1.5 if j == 0 else 9.0 + j * 58, 2.0)
    return fs.save(fig, out, "figS1_cost_vs_outcome")


def figure_s2(data, out: Path) -> list[Path]:
    fig = fs.figure(fs.FULL_WIDTH, 52)
    metrics = [
        ("correct_outcome", "Correct final state (fraction)"),
        ("diagnosis_correct", "Root-cause label correct (fraction)"),
    ]
    for j, (key, xlabel) in enumerate(metrics):
        ax = fs.axes_mm(fig, 32 + j * 80, 8, 52, 30)
        for i, arm in enumerate(ARMS):
            t = ARM_TYPE[arm]
            p1, lo1, hi1, _, _ = rate(data["live"][arm], key, f"{key}/live/{arm}")
            p2, lo2, hi2, _, _ = rate(
                data["live_v2_gpt41mini"][arm], key, f"{key}/live_v2_gpt41mini/{arm}"
            )
            y1, y2 = i - 0.17, i + 0.17
            ax.plot(
                [p1, p2], [y1, y2], color=fs.CONTEXT, linewidth=1.6, zorder=1, solid_capstyle="butt"
            )
            ax.plot([lo1, hi1], [y1, y1], color=fs.MUTED, linewidth=0.7, zorder=2)
            ax.plot([lo2, hi2], [y2, y2], **fs.line_kw(t, width=0.7))
            grey = fs.marker_kw(t)
            grey.update(markerfacecolor=fs.CONTEXT, markeredgecolor=fs.MUTED)
            ax.plot([p1], [y1], **{**grey, "clip_on": False})
            ax.plot([p2], [y2], **{**fs.marker_kw(t), "clip_on": False})
            k1 = STATS[f"{key}/live/{arm}"]["k"]
            k2 = STATS[f"{key}/live_v2_gpt41mini/{arm}"]["k"]
            ax.text(
                1.04,
                i,
                f"{k1} to {k2}",
                transform=ax.get_yaxis_transform(),
                va="center",
                ha="left",
                color=fs.MUTED,
            )
        ax.text(
            1.04,
            -0.75,
            "of 20",
            transform=ax.get_yaxis_transform(),
            va="center",
            ha="left",
            color=fs.MUTED,
        )
        ax.set_yticks(range(len(ARMS)), [ARM_NAME[a] for a in ARMS] if j == 0 else [])
        ax.set_ylim(len(ARMS) - 0.5, -0.95)
        unit_x(ax, 0.25)
        ax.set_xlabel(xlabel)
        fs.panel_label(fig, "ab"[j], 1.5 if j == 0 else 104.0, 2.0)
    fig.text(
        32 / fs.FULL_WIDTH,
        1 - 47 / 52,
        "gpt-4.1-mini (the rule table calls no model). Upper line and grey marker: v1. "
        "Lower line, arm colour: v2.",
        ha="left",
        va="center",
        color=fs.MUTED,
    )
    return fs.save(fig, out, "figS2_v1_to_v2")


def main(argv: list[str] | None = None) -> list[Path]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "figures")
    args = parser.parse_args(argv)
    fs.apply()
    data = {name: by_arm(load(name)) for name, *_ in CONDITIONS}
    paths = figure1(data, args.out)
    paths += figure_s1(data, args.out)
    paths += figure_s2(data, args.out)
    stats = args.out / "figure_stats.json"

    def rnd(v):
        if isinstance(v, float):
            return round(v, 6)
        if isinstance(v, list):
            return [rnd(x) for x in v]
        if isinstance(v, dict):
            return {k: rnd(x) for k, x in v.items()}
        return v

    meta = {
        "interval": "Wilson 95% for rates; percentile bootstrap 95% over incidents for "
        "paired differences and mean cost",
        "bootstrap_resamples": fs.N_BOOT,
        "seed": fs.SEED,
        "resampling_unit": "incident",
    }
    text = json.dumps({"method": meta, "values": rnd(dict(sorted(STATS.items())))}, indent=1)
    stats.write_text(text + "\n", encoding="utf-8", newline="\n")
    return paths + [stats]


if __name__ == "__main__":
    for p in main():
        print(f"wrote {p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else p}")
