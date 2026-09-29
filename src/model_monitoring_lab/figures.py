"""Hand-written SVG figures from demo outputs (no plotting dependency).

Every figure is drawn from monitoring_report.json and alert_timeline.json that a
run actually produced; nothing is drawn from a reported number.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

W, H, L, R, T, B = 760, 360, 70, 20, 40, 60
STATE_COLOUR = {"healthy": "#2f855a", "watch": "#b7791f", "alert": "#c53030", "acknowledged": "#6b46c1", "resolved": "#2b6cb0"}


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _frame(title: str, ylabel: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="12">',
        f'<rect width="{W}" height="{H}" fill="white"/>',
        f'<text x="{L}" y="24" font-size="15" font-weight="bold">{_esc(title)}</text>',
        f'<line x1="{L}" y1="{T}" x2="{L}" y2="{H - B}" stroke="black"/>',
        f'<line x1="{L}" y1="{H - B}" x2="{W - R}" y2="{H - B}" stroke="black"/>',
        f'<text x="14" y="{(T + H - B) // 2}" transform="rotate(-90 14 {(T + H - B) // 2})" text-anchor="middle">{_esc(ylabel)}</text>',
        f'<text x="{(L + W - R) // 2}" y="{H - 12}" text-anchor="middle">window (chronological)</text>',
    ]


def series_figure(report: dict[str, Any], alerts: dict[str, Any], name: str) -> str:
    windows = report["windows"]
    values = [w.get("series", {}).get(name) for w in windows]
    finite = [v for v in values if isinstance(v, (int, float))]
    policy = alerts.get("policies", {}).get(name, {})
    enter_alert = policy.get("enter_alert")
    ymax = max(finite + ([enter_alert] if isinstance(enter_alert, (int, float)) else []) + [1e-9]) * 1.15
    states = {h["window"]: h["state"] for h in alerts.get("history", {}).get(name, [])}
    n = max(len(windows), 1)
    step = (W - L - R) / n
    out = _frame(f"{name} per window (demo, synthetic fixture v1)", name.split(":")[0])
    pts = []
    for i, (w, v) in enumerate(zip(windows, values)):
        x = L + step * (i + 0.5)
        colour = STATE_COLOUR.get(states.get(w["label"], "healthy"), "#888")
        out.append(f'<rect x="{x - step / 2:.1f}" y="{T}" width="{step:.1f}" height="{H - B - T}" fill="{colour}" opacity="0.10"/>')
        if isinstance(v, (int, float)):
            y = H - B - (v / ymax) * (H - B - T)
            pts.append(f"{x:.1f},{y:.1f}")
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{colour}"/>')
    if pts:
        out.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="#1a202c" stroke-width="1.5"/>')
    if isinstance(enter_alert, (int, float)):
        y = H - B - (enter_alert / ymax) * (H - B - T)
        out.append(f'<line x1="{L}" y1="{y:.1f}" x2="{W - R}" y2="{y:.1f}" stroke="#c53030" stroke-dasharray="6 4"/>')
        out.append(f'<text x="{W - R}" y="{y - 4:.1f}" text-anchor="end" fill="#c53030">enter_alert = {enter_alert:.3g}</text>')
    out.append(f'<text x="{L}" y="{H - B + 16}">{_esc(windows[0]["label"]) if windows else ""}</text>')
    out.append(f'<text x="{W - R}" y="{H - B + 16}" text-anchor="end">{_esc(windows[-1]["label"]) if windows else ""}</text>')
    out.append("</svg>")
    return "\n".join(out)


def timeline_figure(alerts: dict[str, Any], report: dict[str, Any]) -> str:
    history = alerts.get("history", {})
    names = sorted(history)
    windows = [w["label"] for w in report["windows"]]
    rows = max(len(names), 1)
    height = T + 22 * rows + B
    step = (W - L - R) / max(len(windows), 1)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" viewBox="0 0 {W} {height}" font-family="sans-serif" font-size="11">',
        f'<rect width="{W}" height="{height}" fill="white"/>',
        f'<text x="{L}" y="24" font-size="15" font-weight="bold">Alert state per series and window (demo)</text>',
    ]
    for r, name in enumerate(names):
        y = T + 22 * r
        out.append(f'<text x="{L - 6}" y="{y + 15}" text-anchor="end">{_esc(name)}</text>')
        state_by_window = {h["window"]: h["state"] for h in history[name]}
        for i, wl in enumerate(windows):
            colour = STATE_COLOUR.get(state_by_window.get(wl, "healthy"), "#ccc")
            out.append(f'<rect x="{L + step * i:.1f}" y="{y + 2}" width="{max(step - 1, 1):.1f}" height="18" fill="{colour}"/>')
    lx = L
    for state, colour in STATE_COLOUR.items():
        out.append(f'<rect x="{lx}" y="{height - 30}" width="12" height="12" fill="{colour}"/>')
        out.append(f'<text x="{lx + 16}" y="{height - 20}">{state}</text>')
        lx += 110
    out.append("</svg>")
    return "\n".join(out)


def render_all(out_dir: Path, figures_dir: Path) -> list[Path]:
    report_path = out_dir / "monitoring_report.json"
    alerts_path = out_dir / "alert_timeline.json"
    for p in (report_path, alerts_path):
        if not p.exists():
            raise FileNotFoundError(f"{p} not found; run `demo` or `check` and `alerts` first")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    alerts = json.loads(alerts_path.read_text(encoding="utf-8"))
    figures_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in ("psi:amount", "psi:score", "missing:income"):
        if name in report.get("series_names", []):
            target = figures_dir / f"series_{name.replace(':', '_')}.svg"
            target.write_text(series_figure(report, alerts, name), encoding="utf-8")
            written.append(target)
    target = figures_dir / "alert_timeline.svg"
    target.write_text(timeline_figure(alerts, report), encoding="utf-8")
    written.append(target)
    return written
