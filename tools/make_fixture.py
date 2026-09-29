"""Generate the authored synthetic reference and shifted prediction streams (fixture v1).

Usage: python tools/make_fixture.py [--seed 42] [--out examples/fixtures/v1]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from model_monitoring_lab.synthetic import (  # noqa: E402
    fixture_card,
    generate_stream,
    reference_spec,
    shifted_spec,
    write_jsonl,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=ROOT / "examples" / "fixtures" / "v1")
    args = parser.parse_args(argv)
    reference = generate_stream(reference_spec(args.seed))
    shifted = generate_stream(shifted_spec(args.seed))
    write_jsonl(reference, args.out / "reference.jsonl")
    write_jsonl(shifted, args.out / "shifted.jsonl")
    (args.out / "FIXTURE.md").write_text(fixture_card(args.seed, len(reference), len(shifted)), encoding="utf-8")
    print(f"reference: {len(reference)} events; shifted: {len(shifted)} events -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
