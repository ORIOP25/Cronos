"""Enforce the Alembic baseline checkpoint before the P11 gate.

Fresh installs must start from the consolidated scheduler v1 baseline. The
current head may add revisions on top of that baseline, but the chain root must
remain the consolidated revision: any other root is a legacy local experiment
and fails unless explicitly accepted.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BASELINE_REVISION = "0001_scheduler_v1_baseline"
CONSOLIDATION_OWNER = "W12"
ACCEPTANCE_ENV = "SCHEDULER_BASELINE_ACCEPTED"


def baseline_status(revision: str | None, *, accepted: bool) -> tuple[bool, str]:
    if revision is None:
        return False, "No Alembic revision is installed."
    if revision == BASELINE_REVISION:
        return True, f"Chain root {revision} is the consolidated v1 baseline."
    if accepted:
        return True, f"Non-baseline revision {revision} is explicitly accepted."
    return (
        False,
        f"Chain root {revision} is not the consolidated v1 baseline "
        f"({BASELINE_REVISION}). Reset and install the baseline in {CONSOLIDATION_OWNER} "
        f"before P11, or set {ACCEPTANCE_ENV}=1 for a local experiment.",
    )


def _script_directory() -> ScriptDirectory:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    return ScriptDirectory.from_config(config)


def chain_root() -> str | None:
    """Walk the current head down to the root revision of its chain."""
    script = _script_directory()
    current = script.get_current_head()
    root: str | None = None
    seen: set[str] = set()
    while current is not None and current not in seen:
        seen.add(current)
        root = current
        revision = script.get_revision(current)
        down = None if revision is None else revision.down_revision
        if isinstance(down, (tuple, list)):
            down = down[0] if down else None
        current = down
    return root


def installed_head() -> str | None:
    return _script_directory().get_current_head()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.check_scheduler_baseline")
    parser.add_argument("--revision", default=None)
    args = parser.parse_args(argv)
    revision = args.revision or chain_root()
    accepted = os.environ.get(ACCEPTANCE_ENV) == "1"
    ok, message = baseline_status(revision, accepted=accepted)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
