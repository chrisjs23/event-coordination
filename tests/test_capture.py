"""Offline integration coverage for capture through the planning baseline."""

import csv
import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "event-planning-coordination-brief" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import capture
import pipeline


SHEET_NAMES = ("attendees", "budget", "vendors", "calendar")
PDF_BYTES = b"%PDF-1.4\nsynthetic floor evidence\n%%EOF\n"


def _notion_page(block_texts, *, cursor=None):
    entries = {}
    children = []
    for index, text in enumerate(block_texts):
        block_id = f"block-{index}"
        children.append(block_id)
        entries[block_id] = {"value": {"type": "text", "properties": {"title": [[text]]}}}
    entries[capture.PAGE_ID] = {"value": {
        "type": "page", "content": children,
        "properties": {"title": [["Demo Day"]]},
    }}
    return json.dumps({"cursor": {"stack": []} if cursor is None else cursor,
                       "recordMap": {"block": entries}}).encode()


BRIEF_TEXTS = [
    "Event brief",
    "Success means at least 80 percent of registered attendees check in.",
    "Plan for 20 people; the planning ceiling is TWD 100,000.",
    "Hard requirements are to preserve the programme and keep attendee information private.",
    "The venue allocates 30 usable audience places, including six wheelchair spaces.",
    "The quiet room has occupancy up to 12 people.",
    "Each demonstration needs 10 minutes of presentation and a separate 3-minute changeover allowance.",
    "Programme has scheduled DEMO-01 and DEMO-02.",
    "For the 17 October 2026 exercise plan, use the disclosed operating window.",
    "The planner may choose the programme sequence after checking dependencies.",
    "For this case, venue coordination includes the quiet room and accessible route.",
    "The package includes setup and venue access subject to confirmation.",
]


def _rows():
    return {
        "attendees": [
            ["SIG-001", "registration", "fellows", "registered_attendees", "10", "people", "2026-08-20", "high"],
            ["SIG-002", "registration", "partners", "registered_attendees", "4", "people", "2026-08-20", "high"],
            ["SIG-003", "operations", "staff", "required_on_site", "2", "people", "2026-08-20", "high"],
            ["SIG-004", "programme", "speakers", "required_on_site", "1", "people", "2026-08-20", "medium"],
            ["SIG-005", "forecast", "walk_ins", "expected_attendees", "3", "people", "2026-08-20", "low"],
            ["SIG-006", "support", "all", "quiet_room_requests", "9", "people", "2026-08-20", "medium"],
        ],
        "budget": [["Venue", "20000", "30000", "5000", "Operations", "budget-v1"]],
        "vendors": [
            ["Q-001", "Supplier A", "Venue", "Basic", "10000", "30", "2026-10-17", "2026-09-01", "held", "scope A"],
            ["Q-002", "Supplier B", "Catering", "Meals", "5000", "40", "2026-10-17", "2026-09-01", "available", "scope B"],
        ],
        "calendar": [
            ["CAL-001", "Operations", "preferred_event_window", "2026-10-17T09:30:00+08:00", "2026-10-17T17:00:00+08:00", "hard", "preferred", "calendar-v1"],
            ["CAL-002", "Operations", "fallback_event_window", "2026-10-24T09:30:00+08:00", "2026-10-24T17:00:00+08:00", "soft", "fallback", "calendar-v1"],
            ["CAL-003", "TICC", "venue_hold", "2026-10-17T07:30:00+08:00", "2026-10-17T18:30:00+08:00", "hard", "hold", "calendar-v1"],
            ["CAL-004", "Programme", "keynote_availability", "2026-10-17T10:00:00+08:00", "2026-10-17T11:00:00+08:00", "hard", "keynote", "calendar-v1"],
            ["CAL-005", "Operations", "decision_deadline", "2026-09-04T17:00:00+08:00", "2026-09-04T17:00:00+08:00", "hard", "decision", "calendar-v1"],
            ["CAL-006", "Learner Experience", "accessibility_walkthrough", "2026-09-25T14:00:00+08:00", "2026-09-25T16:00:00+08:00", "hard", "walkthrough", "calendar-v1"],
            ["CAL-007", "Programme", "rehearsal_window", "2026-10-16T15:00:00+08:00", "2026-10-16T18:00:00+08:00", "soft", "rehearsal", "calendar-v1"],
            ["CAL-008", "TICC", "teardown_deadline", "2026-10-17T17:00:00+08:00", "2026-10-17T18:30:00+08:00", "hard", "teardown", "calendar-v1"],
        ],
    }


class FakeTransport:
    def __init__(self, root, *, unavailable=(), page=None, pdf=PDF_BYTES,
                 mutate_sheet=None):
        self.root = root
        self.unavailable = set(unavailable)
        self.page = page if page is not None else _notion_page(BRIEF_TEXTS)
        self.pdf = pdf
        self.mutate_sheet = mutate_sheet

    def __call__(self, url, body=None):
        if url in self.unavailable:
            raise capture.SourceError("synthetic unavailable source")
        if url == capture.BRIEF_API:
            return self.page, "application/json", {}
        venue = json.loads((self.root / "event-planning-coordination-brief/references/venue-evidence.json").read_text())
        if url == venue["url"]:
            return self.pdf, "application/pdf", {}
        query = parse_qs(urlparse(url).query)
        sheet_name = query.get("sheet", [None])[0]
        contract = json.loads((self.root / "event-planning-coordination-brief/references/sheets.json").read_text())
        name = next((key for key, value in contract.items() if value["tab"] == sheet_name), None)
        if name is None:
            raise AssertionError("unexpected fake source URL")
        fields = list(contract[name]["fields"])
        rows = [list(row) for row in _rows()[name]]
        if self.mutate_sheet:
            fields, rows = self.mutate_sheet(name, fields, rows)
        out = io.StringIO(newline="")
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(fields)
        writer.writerows(rows)
        return out.getvalue().encode(), "text/csv", {}


class CapturePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "root"
        self.output = Path(self.temp.name) / "output"
        self.root.mkdir()
        shutil.copy(ROOT / "snapshot.schema.json", self.root / "snapshot.schema.json")
        references = self.root / "event-planning-coordination-brief/references"
        references.mkdir(parents=True)
        for filename in ("sheets.json", "venue-evidence.json"):
            shutil.copy(ROOT / "event-planning-coordination-brief/references" / filename, references / filename)
        venue_path = references / "venue-evidence.json"
        venue = json.loads(venue_path.read_text())
        venue["reviewed_sha256"] = "sha256:" + hashlib.sha256(PDF_BYTES).hexdigest()
        venue_path.write_text(json.dumps(venue))
        interview = self.root / capture.INTERVIEW
        interview.parent.mkdir(parents=True)
        interview.write_text(
            "using familiar suppliers\n\nstandard policy for how many extra\n\nand then Operations gives the final approval\n",
            encoding="utf-8",
        )

    def run_pipeline(self, **options):
        return pipeline.run_baseline(self.root, self.output, fetch=FakeTransport(self.root, **options))

    def snapshots(self):
        return [json.loads(path.read_text()) for path in sorted((self.output / "snapshots").glob("0*.json"))]

    def test_normal_run_has_four_linked_schema_verified_snapshots_and_correct_baseline(self):
        result = self.run_pipeline()
        self.assertEqual((result["status"], result["snapshots"]), ("partial", 4))
        docs = self.snapshots()
        self.assertEqual([doc["sequence"] for doc in docs], [1, 2, 3, 4])
        self.assertEqual(len({doc["run_id"] for doc in docs}), 1)
        for index in range(1, 4):
            self.assertEqual(docs[index]["predecessor"]["snapshot_id"], docs[index - 1]["snapshot_id"])
            self.assertTrue(docs[index]["predecessor"]["sha256"].startswith("sha256:"))
        baseline = docs[3]["state"]
        count = baseline["headcount_basis"][0]
        self.assertEqual(count["unbuffered_people"], 20)
        self.assertIsNone(count["planning_people"])
        self.assertEqual(count["chosen_buffer"], None)
        self.assertEqual(sum(x["value"] for x in baseline["accessibility_baseline"] if x.get("unit") == "people"), 9)
        self.assertEqual(len(baseline["schedule_dependencies"]), 8 + 3 + 2)
        budget = next(x for x in baseline["budget_baseline"] if x.get("category") == "Venue")
        self.assertEqual(budget["remaining_limit_twd"], 25000)
        self.assertEqual(budget["approval_status"], "pending")

    def test_reordered_rows_and_headers_with_private_extra_column_are_accepted_but_filtered(self):
        def mutate(name, fields, rows):
            fields = list(reversed(fields))
            if name == "attendees":
                fields.insert(1, "private_email")
                rows = [list(reversed(row)) for row in reversed(rows)]
                rows = [row[:1] + ["secret@example.test"] + row[1:] for row in rows]
            else:
                rows = [list(reversed(row)) for row in reversed(rows)]
            return fields, rows

        result = self.run_pipeline(mutate_sheet=mutate)
        self.assertEqual(result["snapshots"], 4)
        payloads = [path.read_bytes() for path in self.output.rglob("*") if path.is_file()]
        self.assertFalse(any(b"secret@example.test" in payload for payload in payloads))
        attendee_source = next(s for s in self.snapshots()[1]["state"]["sources"] if s["id"] == "source:attendees")
        self.assertEqual(attendee_source["retrieval_status"], "retrieved")
        self.assertGreater(attendee_source["version_metadata"]["ignored_columns"], 0)

    def test_unavailable_vendor_does_not_stop_independent_baseline(self):
        contract = json.loads((self.root / "event-planning-coordination-brief/references/sheets.json").read_text())
        vendor_url = contract["vendors"]["url"] + "/gviz/tq?tqx=out%3Acsv&sheet=Vendor+Quotes"
        result = self.run_pipeline(unavailable=(vendor_url,))
        self.assertEqual(result["snapshots"], 4)
        sources = self.snapshots()[1]["state"]["sources"]
        vendor = next(s for s in sources if s["id"] == "source:vendors")
        self.assertEqual(vendor["retrieval_status"], "unavailable")
        self.assertTrue((self.output / "snapshots/evidence/capture-attempts.json").is_file())

    def test_invalid_attendee_values_and_identities_are_not_used_and_extract_retained(self):
        for mode in ("numeric", "missing_header", "duplicate_id"):
            with self.subTest(mode=mode):
                self.output = Path(self.temp.name) / ("output-" + mode)

                def mutate(name, fields, rows):
                    if name != "attendees":
                        return fields, rows
                    if mode == "numeric":
                        rows[0][4] = "not-a-number"
                    elif mode == "missing_header":
                        fields.remove("confidence")
                        rows = [row[:-1] for row in rows]
                    else:
                        rows[1][0] = rows[0][0]
                    return fields, rows

                self.run_pipeline(mutate_sheet=mutate)
                docs = self.snapshots()
                source = next(s for s in docs[1]["state"]["sources"] if s["id"] == "source:attendees")
                self.assertEqual(source["retrieval_status"], "invalid")
                self.assertTrue(source["local_reference"])
                evidence = (self.output / source["local_reference"]).read_bytes()
                self.assertNotIn(b"private_email", evidence)
                self.assertFalse(any(obs["id"].startswith("obs:attendees:") for obs in source["observations"]))
                self.assertFalse(any("source:attendees" in row.get("evidence_ids", []) for row in docs[3]["state"]["headcount_basis"]))

    def test_unavailable_calendar_produces_failure_without_fabricated_snapshots(self):
        contract = json.loads((self.root / "event-planning-coordination-brief/references/sheets.json").read_text())
        calendar_url = contract["calendar"]["url"] + "/gviz/tq?tqx=out%3Acsv&sheet=Calendar+Constraints"
        with self.assertRaisesRegex(ValueError, "baseline execution failed"):
            self.run_pipeline(unavailable=(calendar_url,))
        self.assertTrue((self.output / "failure.json").is_file())
        self.assertFalse(list((self.output / "snapshots").glob("0*.json")))
        attempts = json.loads((self.output / "snapshots/evidence/capture-attempts.json").read_text())
        calendar = next(s for s in attempts["sources"] if s["id"] == "source:calendar")
        self.assertEqual(calendar["retrieval_status"], "unavailable")

    def test_changed_floor_pdf_is_retained_unverified_without_spatial_observations(self):
        result = self.run_pipeline(pdf=b"%PDF-1.7\nchanged reviewed drawing\n%%EOF\n")
        self.assertEqual(result["snapshots"], 4)
        sources = self.snapshots()[1]["state"]["sources"]
        floor = next(s for s in sources if s["id"] == "source:floorplan")
        self.assertEqual(floor["retrieval_status"], "unverified")
        self.assertTrue(floor["local_reference"])
        self.assertEqual(floor["observations"], [])
        self.assertFalse(any("floorplan" in row["id"] for row in self.snapshots()[3]["state"]["accessibility_baseline"]))

    def test_existing_output_is_rejected_without_modification(self):
        self.output.mkdir()
        marker = self.output / "keep.txt"
        marker.write_text("existing")
        with self.assertRaises(FileExistsError):
            self.run_pipeline()
        self.assertEqual(marker.read_text(), "existing")
        self.assertEqual(list(self.output.iterdir()), [marker])

    def test_incomplete_or_paginated_brief_fails_and_retains_attempt(self):
        incomplete = _notion_page(["Missing required brief sections"], cursor={"stack": []})
        with self.assertRaisesRegex(ValueError, "baseline execution failed"):
            self.run_pipeline(page=incomplete)
        attempts = json.loads((self.output / "snapshots/evidence/capture-attempts.json").read_text())
        brief = next(s for s in attempts["sources"] if s["id"] == "source:brief")
        self.assertEqual(brief["retrieval_status"], "invalid")
        self.assertFalse(list((self.output / "snapshots").glob("0*.json")))

        self.output = Path(self.temp.name) / "output-paginated"
        paginated = _notion_page(BRIEF_TEXTS, cursor={"stack": ["next"]})
        with self.assertRaisesRegex(ValueError, "baseline execution failed"):
            self.run_pipeline(page=paginated)
        attempts = json.loads((self.output / "snapshots/evidence/capture-attempts.json").read_text())
        brief = next(s for s in attempts["sources"] if s["id"] == "source:brief")
        self.assertEqual(brief["retrieval_status"], "invalid")


if __name__ == "__main__":
    unittest.main()
