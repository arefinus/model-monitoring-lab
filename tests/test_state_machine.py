from __future__ import annotations

import pytest

from model_monitoring_lab.alerts.state_machine import AlertPolicy, InvalidTransition, SeriesMonitor


def run(mon, values, n=100, maint=None):
    out = []
    for i, v in enumerate(values):
        out.extend(mon.observe(f"w{i}", v, n, in_maintenance=bool(maint and i in maint)))
    return out


def test_healthy_to_watch_to_alert(policy):
    mon = SeriesMonitor("s", policy)
    ev = run(mon, [0.0, 0.12, 0.25])
    assert [e.to_state for e in ev] == ["watch", "alert"]
    assert mon.state == "alert"


def test_hysteresis_band_changes_nothing(policy):
    mon = SeriesMonitor("s", policy)
    run(mon, [0.12])
    assert mon.state == "watch"
    assert run(mon, [0.07, 0.09, 0.06]) == []
    assert mon.state == "watch"


def test_watch_exits_below_exit_watch(policy):
    mon = SeriesMonitor("s", policy)
    run(mon, [0.12, 0.01])
    assert mon.state == "healthy"


def test_repeated_alerts_deduplicated(policy):
    mon = SeriesMonitor("s", policy)
    ev = run(mon, [0.3, 0.4, 0.5, 0.9])
    assert sum(1 for e in ev if e.to_state == "alert") == 1
    assert mon.counters()["suppressed_repeats"] == 3


def test_resolve_requires_consecutive_windows(policy):
    mon = SeriesMonitor("s", policy)
    run(mon, [0.3, 0.01])
    assert mon.state == "alert"
    run(mon, [0.15])
    run(mon, [0.01])
    assert mon.state == "alert"
    run(mon, [0.01])
    assert mon.state == "resolved"


def test_cooldown_suppresses_then_returns_healthy(policy):
    mon = SeriesMonitor("s", policy)
    run(mon, [0.3, 0.01, 0.01])
    assert mon.state == "resolved"
    run(mon, [0.5, 0.5])
    assert mon.state == "resolved"
    assert mon.counters()["suppressed_by_cooldown"] == 2
    ev = run(mon, [0.5])
    assert [e.to_state for e in ev] == ["healthy", "alert"]


def test_min_n_skips_small_windows(policy):
    mon = SeriesMonitor("s", policy)
    assert run(mon, [0.9], n=5) == []
    assert mon.counters()["skipped"] == 1
    assert mon.state == "healthy"


def test_missing_value_skips(policy):
    mon = SeriesMonitor("s", policy)
    assert run(mon, [None]) == []
    assert mon.state == "healthy"


def test_maintenance_window_suppresses(policy):
    mon = SeriesMonitor("s", policy)
    assert run(mon, [0.9], maint={0}) == []
    assert mon.counters()["suppressed_by_maintenance"] == 1
    assert mon.state == "healthy"


def test_acknowledge_only_from_alert(policy):
    mon = SeriesMonitor("s", policy)
    with pytest.raises(InvalidTransition):
        mon.acknowledge("w0", "op")
    run(mon, [0.3])
    ev = mon.acknowledge("w1", "op")
    assert ev.to_state == "acknowledged"
    with pytest.raises(InvalidTransition):
        mon.acknowledge("w2", "op")


def test_acknowledged_still_resolves(policy):
    mon = SeriesMonitor("s", policy)
    run(mon, [0.3])
    mon.acknowledge("w1", "op")
    run(mon, [0.01, 0.01])
    assert mon.state == "resolved"


def test_reset_clears_counters(policy):
    mon = SeriesMonitor("s", policy)
    run(mon, [0.3, 0.01])
    ev = mon.reset("w9", "op")
    assert ev.to_state == "healthy" and mon.below_count == 0 and mon.cooldown_remaining == 0


def test_history_records_every_window(policy):
    mon = SeriesMonitor("s", policy)
    run(mon, [0.0, None, 0.3], n=100)
    assert [h["note"] for h in mon.history] == ["evaluated", "skipped", "evaluated"]


def test_policy_validation():
    with pytest.raises(ValueError):
        AlertPolicy(enter_watch=0.3, enter_alert=0.2, exit_watch=0.1, exit_alert=0.1)
    with pytest.raises(ValueError):
        AlertPolicy(enter_watch=0.1, enter_alert=0.2, exit_watch=0.05, exit_alert=0.3)
    with pytest.raises(ValueError):
        AlertPolicy(enter_watch=0.1, enter_alert=0.2, exit_watch=0.05, exit_alert=0.1, resolve_after=0)


def test_no_retrain_action_exists():
    assert not any("retrain" in name.lower() for name in dir(SeriesMonitor))
