# model-monitoring-lab

An analytics or ML operations team needs to know when the data feeding a model, or the
model's own behaviour, has changed enough to justify investigation. This repository checks
prediction streams window by window for schema changes, missingness, category drift,
distribution drift, score drift, calibration once labels arrive, workload and latency, and
turns those series into alerts through a documented state machine.

**Status:** `demo_ready` (runs end to end on authored synthetic fixtures; no real-data
evaluation performed in this repository). Label: `original_project`.

## Problem and user

The user operates one or more scoring models and receives their prediction events as a
stream. The decision supported is whether a change deserves an investigation ticket now,
a watch, or nothing. Inputs are events in the schema at `schemas/prediction_event.json`.
Outputs are a monitoring report per window, an alert timeline, locked thresholds with
their provenance, and a portfolio export. Nothing here retrains or redeploys a model.

## Demo

```
python -m model_monitoring_lab smoke     # first ten windows, under 30 s
python -m model_monitoring_lab demo      # full stream, alerts, figures
```

`demo` reads the reference stream and the shifted stream from `examples/fixtures/v1/`,
selects and locks thresholds on separate simulated validation streams, checks the test
stream, runs the alert state machine, and writes `examples/output/` plus SVG figures under
`docs/figures/`. Every number in those files was computed by that run on synthetic fixture
v1 (seed 42) and is labelled `demo`.

## Implementation status

Implemented and tested: event schema validation; stream loading with duplicate dropping,
out-of-order counting and an `as_of` cut; fixed-size windows; schema and category change
detection; missingness; PSI, KS and Jensen-Shannon drift indicators with documented
binning; score drift; decision and route workload; latency percentiles; calibration with
bin counts computed only from labels available at `as_of`, otherwise reported as null with
a reason; threshold selection on separate validation streams then locking; the alert
state machine healthy, watch, alert, acknowledged, resolved with hysteresis, minimum
sample size, deduplication, cooldown, resolve-after, and maintenance windows; portfolio
export; run manifest.

Not implemented (`proposed`): connectors to live queues, notification delivery,
multi-model dashboards, any automatic retraining or deployment action.

## Quickstart (offline, CPU, under a minute)

```
pip install -e . && pip install pytest
python tools/make_fixture.py
python -m model_monitoring_lab smoke
python -m pytest -q
```

Without an editable install, prefix commands with `PYTHONPATH=src`.

## Data

Only the authored synthetic fixture ships with this repository (see
`examples/fixtures/v1/FIXTURE.md` and `DATA_CARD.md`). Real streams must be exported in the
documented schema; the loader validates every event and refuses anything else with the
offending field named.

## Architecture / method

`docs/method.md` describes the checks, the drift statistics and their binning, the
calibration rule, threshold selection and locking, and the alert state machine.
`docs/schema.md` documents the event schema so sibling projects can emit it.

## Train, validate, test

There is no trained model here. Thresholds are the tunable part: they are selected on
clean and drifted validation streams generated with different seeds, written to
`configs/locked_thresholds.yaml` with their provenance, and applied unchanged to the test
stream. Rule-based series (missingness, new category, schema change) use documented
settings from `configs/default.yaml`.

## Results and provenance

`examples/output/monitoring_report.json`, `alert_timeline.json`, `threshold_selection.json`
and `portfolio.json` carry `evidence: "demo"`; `run_manifest.yaml` records the fixture
hashes, configuration hash and seed. Without labels the report shows data and prediction
drift only; performance metrics are null with a stated reason, never inferred.

## Limitations

Synthetic streams; thresholds selected on simulated drift are settings, not calibrated
operating points for any real system; PSI and KS on small windows are noisy, which is why
`min_n` exists; the calibration check needs labels and waits for them; maintenance windows
are declared, not detected.

## License and sources

MIT, copyright 2026 Md Sultanul Arefin Sourav. See `NOTICE.md` for provenance. No
third-party data or code is redistributed.
