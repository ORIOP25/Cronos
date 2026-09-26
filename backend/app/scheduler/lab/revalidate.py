"""Revalidate a stored campaign candidate without running the solver.

Usage:

    python -m app.scheduler.lab.revalidate <case.json>

The command rebuilds the snapshot, periods and candidate from the stored
payload, runs the independent validator and the domain quality measurement, and
compares both with the stored report. A tampered candidate fails even when the
tampering would still be valid.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.quality import measure_initial_quality
from app.scheduler.domain.serialization import (
    candidate_digest,
    candidate_from_dict,
    period_from_dict,
    snapshot_from_dict,
)
from app.scheduler.lab.payload import quality_to_dict, validation_to_dict


def _load_payload(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    payload = data.get("payload") or data.get("result", {}).get("payload")
    if not isinstance(payload, dict) or "candidate" not in payload:
        raise ValueError("The file has no revalidatable payload.")
    return payload


def revalidate(path: Path) -> dict:
    payload = _load_payload(path)
    snapshot = snapshot_from_dict(payload["snapshot"])
    periods = tuple(period_from_dict(row) for row in payload["periods"])
    del periods
    candidate = candidate_from_dict(payload["candidate"])
    problems: list[str] = []
    digest = candidate_digest(candidate)
    if payload.get("candidate_digest") and digest != payload["candidate_digest"]:
        problems.append("candidate digest does not match the stored payload")
    report = validate_candidate(snapshot, candidate)
    stored_validation = payload.get("validation")
    if not report.valid:
        problems.append("candidate is no longer valid")
    if stored_validation is not None:
        fresh = validation_to_dict(report)
        if fresh != stored_validation:
            problems.append("the recalculated validation differs from the stored report")
    metrics = measure_initial_quality(snapshot, candidate)
    stored_quality = payload.get("quality")
    if stored_quality is not None and quality_to_dict(metrics) != stored_quality:
        problems.append("the recalculated quality differs from the stored metrics")
    return {
        "case_id": payload.get("case_id"),
        "candidate_digest": digest,
        "valid": report.valid,
        "violations": [violation.code.value for violation in report.violations],
        "quality": quality_to_dict(metrics),
        "problems": problems,
        "revalidated": not problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Revalidate a stored scheduler candidate")
    parser.add_argument("case_file", type=Path)
    args = parser.parse_args(argv)
    try:
        summary = revalidate(args.case_file)
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["revalidated"] else 1


if __name__ == "__main__":
    sys.exit(main())
