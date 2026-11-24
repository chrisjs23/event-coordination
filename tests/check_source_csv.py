#!/usr/bin/env python3
"""Check a source CSV's structural contract without exposing row values."""

import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = ROOT / "event-planning-coordination-brief" / "references" / "sheets.json"


class ContractError(Exception):
    """A safe, user-facing validation error."""


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
    required = list(fields)

    try:
        with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            try:
                header = next(reader)
            except StopIteration:
                raise ContractError("CSV is empty; header is missing")

            if not header or any(name == "" for name in header):
                raise ContractError("CSV header contains a blank column name")
            if len(set(header)) != len(header):
                raise ContractError("CSV header contains duplicate column names")
            missing = [name for name in required if name not in header]
            if missing:
                raise ContractError("CSV header is missing required columns")

            key_index = header.index(key)
            identities = set()
            count = 0
            for row in reader:
                line = reader.line_num
                if len(row) != len(header):
                    raise ContractError(f"CSV row {line} has a malformed width")
                identity = row[key_index].strip()
                if not identity:
                    raise ContractError(f"CSV row {line} has a blank identity")
                if identity in identities:
                    raise ContractError(f"CSV row {line} has a duplicate identity")
                identities.add(identity)
                count += 1
    except ContractError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ContractError("cannot read CSV source") from exc

    if count == 0:
        raise ContractError("CSV has no records")
    return count


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
