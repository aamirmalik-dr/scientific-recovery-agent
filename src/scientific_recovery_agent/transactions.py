"""Revision journal: approval-gated apply with revision checks, and rollback.

Revisions are full configuration snapshots kept in the checkpointed state,
so a resumed episode sees exactly the revisions that were committed. Each
apply or rollback appends a new revision and one journal entry; nothing is
edited in place.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from .schemas import Approval, Patch, RecoveryState, Transaction


class TransactionError(Exception):
    """An apply or rollback that must not happen. ``reason`` is a short code."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


def patch_hash(run_id: str, field: str, value: Any, expected_revision: int) -> str:
    """Stable hash that binds approvals to one exact change."""
    body = json.dumps([run_id, field, value, expected_revision], sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def approval_token(p: Patch, revision: int) -> str:
    """Token bound to the patch hash and the revision it was approved at."""
    return "APR-" + hashlib.sha256(f"{p.patch_hash}:{revision}".encode()).hexdigest()[:12]


def patched(config: dict[str, Any], p: Patch) -> dict[str, Any]:
    """A copy of ``config`` with the patch applied and the revision bumped."""
    out = copy.deepcopy(config)
    out[p.field] = p.new_value
    out["revision"] = config.get("revision", 0) + 1
    return out


def apply(state: RecoveryState, p: Patch, token: str | None) -> Transaction:
    """Apply an approved patch to the current revision.

    Raises:
        TransactionError: Missing or denied approval, wrong token, stale
            revision, or a patch that was already applied.
    """
    approval: Approval | None = state.approvals.get(p.patch_id)
    if approval is None or approval.decision != "approved":
        raise TransactionError("not_approved", f"{p.patch_id} has no approval")
    if token != approval.token or token != approval_token(p, approval.revision):
        raise TransactionError("token_mismatch", "approval token does not match this patch")
    if p.expected_revision != state.revision or approval.revision != state.revision:
        raise TransactionError(
            "stale_revision",
            f"{p.patch_id} targets revision {p.expected_revision}, current is {state.revision}",
        )
    if any(t.kind == "apply" and t.patch_id == p.patch_id for t in state.journal):
        raise TransactionError("duplicate_transaction", f"{p.patch_id} was already applied")
    new = patched(state.current_config, p)
    tx = Transaction(
        transaction_id=f"T{len(state.journal) + 1}",
        kind="apply",
        patch_id=p.patch_id,
        from_revision=state.revision,
        to_revision=state.revision + 1,
        field=p.field,
        old_value=state.current_config.get(p.field),
        new_value=p.new_value,
    )
    state.configs.append(new)
    state.revision += 1
    state.journal.append(tx)
    state.transaction_id = tx.transaction_id
    return tx


def rollback(state: RecoveryState, transaction_id: str) -> Transaction:
    """Restore the revision that preceded the latest apply.

    Raises:
        TransactionError: Unknown transaction, not the latest apply, already
            rolled back, or the current revision is not the one it produced.
    """
    tx = next((t for t in state.journal if t.transaction_id == transaction_id), None)
    if tx is None or tx.kind != "apply":
        raise TransactionError("unknown_transaction", f"no apply transaction {transaction_id}")
    if any(t.rolls_back == transaction_id for t in state.journal):
        raise TransactionError("already_rolled_back", f"{transaction_id} was already rolled back")
    if state.revision != tx.to_revision:
        raise TransactionError(
            "not_latest",
            f"{transaction_id} produced revision {tx.to_revision}, not the current one",
        )
    restored = copy.deepcopy(state.configs[tx.from_revision])
    restored["revision"] = state.revision + 1
    back = Transaction(
        transaction_id=f"T{len(state.journal) + 1}",
        kind="rollback",
        rolls_back=transaction_id,
        from_revision=state.revision,
        to_revision=state.revision + 1,
        field=tx.field,
        old_value=tx.new_value,
        new_value=tx.old_value,
    )
    state.configs.append(restored)
    state.revision += 1
    state.journal.append(back)
    state.transaction_id = back.transaction_id
    return back
