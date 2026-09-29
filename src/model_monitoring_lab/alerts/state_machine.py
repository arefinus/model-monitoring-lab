"""Alert state machine: healthy -> watch -> alert -> acknowledged -> resolved -> healthy.

Rules, per monitored series:

- ``enter_watch`` and ``enter_alert`` are the thresholds a value must reach to move up;
  ``exit_watch`` and ``exit_alert`` are the lower thresholds it must fall below to move
  down. The gap between enter and exit is the hysteresis band; a value inside the band
  changes nothing.
- A window with no value, or with fewer than ``min_n`` observations, never changes the
  state (``skipped``).
- While in ``alert`` or ``acknowledged``, further exceedances are deduplicated: they are
  counted as ``suppressed_repeats`` and emit no new alert event.
- Leaving ``alert``/``acknowledged`` requires ``resolve_after`` consecutive windows below
  ``exit_alert``.
- ``resolved`` holds for ``cooldown_windows`` windows; exceedances inside the cooldown are
  counted as ``suppressed_by_cooldown``. When the cooldown elapses the series returns to
  ``healthy`` and the current value is evaluated again.
- Windows inside a maintenance window change nothing; exceedances are counted as
  ``suppressed_by_maintenance``.
- ``acknowledge`` is a human action and is only valid from ``alert``. ``reset`` returns to
  ``healthy`` and clears every counter. There is no automatic retraining action anywhere.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

STATES = ("healthy", "watch", "alert", "acknowledged", "resolved")


class InvalidTransition(RuntimeError):
    """Raised for a human action that is not valid in the current state."""


@dataclass(frozen=True)
class AlertPolicy:
    enter_watch: float
    enter_alert: float
    exit_watch: float
    exit_alert: float
    min_n: int = 1
    resolve_after: int = 2
    cooldown_windows: int = 2

    def __post_init__(self) -> None:
        if not (self.exit_watch <= self.enter_watch <= self.enter_alert):
            raise ValueError("require exit_watch <= enter_watch <= enter_alert")
        if not (self.exit_alert <= self.enter_alert):
            raise ValueError("require exit_alert <= enter_alert")
        if self.resolve_after < 1 or self.cooldown_windows < 0 or self.min_n < 0:
            raise ValueError("resolve_after must be >= 1; cooldown_windows and min_n must be >= 0")


@dataclass(frozen=True)
class AlertEvent:
    window: str
    series: str
    from_state: str
    to_state: str
    value: float | None
    threshold: float | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SeriesMonitor:
    series: str
    policy: AlertPolicy
    state: str = "healthy"
    below_count: int = 0
    cooldown_remaining: int = 0
    suppressed_repeats: int = 0
    suppressed_by_cooldown: int = 0
    suppressed_by_maintenance: int = 0
    skipped: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    def _event(self, window: str, to_state: str, value: float | None, threshold: float | None, reason: str) -> AlertEvent:
        event = AlertEvent(window, self.series, self.state, to_state, value, threshold, reason)
        self.state = to_state
        return event

    def observe(self, window: str, value: float | None, n: int, in_maintenance: bool = False) -> list[AlertEvent]:
        events: list[AlertEvent] = []
        p = self.policy
        if in_maintenance:
            if value is not None and value >= p.enter_alert:
                self.suppressed_by_maintenance += 1
            self._record(window, value, n, "maintenance")
            return events
        if value is None or n < p.min_n:
            self.skipped += 1
            self._record(window, value, n, "skipped")
            return events

        if self.state == "resolved":
            if self.cooldown_remaining > 0:
                self.cooldown_remaining -= 1
                if value >= p.enter_alert:
                    self.suppressed_by_cooldown += 1
                self._record(window, value, n, "cooldown")
                return events
            events.append(self._event(window, "healthy", value, None, "cooldown elapsed"))

        if self.state == "healthy":
            if value >= p.enter_alert:
                events.append(self._event(window, "alert", value, p.enter_alert, "value reached enter_alert"))
                self.below_count = 0
            elif value >= p.enter_watch:
                events.append(self._event(window, "watch", value, p.enter_watch, "value reached enter_watch"))
        elif self.state == "watch":
            if value >= p.enter_alert:
                events.append(self._event(window, "alert", value, p.enter_alert, "value reached enter_alert"))
                self.below_count = 0
            elif value < p.exit_watch:
                events.append(self._event(window, "healthy", value, p.exit_watch, "value fell below exit_watch"))
        elif self.state in ("alert", "acknowledged"):
            if value >= p.enter_alert:
                self.suppressed_repeats += 1
                self.below_count = 0
            elif value < p.exit_alert:
                self.below_count += 1
                if self.below_count >= p.resolve_after:
                    events.append(self._event(window, "resolved", value, p.exit_alert, f"below exit_alert for {p.resolve_after} windows"))
                    self.cooldown_remaining = p.cooldown_windows
                    self.below_count = 0
            else:
                self.below_count = 0  # inside the hysteresis band
        self._record(window, value, n, "evaluated")
        return events

    def acknowledge(self, window: str, actor: str) -> AlertEvent:
        if self.state != "alert":
            raise InvalidTransition(f"{self.series}: acknowledge is only valid from 'alert', current state is {self.state!r}")
        return self._event(window, "acknowledged", None, None, f"acknowledged by {actor}")

    def reset(self, window: str, actor: str) -> AlertEvent:
        event = self._event(window, "healthy", None, None, f"reset by {actor}")
        self.below_count = 0
        self.cooldown_remaining = 0
        return event

    def _record(self, window: str, value: float | None, n: int, note: str) -> None:
        self.history.append({"window": window, "value": value, "n": n, "state": self.state, "note": note})

    def counters(self) -> dict[str, int]:
        return {
            "suppressed_repeats": self.suppressed_repeats,
            "suppressed_by_cooldown": self.suppressed_by_cooldown,
            "suppressed_by_maintenance": self.suppressed_by_maintenance,
            "skipped": self.skipped,
        }
