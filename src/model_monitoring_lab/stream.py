"""Loading, ordering and windowing of prediction event streams."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from .schema import EventSchema, EventSchemaError, parse_timestamp


@dataclass(frozen=True)
class Stream:
    events: tuple[dict[str, Any], ...]      # sorted by timestamp
    out_of_order: int                       # events whose file position disagreed with time order
    excluded_future: int                    # events after as_of, dropped
    duplicates_dropped: int                 # repeated event_id, later copy dropped
    start: datetime
    end: datetime

    def __len__(self) -> int:
        return len(self.events)


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"stream not found: {path}. Generate fixtures with `python tools/make_fixture.py`.")
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise EventSchemaError(f"{path}:{line_no}: invalid JSON ({exc.msg})") from exc


def load_stream(path: Path, schema: EventSchema, as_of: datetime | None = None) -> Stream:
    return build_stream(list(read_jsonl(path)), schema, as_of)


def build_stream(raw: list[dict[str, Any]], schema: EventSchema, as_of: datetime | None = None) -> Stream:
    if not raw:
        raise ValueError("stream is empty")
    for event in raw:
        schema.require_valid(event)
    seen: set[str] = set()
    kept: list[tuple[datetime, int, dict[str, Any]]] = []
    duplicates = 0
    future = 0
    for position, event in enumerate(raw):
        if event["event_id"] in seen:
            duplicates += 1
            continue
        seen.add(event["event_id"])
        ts = parse_timestamp(event["timestamp"])
        if as_of is not None and ts > as_of:
            future += 1
            continue
        kept.append((ts, position, event))
    if not kept:
        raise ValueError("no events remain after excluding events later than as_of")
    ordered = sorted(kept, key=lambda t: (t[0], t[1]))
    out_of_order = sum(1 for k, (_, position, _) in enumerate(ordered) if position != sorted(p for _, p, _ in kept)[k])
    return Stream(
        events=tuple(e for _, _, e in ordered),
        out_of_order=out_of_order,
        excluded_future=future,
        duplicates_dropped=duplicates,
        start=ordered[0][0],
        end=ordered[-1][0],
    )


@dataclass(frozen=True)
class Window:
    index: int
    start: datetime
    end: datetime
    events: tuple[dict[str, Any], ...]

    @property
    def n(self) -> int:
        return len(self.events)

    @property
    def label(self) -> str:
        return self.start.strftime("%Y-%m-%d")


def windows(stream: Stream, size: timedelta, start: datetime | None = None, end: datetime | None = None) -> list[Window]:
    """Fixed windows covering [start, end); windows with no events are emitted with n = 0."""
    if size <= timedelta(0):
        raise ValueError("window size must be positive")
    first = start or stream.start.replace(hour=0, minute=0, second=0, microsecond=0)
    last = end or (stream.end + size)
    out: list[Window] = []
    cursor = first
    index = 0
    events = list(stream.events)
    pointer = 0
    while cursor < last:
        nxt = cursor + size
        bucket: list[dict[str, Any]] = []
        while pointer < len(events) and parse_timestamp(events[pointer]["timestamp"]) < nxt:
            if parse_timestamp(events[pointer]["timestamp"]) >= cursor:
                bucket.append(events[pointer])
            pointer += 1
        out.append(Window(index=index, start=cursor, end=nxt, events=tuple(bucket)))
        cursor = nxt
        index += 1
    return out
