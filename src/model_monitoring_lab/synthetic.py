"""Authored synthetic prediction-event streams (fixture v1).

Everything is fictional: ``SYN-EVT-`` identifiers, a model called ``demo-scorer``, and
features with no relation to any person or dataset. The shifted stream injects a fixed
schedule of changes so each check has a known target.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

FIXTURE_VERSION = "v1"
MODEL_ID = "demo-scorer"
REGIONS = ["north", "south", "east", "west", "central"]
CHANNELS = ["web", "mobile", "branch"]
DEVICE_TYPES = ["phone", "tablet", "desktop"]
EVENTS_PER_DAY = 160
DAYS = 24


@dataclass(frozen=True)
class Shift:
    """Change schedule for a shifted stream, expressed in day indexes (inclusive starts)."""

    covariate_drift_day: int | None = 8      # amount mean scales up from this day
    prior_shift_day: int | None = 12         # score and label base rate move up
    missing_spike_days: tuple[int, ...] = (6, 7)   # income null rate jumps
    new_category_day: int | None = 14        # region gains a value
    schema_migration_day: int | None = 16    # channel removed, device_type added
    latency_rise_day: int | None = 18        # scored_at lag triples
    empty_days: tuple[int, ...] = (20,)      # no events at all
    out_of_order_share: float = 0.05         # share of events written out of time order
    model_version_after_migration: str = "1.1.0"


CLEAN = Shift(
    covariate_drift_day=None, prior_shift_day=None, missing_spike_days=(), new_category_day=None,
    schema_migration_day=None, latency_rise_day=None, empty_days=(), out_of_order_share=0.0,
)


@dataclass(frozen=True)
class StreamSpec:
    start: datetime
    days: int = DAYS
    events_per_day: int = EVENTS_PER_DAY
    seed: int = 42
    shift: Shift = field(default_factory=lambda: CLEAN)
    label_delay_days: tuple[int, int] = (5, 12)
    model_version: str = "1.0.0"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def generate_stream(spec: StreamSpec) -> list[dict[str, Any]]:
    rng = np.random.default_rng(spec.seed)
    events: list[dict[str, Any]] = []
    counter = 0
    for day in range(spec.days):
        if day in spec.shift.empty_days:
            continue
        day_start = spec.start + timedelta(days=day)
        amount_scale = 1.0
        if spec.shift.covariate_drift_day is not None and day >= spec.shift.covariate_drift_day:
            amount_scale = 1.0 + 0.6 * min(1.0, (day - spec.shift.covariate_drift_day + 1) / 3)
        score_shift = 0.0
        if spec.shift.prior_shift_day is not None and day >= spec.shift.prior_shift_day:
            score_shift = 0.9
        income_missing = 0.45 if day in spec.shift.missing_spike_days else 0.05
        migrated = spec.shift.schema_migration_day is not None and day >= spec.shift.schema_migration_day
        latency_mult = 3.0 if (spec.shift.latency_rise_day is not None and day >= spec.shift.latency_rise_day) else 1.0
        regions = REGIONS + (["north-east-2"] if (spec.shift.new_category_day is not None and day >= spec.shift.new_category_day) else [])

        seconds = np.sort(rng.uniform(0, 86400, size=spec.events_per_day))
        for sec in seconds:
            counter += 1
            ts = day_start + timedelta(seconds=float(sec))
            amount = float(np.exp(rng.normal(4.0, 0.6))) * amount_scale
            tenure = int(rng.geometric(0.08))
            income = None if rng.random() < income_missing else float(rng.normal(60000, 15000))
            region = str(rng.choice(regions))
            logit = -1.2 + 0.35 * np.log(amount) - 0.03 * tenure + rng.normal(0, 0.6) + score_shift
            score = float(1.0 / (1.0 + np.exp(-logit)))
            score = min(max(round(score, 6), 0.0), 1.0)
            decision = "decline" if score >= 0.7 else ("review" if score >= 0.4 else "approve")
            route = {"approve": "auto", "review": "queue_a", "decline": "queue_b"}[decision]
            if decision == "approve" and rng.random() < 0.05:
                route = "queue_a"
            label = int(rng.random() < score)
            delay = int(rng.integers(spec.label_delay_days[0], spec.label_delay_days[1] + 1))
            label_at = ts + timedelta(days=delay, hours=float(rng.uniform(0, 12)))
            latency_ms = float(np.exp(rng.normal(np.log(40.0), 0.35))) * latency_mult
            features: dict[str, Any] = {"amount": round(amount, 2), "tenure_months": tenure, "income": (None if income is None else round(income, 2)), "region": region}
            if migrated:
                features["device_type"] = str(rng.choice(DEVICE_TYPES))
            else:
                features["channel"] = str(rng.choice(CHANNELS))
            events.append(
                {
                    "event_id": f"SYN-EVT-{spec.seed:03d}-{counter:06d}",
                    "timestamp": _iso(ts),
                    "model_id": MODEL_ID,
                    "model_version": spec.shift.model_version_after_migration if migrated else spec.model_version,
                    "features": features,
                    "score": score,
                    "decision": decision,
                    "route": route,
                    "label": label,
                    "label_available_at": _iso(label_at),
                    "scored_at": _iso(ts + timedelta(milliseconds=latency_ms)),
                }
            )
    if spec.shift.out_of_order_share > 0 and len(events) > 1:
        n_swap = int(spec.shift.out_of_order_share * len(events))
        idx = rng.choice(len(events) - 1, size=n_swap, replace=False)
        for i in idx:
            events[i], events[i + 1] = events[i + 1], events[i]
    return events


def write_jsonl(events: list[dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")
    return path


REFERENCE_START = datetime(2026, 6, 1, tzinfo=timezone.utc)
SHIFTED_START = datetime(2026, 7, 1, tzinfo=timezone.utc)
AS_OF = datetime(2026, 7, 25, tzinfo=timezone.utc)


def reference_spec(seed: int = 42) -> StreamSpec:
    return StreamSpec(start=REFERENCE_START, seed=seed, shift=CLEAN)


def shifted_spec(seed: int = 42) -> StreamSpec:
    return StreamSpec(start=SHIFTED_START, seed=seed + 1, shift=Shift())


def validation_specs(seed: int = 42, n_clean: int = 3, n_drifted: int = 3) -> list[tuple[str, StreamSpec]]:
    """Separate simulated streams used only to choose thresholds."""
    specs: list[tuple[str, StreamSpec]] = []
    for k in range(n_clean):
        specs.append(("clean", StreamSpec(start=REFERENCE_START, days=12, seed=seed + 100 + k, shift=CLEAN)))
    drift = Shift(covariate_drift_day=0, prior_shift_day=0, missing_spike_days=(), new_category_day=None,
                  schema_migration_day=None, latency_rise_day=None, empty_days=(), out_of_order_share=0.0)
    for k in range(n_drifted):
        specs.append(("drifted", StreamSpec(start=REFERENCE_START, days=12, seed=seed + 200 + k, shift=drift)))
    return specs


def fixture_card(seed: int, n_reference: int, n_shifted: int) -> str:
    return (
        "# FIXTURE.md\n\n"
        "Authored synthetic demonstration data. Fictional identifiers. Not derived from any "
        "person, company, account or dataset. Generated by `tools/make_fixture.py` seed "
        f"`{seed}`, version {FIXTURE_VERSION}.\n\n"
        f"- `reference.jsonl`: {n_reference} events, {DAYS} days from {REFERENCE_START.date()}, stable behaviour\n"
        f"- `shifted.jsonl`: {n_shifted} events, {DAYS} days from {SHIFTED_START.date()}, with a fixed change schedule:\n"
        "  missing spike on `income` (days 7-8), covariate drift on `amount` (from day 9), prior shift on the "
        "score (from day 13), new `region` value (from day 15), schema migration replacing `channel` with "
        "`device_type` and bumping `model_version` (from day 17), latency rise (from day 19), an empty day (day 21), "
        "and about 5 percent of events written out of time order\n"
        f"- Labels arrive 5 to 12 days after the event; with `as_of` {AS_OF.date()} the latest labels are not yet available\n"
        "- Every event matches `schemas/prediction_event.json`\n\n"
        "Regenerate: `python tools/make_fixture.py --seed 42`\n"
    )
