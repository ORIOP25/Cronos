"""Revalidate every stored annual campaign candidate without the solver.

Run inside the backend test image:

    docker run --rm --network none \
      --mount type=bind,source=<repo>,target=/workspace \
      -w /workspace/backend -e PYTHONPATH=/workspace/backend \
      cronos-backend-test:local python \
      /workspace/documentation/03_scheduler_engine/review_evidence/2026-09-25-w04-w05-correction/revalidate_all.py
"""

from __future__ import annotations

import json
from pathlib import Path

from app.scheduler.lab.revalidate import revalidate

ARTIFACT_DIR = Path(
    "/workspace/.test-artifacts/1790294303847-35956/scheduler-lab"
)
OUTPUT = Path(__file__).with_name("revalidation.json")


def main() -> None:
    cases = sorted(ARTIFACT_DIR.glob("gen-annual-*.json"))
    results = {}
    for path in cases:
        results[path.stem] = revalidate(path)
    OUTPUT.write_text(
        json.dumps(
            {
                "artifact_source": str(ARTIFACT_DIR),
                "revalidated": sum(1 for row in results.values() if row["revalidated"]),
                "total": len(results),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    failures = sorted(
        name for name, row in results.items() if not row["revalidated"]
    )
    print(json.dumps({"total": len(results), "failures": failures}, ensure_ascii=False))


if __name__ == "__main__":
    main()
