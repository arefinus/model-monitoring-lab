# Evaluation

## Protocol
Thresholds for the drift statistics are selected on separate simulated validation streams
(three clean, three drifted, seeds distinct from the fixture) and locked before the test
stream is checked. The shifted fixture stream is the locked test stream. Detection delay
is read off the alert timeline against the scripted change schedule in
`examples/fixtures/v1/FIXTURE.md`. Performance metrics are computed only when labels are
available at `as_of`; otherwise they are null.

## Where the numbers are
`examples/output/monitoring_report.json`, `alert_timeline.json`, `threshold_selection.json`
and `portfolio.json` after `demo`; `examples/output/smoke/` after `smoke`. All values are
`demo`, computed on synthetic fixture v1 (seed 42). Not a benchmark result.

## Local test run (2026-09-27)
```
python -m pytest -q
51 passed in 35.93s
```

## Behaviours the tests lock
- delayed labels: calibration is null before `label_available_at`, computed after;
- clock ordering: out-of-order events are sorted and counted;
- missing windows: `no_data` windows never change state;
- small samples: `min_n` blocks alerts;
- repeated alerts are deduplicated; cooldown and maintenance windows suppress;
- schema migration is detected as added and removed fields;
- acknowledge is valid only from alert; reset clears counters;
- no performance metric exists without labels;
- the fixture generator is deterministic for a seed.
