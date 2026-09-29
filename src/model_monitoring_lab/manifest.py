"""Run manifest writer (contract section 5)."""
from __future__ import annotations

import hashlib
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

PROJECT_ID = "model-monitoring-lab"
SCHEMA_VERSION = 1


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_manifest(out_dir: Path, mode: str, status: str, started_at: str, seed: int, configuration_hash: str, split_manifest_hash: str | None, sample_counts: dict[str, int], metrics_file: str | None, predictions_file: str | None, extra: dict[str, Any] | None = None) -> Path:
    if mode not in ("smoke", "demo", "experiment"):
        raise ValueError("mode must be smoke, demo or experiment")
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "project_id": PROJECT_ID,
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{mode}",
        "status": status,
        "mode": mode,
        "evidence_status": "demo",
        "git_commit": None,
        "data": {"source_id": "synthetic-fixture-v1", "version": "v1", "split_manifest_hash": split_manifest_hash, "sample_counts": sample_counts},
        "configuration_hash": configuration_hash,
        "seed": seed,
        "environment": {"python": platform.python_version(), "device": "cpu"},
        "metrics_file": metrics_file,
        "predictions_file": predictions_file,
        "started_at": started_at,
        "finished_at": now_iso(),
    }
    if extra:
        manifest["extra"] = extra
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "run_manifest.yaml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return path
