from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from model_monitoring_lab.alerts.state_machine import AlertPolicy  # noqa: E402

T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def make_event(i: int, ts: datetime | None = None, **over):
    ts = ts or (T0 + timedelta(minutes=i))
    ev = {
        "event_id": f"SYN-EVT-TEST-{i:06d}",
        "timestamp": iso(ts),
        "model_id": "demo-scorer",
        "model_version": "1.0.0",
        "features": {"amount": 100.0 + i, "tenure_months": 12, "income": 50000.0, "region": "north", "channel": "web"},
        "score": 0.3,
        "decision": "approve",
        "route": "queue_a",
        "label": None,
        "label_available_at": None,
        "scored_at": iso(ts + timedelta(milliseconds=20)),
    }
    ev.update(over)
    return ev


@pytest.fixture
def policy():
    return AlertPolicy(enter_watch=0.1, enter_alert=0.2, exit_watch=0.05, exit_alert=0.1, min_n=10, resolve_after=2, cooldown_windows=2)


@pytest.fixture
def root():
    return ROOT
