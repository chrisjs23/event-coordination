"""Build a proposed, non-overlapping event schedule."""

from datetime import datetime, timedelta


def build_schedule(
    event_start: datetime,
    event_end: datetime,
    keynote_start: datetime,
    keynote_end: datetime,
    demo_ids: list[str],
    presentation_minutes: int,
    changeover_minutes: int,
    venue_start: datetime,
    venue_end: datetime,
) -> list[dict]:
    """Return the proposed programme, setup, readiness and teardown intervals."""

    times = (event_start, event_end, keynote_start, keynote_end, venue_start, venue_end)
    if any(not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None for value in times):
        raise ValueError("All schedule times must be timezone-aware datetimes")
    if not (venue_start < event_start < event_end < venue_end):
        raise ValueError("Event and venue bounds are invalid")
    if not (event_start <= keynote_start < keynote_end <= event_end):
        raise ValueError("Keynote window must be inside the event window")
    if not isinstance(demo_ids, list) or not demo_ids or any(not isinstance(item, str) or not item.strip() for item in demo_ids):
        raise ValueError("Demo IDs must be non-empty strings")
    if len(set(demo_ids)) != len(demo_ids):
        raise ValueError("Demo IDs must be unique")
    if (not isinstance(presentation_minutes, int) or isinstance(presentation_minutes, bool)
            or presentation_minutes <= 0 or not isinstance(changeover_minutes, int)
            or isinstance(changeover_minutes, bool) or changeover_minutes <= 0):
        raise ValueError("Presentation and changeover durations must be positive whole minutes")

    opening_end = event_start + timedelta(minutes=15)
    closing_start = event_end - timedelta(minutes=30)
    if opening_end > keynote_start:
        raise ValueError("Opening does not fit before the keynote")

    rows = []

    def add(identifier, label, start, end, kind):
        if end <= start:
            raise ValueError("Schedule contains a missing or non-positive interval")
        rows.append({
            "id": identifier,
            "label": label,
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "kind": kind,
            "planning_basis": "planner-proposed",
        })

    def add_fixed(identifier, label, start, duration, kind="programme"):
        end = start + duration
        add(identifier, label, start, end, kind)
        return end

    add("opening", "Opening", event_start, opening_end, "programme")
    if keynote_start > opening_end:
        add("event-overview", "Event overview", opening_end, keynote_start, "programme")
    add("keynote", "Keynote", keynote_start, keynote_end, "keynote")

    cursor = add_fixed("post-keynote-break", "Break", keynote_end, timedelta(minutes=15), "break")
    split = (len(demo_ids) + 1) // 2

    def add_demos(ids, cursor):
        for demo_id in ids:
            demo_end = add_fixed(demo_id, "Demo presentation", cursor, timedelta(minutes=presentation_minutes), "demo")
            cursor = add_fixed(f"{demo_id}:changeover", "Changeover", demo_end, timedelta(minutes=changeover_minutes), "changeover")
        return cursor

    cursor = add_demos(demo_ids[:split], cursor)
    cursor = add_fixed("lunch", "Lunch", cursor, timedelta(minutes=60), "meal")
    cursor = add_demos(demo_ids[split:], cursor)
    cursor = add_fixed("afternoon-break", "Break", cursor, timedelta(minutes=15), "break")
    if cursor > closing_start:
        raise ValueError("Programme activities do not fit before closing")
    if cursor < closing_start:
        add("partner-discussions-contingency", "Partner discussions and contingency", cursor, closing_start, "programme")
    add("closing", "Closing", closing_start, event_end, "programme")

    setup_duration = event_start - venue_start
    midpoint = venue_start + setup_duration / 2
    add("setup", "Venue setup", venue_start, midpoint, "setup")
    add("readiness-checks", "Readiness checks", midpoint, event_start, "readiness")
    add("teardown", "Venue teardown", event_end, venue_end, "teardown")
    return sorted(rows, key=lambda row: datetime.fromisoformat(row["start_at"]))
