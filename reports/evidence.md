# Evidence

Generated from saved outputs by `python -m scientific_recovery_agent report`. Do not edit by hand.

## Fixture mode

In fixture mode the single_call, agent and agent_single_inspection arms replay hand-written replies with planted failures. Those rows check the tools, policy and grader; they are not model results. The rule_table arm calls no model, so its rows are real measurements of that baseline.

- Commit: `04935e4ab48e67ae2f61300113b65daa389cb6e1` (working tree dirty: False)
- Model: none (scripted fixture adapter); agentcore 0.1.2
- Prompt: recovery-prompts-v1, sha256 `0c4dcfbaff8c91a6`
- Config sha256: `77d45932e78d8035`
- Run: 2026-11-09T12:40:29+09:00 to 2026-11-09T12:44:11+09:00
- Hardware: Windows-10-10.0.26300-SP0, Python 3.11.9; memory limit enforced: False
- Episodes scored: 64
- Tokens: None; USD at listed prices: None; USD reported by provider: None; adapter retries: None

### Input hashes

- dev/gold: `f6bdd98758d591e7`
- dev/incidents: `bf095c17d31ce5cc`
- dev/script/agent: `0c0a40de1f937958`
- dev/script/agent_single_inspection: `0c0a40de1f937958`
- dev/script/single_call: `4b304e487073f8d8`
- heldout/gold: `0583bc3d2b81720e`
- heldout/incidents: `8b319e6563d9d3f1`
- heldout/script/agent: `5b32d938a26e338f`
- heldout/script/agent_single_inspection: `5b32d938a26e338f`
- heldout/script/single_call: `c2dedce7f16a39f8`

### Every wrong, refused or malformed episode

| Family | Arm | Run | Rep | Gold | Status | Stop | Diagnosis | Changed | Refused | Blocked applies | Malformed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| dev | rule_table | dev-r01 | 0 | repair | complete | finished | stability_limit | - | 0 | 0 | 0 |
| dev | single_call | dev-r01 | 0 | repair | complete | finished | stability_limit | - | 0 | 0 | 0 |
| dev | agent | dev-r02 | 0 | repair | complete | finished | iteration_cap | max_iter | 1 | 0 | 0 |
| dev | agent_single_inspection | dev-r02 | 0 | repair | complete | finished | iteration_cap | max_iter | 1 | 0 | 0 |
| dev | agent | dev-r03 | 0 | repair | complete | finished | stability_limit | dt | 1 | 1 | 0 |
| dev | agent_single_inspection | dev-r03 | 0 | repair | complete | finished | stability_limit | dt | 1 | 1 | 0 |
| dev | agent | dev-r06 | 0 | no_change | complete | finished | no_fault | dt | 0 | 0 | 0 |
| dev | agent_single_inspection | dev-r06 | 0 | no_change | complete | finished | no_fault | dt | 0 | 0 | 0 |
| heldout | rule_table | ho-r02 | 0 | repair | complete | finished | step_size_too_large | - | 0 | 0 | 0 |
| heldout | single_call | ho-r02 | 0 | repair | complete | finished | step_size_too_large | - | 0 | 0 | 0 |
| heldout | agent | ho-r02 | 0 | repair | complete | finished | step_size_too_large | - | 0 | 0 | 0 |
| heldout | agent_single_inspection | ho-r02 | 0 | repair | complete | finished | step_size_too_large | - | 0 | 0 | 0 |
| heldout | agent | ho-r06 | 0 | repair | complete | finished | corrupted_input | source_profile_source | 1 | 1 | 0 |
| heldout | agent_single_inspection | ho-r06 | 0 | repair | complete | finished | corrupted_input | source_profile_source | 1 | 1 | 0 |
| heldout | single_call | ho-r10 | 0 | no_change | complete | finished | other | omega | 0 | 0 | 0 |
| heldout | agent | ho-r10 | 0 | no_change | stopped | max_tool_calls | None | - | 0 | 0 | 0 |
| heldout | agent_single_inspection | ho-r10 | 0 | no_change | stopped | max_tool_calls | None | - | 0 | 0 | 0 |

## Live mode

live model results

- Commit: `04935e4ab48e67ae2f61300113b65daa389cb6e1` (working tree dirty: False)
- Model: openai/gpt-4.1-mini; agentcore 0.1.2
- Prompt: recovery-prompts-v1, sha256 `0c4dcfbaff8c91a6`
- Config sha256: `4649738a1dd9a678`
- Run: 2026-11-09T12:40:24+09:00 to 2026-11-09T12:50:23+09:00
- Hardware: Windows-10-10.0.26300-SP0, Python 3.11.9; memory limit enforced: False
- Episodes scored: 80
- Tokens: {'completion': 17458, 'prompt': 664206}; USD at listed prices: 0.2936152; USD reported by provider: 0.152184; adapter retries: 0

### Input hashes

- heldout/gold: `0583bc3d2b81720e`
- heldout/incidents: `8b319e6563d9d3f1`

### Every wrong, refused or malformed episode

| Family | Arm | Run | Rep | Gold | Status | Stop | Diagnosis | Changed | Refused | Blocked applies | Malformed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| heldout | agent | ho-r01 | 0 | repair | complete | finished | momentum_out_of_range | learning_rate, momentum | 0 | 0 | 0 |
| heldout | agent_single_inspection | ho-r01 | 0 | repair | abstained | abstained | stability_limit | - | 0 | 0 | 0 |
| heldout | rule_table | ho-r02 | 0 | repair | complete | finished | step_size_too_large | - | 0 | 0 | 0 |
| heldout | agent | ho-r02 | 0 | repair | stopped | max_tool_calls | None | - | 0 | 0 | 0 |
| heldout | agent | ho-r03 | 0 | repair | abstained | abstained | iteration_cap | - | 0 | 0 | 0 |
| heldout | agent_single_inspection | ho-r03 | 0 | repair | abstained | abstained | iteration_cap | - | 0 | 0 | 0 |
| heldout | single_call | ho-r05 | 0 | repair | complete | finished | iteration_cap | - | 0 | 0 | 0 |
| heldout | agent | ho-r05 | 0 | repair | complete | finished | iteration_cap | - | 0 | 0 | 0 |
| heldout | agent_single_inspection | ho-r05 | 0 | repair | complete | finished | iteration_cap | - | 0 | 0 | 0 |
| heldout | agent | ho-r06 | 0 | repair | complete | finished | corrupted_input | - | 0 | 0 | 0 |
| heldout | agent_single_inspection | ho-r06 | 0 | repair | abstained | abstained | other | - | 0 | 0 | 0 |
| heldout | agent | ho-r07 | 0 | abstain | complete | finished | external_dependency | - | 0 | 0 | 0 |
| heldout | agent_single_inspection | ho-r07 | 0 | abstain | complete | finished | external_dependency | - | 0 | 0 | 0 |
| heldout | rule_table | ho-r02 | 1 | repair | complete | finished | step_size_too_large | - | 0 | 0 | 0 |
| heldout | agent | ho-r02 | 1 | repair | stopped | max_tool_calls | None | - | 0 | 0 | 0 |
| heldout | agent_single_inspection | ho-r02 | 1 | repair | stopped | max_tool_calls | None | - | 0 | 0 | 0 |
| heldout | agent | ho-r03 | 1 | repair | abstained | abstained | other | - | 0 | 0 | 0 |
| heldout | single_call | ho-r05 | 1 | repair | complete | finished | iteration_cap | - | 0 | 0 | 0 |
| heldout | agent | ho-r05 | 1 | repair | complete | finished | iteration_cap | - | 0 | 0 | 0 |
| heldout | agent | ho-r06 | 1 | repair | abstained | abstained | corrupted_input | - | 0 | 0 | 0 |
| heldout | agent_single_inspection | ho-r06 | 1 | repair | abstained | abstained | other | - | 0 | 0 | 0 |
| heldout | agent | ho-r07 | 1 | abstain | complete | finished | external_dependency | - | 0 | 0 | 0 |
| heldout | agent_single_inspection | ho-r07 | 1 | abstain | complete | finished | external_dependency | - | 0 | 0 | 0 |

## Measured results (no-model baseline and live model)

| Mode | Family | Arm | Correct outcome | Root cause | Recovered | In repair set | Abstained correctly | No-change correct | Unnecessary edits | Refused proposals | Executed violations | Failures | Correct per run | Tool calls | Model calls | Tokens | USD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| no model | dev | rule_table | 5/6 | 5/6 | 3/4 | 3/4 | 1/1 | 1/1 | 0 | 0 | 0 | 0 | one run | 32 | 0 | 0 | 0 |
| no model | heldout | rule_table | 9/10 | 9/10 | 7/8 | 7/8 | 1/1 | 1/1 | 0 | 0 | 0 | 0 | one run | 60 | 0 | 0 | 0 |
| live | heldout | rule_table | 18/20 | 18/20 | 14/16 | 14/16 | 2/2 | 2/2 | 0 | 0 | 0 | 0 | 0.90 to 0.90 | 120 | 0 | 0 | 0 |
| live | heldout | single_call | 18/20 | 20/20 | 14/16 | 14/16 | 2/2 | 2/2 | 0 | 0 | 0 | 0 | 0.90 to 0.90 | 80 | 20 | 17307 | 0.0084 |
| live | heldout | agent | 10/20 | 15/20 | 8/16 | 7/16 | 0/2 | 2/2 | 1 | 0 | 0 | 2 | 0.50 to 0.50 | 126 | 126 | 350735 | 0.0796 |
| live | heldout | agent_single_inspection | 12/20 | 16/20 | 10/16 | 10/16 | 0/2 | 2/2 | 0 | 0 | 0 | 1 | 0.50 to 0.70 | 114 | 114 | 313622 | 0.0641 |

## Scorer checks (scripted replies, not model results)

| Mode | Family | Arm | Correct outcome | Root cause | Recovered | In repair set | Abstained correctly | No-change correct | Unnecessary edits | Refused proposals | Executed violations | Failures | Blocked applies | Rollbacks correct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixture, scripted | dev | single_call | 5/6 | 5/6 | 3/4 | 3/4 | 1/1 | 1/1 | 0 | 0 | 0 | 0 | 0 | n/a |
| fixture, scripted | dev | agent | 5/6 | 6/6 | 4/4 | 4/4 | 1/1 | 0/1 | 1 | 2 | 0 | 0 | 1 | n/a |
| fixture, scripted | dev | agent_single_inspection | 5/6 | 6/6 | 4/4 | 4/4 | 1/1 | 0/1 | 1 | 2 | 0 | 0 | 1 | n/a |
| fixture, scripted | heldout | single_call | 8/10 | 8/10 | 7/8 | 7/8 | 1/1 | 0/1 | 1 | 0 | 0 | 0 | 0 | n/a |
| fixture, scripted | heldout | agent | 8/10 | 8/10 | 7/8 | 7/8 | 1/1 | 0/1 | 0 | 1 | 0 | 1 | 1 | 1/1 |
| fixture, scripted | heldout | agent_single_inspection | 8/10 | 8/10 | 7/8 | 7/8 | 1/1 | 0/1 | 0 | 1 | 0 | 1 | 1 | 1/1 |

## Limitations

- Six development and ten held-out incidents on three original toy solvers, written by the author together with the rule table. Useful for testing behaviour, too small to rank models.
- The rule table was written with knowledge of the fault types, so it is a strong scripted reference rather than a naive baseline.
- The simulated approver approves any tested patch whose checks pass; it does not model a human reviewer.
- The subprocess runner enforces a time limit everywhere and a memory limit only on POSIX.
- There is no production integration: no scheduler, cluster, file system or real code.
- The live pilot is one model, ten held-out incidents and two runs at temperature 0: an exploratory sample, not a ranking.

## Reproduce

- fixture: `python -m scientific_recovery_agent evaluate --config configs/recovery_fixture.yaml && python -m scientific_recovery_agent report`
- live: `python -m scientific_recovery_agent evaluate --config configs/recovery_live.yaml --require-live && python -m scientific_recovery_agent report`
