#!/usr/bin/env python3
"""Preflight entry point for the event planning coordination brief."""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse


EXPECTED_SCHEMA_ID = (
    "https://gitroll.dev/curriculum/challenges/event-coordination/snapshot.schema.json"
)
BUSINESS_CLOCK = "2026-08-26T12:00:00+08:00"
SHEETS = ("attendees", "budget", "vendors", "calendar")


def _parser():
    parser = argparse.ArgumentParser(
        description="Check local inputs or capture sources through the planning baseline."
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="validate local schema and source map")
    modes.add_argument("--through", choices=("planning-baseline", "decision-and-approval", "publication-validation"),
                       help="capture sources through the selected snapshot boundary")
    resume = parser.add_mutually_exclusive_group()
    resume.add_argument("--resume-baseline", action="store_true",
                        help="review a verified captured baseline without refreshing sources")
    resume.add_argument("--resume-review", action="store_true",
                        help="render a verified captured review into the four local drafts")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "deliverables",
        metavar="PATH",
        help="output root; full runs archive and replace earlier results (default: repository deliverables)",
    )
    return parser


def _load_json(path):
    try:
        with path.open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read valid JSON from {path}: {exc}") from exc


def _validate_inputs(root):
    schema_path = root / "snapshot.schema.json"
    source_map_path = root / "event-planning-coordination-brief" / "references" / "sheets.json"
    schema = _load_json(schema_path)
    source_map = _load_json(source_map_path)
    if not isinstance(schema, dict) or schema.get("$id") != EXPECTED_SCHEMA_ID:
        raise ValueError(f"unexpected or missing schema $id in {schema_path}")
    if not isinstance(source_map, dict):
        raise ValueError(f"source map must be a JSON object: {source_map_path}")
    for name in SHEETS:
        entry = source_map.get(name)
        if not isinstance(entry, dict):
            raise ValueError(f"source map entry {name!r} is missing or malformed")
        fields = entry.get("fields")
        key = entry.get("key")
        url = entry.get("url")
        if not isinstance(fields, dict) or not isinstance(key, str) or key not in fields:
            raise ValueError(f"source map entry {name!r} must have a key present in fields")
        if not isinstance(url, str) or urlparse(url).scheme != "https" or not urlparse(url).netloc:
            raise ValueError(f"source map entry {name!r} must have an HTTPS URL")
    return schema_path, source_map_path


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    if args.resume_baseline and args.through != "decision-and-approval":
        parser.error("--resume-baseline requires --through decision-and-approval")
    if args.resume_review and args.through != "publication-validation":
        parser.error("--resume-review requires --through publication-validation")
    if not args.check and not args.through:
        print(
            "Choose --through publication-validation for a new run; --check is available for preflight.",
            file=sys.stderr,
        )
        return 3

    root = Path(__file__).resolve().parents[2]
    try:
        schema_path, source_map_path = _validate_inputs(root)
    except ValueError as exc:
        print(f"Preflight failed: {exc}", file=sys.stderr)
        return 1

    output_dir = args.output_dir.expanduser().resolve()
    if args.through:
        try:
            from pipeline import run_baseline, resume_review
            from locking import output_lock
            if args.resume_review:
                from publication import publish_review
                with output_lock(output_dir):
                    report = publish_review(root, output_dir)
                report["basis"] = "captured-run-publication"
            elif args.resume_baseline:
                with output_lock(output_dir):
                    report = resume_review(root, output_dir)
            elif args.through == "publication-validation":
                from refresh import refresh_run
                report = refresh_run(root, output_dir)
            else:
                with output_lock(output_dir):
                    report = run_baseline(root, output_dir, through=args.through)
        except ImportError:
            print("Install dependencies from event-planning-coordination-brief/requirements.txt", file=sys.stderr)
            return 1
        except (ValueError, OSError) as exc:
            print(f"Capture failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, indent=2))
        return 0
    report = {
        "status": "ready",
        "mode": "preflight",
        "pipeline_available": True,
        "business_clock": BUSINESS_CLOCK,
        "output_dir": str(output_dir),
        "schema_path": str(schema_path),
        "source_map_path": str(source_map_path),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
