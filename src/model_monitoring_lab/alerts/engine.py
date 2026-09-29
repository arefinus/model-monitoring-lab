"""Drive one SeriesMonitor per series over the windows of a monitoring report."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..schema import parse_timestamp
from .state_machine import AlertEvent, AlertPolicy, SeriesMonitor


def in_maintenance(window_start: datetime, window_end: datetime, maintenance: list[dict[str, str]]) -> bool:
    for item in maintenance:
        start, end = parse_timestamp(item["start"]), parse_timestamp(item["end"])
        if window_start < end and window_end > start:
            return True
    return False


def run_alerts(
    report: dict[str, Any],
    policies: dict[str, AlertPolicy],
    maintenance: list[dict[str, str]],
    simulate_ack_after: int | None = None,
) -> dict[str, Any]:
    """Return the alert timeline and final states for every series with a policy."""
    monitors = {name: SeriesMonitor(name, policy) for name, policy in policies.items()}
    timeline: list[AlertEvent] = []
    pending_ack: dict[str, int] = {}
    for window in report["windows"]:
        w_start, w_end = parse_timestamp(window["start"]), parse_timestamp(window["end"])
        maint = in_maintenance(w_start, w_end, maintenance)
        values = window.get("series", {})
        for name, monitor in monitors.items():
            if name in pending_ack and monitor.state == "alert":
                pending_ack[name] -= 1
                if pending_ack[name] <= 0:
                    timeline.append(monitor.acknowledge(window["label"], "simulated-operator"))
                    del pending_ack[name]
            events = monitor.observe(window["label"], values.get(name), window["n"], in_maintenance=maint)
            timeline.extend(events)
            if simulate_ack_after is not None:
                for e in events:
                    if e.to_state == "alert":
                        pending_ack[name] = simulate_ack_after
    return {
        "note": "acknowledgements in the demo are made by a simulated operator; no automatic retraining or rollback exists",
        "maintenance_windows": maintenance,
        "policies": {name: policy.__dict__ for name, policy in policies.items()},
        "timeline": [e.to_dict() for e in timeline],
        "final_states": {name: m.state for name, m in monitors.items()},
        "counters": {name: m.counters() for name, m in monitors.items()},
        "history": {name: m.history for name, m in monitors.items()},
    }
