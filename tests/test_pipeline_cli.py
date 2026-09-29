from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from model_monitoring_lab.alerts.engine import in_maintenance, run_alerts
from model_monitoring_lab.alerts.state_machine import AlertPolicy
from model_monitoring_lab.config import load_config
from model_monitoring_lab.portfolio import build_portfolio
from model_monitoring_lab.synthetic import generate_stream, reference_spec, shifted_spec


def cli(root: Path, *args, timeout=300):
    env = dict(os.environ, PYTHONPATH=str(root / "src"), OMP_NUM_THREADS="1")
    return subprocess.run([sys.executable, "-m", "model_monitoring_lab", *args], cwd=root, env=env, capture_output=True, text=True, timeout=timeout)


def fake_report(values):
    windows = []
    for i, v in enumerate(values):
        day = 1 + i
        windows.append({"index": i, "label": f"2026-07-{day:02d}", "start": f"2026-07-{day:02d}T00:00:00Z", "end": f"2026-07-{day + 1:02d}T00:00:00Z", "n": 200, "status": "ok", "series": {"psi:amount": v}})
    return {"windows": windows, "series_names": ["psi:amount"], "as_of": "2026-07-31T00:00:00Z", "evidence": "demo"}


def d(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def test_in_maintenance_overlap():
    m = [{"start": "2026-07-02T00:00:00Z", "end": "2026-07-03T00:00:00Z"}]
    assert in_maintenance(d("2026-07-02T00:00:00Z"), d("2026-07-03T00:00:00Z"), m)
    assert not in_maintenance(d("2026-07-05T00:00:00Z"), d("2026-07-06T00:00:00Z"), m)


def test_run_alerts_timeline_and_maintenance_suppression():
    pol = {"psi:amount": AlertPolicy(0.1, 0.2, 0.05, 0.1, min_n=50)}
    report = fake_report([0.0, 0.5, 0.5, 0.0, 0.0])
    out = run_alerts(report, pol, [], None)
    raised = [e for e in out["timeline"] if e["to_state"] == "alert"]
    assert len(raised) == 1 and raised[0]["window"] == "2026-07-02"
    assert out["final_states"]["psi:amount"] == "resolved"
    suppressed = run_alerts(report, pol, [{"start": "2026-07-02T00:00:00Z", "end": "2026-07-04T00:00:00Z"}], None)
    assert not [e for e in suppressed["timeline"] if e["to_state"] == "alert"]


def test_run_alerts_simulated_acknowledge():
    pol = {"psi:amount": AlertPolicy(0.1, 0.2, 0.05, 0.1, min_n=50)}
    out = run_alerts(fake_report([0.5, 0.5, 0.5, 0.5]), pol, [], 1)
    assert any(e["to_state"] == "acknowledged" for e in out["timeline"])


def test_portfolio_shape():
    pol = {"psi:amount": AlertPolicy(0.1, 0.2, 0.05, 0.1, min_n=50)}
    report = fake_report([0.0, 0.5, 0.0])
    alerts = run_alerts(report, pol, [], None)
    p = build_portfolio(report, alerts, {"statistics": {}, "provenance": {}})
    assert p["mode"] == "synthetic-demo" and p["schemaVersion"] == 1
    assert p["series"][0]["name"] == "psi:amount" and len(p["series"][0]["points"]) == 3
    assert all(isinstance(pt["value"], (int, float)) or pt["value"] is None for pt in p["series"][0]["points"])


def test_config_hash_deterministic_and_sensitive(root, tmp_path):
    c1 = load_config(root / "configs" / "default.yaml")
    c2 = load_config(root / "configs" / "default.yaml")
    assert c1.hash() == c2.hash()
    raw = yaml.safe_load((root / "configs" / "default.yaml").read_text(encoding="utf-8"))
    raw["min_n"] = raw["min_n"] + 1
    alt = tmp_path / "alt.yaml"
    alt.write_text(yaml.safe_dump(raw), encoding="utf-8")
    assert load_config(alt).hash() != c1.hash()


def test_fixture_generation_deterministic():
    a = generate_stream(reference_spec(42))
    b = generate_stream(reference_spec(42))
    assert a == b
    assert generate_stream(reference_spec(7))[0]["features"] != a[0]["features"]


def test_shifted_stream_has_schema_migration_and_unique_ids():
    s = generate_stream(shifted_spec(42))
    fields = {k for e in s for k in e["features"]}
    ref_fields = {k for e in generate_stream(reference_spec(42)) for k in e["features"]}
    assert fields != ref_fields
    ids = [e["event_id"] for e in s]
    assert len(ids) == len(set(ids))


def test_cli_check_missing_input_exits_2(root, tmp_path):
    r = cli(root, "check", "--reference", str(tmp_path / "nope.jsonl"), "--stream", str(tmp_path / "nope2.jsonl"))
    assert r.returncode == 2 and "not found" in r.stderr


def test_cli_alerts_missing_report_exits_2(root, tmp_path):
    r = cli(root, "alerts", "--report", str(tmp_path / "missing.json"))
    assert r.returncode == 2


def test_cli_check_rejects_invalid_schema(root, tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"event_id": "x"}\n', encoding="utf-8")
    r = cli(root, "check", "--reference", str(root / "examples/fixtures/v1/reference.jsonl"), "--stream", str(bad), "--out", str(tmp_path / "r.json"))
    assert r.returncode == 2 and "schema" in r.stderr.lower()


def test_cli_smoke_writes_all_outputs(root, tmp_path):
    out = tmp_path / "smoke"
    r = cli(root, "smoke", "--out", str(out))
    assert r.returncode == 0, r.stderr
    for f in ("monitoring_report.json", "alert_timeline.json", "threshold_selection.json", "portfolio.json", "run_manifest.yaml"):
        assert (out / f).exists()
    man = yaml.safe_load((out / "run_manifest.yaml").read_text(encoding="utf-8"))
    assert man["mode"] == "smoke" and man["git_commit"] is None and man["evidence_status"] == "demo"
    report = json.loads((out / "monitoring_report.json").read_text(encoding="utf-8"))
    for w in report["windows"]:
        if w["status"] == "ok" and w["calibration"]["performance"] is None:
            assert "labels" in (w["calibration"]["reason"] or "")
