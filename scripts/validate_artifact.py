"""Validate one versioned pipeline artifact without modifying its input."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from audio_engine.validation import ARTIFACT_TYPES, ValidationReport, load_artifact_file


def _write_report(path: Path, report: ValidationReport) -> None:
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", required=True, choices=ARTIFACT_TYPES, dest="artifact_type")
    parser.add_argument("--input", required=True, type=Path, dest="input_path")
    parser.add_argument("--report", type=Path, help="optional full JSON validation report")
    parser.add_argument(
        "--allowed-input-root",
        type=Path,
        action="append",
        default=[],
        help="allowed root for filesystem source locators; repeat as needed",
    )
    parser.add_argument(
        "--allowed-output-root",
        type=Path,
        action="append",
        default=[],
        help="allowed root for collection output_path; repeat as needed",
    )
    args = parser.parse_args(argv)

    if args.report is not None:
        try:
            if args.report.resolve() == args.input_path.resolve():
                parser.error("--report must not overwrite --input")
        except (OSError, RuntimeError):
            parser.error("--input and --report paths must be resolvable")

    _, report = load_artifact_file(
        args.artifact_type,
        args.input_path,
        allowed_input_roots=args.allowed_input_root,
        allowed_output_roots=args.allowed_output_root,
    )
    if args.report is not None:
        try:
            _write_report(args.report, report)
        except OSError:
            print(
                json.dumps(
                    {
                        "artifact_type": args.artifact_type,
                        "valid": False,
                        "errors": [
                            {
                                "code": "report_write_failed",
                                "path": "/",
                                "message": "full validation report could not be written",
                            }
                        ],
                        "warnings": [],
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 2

    output = json.dumps(report.to_dict(concise=True), separators=(",", ":"), sort_keys=True)
    print(output, file=sys.stdout if report.valid else sys.stderr)
    return 0 if report.valid else 1


if __name__ == "__main__":  # pragma: no cover - exercised through smoke tests
    raise SystemExit(main())
