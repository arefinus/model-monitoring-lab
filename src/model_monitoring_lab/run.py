"""Orchestration: select thresholds on validation streams, lock, check the test stream, alert."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .alerts.engine import run_alerts
from .alerts.state_machine import AlertPolicy
from .alerts.thresholds import STATISTICS, ThresholdSet, read_locked, select_thresholds, write_locked
from .config import MonitorConfig
from .manifest import now_iso, sha256_file, write_manifest
from .monitor import build_reference, check_stream
from .portfolio import build_portfolio
from .schema import EventSchema
from .stream import Stream, build_stream, load_stream
from .synthetic import generate_stream, validation_specs


def select_and_lock(config: MonitorConfig, reference: Any) -> dict[str, Any]:
    """Run the checks on simulated clean and drifted validation streams; pick and lock thresholds."""
    schema = EventSchema.load()
    per_stat: dict[str, dict[str, list[float]]] = {s: {"clean": [], "drifted": []} for s in STATISTICS}
    used: list[dict[str, Any]] = []
    for kind, spec in validation_specs(config.seed, config.validation_n_clean, config.validation_n_drifted):
        stream = build_stream(generate_stream(spec), schema)
        report = check_stream(reference, stream, config)
        used.append({"kind": kind, "seed": spec.seed, "days": spec.days, "events": len(stream)})
        for w in report["windows"]:
            if w["status"] != "ok":
                continue
            for name, value in w["series"].items():
                stat, _, field = name.partition(":")
                if stat in per_stat and field in config.numeric_features and value is not None:
                    per_stat[stat][kind].append(float(value))
    selected = {s: select_thresholds(v["clean"], v["drifted"]) for s, v in per_stat.items()}
    provenance = {"streams": used, "features_pooled": list(config.numeric_features), "note": "per-window statistics pooled across the numeric features of each validation stream"}
    write_locked(config.thresholds(), selected, provenance)
    return {"statistics": {s: t.to_dict() for s, t in selected.items()}, "provenance": provenance}


def policies_from(config: MonitorConfig, locked: dict[str, dict[str, Any]], series_names: list[str]) -> dict[str, AlertPolicy]:
    common = {"min_n": config.min_n, "resolve_after": config.resolve_after, "cooldown_windows": config.cooldown_windows}
    out: dict[str, AlertPolicy] = {}
    for name in series_names:
        stat, _, _field = name.partition(":")
        if stat in locked:
            t = locked[stat]
            out[name] = AlertPolicy(t["enter_watch"], t["enter_alert"], t["exit_watch"], t["exit_alert"], **common)
        elif stat == "missing":
            r = config.rules["missingness_delta"]
            out[name] = AlertPolicy(r.enter_watch, r.enter_alert, r.exit_watch, r.exit_alert, **common)
        elif stat == "category":
            r = config.rules["new_category"]
            out[name] = AlertPolicy(r.enter_watch, r.enter_alert, r.exit_watch, r.exit_alert, **common)
        elif stat == "schema":
            r = config.rules["schema_change"]
            out[name] = AlertPolicy(r.enter_watch, r.enter_alert, r.exit_watch, r.exit_alert, **common)
        elif stat == "latency":
            r = config.rules["latency_ratio"]
            out[name] = AlertPolicy(r.enter_watch, r.enter_alert, r.exit_watch, r.exit_alert, **common)
    return out


def run_pipeline(config: MonitorConfig, out_dir: Path, mode: str, max_windows: int | None = None) -> dict[str, Any]:
    started = now_iso()
    out_dir.mkdir(parents=True, exist_ok=True)
    schema = EventSchema.load()
    reference_stream = load_stream(config.reference(), schema)
    test_stream = load_stream(config.stream(), schema, as_of=config.as_of_dt())
    reference = build_reference(reference_stream, config)

    selection = select_and_lock(config, reference)
    locked = read_locked(config.thresholds())

    report = check_stream(reference, test_stream, config)
    if max_windows is not None:
        report["windows"] = report["windows"][:max_windows]
    (out_dir / "monitoring_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (out_dir / "threshold_selection.json").write_text(json.dumps(selection, indent=1), encoding="utf-8")

    policies = policies_from(config, locked, report["series_names"])
    alerts = run_alerts(report, policies, list(config.maintenance_windows), config.simulate_acknowledge_after_windows)
    (out_dir / "alert_timeline.json").write_text(json.dumps(alerts, indent=1), encoding="utf-8")

    portfolio = build_portfolio(report, alerts, selection)
    (out_dir / "portfolio.json").write_text(json.dumps(portfolio, indent=1), encoding="utf-8")

    window_hash = hashlib.sha256(json.dumps([(w["label"], w["n"]) for w in report["windows"]]).encode()).hexdigest()
    write_manifest(
        out_dir, mode=mode, status="completed", started_at=started, seed=config.seed, configuration_hash=config.hash(),
        split_manifest_hash=window_hash,
        sample_counts={"reference_events": len(reference_stream), "stream_events": len(test_stream), "windows": len(report["windows"])},
        metrics_file="monitoring_report.json", predictions_file=None,
        extra={"reference_sha256": sha256_file(config.reference()), "stream_sha256": sha256_file(config.stream()), "thresholds_file": str(config.thresholds_file)},
    )
    return {
        "out_dir": str(out_dir),
        "reference_events": len(reference_stream),
        "stream_events": len(test_stream),
        "windows": len(report["windows"]),
        "no_data_windows": sum(1 for w in report["windows"] if w["status"] == "no_data"),
        "out_of_order": test_stream.out_of_order,
        "alerts_raised": sum(1 for e in alerts["timeline"] if e["to_state"] == "alert"),
        "timeline_events": len(alerts["timeline"]),
        "final_states": {k: v for k, v in alerts["final_states"].items() if v != "healthy"},
        "thresholds": {k: {"enter_alert": v["enter_alert"], "separated": v["separated"]} for k, v in selection["statistics"].items()},
    }
