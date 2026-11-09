"""Subprocess entry point: ``python -I -m scientific_recovery_agent.toy_jobs.entry <dir>``.

Reads ``config.json`` and ``inputs/`` from the job directory, runs the
template and writes ``result.json`` and ``run.log`` back into it. The process
exits 0 whenever the solver finishes, even if validity checks fail, as many
real codes do; the checks in ``result.json`` decide validity. Exit code 3
means an unavailable external dependency, 1 any other crash.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from . import TEMPLATES, DependencyError, check_backend

PROFILE_FIELDS = {
    "diffusion1d": ("initial_profile", "initial_profile_source"),
    "relax1d": ("source_profile", "source_profile_source"),
}


def load_inputs(job: Path, config: dict[str, Any]) -> tuple[dict[str, list[float]], bool]:
    """Read the selected input profile and verify its checksum."""
    spec = PROFILE_FIELDS.get(config["template"])
    if spec is None:
        return {}, True
    name, source_field = spec
    path = job / "inputs" / f"{config[source_field]}.csv"
    raw = path.read_bytes()
    sums = json.loads((job / "inputs" / "checksums.json").read_text(encoding="utf-8"))
    ok = hashlib.sha256(raw).hexdigest() == sums.get(path.name)
    values = [float(v) for v in raw.decode().split(",") if v.strip()]
    return {name: values}, ok


def run_job(job: Path) -> int:
    """Run one job directory; return the process exit code."""
    lines: list[str] = []

    def log(msg: str) -> None:
        lines.append(msg)

    code = 0
    result: dict[str, Any]
    try:
        config = json.loads((job / "config.json").read_text(encoding="utf-8"))
        log(f"job: template={config['template']} revision={config.get('revision', 0)}")
        check_backend(config)
        inputs, checksum_ok = load_inputs(job, config)
        if not checksum_ok:
            log("job: WARNING input checksum mismatch")
        config["_input_checksum_ok"] = checksum_ok
        result = TEMPLATES[config["template"]](config, inputs, log)
        failed = [k for k, v in result["checks"].items() if not v]
        for name, ok in result["checks"].items():
            log(f"check {name}: {'pass' if ok else 'FAIL'}")
        log("job: finished, " + ("all checks pass" if not failed else f"failed checks: {failed}"))
    except DependencyError as exc:
        log(f"job: ImportError: {exc}")
        result, code = {"error": "dependency", "checks": {}}, 3
    except Exception as exc:  # noqa: BLE001, any solver crash is reported, not raised
        log(f"job: crashed with {type(exc).__name__}: {exc}")
        result, code = {"error": type(exc).__name__, "message": str(exc), "checks": {}}, 1
    log(f"job: exit status {code}")
    (job / "run.log").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    (job / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(run_job(Path(sys.argv[1])))
