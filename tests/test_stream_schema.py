from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import T0, make_event

from model_monitoring_lab.schema import EventSchema, EventSchemaError, parse_timestamp
from model_monitoring_lab.stream import build_stream, windows


@pytest.fixture
def schema():
    return EventSchema.load()


def test_schema_rejects_missing_required(schema):
    ev = make_event(1)
    del ev["score"]
    assert any("score" in p for p in schema.validate(ev))
    with pytest.raises(EventSchemaError):
        schema.require_valid(ev)


def test_schema_rejects_bad_type(schema):
    ev = make_event(1, score="high")
    assert schema.validate(ev)


def test_schema_accepts_null_label(schema):
    assert schema.validate(make_event(1)) == []


def test_duplicate_event_ids_dropped(schema):
    raw = [make_event(1), make_event(1), make_event(2)]
    s = build_stream(raw, schema)
    assert len(s) == 2 and s.duplicates_dropped == 1


def test_out_of_order_counted_and_sorted(schema):
    raw = [make_event(2), make_event(1), make_event(3)]
    s = build_stream(raw, schema)
    ts = [parse_timestamp(e["timestamp"]) for e in s.events]
    assert ts == sorted(ts)
    assert s.out_of_order >= 1


def test_future_events_excluded_by_as_of(schema):
    raw = [make_event(i) for i in range(5)]
    s = build_stream(raw, schema, as_of=T0 + timedelta(minutes=2))
    assert len(s) == 3 and s.excluded_future == 2


def test_empty_stream_raises(schema):
    with pytest.raises(ValueError):
        build_stream([], schema)
    with pytest.raises(ValueError):
        build_stream([make_event(5)], schema, as_of=T0)


def test_windows_cover_stream_without_gaps(schema):
    raw = [make_event(i, ts=T0 + timedelta(hours=6 * i)) for i in range(12)]
    s = build_stream(raw, schema)
    ws = windows(s, timedelta(days=1))
    assert len(ws) in (3, 4)
    assert sum(w.n for w in ws) == 12
    assert all(ws[i].end == ws[i + 1].start for i in range(len(ws) - 1))


def test_windows_can_be_empty_when_range_forced(schema):
    raw = [make_event(i) for i in range(3)]
    s = build_stream(raw, schema)
    ws = windows(s, timedelta(days=1), start=T0, end=T0 + timedelta(days=3))
    assert len(ws) == 3 and ws[1].n == 0 and ws[2].n == 0


def test_parse_timestamp():
    assert parse_timestamp("2026-07-01T00:00:00Z").tzinfo is not None
    with pytest.raises(ValueError):
        parse_timestamp("not a date")
