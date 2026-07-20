from __future__ import annotations

import enum
import hashlib
import json
from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any


class SchedulerSerializationError(ValueError):
    pass


def canonical_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise SchedulerSerializationError("Scheduler snapshots require finite numbers.")
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, enum.Enum):
        return canonical_json_value(value.value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): canonical_json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [canonical_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        canonical_items = [canonical_json_value(item) for item in value]
        return sorted(canonical_items, key=canonical_json_bytes)
    raise SchedulerSerializationError(
        f"Unsupported scheduler snapshot value: {type(value).__name__}."
    )


def canonical_json_bytes(value: Any) -> bytes:
    normalized = canonical_json_value(value)
    return json.dumps(
        normalized,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()
