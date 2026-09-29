"""Build a reference profile from one stream and check another stream window by window."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .checks.distribution import ReferenceBins, js_distance, ks_statistic, psi, reference_bins, summary
from .checks.outcomes import calibration, decision_rates, latency, workload
from .checks.quality import category_change, category_values, feature_field_set, missingness, schema_change
from .config import MonitorConfig
from .stream import Stream, Window, windows

NOTE = "computed by `make demo` on synthetic fixture v1, seed 42, not a benchmark result"


@dataclass(frozen=True)
class Reference:
    fields: frozenset[str]
    numeric_values: dict[str, list[float]]
    numeric_bins: dict[str, ReferenceBins]
    categorical_values: dict[str, frozenset[str]]
    missing_rates: dict[str, float]
    score_values: list[float]
    score_bins: ReferenceBins
    latency_p95_ms: float | None
    n: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "fields": sorted(self.fields),
            "numeric": {f: {"summary": summary(v), "bins": self.numeric_bins[f].to_dict()} for f, v in self.numeric_values.items()},
            "categorical": {f: sorted(v) for f, v in self.categorical_values.items()},
            "missing_rates": self.missing_rates,
            "score": {"summary": summary(self.score_values), "bins": self.score_bins.to_dict()},
            "latency_p95_ms": self.latency_p95_ms,
        }


def _numeric(events: tuple[dict[str, Any], ...], field: str) -> list[float]:
    out: list[float] = []
    for e in events:
        v = e["features"].get(field)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append(float(v))
    return out


def build_reference(stream: Stream, config: MonitorConfig) -> Reference:
    events = stream.events
    fields = feature_field_set(events)
    numeric_values = {f: _numeric(events, f) for f in config.numeric_features if f in fields}
    numeric_bins = {f: reference_bins(v, config.psi_bins) for f, v in numeric_values.items() if len(v) >= config.psi_bins}
    categorical = {f: frozenset(category_values(events, f)) for f in config.categorical_features if f in fields}
    miss = {f: (m["rate"] or 0.0) for f, m in missingness(events, sorted(fields)).items()}
    scores = [float(e["score"]) for e in events]
    lat = latency(events)
    return Reference(
        fields=frozenset(fields),
        numeric_values=numeric_values,
        numeric_bins=numeric_bins,
        categorical_values=categorical,
        missing_rates=miss,
        score_values=scores,
        score_bins=reference_bins(scores, config.psi_bins),
        latency_p95_ms=lat["p95_ms"],
        n=len(events),
    )


def check_window(window: Window, reference: Reference, config: MonitorConfig, as_of: datetime) -> dict[str, Any]:
    events = window.events
    base: dict[str, Any] = {"index": window.index, "label": window.label, "start": window.start.isoformat(), "end": window.end.isoformat(), "n": window.n}
    if window.n == 0:
        return {**base, "status": "no_data", "series": {}, "calibration": {"n_events": 0, "n_labelled": 0, "performance": None, "reason": "no events in window"}}
    status = "ok" if window.n >= config.min_n else "insufficient_sample"
    schema = schema_change(set(reference.fields), events)
    all_fields = sorted(set(reference.fields) | set(schema["added_fields"]))
    miss = missingness(events, all_fields)
    cats = {f: category_change(set(reference.categorical_values.get(f, frozenset())), events, f) for f in config.categorical_features if f in reference.categorical_values or f in schema["added_fields"]}
    numeric: dict[str, Any] = {}
    series: dict[str, float | None] = {}
    for f, bins in reference.numeric_bins.items():
        values = _numeric(events, f)
        block = {"summary": summary(values), "psi": psi(bins, values), "ks": ks_statistic(reference.numeric_values[f], values), "js": js_distance(bins, values)}
        numeric[f] = block
        series[f"psi:{f}"] = block["psi"]["value"]
        series[f"ks:{f}"] = block["ks"]["value"]
        series[f"js:{f}"] = block["js"]["value"]
    scores = [float(e["score"]) for e in events]
    score_block = {"summary": summary(scores), "psi": psi(reference.score_bins, scores), "ks": ks_statistic(reference.score_values, scores), "js": js_distance(reference.score_bins, scores)}
    series["psi:score"] = score_block["psi"]["value"]
    series["ks:score"] = score_block["ks"]["value"]
    series["js:score"] = score_block["js"]["value"]
    for f in reference.fields:
        rate = miss[f]["rate"]
        series[f"missing:{f}"] = None if rate is None else round(rate - reference.missing_rates.get(f, 0.0), 6)
    for f, c in cats.items():
        series[f"category:{f}"] = 1.0 if c["changed"] else 0.0
    series["schema"] = 1.0 if schema["changed"] else 0.0
    lat = latency(events)
    series["latency:p95_ratio"] = (None if (lat["p95_ms"] is None or not reference.latency_p95_ms) else round(lat["p95_ms"] / reference.latency_p95_ms, 6))
    return {
        **base,
        "status": status,
        "schema": schema,
        "missingness": miss,
        "categories": cats,
        "numeric": numeric,
        "score": score_block,
        "decisions": decision_rates(events),
        "workload": workload(events),
        "calibration": calibration(events, as_of, config.ece_bins, config.min_labels),
        "latency": lat,
        "series": series,
    }


def check_stream(reference: Reference, stream: Stream, config: MonitorConfig) -> dict[str, Any]:
    as_of = config.as_of_dt()
    wins = windows(stream, config.window())
    checked = [check_window(w, reference, config, as_of) for w in wins]
    names = sorted({k for w in checked for k in w.get("series", {})})
    return {
        "evidence": "demo",
        "note": NOTE,
        "as_of": as_of.isoformat(),
        "window_days": config.window_days,
        "min_n": config.min_n,
        "reference": reference.to_dict(),
        "stream": {"n": len(stream), "out_of_order": stream.out_of_order, "excluded_future": stream.excluded_future, "duplicates_dropped": stream.duplicates_dropped, "start": stream.start.isoformat(), "end": stream.end.isoformat()},
        "series_names": names,
        "windows": checked,
        "performance_note": "performance metrics are computed only from labels available at as_of; windows without labels show performance: null and are never described as degraded",
    }
