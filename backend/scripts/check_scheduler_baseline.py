"""Enforce the Alembic baseline checkpoint before the P11 gate.

Fresh installs must start from the consolidated scheduler v1 baseline. Any
other installed head is either a legacy local experiment or an outdated chain
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
        return True, f"Installed revision {revision} is the consolidated v1 baseline."
    if accepted:
        return True, f"Non-baseline revision {revision} is explicitly accepted."
    return (
        False,
        f"Installed revision {revision} is not the consolidated v1 baseline "
        f"({BASELINE_REVISION}). Reset and install the baseline in {CONSOLIDATION_OWNER} "
        f"before P11, or set {ACCEPTANCE_ENV}=1 for a local experiment.",
    )


def installed_head() -> str | None:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.check_scheduler_baseline")
    parser.add_argument("--revision", default=None)
    args = parser.parse_args(argv)
    revision = args.revision or installed_head()
    accepted = os.environ.get(ACCEPTANCE_ENV) == "1"
    ok, message = baseline_status(revision, accepted=accepted)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
