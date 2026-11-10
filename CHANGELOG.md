# Changelog

All live results were produced through OpenRouter at temperature 0. Counts are episodes that reached the correct final state, on held-out incident families. Every version keeps the full history of saved outputs and transaction journals.

## 0.2.0 (2026-11-10)

v2 round, pre-registered in `docs/v2_preregistration.md`. Four changes target the v1 agent's failures:
- A `finish` that names a fault is refused until a repair is applied.
- The agent is told to keep going after a failed test and to read config notes.
- The readable config keys are listed.
- The validator reports the solver step limit.

Evaluation and results:
- New held-out family `heldout_v2` (10 incidents), written after the changes were committed.
- Live results with `openai/gpt-4.1-mini`, 10 incidents x 2 runs:
  - agent 15/20
  - agent with one log and one config read 15/20
  - single call 16/20
  - rule table 16/20
- Live results with `anthropic/claude-sonnet-4.6`, 1 run:
  - agent 10/10
  - single call 10/10
  - rule table 8/10
- Zero executed violations in v2.
- Live configs take the adapter retry count and backoff.

Figures:
- `scripts/make_figures.py` draws every figure from saved diagnosis results and journals.
  - Figure 1 panel d reruns the deterministic toy solver on three saved configurations, because residual trajectories are not saved.
- The current set:
  - Figure 1: rates by arm, paired difference against the single call, per-incident tiles, and the example incident h2-r04 as a semilog residual trace.
  - Figure S1: correct final state against cost.
  - Figure S2: v1 to v2 dumbbells.
  - All figures are exported as SVG and 300 dpi PNG.
  - Wilson intervals and a paired incident-level bootstrap.
  - Every plotted value is in `docs/figures/figure_stats.json`.
  - The typeface, Liberation Sans, is vendored under the SIL Open Font License.
- README changes:
  - "Main result" section, Statistical methods paragraph and a Mermaid architecture diagram.
  - Text corrections, with no result number changed:
    - The incident count is twenty-six since v2.
    - The cost ratio is stated as measured: 7.6 to 12.2 times.
- `tests/test_figures.py` checks that every figure is produced, stays within size limits and is reproducible.

## 0.1.0 (2026-11-09)

- Three original toy solvers.
- Read-only inspection tools, a static validator, a finite patch allowlist, dry-run tests on a copy, simulated approval, and applies with a revision check and rollback.
- Rule-table and single-call baselines, an ablation limited to one log read and one config read, rubric scoring and evidence reports.
- Fixtures are written with LF line endings on every platform.
- v1 live pilot with `openai/gpt-4.1-mini`, 10 held-out incidents x 2 runs:
  - rule table 18/20
  - single call 18/20
  - agent 10/20
  - one-read ablation 12/20
- Safety: no executed violations and no check weakening in any arm.
