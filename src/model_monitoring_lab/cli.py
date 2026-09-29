"""Command line interface: smoke, demo, check, alerts, figures."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .alerts.engine import run_alerts
from .alerts.thresholds import read_locked
from .config import MonitorConfig, load_config
from .figures import render_all
from .monitor import build_reference, check_stream
from .run import policies_from, run_pipeline
from .schema import PACKAGE_ROOT, EventSchema, EventSchemaError
from .stream import load_stream

REQUIRED_OUTPUTS = ("monitoring_report.json", "alert_timeline.json", "threshold_selection.json", "portfolio.json", "run_manifest.yaml")
SMOKE_WINDOWS = 10


def _config(args: argparse.Namespace) -> MonitorConfig:
    return load_config(Path(args.config) if args.config else None)


def cmd_smoke(args: argparse.Namespace) -> int:
    config = _config(args)
    out = Path(args.out) if args.out else config.output() / "smoke"
    summary = run_pipeline(config, out, mode="smoke", max_windows=SMOKE_WINDOWS)
    missing = [f for f in REQUIRED_OUTPUTS if not (out / f).exists()]
    if missing:
        print(f"smoke FAILED: missing outputs {missing}", file=sys.stderr)
        return 1
    report = json.loads((out / "monitoring_report.json").read_text(encoding="utf-8"))
    if not report.get("windows") or "series_names" not in report or report.get("evidence") != "demo":
        print("smoke FAILED: monitoring_report.json schema mismatch", file=sys.stderr)
        return 1
    portfolio = json.loads((out / "portfolio.json").read_text(encoding="utf-8"))
    if portfolio.get("mode") != "synthetic-demo" or "series" not in portfolio or "alerts" not in portfolio:
        print("smoke FAILED: portfolio.json schema mismatch", file=sys.stderr)
        return 1
    print(f"smoke ok: {summary['windows']} windows, {summary['stream_events']} events, outputs in {out}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    config = _config(args)
    out = Path(args.out) if args.out else config.output()
    summary = run_pipeline(config, out, mode="demo")
    figures = render_all(out, PACKAGE_ROOT / "docs" / "figures")
    print(json.dumps(summary, indent=1))
    print(f"figures: {[str(p) for p in figures]}")
    print("all numbers above were computed by this run on synthetic fixture v1 (seed 42); not a benchmark result")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    config = _config(args)
    ref_path = Path(args.reference) if args.reference else config.reference()
    stream_path = Path(args.stream) if args.stream else config.stream()
    for p in (ref_path, stream_path):
        if not p.exists():
            print(f"check: input not found: {p}. Generate fixtures with `python tools/make_fixture.py` or pass --reference/--stream.", file=sys.stderr)
            return 2
    schema = EventSchema.load()
    try:
        reference = build_reference(load_stream(ref_path, schema), config)
        stream = load_stream(stream_path, schema, as_of=config.as_of_dt())
    except EventSchemaError as exc:
        print(f"check: schema violation: {exc}", file=sys.stderr)
        return 2
    report = check_stream(reference, stream, config)
    out = Path(args.out) if args.out else config.output() / "monitoring_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"check: {len(report['windows'])} windows, {len(stream)} events ({stream.out_of_order} out of order) -> {out}")
    return 0


def cmd_alerts(args: argparse.Namespace) -> int:
    config = _config(args)
    report_path = Path(args.report) if args.report else config.output() / "monitoring_report.json"
    if not report_path.exists():
        print(f"alerts: report not found: {report_path}. Run `check` first.", file=sys.stderr)
        return 2
    try:
        locked = read_locked(config.thresholds())
    except FileNotFoundError as exc:
        print(f"alerts: {exc}", file=sys.stderr)
        return 2
    report = json.loads(report_path.read_text(encoding="utf-8"))
    policies = policies_from(config, locked, report["series_names"])
    alerts = run_alerts(report, policies, list(config.maintenance_windows), config.simulate_acknowledge_after_windows)
    out = Path(args.out) if args.out else config.output() / "alert_timeline.json"
    out.write_text(json.dumps(alerts, indent=1), encoding="utf-8")
    raised = sum(1 for e in alerts["timeline"] if e["to_state"] == "alert")
    print(f"alerts: {len(alerts['timeline'])} transitions, {raised} alerts raised -> {out}")
    return 0


def cmd_figures(args: argparse.Namespace) -> int:
    config = _config(args)
    out = Path(args.out) if args.out else config.output()
    try:
        written = render_all(out, PACKAGE_ROOT / "docs" / "figures")
    except FileNotFoundError as exc:
        print(f"figures: {exc}", file=sys.stderr)
        return 2
    print("\n".join(str(p) for p in written))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="model_monitoring_lab", description="Drift, calibration and data-quality monitoring for prediction streams.")
    parser.add_argument("--config", default=None, help="path to a YAML config (default configs/default.yaml)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("smoke", help="fast offline check on the first windows"); p.add_argument("--out", default=None); p.set_defaults(func=cmd_smoke)
    p = sub.add_parser("demo", help="select thresholds, check the test stream, run alerts, render figures"); p.add_argument("--out", default=None); p.set_defaults(func=cmd_demo)
    p = sub.add_parser("check", help="check a stream against a reference stream")
    p.add_argument("--reference", default=None); p.add_argument("--stream", default=None); p.add_argument("--out", default=None); p.set_defaults(func=cmd_check)
    p = sub.add_parser("alerts", help="run the alert state machine over a monitoring report with locked thresholds")
    p.add_argument("--report", default=None); p.add_argument("--out", default=None); p.set_defaults(func=cmd_alerts)
    p = sub.add_parser("figures", help="render SVG figures from demo outputs"); p.add_argument("--out", default=None); p.set_defaults(func=cmd_figures)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))
