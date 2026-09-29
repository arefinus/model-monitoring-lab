from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest
from conftest import T0, iso, make_event

from model_monitoring_lab.checks.distribution import js_distance, ks_statistic, psi, reference_bins, summary
from model_monitoring_lab.checks.outcomes import calibration, decision_rates, latency, workload
from model_monitoring_lab.checks.quality import category_change, feature_field_set, missingness, schema_change


def test_psi_zero_on_identical_distribution():
    ref = np.random.default_rng(0).normal(size=2000)
    b = reference_bins(ref, bins=10)
    assert psi(b, ref)["value"] < 0.01


def test_psi_grows_with_shift():
    rng = np.random.default_rng(0)
    ref = rng.normal(size=2000)
    b = reference_bins(ref)
    small = psi(b, rng.normal(0.2, size=2000))["value"]
    large = psi(b, rng.normal(2.0, size=2000))["value"]
    assert 0 <= small < large


def test_psi_bin_counts_sum_to_n():
    ref = np.random.default_rng(0).normal(size=500)
    b = reference_bins(ref)
    r = psi(b, ref[:123])
    assert sum(r["bin_counts"]) == r["n"] == 123


def test_ks_bounds_and_identity():
    rng = np.random.default_rng(1)
    a = rng.normal(size=300)
    assert ks_statistic(a, a)["value"] == 0.0
    v = ks_statistic(a, rng.normal(3, size=300))["value"]
    assert 0.5 < v <= 1.0


def test_js_bounded_and_monotone():
    ref = np.random.default_rng(0).normal(size=500)
    b = reference_bins(ref)
    assert 0.0 <= js_distance(b, ref)["value"] <= 1.0
    assert js_distance(b, ref + 50)["value"] > js_distance(b, ref)["value"]


def test_summary_handles_empty():
    assert summary([])["n"] == 0


def test_missingness_rate():
    evs = [make_event(i) for i in range(10)]
    for e in evs[:3]:
        e["features"]["income"] = None
    m = missingness(evs, ["income", "amount"])
    assert m["income"]["rate"] == pytest.approx(0.3) and m["amount"]["rate"] == 0.0


def test_schema_change_detects_added_and_removed():
    ref = feature_field_set([make_event(0)])
    ev = make_event(1)
    ev["features"].pop("income")
    ev["features"]["device_type"] = "ios"
    r = schema_change(ref, [ev])
    assert r["added_fields"] == ["device_type"] and r["removed_fields"] == ["income"] and r["changed"]


def test_category_change_detects_new_value():
    ev = make_event(0)
    ev["features"]["region"] = "west"
    r = category_change({"north", "south"}, [ev], "region")
    assert r["new_values"] == ["west"] and r["new_value_count"] == 1 and r["changed"]
    assert not category_change({"north"}, [make_event(0)], "region")["changed"]


def test_calibration_null_without_labels():
    evs = [make_event(i) for i in range(50)]
    r = calibration(evs, T0 + timedelta(days=30))
    assert r["performance"] is None and r["n_labelled"] == 0


def test_calibration_respects_label_delay():
    avail = iso(T0 + timedelta(days=5))
    evs = [make_event(i, label=1, label_available_at=avail) for i in range(60)]
    early = calibration(evs, T0 + timedelta(days=1))
    late = calibration(evs, T0 + timedelta(days=10))
    assert early["performance"] is None and early["n_labels_pending"] == 60
    assert late["performance"] is not None and late["n_labelled"] == 60


def test_calibration_ece_bins_carry_counts():
    rng = np.random.default_rng(2)
    evs = []
    for i in range(400):
        p = float(rng.uniform())
        evs.append(make_event(i, score=p, label=int(rng.uniform() < p), label_available_at=iso(T0)))
    perf = calibration(evs, T0 + timedelta(days=1), bins=10, min_labels=30)["performance"]
    assert sum(b["count"] for b in perf["bins"]) == 400
    assert 0 <= perf["ece"] < 0.2


def test_calibration_below_min_labels_is_null():
    evs = [make_event(i, label=0, label_available_at=iso(T0)) for i in range(10)]
    assert calibration(evs, T0 + timedelta(days=1), min_labels=30)["performance"] is None


def test_latency_percentiles_and_negatives():
    evs = [make_event(i) for i in range(5)]
    bad = make_event(9, scored_at=iso(T0))
    r = latency(evs + [bad])
    assert r["n"] == 6 and r["negative"] == 1 and r["p95_ms"] >= r["p50_ms"]


def test_decision_rates_and_workload_sum_to_one():
    evs = [make_event(i, decision="approve" if i % 2 else "decline", route="q1" if i % 3 else "q2") for i in range(12)]
    assert sum(decision_rates(evs)["rates"].values()) == pytest.approx(1.0)
    assert sum(workload(evs)["share"].values()) == pytest.approx(1.0)
