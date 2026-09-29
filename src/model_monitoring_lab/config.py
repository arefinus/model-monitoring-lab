"""Typed configuration loaded from YAML."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from .schema import PACKAGE_ROOT, parse_timestamp

DEFAULT_CONFIG_PATH = PACKAGE_ROOT / "configs" / "default.yaml"


@dataclass(frozen=True)
class RuleThresholds:
    enter_watch: float
    enter_alert: float
    exit_watch: float
    exit_alert: float


@dataclass(frozen=True)
class MonitorConfig:
    seed: int = 42
    window_days: int = 1
    as_of: str = "2026-07-25T00:00:00Z"
    min_n: int = 50
    psi_bins: int = 10
    ece_bins: int = 10
    min_labels: int = 30
    numeric_features: tuple[str, ...] = ("amount", "tenure_months", "income")
    categorical_features: tuple[str, ...] = ("region", "channel", "device_type")
    reference_path: str = "examples/fixtures/v1/reference.jsonl"
    stream_path: str = "examples/fixtures/v1/shifted.jsonl"
    output_dir: str = "examples/output"
    thresholds_file: str = "configs/locked_thresholds.yaml"
    maintenance_windows: tuple[dict[str, str], ...] = ()
    resolve_after: int = 2
    cooldown_windows: int = 2
    rules: dict[str, RuleThresholds] = field(default_factory=dict)
    validation_n_clean: int = 3
    validation_n_drifted: int = 3
    simulate_acknowledge_after_windows: int | None = 1

    def as_of_dt(self) -> datetime:
        return parse_timestamp(self.as_of)

    def window(self) -> timedelta:
        return timedelta(days=self.window_days)

    def _resolve(self, value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else PACKAGE_ROOT / p

    def reference(self) -> Path:
        return self._resolve(self.reference_path)

    def stream(self) -> Path:
        return self._resolve(self.stream_path)

    def output(self) -> Path:
        return self._resolve(self.output_dir)

    def thresholds(self) -> Path:
        return self._resolve(self.thresholds_file)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def hash(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True, default=str).encode("utf-8")).hexdigest()


_DEFAULT_RULES = {
    "missingness_delta": RuleThresholds(0.10, 0.15, 0.02, 0.05),
    "new_category": RuleThresholds(1, 1, 0, 0),
    "schema_change": RuleThresholds(1, 1, 0, 0),
    "latency_ratio": RuleThresholds(1.5, 2.5, 1.2, 1.5),
}


def load_config(path: Path | None = None) -> MonitorConfig:
    path = path or DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules = dict(_DEFAULT_RULES)
    for name, spec in (raw.get("rules") or {}).items():
        rules[name] = RuleThresholds(**{k: float(v) for k, v in spec.items()})
    fixture = raw.get("fixture", {})
    sm = raw.get("state_machine", {})
    val = raw.get("validation", {})
    return MonitorConfig(
        seed=int(raw.get("seed", 42)),
        window_days=int(raw.get("window_days", 1)),
        as_of=str(raw.get("as_of", MonitorConfig.as_of)),
        min_n=int(raw.get("min_n", 50)),
        psi_bins=int(raw.get("psi_bins", 10)),
        ece_bins=int(raw.get("ece_bins", 10)),
        min_labels=int(raw.get("min_labels", 30)),
        numeric_features=tuple(raw.get("numeric_features", MonitorConfig.numeric_features)),
        categorical_features=tuple(raw.get("categorical_features", MonitorConfig.categorical_features)),
        reference_path=str(fixture.get("reference", MonitorConfig.reference_path)),
        stream_path=str(fixture.get("stream", MonitorConfig.stream_path)),
        output_dir=str(raw.get("output_dir", MonitorConfig.output_dir)),
        thresholds_file=str(raw.get("thresholds_file", MonitorConfig.thresholds_file)),
        maintenance_windows=tuple(dict(m) for m in raw.get("maintenance_windows", []) or []),
        resolve_after=int(sm.get("resolve_after", 2)),
        cooldown_windows=int(sm.get("cooldown_windows", 2)),
        rules=rules,
        validation_n_clean=int(val.get("n_clean", 3)),
        validation_n_drifted=int(val.get("n_drifted", 3)),
        simulate_acknowledge_after_windows=raw.get("simulate_acknowledge_after_windows", 1),
    )
