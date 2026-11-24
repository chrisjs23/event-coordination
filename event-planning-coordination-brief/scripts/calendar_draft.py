"""Render a review-gated calendar draft without sending or storing it."""

from datetime import datetime, timezone

from icalendar import Calendar, Event


UID = "quillhaven-fellowship-demo-day@event-coordination.local"


def _aware(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def supported_window(context: dict) -> dict | None:
    """Return the sole matching, positive, timezone-aware event window, if any."""
    review = context.get("review") or {}
    selected = (review.get("model") or {}).get("selected_option")
    if not selected or not selected.get("id") or review.get("recommendation") != selected.get("id"):
        return None
    event_date = selected.get("event_date")
    if not isinstance(event_date, str):
        return None
    records = (review.get("model") or {}).get("calendar_records") or []
    matches = []
    for record in records:
        if record.get("constraint_type") not in {"preferred_event_window", "fallback_event_window"}:
            continue
        start = _aware(record.get("start_at"))
        end = _aware(record.get("end_at"))
        if start is None or end is None or end <= start:
            continue
        if start.date().isoformat() == event_date and end.date().isoformat() == event_date:
            matches.append(record)
    return matches[0] if len(matches) == 1 else None


def render_calendar(context: dict) -> bytes:
    """Return a VCALENDAR byte string containing a tentative event or no events."""
    cal = Calendar()
    cal.add("version", "2.0")
    cal.add("method", "PUBLISH")
    cal.add("prodid", "-//Quillhaven Academy//Event Coordination//EN")

    window = supported_window(context)
    review = context.get("review") or {}
    selected = (review.get("model") or {}).get("selected_option") or {}
    created_at = _aware(context.get("created_at"))
    if window is None or created_at is None:
        return cal.to_ical()

    start = _aware(window.get("start_at"))
    end = _aware(window.get("end_at"))
    event = Event()
    event.add("uid", UID)
    event.add("dtstamp", created_at.astimezone(timezone.utc).replace(microsecond=0))
    event.add("dtstart", start.astimezone(timezone.utc))
    event.add("dtend", end.astimezone(timezone.utc))
    event.add("status", "TENTATIVE")
    event.add("summary", "UNSENT DRAFT — Fellowship Demo Day")
    lines = [
        "Pending human approval; this is an unsent planning draft.",
        f"Planning people: {selected.get('planning_people', 'unknown')}",
        f"Cost: {selected.get('cost_twd', 'unknown')} {selected.get('currency', 'unknown')}",
        "Calendar records considered:",
    ]
    records = (review.get("model") or {}).get("calendar_records") or []
    for row in records:
        fields = ("constraint_id", "owner", "constraint_type", "start_at", "end_at",
                  "priority", "notes", "record_version")
        lines.append("; ".join(f"{field}={row.get(field, '')}" for field in fields))
    event.add("description", "\n".join(lines))
    event.add("x-run-id", context.get("run_id", ""))
    event.add("x-option-id", selected.get("id", ""))
    cal.add_component(event)
    return cal.to_ical()
