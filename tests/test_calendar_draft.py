import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

from icalendar import Calendar

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "event-planning-coordination-brief/scripts"))
from calendar_draft import UID, render_calendar, supported_window


def context():
    records = []
    for i in range(8):
        records.append({
            "constraint_id": f"CAL-{i:03}", "owner": "Operations",
            "constraint_type": "preferred_event_window" if i == 0 else "keynote_availability",
            "start_at": "2026-10-17T09:30:00+08:00" if i == 0 else f"2026-10-17T{i+1:02}:00:00+08:00",
            "end_at": "2026-10-17T17:00:00+08:00" if i == 0 else f"2026-10-17T{i+2:02}:00:00+08:00",
            "priority": "hard", "notes": "source note", "record_version": "v1",
        })
    return {
        "run_id": "run-1", "created_at": "2026-08-26T12:00:01+08:00", "scope": {}, "sources": [],
        "review": {"recommendation": "option-1", "model": {
            "selected_option": {"id": "option-1", "event_date": "2026-10-17",
                                "planning_people": 42, "cost_twd": 500000, "currency": "TWD"},
            "calendar_records": records,
        }},
    }


def parsed(data):
    return Calendar.from_ical(data)


class CalendarDraftTests(unittest.TestCase):
    def test_supported_draft_has_utc_bounds_and_required_review_details(self):
        ctx = context()
        self.assertEqual(supported_window(ctx)["constraint_id"], "CAL-000")
        cal = parsed(render_calendar(ctx))
        event, = cal.walk("VEVENT")
        self.assertEqual(str(cal.get("version")), "2.0")
        self.assertEqual(str(cal.get("method")), "PUBLISH")
        self.assertEqual(event.decoded("dtstart"), datetime(2026, 10, 17, 1, 30, tzinfo=timezone.utc))
        self.assertEqual(event.decoded("dtend"), datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc))
        self.assertEqual(event.decoded("dtstamp"), datetime(2026, 8, 26, 4, 0, 1, tzinfo=timezone.utc))
        self.assertEqual(str(event.get("uid")), UID)
        desc = str(event.get("description"))
        for content in ("Pending human approval", "42", "500000 TWD", "CAL-007", "record_version=v1"):
            self.assertIn(content, desc)
        self.assertEqual(str(event.get("status")), "TENTATIVE")
        self.assertIsNone(event.get("attendee"))

    def test_uid_is_stable_and_calendar_defers_for_missing_or_ambiguous_support(self):
        a, b = context(), context()
        b["run_id"] = "run-2"
        uid_a = str(parsed(render_calendar(a)).walk("VEVENT")[0]["uid"])
        uid_b = str(parsed(render_calendar(b)).walk("VEVENT")[0]["uid"])
        self.assertEqual(uid_a, uid_b)
        b["review"]["model"]["selected_option"]["event_date"] = "2026-10-24"
        for ctx in (b, {**a, "review": {"recommendation": None, "model": {}}}):
            self.assertEqual(parsed(render_calendar(ctx)).walk("VEVENT"), [])
            self.assertEqual(str(parsed(render_calendar(ctx)).get("version")), "2.0")
        mismatch = context()
        mismatch["review"]["recommendation"] = "different"
        self.assertIsNone(supported_window(mismatch))
        self.assertEqual(parsed(render_calendar(mismatch)).walk("VEVENT"), [])

    def test_notes_are_escaped_utf8_and_lines_are_folded(self):
        ctx = context()
        ctx["review"]["model"]["calendar_records"][0]["notes"] = "中文\nATTENDEE:evil@example.com"
        data = render_calendar(ctx)
        self.assertIn("ATTENDEE:evil@example.com", str(parsed(data).walk("VEVENT")[0]["description"]))
        self.assertNotIn(b"\r\nATTENDEE:evil@example.com", data)
        self.assertIn("中文".encode(), data)
        self.assertTrue(all(len(line) <= 75 for line in data.split(b"\r\n") if line),
                        "icalendar folds serialized lines to at most 75 octets")


if __name__ == "__main__":
    unittest.main()
