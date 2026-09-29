"""Portfolio JSON export consumed by the owner's portfolio site."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

PORTFOLIO_SCHEMA_VERSION = 1
MODE = "synthetic-demo"
FEATURED_SERIES = ("psi:amount", "psi:score", "missing:income", "category:region", "schema", "latency:p95_ratio", "ks:amount")


def build_portfolio(report: dict[str, Any], alerts: dict[str, Any], threshold_selection: dict[str, Any]) -> dict[str, Any]:
    state_by_window: dict[str, dict[str, str]] = {}
    for name, history in alerts["history"].items():
        state_by_window[name] = {h["window"]: h["state"] for h in history}
    series = []
    for name in FEATURED_SERIES:
        if name not in report["series_names"]:
            continue
        points = []
        for w in report["windows"]:
            points.append({"window": w["label"], "n": w["n"], "value": w.get("series", {}).get(name), "state": state_by_window.get(name, {}).get(w["label"], "healthy")})
        stat = name.split(":")[0]
        policy = alerts["policies"].get(name, {})
        series.append({"name": name, "statistic": stat, "enterAlert": policy.get("enter_alert"), "enterWatch": policy.get("enter_watch"), "points": points})
    return {
        "schemaVersion": PORTFOLIO_SCHEMA_VERSION,
        "mode": MODE,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "evidence": "demo",
        "note": "computed on authored synthetic fixture v1, seed 42; thresholds selected on separate simulated validation streams; not a benchmark result",
        "asOf": report["as_of"],
        "series": series,
        "alerts": [
            {"window": e["window"], "series": e["series"], "fromState": e["from_state"], "toState": e["to_state"], "value": e["value"], "threshold": e["threshold"], "reason": e["reason"]}
            for e in alerts["timeline"]
        ],
        "finalStates": alerts["final_states"],
        "thresholdSelection": {k: {"enterAlert": v["enter_alert"], "enterWatch": v["enter_watch"], "separated": v["separated"]} for k, v in threshold_selection.get("statistics", {}).items()},
    }
