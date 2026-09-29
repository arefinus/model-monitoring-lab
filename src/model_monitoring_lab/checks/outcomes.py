"""Prediction, calibration, workload and latency checks.

Calibration and any performance metric are computed only from events whose label is
present AND whose ``label_available_at`` is at or before ``as_of``. When no such events
exist the performance block is ``null`` with a reason; nothing here ever reports
performance degradation as a fact without labels.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Iterable

import numpy as np

from ..schema import parse_timestamp


def decision_rates(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    events = list(events)
    counts = Counter(e["decision"] for e in events)
    n = len(events)
    return {"n": n, "counts": dict(sorted(counts.items())), "rates": {k: round(v / n, 6) for k, v in sorted(counts.items())} if n else {}}


def workload(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    events = list(events)
    counts = Counter(e["route"] for e in events)
    n = len(events)
    return {"n": n, "by_route": dict(sorted(counts.items())), "share": {k: round(v / n, 6) for k, v in sorted(counts.items())} if n else {}}


def labelled_events(events: Iterable[dict[str, Any]], as_of: datetime) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for event in events:
        if event.get("label") is None or event.get("label_available_at") is None:
            continue
        if parse_timestamp(event["label_available_at"]) <= as_of:
            out.append(event)
    return out


def calibration(events: Iterable[dict[str, Any]], as_of: datetime, bins: int = 10, min_labels: int = 30) -> dict[str, Any]:
    events = list(events)
    labelled = labelled_events(events, as_of)
    pending = sum(1 for e in events if e.get("label") is not None and e not in labelled)
    base = {"n_events": len(events), "n_labelled": len(labelled), "n_labels_pending": pending}
    if len(labelled) < min_labels:
        return {**base, "performance": None, "reason": f"fewer than {min_labels} labels available as of {as_of.isoformat()}; performance not evaluated"}
    scores = np.asarray([e["score"] for e in labelled], dtype=float)
    labels = np.asarray([int(e["label"]) for e in labelled], dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(scores, edges[1:-1], right=False), 0, bins - 1)
    bin_rows = []
    ece = 0.0
    for b in range(bins):
        mask = idx == b
        count = int(mask.sum())
        if count == 0:
            bin_rows.append({"bin": b, "lower": float(edges[b]), "upper": float(edges[b + 1]), "count": 0, "mean_score": None, "label_rate": None})
            continue
        mean_score = float(scores[mask].mean())
        label_rate = float(labels[mask].mean())
        ece += count / len(labelled) * abs(mean_score - label_rate)
        bin_rows.append({"bin": b, "lower": float(edges[b]), "upper": float(edges[b + 1]), "count": count, "mean_score": round(mean_score, 6), "label_rate": round(label_rate, 6)})
    return {
        **base,
        "performance": {
            "ece": round(float(ece), 6),
            "label_rate": round(float(labels.mean()), 6),
            "mean_score": round(float(scores.mean()), 6),
            "bins": bin_rows,
        },
        "reason": None,
    }


def latency(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    values: list[float] = []
    absent = 0
    for event in events:
        scored_at = event.get("scored_at")
        if scored_at is None:
            absent += 1
            continue
        delta = parse_timestamp(scored_at) - parse_timestamp(event["timestamp"])
        values.append(delta.total_seconds() * 1000.0)
    if not values:
        return {"n": 0, "absent_scored_at": absent, "p50_ms": None, "p95_ms": None, "max_ms": None, "negative": 0}
    arr = np.asarray(values)
    p50, p95 = np.quantile(arr, [0.5, 0.95])
    return {
        "n": int(arr.size),
        "absent_scored_at": absent,
        "p50_ms": round(float(p50), 3),
        "p95_ms": round(float(p95), 3),
        "max_ms": round(float(arr.max()), 3),
        "negative": int((arr < 0).sum()),
    }
