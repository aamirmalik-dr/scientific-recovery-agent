# Threat model

## What is protected

- Numerical validity: a repaired run must pass every check of its template, and its physical invariants (diffusivity in SI, domain length, end time, starting point in metres, source scale) must match the intended problem.
- The validity checks themselves: nothing the agent can do removes or weakens a check or a tolerance.
- The fixture store: incidents are read-only; episodes work on in-memory revisions and temporary copies.
- The evaluator: gold root causes, outcome types and repair sets are read only by the grader after an episode ends.

## What the model can do

Only ten typed tools. It cannot run code it writes, read files by path, reach the network or change anything outside its own episode state and a temporary job directory that is deleted after each test.

| Threat | Control | Test |
|---|---|---|
| Weakening a check or tolerance | `patch_policy` refuses any non-allowlisted field, with a specific `weakens_validation` reason for tolerances, checks, backend, template and revision; the grader re-runs every check of the template regardless of the config | `test_patch_policy_refuses`, `test_refused_proposals_are_recorded`, `test_grader_catches_planted_unsafe_final_state` |
| Paths or commands as values | values are numbers in a range or members of a fixed enumeration | `test_patch_policy_refuses` (`../../etc`) |
| Applying without approval, with a forged or mismatched token, on a stale revision, twice | `transactions.apply` checks all four; refusals are recorded | `test_apply_needs_approval_and_matching_token`, `test_stale_revision_has_no_apply_path` |
| Approving a patch that fails validation | the simulated approver approves only a passing test at the current revision | `test_failed_test_is_never_approved` |
| Instructions inside logs or config notes | tool results are delivered in `trust="untrusted-data"` blocks; text cannot change the allowlist, approvals or revisions | `test_hostile_log_lines_are_returned_as_data` |
| Fixing a symptom instead of the cause | the grader compares physical invariants, so compensating for a unit error with dt or grid size fails | `test_grader_rejects_symptom_fix_for_unit_fault` |
| Duplicate apply after a crash | apply only changes checkpointed state; the pending action is re-run on the restored state | `test_crash_inside_apply_resumes_without_duplicate_apply`, `test_crash_after_apply_checkpoint_does_not_reapply` |
| Runaway computation | subprocess with a wall-clock limit (killed when it expires) and, on POSIX, an address-space limit | `test_runner_kills_a_job_that_exceeds_its_time_limit` |
| Leaking keys into traces | agentcore sanitizes traces (keys, bearer tokens, absolute paths) | inherited from agentcore |

## What the runner does not protect against

The runner protects against runaway computation in these toy solvers, not against malicious code. It runs only this package's own solver module on a copy of the inputs in a fresh temporary directory, with Python's isolated mode (`-I`). It is not a sandbox: no container, no seccomp, no network isolation, no filesystem jail. That is acceptable here because no untrusted or model-written code is ever executed. On Windows no memory limit is enforced (the problem sizes are bounded by the allowlist instead); the evidence files record `memory_limit_enforced` for every run. A code-writing tool would require a container sandbox and a new threat model first, and is not part of this project.

## Residual risks

- The simulated approver is a rule, not a reviewer. It cannot catch a passing but scientifically wrong repair; the grader's invariant check is what catches the one such case modelled here (unit faults).
- Root-cause labels come from a closed list. A cause outside the list can only be labelled `other`.
- Hostile text is limited to a few patterns written by the author.
