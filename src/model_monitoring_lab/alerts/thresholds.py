"""Threshold selection on validation streams, then locking.

For each statistic (psi, ks, js) the per-window values from clean validation streams and
from drifted validation streams are compared:

- ``enter_alert`` is the midpoint between the 99th percentile of clean windows and the 5th
  percentile of drifted windows when the two are separated; otherwise the clean 99th
  percentile, and ``separated`` is recorded as false.
- ``enter_watch`` is the clean 95th percentile (capped below ``enter_alert``).
- ``exit_alert`` equals ``enter_watch``; ``exit_watch`` is the clean median.

The selected values are written to a YAML file with their provenance and then applied
unchanged to the test stream.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

STATISTICS = ("psi", "ks", "js")


@dataclass(frozen=True)
class ThresholdSet:
    enter_watch: float
    enter_alert: float
    exit_watch: float
    exit_alert: float
    separated: bool
    n_clean_windows: int
    n_drifted_windows: int
    clean_q50: float
    clean_q95: float
    clean_q99: float
    drifted_q05: float

    def to_dict(self) -> dict[str, Any]:
        return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def select_thresholds(clean: list[float], drifted: list[float]) -> ThresholdSet:
    clean_arr = np.asarray([v for v in clean if v is not None], dtype=float)
    drift_arr = np.asarray([v for v in drifted if v is not None], dtype=float)
    if clean_arr.size < 5 or drift_arr.size < 5:
        raise ValueError("need at least 5 clean and 5 drifted window values to select thresholds")
    q50, q95, q99 = np.quantile(clean_arr, [0.5, 0.95, 0.99])
    d05 = float(np.quantile(drift_arr, 0.05))
    separated = d05 > q99
    enter_alert = float((q99 + d05) / 2) if separated else float(q99)
    enter_watch = float(min(q95, enter_alert * 0.8))
    exit_alert = enter_watch
    exit_watch = float(min(q50, enter_watch))
    return ThresholdSet(
        enter_watch=enter_watch,
        enter_alert=enter_alert,
        exit_watch=exit_watch,
        exit_alert=exit_alert,
        separated=bool(separated),
        n_clean_windows=int(clean_arr.size),
        n_drifted_windows=int(drift_arr.size),
        clean_q50=float(q50),
        clean_q95=float(q95),
        clean_q99=float(q99),
        drifted_q05=d05,
    )


def write_locked(path: Path, selected: dict[str, ThresholdSet], provenance: dict[str, Any]) -> Path:
    payload = {
        "note": "Thresholds selected on separate simulated validation streams and locked; applied unchanged to the test stream. Settings, not results.",
        "provenance": provenance,
        "statistics": {name: ts.to_dict() for name, ts in selected.items()},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def read_locked(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"locked thresholds not found at {path}; run `python -m model_monitoring_lab demo` to select and lock them")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    stats = payload.get("statistics", {})
    missing = [s for s in STATISTICS if s not in stats]
    if missing:
        raise ValueError(f"locked thresholds file lacks statistics {missing}")
    return stats
