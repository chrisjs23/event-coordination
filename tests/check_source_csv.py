#!/usr/bin/env python3
"""Check a source CSV's structural contract without exposing row values."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "event-planning-coordination-brief" / "scripts"))
from records import SourceError, read_sheet


ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = ROOT / "event-planning-coordination-brief" / "references" / "sheets.json"


ContractError = SourceError


def validate(source, csv_path):
    try:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError("cannot read source contract") from exc

    if not isinstance(contract, dict) or source not in contract:
        raise ContractError(f"unknown source: {source}")
    spec = contract[source]
    if not isinstance(spec, dict):
        raise ContractError("source contract is invalid")
    fields = spec.get("fields")
    key = spec.get("key")
    if not isinstance(fields, dict) or not isinstance(key, str) or key not in fields:
        raise ContractError("source contract is invalid")
    try:
        parsed = read_sheet(Path(csv_path).read_bytes(), spec)
    except SourceError:
        raise
    except OSError as exc:
        raise ContractError("cannot read CSV source") from exc
    return len(parsed["records"])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("usage: python3 tests/check_source_csv.py <source> <csv-file>", file=sys.stderr)
        return 2
    try:
        count = validate(argv[0], argv[1])
    except ContractError as exc:
        print(f"invalid source CSV: {exc}", file=sys.stderr)
        return 1
    print(f"valid source CSV: {count} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
