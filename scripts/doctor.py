"""Validate local configuration and tools without contacting live services."""

from __future__ import annotations

import argparse
from pathlib import Path

from audio_engine.doctor import format_report, run_doctor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, help="YAML profile below an allowed input root")
    args = parser.parse_args(argv)
    if args.profile is None:
        parser.error("--profile is required")

    repo_root = Path(__file__).resolve().parents[1]
    report = run_doctor(args.profile, repo_root=repo_root)
    print(format_report(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
