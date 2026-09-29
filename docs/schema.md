# Prediction event schema

Machine-readable definition: `schemas/prediction_event.json`. One JSON object per line.
Sibling projects can emit this shape so their predictions can be monitored here.

| field | type | meaning |
|---|---|---|
| `event_id` | string | unique identifier of the scored event; repeats are dropped and counted |
| `timestamp` | string | event time, ISO 8601 with timezone; windows are cut on this |
| `model_id` | string | which model produced the score |
| `model_version` | string | version string; a change is reported under schema |
| `features` | object | feature name to value; number, string, boolean or null |
| `score` | number | model output used for the decision |
| `decision` | string | categorical decision taken from the score |
| `route` | string | where the event went next (auto, queue name, review desk) |
| `label` | integer or null | ground truth when known; null until it arrives |
| `label_available_at` | string or null | when the label became or will become known; null when none exists |
| `scored_at` | string or null | optional; when the score was produced; latency is `scored_at` minus `timestamp` |

Rules the loader enforces: every required field present, correct types, timestamps with a
timezone. Rules the monitor enforces: a label counts only when `label_available_at` is at
or before the configured `as_of`; events after `as_of` are excluded entirely.
