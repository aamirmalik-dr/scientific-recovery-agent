"""Run a toy job on a copy, in a fresh temporary directory, in a subprocess.

Limits: a wall-clock timeout on every platform (the process tree is killed
when it expires) and, on POSIX, an address-space limit set with
``resource.setrlimit`` before the solver starts. On Windows no memory limit
is enforced; problem sizes are bounded by the patch policy instead. This
protects against runaway computation in the toy solvers. It is not a sandbox
for untrusted code, and no untrusted code is ever executed here.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MEMORY_MB = 512


class RunOutcome(BaseModel):
    """What one sandboxed run produced."""

    exit_code: int | None
    timed_out: bool
    elapsed_s: float
    checks: dict[str, bool]
    all_checks_pass: bool
    summary: dict[str, Any]
    log_tail: list[str]
    memory_limit_enforced: bool


def _limit_memory(mb: int):  # pragma: no cover - only runs on POSIX in the child
    def apply() -> None:
        import resource

        limit = mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

    return apply


def run_config(
    config: dict[str, Any],
    inputs: dict[str, bytes],
    timeout_s: float = DEFAULT_TIMEOUT_S,
    memory_mb: int = DEFAULT_MEMORY_MB,
) -> RunOutcome:
    """Write the job to a temporary directory and run it in a subprocess.

    Args:
        config: Full job configuration (one revision, possibly patched).
        inputs: Input files by name (profiles and checksums.json), copied in.
        timeout_s: Wall-clock limit; the child is killed when it expires.
        memory_mb: Address-space limit on POSIX; ignored on Windows.

    Returns:
        The validity checks, a summary and the last lines of the run log.
    """
    posix = sys.platform != "win32"
    with tempfile.TemporaryDirectory(prefix="toyjob-") as tmp:
        job = Path(tmp)
        (job / "inputs").mkdir()
        for name, data in inputs.items():
            (job / "inputs" / name).write_bytes(data)
        (job / "config.json").write_text(json.dumps(config), encoding="utf-8")
        cmd = [sys.executable, "-I", "-m", "scientific_recovery_agent.toy_jobs.entry", str(job)]
        start = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.run(
                cmd,
                cwd=job,
                capture_output=True,
                timeout=timeout_s,
                preexec_fn=_limit_memory(memory_mb) if posix else None,  # noqa: PLW1509
            )
            code: int | None = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out, code = True, None
        elapsed = time.monotonic() - start
        result: dict[str, Any] = {}
        if (job / "result.json").exists():
            result = json.loads((job / "result.json").read_text(encoding="utf-8"))
        log = (
            (job / "run.log").read_text(encoding="utf-8").splitlines()
            if (job / "run.log").exists()
            else ["job: killed after the time limit" if timed_out else "job: no log"]
        )
    checks = {k: bool(v) for k, v in result.get("checks", {}).items()}
    return RunOutcome(
        exit_code=code,
        timed_out=timed_out,
        elapsed_s=round(elapsed, 3),
        checks=checks,
        all_checks_pass=bool(checks) and all(checks.values()) and code == 0,
        summary={k: v for k, v in result.items() if k != "checks"},
        log_tail=log[-12:],
        memory_limit_enforced=posix,
    )
