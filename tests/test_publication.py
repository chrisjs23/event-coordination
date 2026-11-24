"""Publication entry points preserve captures and verify written artifacts."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_capture as fixtures
from publication import publish_review
from snapshots import FILENAMES, verify_publication
import pipeline

ROOT = fixtures.ROOT
SCRIPT = ROOT / "event-planning-coordination-brief/scripts/run.py"
VERIFY = ROOT / "event-planning-coordination-brief/scripts/snapshots.py"


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "run"
        (self.output / "snapshots").mkdir(parents=True)
        for name in FILENAMES[:7]:
            shutil.copy2(ROOT / "deliverables/snapshots" / name, self.output / "snapshots" / name)
        shutil.copytree(ROOT / "deliverables/snapshots/evidence", self.output / "snapshots/evidence")

    def test_cli_publication_then_standalone_verification(self):
        old = {name: (self.output / "snapshots" / name).read_bytes() for name in FILENAMES[:7]}
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--through", "publication-validation",
                                 "--resume-review", "--output-dir", str(self.output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "complete")
        self.assertEqual(json.loads(result.stdout)["snapshots"], 9)
        for name, content in old.items():
            self.assertEqual((self.output / "snapshots" / name).read_bytes(), content)
        verified = subprocess.run([sys.executable, "-B", str(VERIFY), str(self.output),
                                   "--through", "publication-validation"], capture_output=True, text=True)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        artifact = self.output / "event-plan.md"
        artifact.write_text(artifact.read_text().replace("512000", "512001"))
        damaged = subprocess.run([sys.executable, "-B", str(VERIFY), str(self.output),
                                  "--through", "publication-validation"], capture_output=True, text=True)
        self.assertNotEqual(damaged.returncode, 0)

    def test_repeated_publication_rejects_before_modifying_outputs(self):
        publish_review(ROOT, self.output)
        originals = {p: p.read_bytes() for p in self.output.glob("*") if p.is_file()}
        with self.assertRaises(FileExistsError):
            publish_review(ROOT, self.output)
        for path, content in originals.items():
            self.assertEqual(path.read_bytes(), content)

    def test_invalid_generated_draft_is_retained_as_failed_publication(self):
        import publication
        original = publication.render_drafts

        def invalid(context):
            payloads = original(context)
            payloads["vendor-comparison.csv"] = b"wrong,columns\n"
            return payloads

        with patch.object(publication, "render_drafts", side_effect=invalid):
            with self.assertRaisesRegex(ValueError, "publication failed"):
                publish_review(ROOT, self.output)
        failure = json.loads((self.output / "failure.json").read_text())
        self.assertEqual(failure["affected_stage"], "draft-propagation-or-publication-validation")
        final = json.loads((self.output / "snapshots" / FILENAMES[8]).read_text())
        self.assertEqual(final["status"], "failed")
        self.assertEqual(final["state"]["publication_status"], "failed")
        self.assertEqual((self.output / "vendor-comparison.csv").read_bytes(), b"wrong,columns\n")

    def test_shared_model_mismatch_is_rejected_before_rendering(self):
        path = self.output / "snapshots" / FILENAMES[6]
        doc = json.loads(path.read_text())
        doc["state"]["model"]["selected_option"]["cost_twd"] += 1
        path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, "Selected option disagrees"):
            publish_review(ROOT, self.output)
        self.assertFalse((self.output / "event-plan.md").exists())

    def test_fresh_capture_can_write_a_valid_blocked_nine_stage_result(self):
        case = fixtures.CapturePipelineTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        shutil.copy2(ROOT / "event-planning-coordination-brief/references/planning-policy.json",
                     case.root / "event-planning-coordination-brief/references/planning-policy.json")
        result = pipeline.run_baseline(case.root, case.output, fetch=fixtures.FakeTransport(case.root),
                                       through="publication-validation")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["snapshots"], 9)
        self.assertEqual(verify_publication(case.output, case.root / "snapshot.schema.json")["snapshots"], 9)
        from icalendar import Calendar
        self.assertEqual(Calendar.from_ical((case.output / "event-calendar.ics").read_bytes()).walk("VEVENT"), [])

    def test_resume_review_requires_publication_boundary(self):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--resume-review"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
