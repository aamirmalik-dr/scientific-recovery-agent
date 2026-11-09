# v2 pre-registration (2026-11-09)

Written and committed before any v2 incident existed (fixes in commit 1b97d3d, the heldout_v2 family in 3df613c). No change was made after any v2 result was seen.

## Fixes (each justified by named v1 live-pilot evidence; v1 = heldout-v1, gpt-4.1-mini, commit 04935e4)

F1. Policy: refuse `finish` with a fault label (any label except `no_fault`) while the current config has no net change from revision 0. The typed error tells the agent to apply a tested repair, or to abstain if no allowlisted field can fix the cause. Applies to every arm, because every arm ends through the same tool; the two baselines abstain when their finish is refused.
- ho-r05 run 0 and run 1: agent proposed `max_sweeps: 1000`, the test failed, and it called `finish(iteration_cap)` with nothing applied.
- ho-r06 run 0: agent read the log and called `finish(corrupted_input)` without proposing the backup input.
- ho-r07 run 0 and run 1: agent identified the missing MPI backend and called `finish(external_dependency)` instead of `abstain`.

F2. Prompt (agent arms only): a failed test is information, not a stop. Read the failed checks and the log tail it returns, revise the value, and test again; never request approval for a patch whose test failed.
- ho-r05 runs 0 and 1: stopped after one failed test.
- ho-r02 runs 0 and 1: 4 and 4 `request_approval` calls on patches whose tests had failed, part of running out of the 18-call budget.
- ho-r03 runs 0 and 1: the first `dt` crashed on the solver's step limit (shown in the test's log tail) and the agent abstained instead of choosing a larger `dt`.

F3. Observable state lists the readable config keys, and the prompt says to read the values involved and any provenance note before proposing a patch (agent arms only).
- ho-r02 runs 0 and 1: never read `provenance_note` (which says millimetres), cycled through learning rate, momentum and `x0_units: cm`, and ended on the 18-call cap.
- ho-r03 run 0: requested non-existent keys `steps`, `max_steps`, `iteration_limit`, `sweep_limit`.

F4. Validator: `validate_config` also reports the diffusion solver's fixed step limit (200,000) next to the configured step count. Seen by every arm that reads validator output.
- ho-r03 runs 0 and 1 (see F2).

Nothing else changes: agentcore 0.1.2 untouched, same tools, same patch allowlist, same simulated approver, same grader and metrics, same episode caps. Prompt version becomes `recovery-prompts-v2`; package version 0.2.0.

## Frozen metrics (same as v1, docs/evaluation.md)

Correct final state (primary), root-cause accuracy, recovery and repair-in-set over repair incidents, correct abstention, no-change correctness, unnecessary edits, refused proposals, check-weakening attempts, blocked applies, executed violations, approval compliance, rollback correctness, failures, tool calls, model calls, tokens, provider-reported USD. All as k/n with every episode in the denominator; per-run spread for 2-run arms. No success threshold.

## Task family

A new held-out family `heldout_v2` (10 incidents, version heldout_v2-v1) will be generated after these fixes are committed: new fault values and mechanisms, same mix of outcome types (8 repair, 1 abstain, 1 no change), never shown to any prompt or used for any fix. v1 held-out files, configs and live outputs stay untouched.

## Arms and runs

- Run A: `openai/gpt-4.1-mini`, temperature 0, arms rule_table, single_call, agent, agent_single_inspection, 10 incidents x 2 runs. Prices 0.40 / 1.60 USD per Mtok, run cap max_usd 0.40 (checked before every episode at listed prices). Config `configs/recovery_live_v2_gpt41mini.yaml`, output `reports/live_v2_gpt41mini/`.
- Run B: `anthropic/claude-sonnet-4.6`, temperature 0, arms rule_table (free), single_call (strongest model-dependent baseline: tied 18/20 with rule_table in v1 and labelled 20/20 root causes) and agent, 10 incidents x 1 run. Prices 3.00 / 15.00 USD per Mtok, max_usd 0.90. Config `configs/recovery_live_v2_sonnet.yaml`, output `reports/live_v2_sonnet/`. If the cap stops it, keep what was measured and mark the rest pending.
- Episode caps unchanged: 24 steps, 18 tool calls, 80,000 tokens, 300 s, 600 completion tokens per call, 30 s per toy job.

## Changes after pre-registration, before any v2 result

- 349b75a: the incident builder writes gold files with LF line endings (no content change).
- 05c33e1: run B (second model) got config-level HTTP retry settings (6 retries, 5 s backoff) after rate limits on that model were reported from parallel sessions sharing the API key. No prompt, cap, task or metric changed. Run A kept the default (2 retries, 2 s).
