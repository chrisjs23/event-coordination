import csv
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from datetime import timezone
from pathlib import Path

from icalendar import Calendar

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "event-planning-coordination-brief" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import drafts
from publication import publication_state, validate_drafts

_spec = importlib.util.spec_from_file_location("test_options_fixtures", ROOT / "tests" / "test_options.py")
fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixtures)


def snapshot_values(value):
    return json.loads(json.dumps(value, default=lambda item: item.isoformat()))


def make_context():
    case = fixtures.load_case()
    option_state, result_state, review, unresolved = fixtures.review(case)
    # Publication context is reconstructed from JSON snapshots, where source dates are ISO strings.
    review = snapshot_values(review)
    sources = []
    for name in ("brief", "attendees", "budget", "vendors", "calendar", "floorplan", "interview"):
        sources.append({"id": "source:" + name, "retrieval_status": "retrieved",
                        "retrieved_at": "2026-08-26T04:00:00+00:00", "version_metadata": {},
                        "local_reference": "snapshots/evidence/" + name})
    return {"run_id": "test-publication", "created_at": "2026-11-24T03:00:00+00:00",
            "scope": {"objective": "Coordinate a review-ready fellowship demo day."},
            "sources": sources, "review": review,
            "unresolved": unresolved, "rejected_early": option_state["rejected_early"]}


def write_payloads(root, payloads):
    for name, data in payloads.items():
        (root / name).write_bytes(data)


class DraftPublicationTests(unittest.TestCase):
    def test_four_drafts_are_deterministic_and_match_canonical_review(self):
        context = make_context()
        first, second = drafts.render_drafts(context), drafts.render_drafts(context)
        self.assertEqual(first, second)
        self.assertEqual(set(first), set(drafts.ARTIFACTS))

        rows = list(csv.DictReader(io.StringIO(first["vendor-comparison.csv"].decode())))
        self.assertEqual(len(rows), 10)
        self.assertEqual(list(rows[0]), list(drafts.CSV_FIELDS))
        self.assertTrue(all(row["cost_twd"].isdigit() for row in rows))
        costs = {row["cost_twd"] for row in rows}
        self.assertIn("494000", costs)
        selected = context["review"]["model"]["selected_option"]
        self.assertEqual(selected["cost_twd"], 512000)
        self.assertEqual(selected["planning_people"], 260)
        self.assertEqual(next(row for row in rows if row["option_id"] == selected["id"])["cost_twd"], "512000")
        self.assertIn("category=", rows[0]["tradeoffs"])

        plan = first["event-plan.md"].decode()
        self.assertIn("Registered check-in target is 80% of 180 registrations, or at least 144 people", plan)
        for i in range(1, 13):
            self.assertIn(f"DEMO-{i:02}", plan)
        for row in context["review"]["model"]["calendar_records"]:
            self.assertIn(row["constraint_id"], plan)
        self.assertIn("512000", plan)
        messages = first["draft-communications.md"].decode()
        sections = messages.split("## UNSENT DRAFT — ")[1:]
        self.assertTrue(sections)
        for section in sections:
            for label in ("Audience —", "Purpose —", "Conditions —", "Approval owner —"):
                self.assertIn(label, section)

        cal = Calendar.from_ical(first["event-calendar.ics"])
        events = cal.walk("VEVENT")
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(str(event.get("STATUS")), "TENTATIVE")
        self.assertEqual(event.decoded("dtstart").utcoffset(), timezone.utc.utcoffset(None))
        self.assertEqual(event.decoded("dtstart").hour, 1)
        self.assertEqual(event.decoded("dtstart").minute, 30)
        for row in context["review"]["model"]["calendar_records"]:
            self.assertIn(row["constraint_id"], str(event.get("DESCRIPTION")))
            self.assertIn(row["notes"], str(event.get("DESCRIPTION")))
        for component in cal.walk():
            for key in ("ATTENDEE", "ORGANIZER", "VALARM"):
                self.assertNotIn(key, component)

    def test_deferred_recommendation_emits_empty_calendar_and_explains_deferral(self):
        context = make_context()
        context["review"]["recommendation"] = None
        context["review"]["model"]["selected_option"] = None
        payloads = drafts.render_drafts(context)
        cal = Calendar.from_ical(payloads["event-calendar.ics"])
        self.assertEqual(cal.walk("VEVENT"), [])
        self.assertIn("Recommendation deferred", payloads["event-plan.md"].decode())
        self.assertIn("calendar contains no events", payloads["event-plan.md"].decode())
        self.assertIn("await resolution", payloads["draft-communications.md"].decode())

    def test_unknown_source_marks_partial_and_validates_unknown_cost_reason(self):
        context = make_context()
        context["sources"][0]["retrieval_status"] = "unavailable"
        context["review"]["model"]["constraints"]["unknowns"].append({"id": "issue:source-test"})
        payloads = drafts.render_drafts(context)
        self.assertEqual(publication_state(context), "partial")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_payloads(root, payloads)
            self.assertEqual([row["outcome"] for row in validate_drafts(root, context)], ["passed"] * 4)

    def test_unknown_package_cost_is_blank_with_reason(self):
        case = fixtures.load_case()
        case["rows"]["vendors"] = [q for q in case["rows"]["vendors"] if q["quote_id"] != "Q-009"]
        option_state, _, review, unresolved = fixtures.review(case)
        review = snapshot_values(review)
        context = make_context()
        context["review"] = review
        context["unresolved"] = unresolved
        context["rejected_early"] = option_state["rejected_early"]
        payloads = drafts.render_drafts(context)
        rows = list(csv.DictReader(io.StringIO(payloads["vendor-comparison.csv"].decode())))
        unknown = [row for row in rows if not row["cost_twd"]]
        self.assertTrue(unknown)
        self.assertTrue(all(json.loads(row["unresolved"]) for row in unknown))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_payloads(root, payloads)
            self.assertEqual(validate_drafts(root, context)[0]["outcome"], "passed")

    def test_each_written_artifact_corruption_fails_its_own_check(self):
        context = make_context()
        originals = drafts.render_drafts(context)
        mutations = {
            "vendor-comparison.csv": lambda b: b.replace(b"512000", b"512001", 1),
            "event-plan.md": lambda b: b.replace(b"512000", b"512001", 1),
            "draft-communications.md": lambda b: b.replace(b"UNSENT DRAFT", b"SENT", 1),
        }
        for filename, mutate in mutations.items():
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                payloads = dict(originals)
                payloads[filename] = mutate(payloads[filename])
                write_payloads(root, payloads)
                checks = validate_drafts(root, context)
                by_artifact = {check["artifact_ids"][0]: check["outcome"] for check in checks}
                self.assertEqual(by_artifact["artifact:" + filename], "failed")
                self.assertTrue(all(outcome == "passed" for artifact, outcome in by_artifact.items()
                                    if artifact != "artifact:" + filename))

        calendar_mutations = (
            lambda b: b.replace(b"METHOD:PUBLISH", b"METHOD:REQUEST", 1),
            lambda b: b.replace(b"DTSTART:20261017T013000Z", b"DTSTART:20261017T023000Z", 1),
            lambda b: b.replace(b"X-RUN-ID:test-publication", b"X-RUN-ID:other-run", 1),
            lambda b: b.replace(b"STATUS:TENTATIVE", b"STATUS:TENTATIVE\r\nATTENDEE:bad@example.com", 1),
        )
        for mutate in calendar_mutations:
            with self.subTest(calendar_mutation=mutate), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                payloads = dict(originals)
                payloads["event-calendar.ics"] = mutate(payloads["event-calendar.ics"])
                write_payloads(root, payloads)
                checks = validate_drafts(root, context)
                by_artifact = {check["artifact_ids"][0]: check["outcome"] for check in checks}
                self.assertEqual(by_artifact["artifact:event-calendar.ics"], "failed")
                self.assertTrue(all(outcome == "passed" for artifact, outcome in by_artifact.items()
                                    if artifact != "artifact:event-calendar.ics"))


if __name__ == "__main__":
    unittest.main()
