# Contributing

Thank you for looking at this project. It is a small, deterministic monitoring tool, and the
rules below keep it that way.

## Ground rules

1. **No real data, ever.** Only authored synthetic fixtures under `examples/fixtures/`.
   Organisation names must be obviously fictional. Identifiers use the `SYN-` prefix.
2. **No performance without labels.** Never report a metric that needs labels when they are not yet available; return null with a reason.
3. **Determinism is a feature.** All randomness is
   in `synthetic.py` and is seeded. A change that makes the same seed
   produce a different stream must be deliberate and must update the fixture via
   `python tools/make_fixture.py` and the outputs in `docs/evaluation.md`.
4. **Every number in the docs is computed.** If you change behaviour, rerun
   `python -m model_monitoring_lab demo` and `python -m pytest -q` and paste the real
   output into `docs/evaluation.md`. Do not edit a number by hand.
5. **No retraining or deployment actions.** The alert state machine describes what the checks
   observed on a stream; acting on it is a human decision outside this code.

## Workflow

```
pip install -e . && pip install pytest
python -m model_monitoring_lab smoke
python -m pytest -q
```

Add a focused test for every behaviour change, including the failure case. Keep modules
under 300 lines. Type hints everywhere, frozen dataclasses where natural, no `print` in
library code (the CLI module is the only place that writes to stdout).

## Reporting problems

Open an issue with the config file, the fixture seed, the stream files (or the seed that
generated them) and the command you ran. Because runs are deterministic, that is enough to
reproduce any result exactly.
