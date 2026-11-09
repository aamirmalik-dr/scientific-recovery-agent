# agentcore changes

`src/scientific_recovery_agent/agentcore/` is vendored from evidence-ledger-agent at commit 45f6ff8 (agentcore 0.1.2).

Local changes: none. The files are byte-identical to that version. This project's needs (one-field patches, approvals, revisions, rollback, subprocess validation) all live in the project's own tools, which return agentcore's existing error codes (`precondition_failed`, `out_of_range`, `not_found`, `budget_exhausted`).
