"""Offline integration checks for transactional refresh and recovery."""

import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "event-planning-coordination-brief/scripts"
sys.path.insert(0, str(SCRIPTS))

import capture
import changes
import history
import refresh
from locking import output_lock
from snapshots import FILENAMES, PUBLICATION_ARTIFACTS, verify_publication
from publication import validate_existing

PDF_BYTES = b"%PDF-1.4\nsynthetic fixture floor plan\n%%EOF\n"
FIXTURE = ROOT / "tests/fixtures/review-case.json"


def _notion_body(blocks):
    entries = {}
    children = []
    for block in blocks:
        if block["id"] == capture.PAGE_ID:
            continue
        children.append(block["id"])
        entries[block["id"]] = {"value": {"type": block.get("type", "text"),
                                           "properties": {"title": [[block["text"]]]}}}
    entries[capture.PAGE_ID] = {"value": {"type": "page", "content": children,
                                                    "properties": {"title": [["Project 3 Event Coordination"]]}}}
    return json.dumps({"cursor": {"stack": []}, "recordMap": {"block": entries}}).encode()


class FixtureTransport:
    def __init__(self, root, *, unavailable=(), price_delta=0, pdf=PDF_BYTES):
        self.root = root
        self.unavailable = set(unavailable)
        self.price_delta = price_delta
        self.pdf = pdf
        self.calls = []
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.contract = json.loads((root / "event-planning-coordination-brief/references/sheets.json").read_text())

    def __call__(self, url, body=None):
        self.calls.append(url)
        if url in self.unavailable:
            raise capture.SourceError("fixture source unavailable")
        if url == capture.BRIEF_API:
            return _notion_body(self.fixture["blocks"]), "application/json", {}
        venue = json.loads((self.root / "event-planning-coordination-brief/references/venue-evidence.json").read_text())
        if url == venue["url"]:
            return self.pdf, "application/pdf", {}
        query = parse_qs(urlparse(url).query)
        tab = query.get("sheet", [None])[0]
        name = next((key for key, value in self.contract.items() if value["tab"] == tab), None)
        if name is None:
            raise AssertionError("Unexpected fixture source URL")
        fields = list(self.contract[name]["fields"])
        rows = []
        for fixture_row in self.fixture["rows"][name]:
            row = {key: value for key, value in fixture_row.items() if key != "_row"}
            if name == "vendors" and row["quote_id"] == "Q-003":
                row["quote_amount_twd"] += self.price_delta
            rows.append(row)
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return stream.getvalue().encode(), "text/csv", {}


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "project"
        self.output = base / "deliverables"
        self.root.mkdir()
        shutil.copy(ROOT / "snapshot.schema.json", self.root / "snapshot.schema.json")
        refs = self.root / "event-planning-coordination-brief/references"
        refs.mkdir(parents=True)
        for name in ("sheets.json", "venue-evidence.json", "planning-policy.json"):
            shutil.copy(ROOT / "event-planning-coordination-brief/references" / name, refs / name)
        venue_path = refs / "venue-evidence.json"
        venue = json.loads(venue_path.read_text())
        venue["reviewed_sha256"] = "sha256:" + hashlib.sha256(PDF_BYTES).hexdigest()
        venue_path.write_text(json.dumps(venue), encoding="utf-8")
        interview = self.root / capture.INTERVIEW
        interview.parent.mkdir(parents=True)
        shutil.copy(ROOT / capture.INTERVIEW, interview)

    def run_refresh(self, **transport_options):
        transport = FixtureTransport(self.root, **transport_options)
        result = refresh.refresh_run(self.root, self.output, fetch=transport)
        return result, transport

    def current_docs(self):
        return [json.loads((self.output / "snapshots" / name).read_text()) for name in FILENAMES]

    def test_initial_run_is_complete_publication_with_two_feasible_options(self):
        result, transport = self.run_refresh()
        self.assertEqual(result["snapshots"], 9)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(transport.calls), 6)
        docs = self.current_docs()
        self.assertEqual(len({doc["run_id"] for doc in docs}), 1)
        self.assertEqual(verify_publication(self.output, self.root / "snapshot.schema.json")["snapshots"], 9)
        validate_existing(self.output)
        review = docs[6]["state"]
        self.assertEqual(sum(row["feasibility"] == "feasible" for row in review["model"]["results"]), 2)

    def test_price_change_archives_prior_run_and_marks_only_supported_changed_evidence(self):
        first, _ = self.run_refresh()
        second, _ = self.run_refresh(price_delta=1000)
        self.assertNotEqual(first["run_id"], second["run_id"])
        archived = self.output / second["history_path"]
        self.assertTrue(history.verify_archive(archived))
        stage1 = self.current_docs()[0]["state"]
        self.assertEqual(stage1["supersedes_run_id"], first["run_id"])
        self.assertEqual(stage1["predecessor_history"], second["history_path"])
        self.assertIn("source:vendors", stage1["changed_source_ids"])
        self.assertIn("obs:vendors:Q-003", stage1["changed_record_ids"])
        self.assertTrue(stage1["unchanged_evidence_ids"])
        self.assertEqual(stage1["previous_integrity"], "validated-publication")

    def test_unchanged_refresh_gets_new_identity_and_revalidates_installed_artifacts(self):
        first, _ = self.run_refresh()
        second, _ = self.run_refresh()
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertEqual(second["status"], "complete")
        stage1 = self.current_docs()[0]["state"]
        self.assertEqual(stage1["changed_source_ids"], [])
        self.assertTrue(stage1["unchanged_source_ids"])
        self.assertEqual(stage1["change_reason"], "unchanged inputs refreshed and revalidated")
        verify_publication(self.output, self.root / "snapshot.schema.json")
        validate_existing(self.output)

    def test_each_missing_or_corrupt_artifact_is_retained_in_history_and_repaired(self):
        self.run_refresh()
        for index, name in enumerate(PUBLICATION_ARTIFACTS):
            with self.subTest(artifact=name):
                path = self.output / name
                if index % 2:
                    path.unlink()
                    damaged_bytes = None
                else:
                    damaged_bytes = b"retained corrupt draft: " + name.encode()
                    path.write_bytes(damaged_bytes)
                result, _ = self.run_refresh()
                archived = self.output / result["history_path"]
                self.assertEqual(self.current_docs()[0]["state"]["previous_integrity"], "validated-review")
                if damaged_bytes is None:
                    self.assertFalse((archived / name).exists())
                else:
                    self.assertEqual((archived / name).read_bytes(), damaged_bytes)
                self.assertTrue((self.output / name).is_file())
                validate_existing(self.output)

    def test_unavailable_calendar_installs_explicit_failure_then_next_call_recovers_freshly(self):
        first, _ = self.run_refresh()
        calendar = json.loads((self.root / "event-planning-coordination-brief/references/sheets.json").read_text())["calendar"]
        unavailable_url = calendar["url"] + "/gviz/tq?tqx=out%3Acsv&sheet=Calendar+Constraints"
        failed_transport = FixtureTransport(self.root, unavailable=(unavailable_url,))
        with self.assertRaisesRegex(ValueError, "Fresh planning attempt failed"):
            refresh.refresh_run(self.root, self.output, fetch=failed_transport)
        failure = json.loads((self.output / "failure.json").read_text())
        self.assertEqual(failure["supersedes_run_id"], first["run_id"])
        self.assertFalse(any((self.output / name).exists() for name in PUBLICATION_ARTIFACTS))
        failed_history = list((self.output / "history").glob("*") )
        self.assertTrue(any(path.name == first["run_id"] for path in failed_history))
        recovered, _ = self.run_refresh()
        self.assertNotEqual(recovered["run_id"], first["run_id"])
        self.assertTrue(all(approval["status"] == "pending"
                            for approval in self.current_docs()[6]["state"]["approval_requirements"]))
        validate_existing(self.output)

    def test_unavailable_vendor_preserves_partial_or_blocked_drafts(self):
        vendors = json.loads((self.root / "event-planning-coordination-brief/references/sheets.json").read_text())["vendors"]
        unavailable_url = vendors["url"] + "/gviz/tq?tqx=out%3Acsv&sheet=Vendor+Quotes"
        result, _ = self.run_refresh(unavailable=(unavailable_url,))
        self.assertIn(result["status"], {"partial", "blocked"})
        docs = self.current_docs()
        self.assertEqual(len(docs), 9)
        calendar = (self.output / "event-calendar.ics").read_text()
        self.assertNotIn("BEGIN:VEVENT", calendar)
        communications = (self.output / "draft-communications.md").read_text()
        self.assertIn("UNSENT DRAFT", communications)
        validate_existing(self.output)

    def test_policy_change_records_headcount_decision(self):
        self.run_refresh()
        policy_path = self.root / "event-planning-coordination-brief/references/planning-policy.json"
        policy = json.loads(policy_path.read_text())
        policy["buffer_people"] += 1
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        self.run_refresh()
        stage1 = self.current_docs()[0]["state"]
        self.assertIn("decision:headcount-buffer", stage1["changed_decision_ids"])

    def test_missing_previous_policy_does_not_claim_unchanged_inputs(self):
        same_source = {"id": "source:vendors", "retrieval_status": "retrieved", "content_hash": "h",
                       "source_role": "vendor-record", "version_metadata": None,
                       "observations": [{"id": "obs:vendors:Q003", "summary": "Quote", "data": {"price": 10},
                                         "locator": {"kind": "section", "value": "Q003"}}]}
        result = changes.describe_change({"integrity": "validated-publication", "sources": [same_source],
                                          "policy": None}, [same_source], {})
        self.assertEqual(result["comparison_status"], "comparison-unverified")
        self.assertNotEqual(result["change_reason"], "unchanged inputs refreshed and revalidated")

    def test_observation_data_change_marks_source_and_affects_decisions(self):
        previous_source = {"id": "source:vendors", "retrieval_status": "retrieved", "content_hash": "same-hash",
                           "source_role": "vendor-record", "version_metadata": None,
                           "observations": [{"id": "obs:vendors:Q003", "summary": "Quote", "data": {"price": 10},
                                             "locator": {"kind": "section", "value": "Q003"}}]}
        new_source = json.loads(json.dumps(previous_source))
        new_source["observations"][0]["data"]["price"] = 12
        result = changes.describe_change({"integrity": "validated-publication", "sources": [previous_source],
                                          "policy": {"buffer_people": 1, "buffer_rationale": "r"}},
                                         [new_source], {"buffer_people": 1, "buffer_rationale": "r"})
        self.assertEqual(result["changed_source_ids"], ["source:vendors"])
        self.assertEqual(result["changed_record_ids"], ["obs:vendors:Q003"])
        self.assertEqual(result["affected_decision_ids"], ["decision:headcount-buffer", "decision:selection"])

    def test_unknown_existing_directory_is_rejected_without_mutation(self):
        self.output.mkdir()
        marker = self.output / "keep.txt"
        marker.write_text("existing data")
        with self.assertRaisesRegex(ValueError, "recognized planning run"):
            refresh.refresh_run(self.root, self.output, fetch=FixtureTransport(self.root))
        self.assertEqual(marker.read_text(), "existing data")

    def test_active_output_lock_fails_without_fetch_or_current_run_mutation(self):
        self.run_refresh()
        before = history.inventory(self.output)
        calls = []
        with output_lock(self.output):
            with self.assertRaisesRegex(ValueError, "operation is active"):
                refresh.refresh_run(self.root, self.output, fetch=lambda *args: calls.append(args))
        self.assertEqual(calls, [])
        self.assertEqual(history.inventory(self.output), before)

    def test_invalid_journal_token_is_rejected_without_changing_current_run(self):
        self.run_refresh()
        before = history.inventory(self.output)
        journal = refresh._journal_path(self.output)
        journal.write_text(json.dumps({"token": "../escape", "output": str(self.output), "phase": "building"}))
        with self.assertRaisesRegex(ValueError, "transaction identity"):
            refresh.refresh_run(self.root, self.output, fetch=FixtureTransport(self.root))
        self.assertEqual(history.inventory(self.output), before)

    def test_journal_archive_path_cannot_escape_history(self):
        self.run_refresh()
        token = "d" * 32
        stage, _ = refresh._paths(self.output, token)
        shutil.copytree(self.output, stage)
        journal = {"token": token, "output": str(self.output), "phase": "ready",
                   "archive_path": "../../outside", "candidate_inventory": history.inventory(stage),
                   "candidate_run_id": refresh._identity(stage), "previous": None}
        refresh._save_journal(self.output, journal)
        with self.assertRaisesRegex(ValueError, "escapes history"):
            refresh.refresh_run(self.root, self.output, fetch=FixtureTransport(self.root))

    def test_reconciles_interrupted_partial_candidate_then_runs_new_fresh_attempt(self):
        first, _ = self.run_refresh()
        real_run = refresh.run_baseline

        def interrupted(root, stage, **kwargs):
            kwargs["through"] = "planning-baseline"
            real_run(root, stage, **kwargs)
            raise KeyboardInterrupt("simulated process interruption")

        with patch.object(refresh, "run_baseline", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                refresh.refresh_run(self.root, self.output, fetch=FixtureTransport(self.root))
        self.assertTrue(refresh._journal_path(self.output).is_file())
        result, _ = self.run_refresh()
        self.assertIn("recovery", result)
        self.assertNotEqual(first["run_id"], result["run_id"])
        self.assertEqual(verify_publication(self.output, self.root / "snapshot.schema.json")["snapshots"], 9)
        self.assertTrue(any((self.output / "history").glob("*/failure.json")))

    def test_install_interruption_after_history_move_recovers_without_losing_history(self):
        initial, _ = self.run_refresh()
        real_replace = refresh.os.replace
        raised = False

        def replace_then_interrupt(source, destination):
            nonlocal raised
            real_replace(source, destination)
            if not raised and Path(source) == self.output / "history":
                raised = True
                raise KeyboardInterrupt("after history move")

        with patch.object(refresh.os, "replace", side_effect=replace_then_interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_refresh()
        result, _ = self.run_refresh()
        self.assertIn("recovery", result)
        self.assertTrue((self.output / "history" / initial["run_id"]).is_dir())
        history.verify_history_link(self.output)
        validate_existing(self.output)

    def test_install_interruption_after_old_root_rename_recovers_without_mixed_run(self):
        self.run_refresh()
        real_replace = refresh.os.replace
        raised = False

        def replace_then_interrupt(source, destination):
            nonlocal raised
            real_replace(source, destination)
            if (not raised and Path(source) == self.output
                    and Path(destination).name.endswith(".old")):
                raised = True
                raise KeyboardInterrupt("after old root rename")

        with patch.object(refresh.os, "replace", side_effect=replace_then_interrupt):
            with self.assertRaises(KeyboardInterrupt):
                refresh.refresh_run(self.root, self.output, fetch=FixtureTransport(self.root))
        result, _ = self.run_refresh()
        self.assertIn("recovery", result)
        docs = self.current_docs()
        self.assertEqual(len({doc["run_id"] for doc in docs}), 1)
        verify_publication(self.output, self.root / "snapshot.schema.json")


if __name__ == "__main__":
    unittest.main()
