"""Read-only store of failed toy runs: config revision 0, inputs and the log.

Incidents live under ``tests/fixtures/incidents/<family>/<run_id>/``. Every
read returns a copy, so nothing an episode does can change the stored
fixture. Gold labels are not here; they live in ``evaluator/``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from .schemas import Incident


class FixtureStore:
    """All incidents of one family, loaded into memory once."""

    def __init__(self, incidents: dict[str, Incident]) -> None:
        self._incidents = incidents

    @classmethod
    def load(cls, folder: Path) -> FixtureStore:
        """Load every incident directory under ``folder``."""
        out = {}
        for d in sorted(p for p in Path(folder).iterdir() if p.is_dir()):
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            inputs = {f.name: f.read_bytes() for f in sorted((d / "inputs").glob("*"))}
            out[d.name] = Incident(
                run_id=d.name,
                family=meta["family"],
                template=meta["template"],
                alert=meta["alert"],
                visible_keys=meta["visible_keys"],
                config=json.loads((d / "config.json").read_text(encoding="utf-8")),
                log_lines=(d / "run.log").read_text(encoding="utf-8").splitlines(),
                inputs=inputs,
            )
        return cls(out)

    def ids(self) -> list[str]:
        """Run ids in a stable order."""
        return sorted(self._incidents)

    def get(self, run_id: str) -> Incident | None:
        """A deep copy of one incident, or None."""
        inc = self._incidents.get(run_id)
        return copy.deepcopy(inc) if inc is not None else None
