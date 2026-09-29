# Reproducibility

## What is and is not reproduced
Every number in `examples/output/` and `docs/figures/` was computed by the commands below
on synthetic fixture v1 (seed 42) and carries the evidence label `demo`. Nothing here is a
benchmark result and nothing is reproduced from a publication.

## Exact commands
```
pip install -e . && pip install pytest          # or prefix commands with PYTHONPATH=src
python tools/make_fixture.py --seed 42          # regenerates examples/fixtures/v1
python -m model_monitoring_lab smoke            # first ten windows, validates outputs
python -m model_monitoring_lab demo             # full run, alerts, figures
python -m model_monitoring_lab check --reference examples/fixtures/v1/reference.jsonl --stream examples/fixtures/v1/shifted.jsonl
python -m model_monitoring_lab alerts --report examples/output/monitoring_report.json
python -m pytest -q
```
Set `OMP_NUM_THREADS=1` for bit-identical reruns.

## Determinism
The fixture generator is seeded; regenerating with the same seed gives byte-identical
streams (tested). Threshold selection uses seeded validation streams recorded with their
seeds in `threshold_selection.json` and `configs/locked_thresholds.yaml`.

## Run manifest
Each `smoke` and `demo` run writes `run_manifest.yaml`: mode, evidence status, fixture
SHA-256 hashes, configuration hash, seed, sample counts, window hash. `git_commit` is null
until the publishing tooling fills it and is never fabricated.

## Environment
Python 3.10 locally; CI runs 3.10, 3.11 and 3.12 on Ubuntu. Dependencies: numpy, scipy,
pyyaml. No GPU, network, API key or model service is needed.
