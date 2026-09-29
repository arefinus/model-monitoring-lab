"""Data-quality checks: schema field set, missingness, category sets."""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


def feature_field_set(events: Iterable[dict[str, Any]]) -> set[str]:
    fields: set[str] = set()
    for event in events:
        fields.update(event["features"].keys())
    return fields


def schema_change(reference_fields: set[str], events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    current = feature_field_set(events)
    added = sorted(current - reference_fields)
    removed = sorted(reference_fields - current)
    versions = sorted({e["model_version"] for e in events})
    return {"added_fields": added, "removed_fields": removed, "changed": bool(added or removed), "model_versions": versions}


def missingness(events: Iterable[dict[str, Any]], fields: Iterable[str]) -> dict[str, dict[str, Any]]:
    events = list(events)
    out: dict[str, dict[str, Any]] = {}
    for field in fields:
        present = 0
        missing = 0
        for event in events:
            value = event["features"].get(field, None)
            if value is None:
                missing += 1
            else:
                present += 1
        total = present + missing
        out[field] = {"n": total, "missing": missing, "rate": (round(missing / total, 6) if total else None)}
    return out


def category_values(events: Iterable[dict[str, Any]], field: str) -> Counter:
    counter: Counter = Counter()
    for event in events:
        value = event["features"].get(field, None)
        if value is not None:
            counter[str(value)] += 1
    return counter


def category_change(reference_values: set[str], events: Iterable[dict[str, Any]], field: str) -> dict[str, Any]:
    counts = category_values(events, field)
    new = sorted(set(counts) - reference_values)
    missing = sorted(reference_values - set(counts))
    return {
        "field": field,
        "new_values": new,
        "new_value_count": int(sum(counts[v] for v in new)),
        "unseen_reference_values": missing,
        "changed": bool(new),
        "counts": dict(sorted(counts.items())),
    }
