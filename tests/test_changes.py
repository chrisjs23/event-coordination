"""Prior-run inspection and source comparison tests."""

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "event-planning-coordination-brief/scripts"))
import changes
import test_refresh as golden


def source(content_hash="h1", *, status="retrieved", row=2, fields="price", summary="Price 10", price=10,
           metadata=None):
    return {"id": "source:vendors", "retrieval_status": status, "content_hash": content_hash,
            "source_role": "vendor-record", "version_metadata": {"record_version": "v1"} if metadata is None else metadata,
            "observations": [{"id": "obs:vendors:item-1", "summary": summary,
                              "locator": {"kind": "cell-range", "value": f"Sheet, row {row}, fields {fields}"},
                              "data": {"price": price, "_row": row}}]}


class ChangeTests(unittest.TestCase):
    def make_archive(self, destination):
        case = golden.RefreshTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.run_refresh()
        shutil.copytree(case.output, destination, symlinks=True)

    def test_row_reorder_is_evidence_unchanged_even_when_source_hash_changes(self):
        previous = {"run_id": "run-" + "a" * 32, "integrity": "validated-publication",
                    "sources": [source()], "policy": {"buffer_people": 2, "buffer_rationale": "r", "venue": "v1"}}
        new = source("h2", row=8, fields="price, status")
        result = changes.describe_change(previous, [new], dict(previous["policy"]))
        self.assertEqual(result["changed_source_ids"], ["source:vendors"])
        self.assertEqual(result["changed_record_ids"], [])
        self.assertEqual(result["unchanged_evidence_ids"], ["obs:vendors:item-1"])

    def test_null_version_metadata_is_safe_and_cell_header_reorder_is_semantically_stable(self):
        previous = {"integrity": "validated-publication", "sources": [source(metadata=None)],
                    "policy": {"buffer_people": 1, "buffer_rationale": "r"},
                    "history_path": "deliverables/history/run-old"}
        new = source("h2", row=12, fields="status, price", metadata=None)
        result = changes.describe_change(previous, [new], previous["policy"])
        self.assertEqual(result["changed_record_ids"], [])
        self.assertEqual(result["predecessor_history"], "deliverables/history/run-old")

    def test_changed_price_changes_source_and_observation(self):
        previous = {"run_id": None, "integrity": "validated-review", "sources": [source()],
                    "policy": {"buffer_people": 2, "buffer_rationale": "r"}}
        result = changes.describe_change(previous, [source("h2", summary="Price 12", price=12)], previous["policy"])
        self.assertEqual(result["changed_source_ids"], ["source:vendors"])
        self.assertEqual(result["changed_record_ids"], ["obs:vendors:item-1"])
        self.assertIn("decision:selection", result["affected_decision_ids"])

    def test_status_and_policy_changes_are_reported(self):
        previous = {"integrity": "validated-publication", "sources": [source()],
                    "policy": {"buffer_people": 2, "buffer_rationale": "r", "venue": "v1"}}
        result = changes.describe_change(previous, [source(status="unavailable")],
                                         {"buffer_people": 3, "buffer_rationale": "new", "venue": "v2"})
        self.assertEqual(result["changed_decision_ids"], ["decision:headcount-buffer", "decision:selection"])
        self.assertEqual(result["affected_decision_ids"], ["decision:headcount-buffer", "decision:selection"])

    def test_unknown_previous_does_not_invent_history_ids(self):
        result = changes.describe_change({"run_id": None, "integrity": "unverified", "sources": None,
                                          "policy": None}, [source()], {})
        self.assertEqual(result["comparison_status"], "comparison-unverified")
        self.assertEqual(result["changed_source_ids"], [])
        self.assertEqual(result["changed_record_ids"], [])
        self.assertEqual(result["unchanged_evidence_ids"], [])

    def test_inspects_copied_valid_publication_and_corrupt_output_falls_back_to_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            archived = Path(tmp) / "archive"
            self.make_archive(archived)
            result = changes.inspect_previous(ROOT, archived)
            self.assertEqual(result["integrity"], "validated-publication")
            self.assertTrue(result["identity_verified"])
            (archived / "event-plan.md").write_text("corrupt", encoding="utf-8")
            result = changes.inspect_previous(ROOT, archived)
            self.assertEqual(result["integrity"], "validated-review")
            self.assertIsInstance(result["sources"], list)
            self.assertIsInstance(result["policy"], dict)

    def test_failure_record_blocks_publication_but_valid_review_remains_usable(self):
        with tempfile.TemporaryDirectory() as tmp:
            archived = Path(tmp) / "archive"
            self.make_archive(archived)
            (archived / "failure.json").write_text("{}", encoding="utf-8")
            result = changes.inspect_previous(ROOT, archived)
            self.assertEqual(result["integrity"], "validated-review")
            self.assertTrue(result["identity_verified"])

    def test_corrupt_source_evidence_returns_no_reusable_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            archived = Path(tmp) / "archive"
            self.make_archive(archived)
            evidence = next((archived / "snapshots/evidence").iterdir())
            evidence.write_bytes(b"corrupt")
            result = changes.inspect_previous(ROOT, archived)
            self.assertEqual(result["integrity"], "unverified")
            self.assertIsNone(result["sources"])
            self.assertFalse(result["identity_verified"])
            self.assertTrue(all(set(error) == {"stage", "error"} for error in result["integrity_errors"]))

    def test_symlinked_snapshot_is_rejected_without_reusing_external_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archived = base / "archive"
            self.make_archive(archived)
            external = base / "external.json"
            external.write_bytes((archived / "snapshots/01-scope-and-approval-gates.json").read_bytes())
            (archived / "snapshots/01-scope-and-approval-gates.json").unlink()
            (archived / "snapshots/01-scope-and-approval-gates.json").symlink_to(external)
            result = changes.inspect_previous(ROOT, archived)
            self.assertEqual(result["integrity"], "unverified")
            self.assertIsNone(result["run_id"])
            self.assertIsNone(result["sources"])
            self.assertEqual(result["integrity_errors"], [{"stage": "archive", "error": "UnsafeSymlink"}])

    def test_symlinked_failure_record_is_rejected_without_reading_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archived = base / "archive"
            self.make_archive(archived)
            external = base / "failure.json"
            external.write_text(json.dumps({"run_id": "run-" + "b" * 32}), encoding="utf-8")
            (archived / "failure.json").symlink_to(external)
            result = changes.inspect_previous(ROOT, archived)
            self.assertEqual(result["integrity"], "unverified")
            self.assertIsNone(result["run_id"])
            self.assertIsNone(result["sources"])


if __name__ == "__main__":
    unittest.main()
