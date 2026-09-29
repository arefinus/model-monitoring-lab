"""Validation of prediction events against schemas/prediction_event.json.

A small hand-written validator is used so the repository has no dependency beyond the
standard library for this step. It supports the subset of JSON Schema the file uses:
``required``, ``additionalProperties: false``, ``type`` (single or list), ``minLength``,
``minimum`` and ``maximum``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PACKAGE_ROOT / "schemas" / "prediction_event.json"

_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


class EventSchemaError(ValueError):
    """Raised when an event does not match the prediction event schema."""


@dataclass(frozen=True)
class EventSchema:
    required: tuple[str, ...]
    properties: dict[str, dict[str, Any]]
    additional_properties: bool

    @classmethod
    def load(cls, path: Path = SCHEMA_PATH) -> "EventSchema":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            required=tuple(raw["required"]),
            properties=dict(raw["properties"]),
            additional_properties=bool(raw.get("additionalProperties", True)),
        )

    def validate(self, event: dict[str, Any]) -> list[str]:
        """Return a list of problems; empty means valid."""
        problems: list[str] = []
        if not isinstance(event, dict):
            return ["event is not an object"]
        for key in self.required:
            if key not in event:
                problems.append(f"missing required field {key!r}")
        if not self.additional_properties:
            for key in event:
                if key not in self.properties:
                    problems.append(f"unexpected field {key!r}")
        for key, spec in self.properties.items():
            if key not in event:
                continue
            problems.extend(_check_value(key, event[key], spec))
        return problems

    def require_valid(self, event: dict[str, Any]) -> None:
        problems = self.validate(event)
        if problems:
            raise EventSchemaError(f"event {event.get('event_id', '<no id>')!r}: " + "; ".join(problems))


def _check_value(key: str, value: Any, spec: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    types = spec.get("type")
    if types is not None:
        allowed = types if isinstance(types, list) else [types]
        if not any(_TYPE_CHECKS[t](value) for t in allowed):
            problems.append(f"field {key!r} has type {type(value).__name__}, expected {allowed}")
            return problems
    if isinstance(value, str):
        if "minLength" in spec and len(value) < spec["minLength"]:
            problems.append(f"field {key!r} is shorter than {spec['minLength']}")
        if spec.get("format") == "date-time":
            try:
                parse_timestamp(value)
            except ValueError:
                problems.append(f"field {key!r} is not an ISO 8601 date-time: {value!r}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in spec and value < spec["minimum"]:
            problems.append(f"field {key!r} below minimum {spec['minimum']}")
        if "maximum" in spec and value > spec["maximum"]:
            problems.append(f"field {key!r} above maximum {spec['maximum']}")
    return problems


def parse_timestamp(value: str) -> datetime:
    """Parse ISO 8601 with a mandatory timezone; 'Z' is accepted."""
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp {value!r} has no timezone")
    return parsed
