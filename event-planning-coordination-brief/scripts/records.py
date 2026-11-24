"""Structural and business-value validation for the disclosed source sheets."""

import csv
import datetime as dt
import io


class SourceError(ValueError):
    """Safe source validation error; messages never include source values."""


def _parse_csv(data):
    if not isinstance(data, bytes):
        raise SourceError("invalid sheet input")
    try:
        reader = csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
        header = next(reader)
        rows = list(reader)
    except StopIteration as exc:
        raise SourceError("CSV is empty; header is missing") from exc
    except (UnicodeError, csv.Error) as exc:
        raise SourceError("cannot read CSV source") from exc
    return header, rows


def _permitted_columns(header, rows, fields):
    """Serialize only declared columns, tolerating invalid widths and headers."""
    indexes = [index for index, name in enumerate(header) if name in fields]
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([header[index] for index in indexes])
    for row in rows:
        padded = row[:len(header)] + [""] * max(0, len(header) - len(row))
        writer.writerow([padded[index] for index in indexes])
    return output.getvalue().encode("utf-8")


def permitted_extract(data: bytes, spec: dict) -> bytes:
    """Return a CSV extract containing only declared headers, even if invalid."""
    if not isinstance(spec, dict) or not isinstance(spec.get("fields"), dict):
        raise SourceError("source contract is invalid")
    header, rows = _parse_csv(data)
    return _permitted_columns(header, rows, spec["fields"])


def read_sheet(data: bytes, spec: dict) -> dict:
    if not isinstance(data, bytes) or not isinstance(spec, dict):
        raise SourceError("invalid sheet input")
    fields, key = spec.get("fields"), spec.get("key")
    if not isinstance(fields, dict) or not isinstance(key, str) or key not in fields:
        raise SourceError("source contract is invalid")
    required = list(fields)
    try:
        header, rows = _parse_csv(data)
        if not header or any(not name.strip() for name in header):
            raise SourceError("CSV header contains a blank column name")
        if len(set(header)) != len(header):
            raise SourceError("CSV header contains duplicate column names")
        if any(name not in header for name in required):
            raise SourceError("CSV header is missing required columns")
        required_order = [name for name in header if name in fields]
        indexes = [header.index(name) for name in required_order]
        key_index = header.index(key)
        records, identities = [], set()
        for row_number, row in enumerate(rows, 2):
            if len(row) != len(header):
                raise SourceError(f"CSV row {row_number} has a malformed width")
            identity = row[key_index].strip()
            if not identity:
                raise SourceError(f"CSV row {row_number} has a blank identity")
            if identity in identities:
                raise SourceError(f"CSV row {row_number} has a duplicate identity")
            identities.add(identity)
            record = {name: row[index] for name, index in zip(required_order, indexes)}
            record["_row"] = row_number
            records.append(record)
    except SourceError:
        raise
    if not records:
        raise SourceError("CSV has no records")
    return {
        "records": records,
        "extract": _permitted_columns(
            required_order,
            [[record[name] for name in required_order] for record in records],
            set(required_order),
        ),
        "columns": required_order,
        "ignored_columns": len(header) - len(required_order),
    }


def _required(record, fields, optional=()):
    for field in fields:
        value = record.get(field)
        if (value is None or not value.strip()) and field not in optional:
            raise SourceError(f"row {record['_row']} has a blank required field")


def _integer(record, field, positive=False):
    value = record[field]
    if not value.isascii() or not value.isdecimal():
        raise SourceError(f"row {record['_row']} has an invalid numeric field")
    parsed = int(value)
    if positive and parsed == 0:
        raise SourceError(f"row {record['_row']} has an invalid numeric field")
    record[field] = parsed


def _date(record, field):
    value = record[field]
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise SourceError(f"row {record['_row']} has an invalid date") from exc
    if parsed.isoformat() != value:
        raise SourceError(f"row {record['_row']} has an invalid date")
    record[field] = parsed


def validate_sheet(name, rows):
    """Validate and type records previously returned by :func:`read_sheet`."""
    if name not in {"attendees", "budget", "vendors", "calendar"}:
        raise SourceError("unknown source")
    if not isinstance(rows, list) or not rows:
        raise SourceError("source has no records")
    result = []
    versions = set()
    for original in rows:
        if not isinstance(original, dict) or not isinstance(original.get("_row"), int):
            raise SourceError("invalid source record")
        row = dict(original)
        if name == "attendees":
            _required(
                row,
                (
                    "signal_id", "source", "segment", "signal", "value", "unit",
                    "observed_at", "confidence",
                ),
            )
            _integer(row, "value")
            _date(row, "observed_at")
            if row["confidence"] not in {"high", "medium", "low"}:
                raise SourceError(f"row {row['_row']} has an unknown confidence")
            valid_person_signals = {
                ("registered_attendees", "fellows"),
                ("registered_attendees", "partners"),
                ("required_on_site", "staff"),
                ("required_on_site", "speakers"),
                ("expected_attendees", "walk_ins"),
            }
            request_signals = {
                "wheelchair_spaces", "mobility_companions", "live_caption_requests",
                "hearing_loop_requests", "quiet_room_requests", "severe_allergy_follow_up",
            }
            valid_meal_signals = {"vegetarian_meals", "halal_meals"}
            is_person_measure = (
                row["unit"] == "people"
                and (row["signal"], row["segment"]) in valid_person_signals
            )
            is_people_request = (
                row["unit"] == "people"
                and row["segment"] == "all"
                and row["signal"] in request_signals
            )
            is_meal_request = (
                row["unit"] == "meals"
                and row["segment"] == "all"
                and row["signal"] in valid_meal_signals
            )
            if not (is_person_measure or is_people_request or is_meal_request):
                raise SourceError(f"row {row['_row']} has an unknown signal meaning")
        elif name == "vendors":
            _required(
                row,
                (
                    "quote_id", "vendor", "category", "option", "quote_amount_twd",
                    "capacity", "available_date", "valid_until", "status", "notes",
                ),
                ("notes",),
            )
            _integer(row, "quote_amount_twd")
            _integer(row, "capacity", positive=True)
            _date(row, "available_date")
            _date(row, "valid_until")
            if row["status"] not in {"held", "available", "conditional", "unavailable"}:
                raise SourceError(f"row {row['_row']} has an unknown vendor status")
        elif name == "calendar":
            _required(
                row,
                (
                    "constraint_id", "owner", "constraint_type", "start_at", "end_at",
                    "priority", "notes", "record_version",
                ),
            )
            valid_priorities = {"hard", "soft"}
            valid_constraint_types = {
                "preferred_event_window", "fallback_event_window", "venue_hold",
                "keynote_availability", "decision_deadline", "accessibility_walkthrough",
                "rehearsal_window", "teardown_deadline",
            }
            if (
                row["priority"] not in valid_priorities
                or row["constraint_type"] not in valid_constraint_types
            ):
                raise SourceError(f"row {row['_row']} has an unknown calendar meaning")
            parsed = []
            for field in ("start_at", "end_at"):
                try:
                    value = dt.datetime.fromisoformat(row[field])
                except ValueError as exc:
                    raise SourceError(f"row {row['_row']} has an invalid timestamp") from exc
                if value.utcoffset() is None:
                    raise SourceError(f"row {row['_row']} timestamp lacks an offset")
                row[field] = value
                parsed.append(value)
            invalid_order = parsed[1] < parsed[0]
            invalid_point = parsed[1] == parsed[0] and row["constraint_type"] != "decision_deadline"
            if invalid_order or invalid_point:
                raise SourceError(f"row {row['_row']} has an invalid interval")
            versions.add(row["record_version"])
        else:
            _required(
                row,
                (
                    "category", "planned_amount_twd", "approval_limit_twd",
                    "committed_amount_twd", "owner", "record_version",
                ),
            )
            _integer(row, "planned_amount_twd")
            _integer(row, "approval_limit_twd")
            _integer(row, "committed_amount_twd")
            versions.add(row["record_version"])
        result.append(row)
    if name in {"budget", "calendar"} and len(versions) != 1:
        raise SourceError("source contains mixed record versions")
    return result
