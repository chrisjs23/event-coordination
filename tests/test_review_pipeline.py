"""Exercise the seven-snapshot boundary through the pipeline and command."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

import test_capture as fixtures
ROOT = fixtures.ROOT
import pipeline
from snapshots import verify_review


class ReviewPipelineTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.CapturePipelineTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        source = ROOT / "event-planning-coordination-brief/references/planning-policy.json"
        target = self.case.root / "event-planning-coordination-brief/references/planning-policy.json"
        shutil.copy2(source, target)

    def test_fresh_capture_can_stop_at_seven_snapshots(self):
        result = pipeline.run_baseline(self.case.root, self.case.output,
                                       fetch=fixtures.FakeTransport(self.case.root),
                                       through="decision-and-approval")
        self.assertEqual(result["snapshots"], 7)
        self.assertEqual(result["status"], "partial")
        verified = verify_review(self.case.output, self.case.root / "snapshot.schema.json")
        self.assertEqual(verified["snapshots"], 7)

    def test_cli_resumes_the_captured_run_and_preserves_prior_bytes(self):
        self.case.run_pipeline()
        originals = {p: p.read_bytes() for p in self.case.output.glob("snapshots/0*.json")}
        script = ROOT / "event-planning-coordination-brief/scripts/run.py"
        command = [sys.executable, "-B", str(script), "--through", "decision-and-approval",
                   "--resume-baseline", "--output-dir", str(self.case.output)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["snapshots"], 7)
        self.assertEqual(report["basis"], "captured-run-review")
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)
        completed = {p: p.read_bytes() for p in self.case.output.glob("snapshots/0*.json")}
        again = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(again.returncode, 1)
        for path, original in completed.items():
            self.assertEqual(path.read_bytes(), original)

    def test_resume_without_review_boundary_is_an_argument_error(self):
        script = ROOT / "event-planning-coordination-brief/scripts/run.py"
        result = subprocess.run([sys.executable, "-B", str(script), "--resume-baseline"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
