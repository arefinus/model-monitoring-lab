# Data card

## Synthetic prediction streams (the only data in this repository)

- Provider: this repository, `tools/make_fixture.py`, seed 42, fixture version v1.
- Terms: MIT, same as the code. Authored synthetic data; fictional identifiers
  (`SYN-EVT-...`, model id `demo-scorer`); not derived from any person, company, account,
  or dataset.
- Record unit: one prediction event (one scored request).
- Target: `label` is a binary outcome that becomes known at `label_available_at`; it is
  null until then. Monitoring never uses a label before that timestamp.
- Columns: see `schemas/prediction_event.json` and `docs/schema.md`. Numeric features
  `amount`, `tenure_months`, `income`; categorical `region`, `channel` (replaced by
  `device_type` after the scripted schema migration in the shifted stream).
- Temporal coverage: reference stream 24 days from 2026-06-01; shifted stream 24 days from
  2026-07-01, with the change schedule listed in `examples/fixtures/v1/FIXTURE.md`.
- Splits: reference stream fits the reference bins and field sets; validation streams
  (clean and drifted, other seeds, generated on the fly) select thresholds; the shifted
  stream is the locked test stream. No event appears in two roles.
- Missingness: scripted spike on `income` in the shifted stream; otherwise low and random.
- Duplicates: none by construction; the loader drops repeated `event_id` and counts them.
- Redistribution: the fixture may be regenerated at any time; it carries no rights beyond
  the repository licence.

## Adapting to real streams

Export events in the documented schema, one JSON object per line. Timestamps must be
ISO 8601 with a timezone. Set `as_of` in the config to the analysis time so that labels
that arrive later are excluded honestly. Keep a reference stream from a period you trust.
Threshold values in `configs/locked_thresholds.yaml` were selected on synthetic streams and
must be reselected on your own validation streams before they mean anything.
