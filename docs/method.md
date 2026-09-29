# Method

## 1. Streams and windows (`stream.py`)

Events are validated one by one against `schemas/prediction_event.json`. Repeated
`event_id` values are dropped and counted; events later than `as_of` are excluded and
counted; events are sorted by event time and the number whose file position disagrees with
time order is reported. Windows are fixed-size (`window_days`, default one day) and cover
the stream without gaps; a window with fewer than `min_n` events has status `no_data` and
never changes an alert state.

## 2. Reference (`monitor.py`)

The reference stream fixes: quantile bin edges per numeric feature and for the score
(`psi_bins`), the set of feature fields, the set of values per categorical feature, and
latency percentiles. Nothing from the test stream enters the reference.

## 3. Checks per window (`checks/`)

- Schema: fields added or removed relative to the reference; model versions present.
- Missingness: rate per configured feature.
- Categories: new values and their count, unseen reference values.
- Distribution drift per numeric feature and for the score: PSI on the reference
  quantile bins with epsilon smoothing, two-sample KS statistic, Jensen-Shannon distance on
  the same bins. Each result carries `n` and, for PSI, the bin counts.
- Decisions and workload: decision rates and route shares.
- Calibration: computed only from events whose `label_available_at` is at or before
  `as_of`, and only when at least `min_labels` such events exist; otherwise `performance`
  is null with a reason. ECE uses `ece_bins` equal-width bins and reports the count per bin.
- Latency: `scored_at` minus `timestamp` in milliseconds, p50, p95, max, and the number
  of negative values (clock problems).

Without labels the report shows data and prediction drift; it never reports a
performance degradation it did not measure.

## 4. Threshold selection and locking (`alerts/thresholds.py`, `run.py`)

For each drift statistic (PSI, KS, JS) the pipeline generates `validation.n_clean` clean
streams and `validation.n_drifted` drifted streams with seeds distinct from the fixture,
computes the per-window statistic on each, and chooses enter/exit thresholds from the two
empirical distributions (see the module for the exact rule). Whether the two distributions
were separable is recorded as `separated`. Thresholds are written to
`configs/locked_thresholds.yaml` with the seeds, sizes and kinds of the streams used, then
applied unchanged to the test stream. Rule-based series (missingness delta, new category,
schema change, latency ratio) use the documented settings in `configs/default.yaml`.

## 5. Alert state machine (`alerts/state_machine.py`)

States: healthy, watch, alert, acknowledged, resolved. Per series:

- values at or above `enter_alert` move to alert; at or above `enter_watch` move to watch;
  below `exit_watch` or `exit_alert` move down; the band between enter and exit is the
  hysteresis band and changes nothing;
- windows with a null value or fewer than `min_n` events are skipped;
- while in alert or acknowledged, repeated exceedances are counted as suppressed repeats
  and produce no new event (deduplication);
- leaving alert or acknowledged needs `resolve_after` consecutive windows below
  `exit_alert`;
- resolved holds for `cooldown_windows` windows, suppressing exceedances inside it, then
  returns to healthy and re-evaluates;
- windows inside a declared maintenance window change nothing and count suppressions;
- acknowledge is a human action valid only from alert; reset returns to healthy;
- there is no retrain or redeploy action.

The demo simulates an operator acknowledging one window after each alert so the full
state path is visible (`simulate_acknowledge_after_windows`).

## 6. Outputs

`monitoring_report.json` (per-window checks and the flat `series` map),
`threshold_selection.json`, `alert_timeline.json` (transitions, per-series history,
counters, final states), `portfolio.json` (featured series with per-window state, alerts,
`mode: synthetic-demo`), `run_manifest.yaml`, and SVG figures drawn from those files.
