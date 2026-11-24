import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "event-planning-coordination-brief" / "scripts" / "run.py"


class CommandTests(unittest.TestCase):
    def run_command(self, *args, cwd=None, script=SCRIPT):
        return subprocess.run(
            [sys.executable, "-B", str(script), *map(str, args)],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_help(self):
        result = self.run_command("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--check", result.stdout)
        self.assertIn("--output-dir", result.stdout)

    def test_check_from_unrelated_cwd_reports_paths_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            cwd = Path(temporary)
            sentinel = cwd / "deliverables"
            sentinel.mkdir()
            keep = sentinel / "keep.txt"
            keep.write_text("preserve me", encoding="utf-8")
            result = self.run_command("--check", cwd=cwd)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["mode"], "preflight")
            self.assertIs(report["pipeline_available"], True)
            self.assertEqual(report["business_clock"], "2026-08-26T12:00:00+08:00")
            self.assertEqual(
                report["output_dir"], str((ROOT / "deliverables").resolve())
            )
            self.assertEqual(report["schema_path"], str((ROOT / "snapshot.schema.json").resolve()))
            self.assertEqual(
                report["source_map_path"],
                str((ROOT / "event-planning-coordination-brief/references/sheets.json").resolve()),
            )
            self.assertEqual(keep.read_text(encoding="utf-8"), "preserve me")
            self.assertEqual(set(p.name for p in sentinel.iterdir()), {"keep.txt"})

    def test_supplied_relative_and_absolute_output_paths_are_reported_without_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            cwd = Path(temporary)
            existing = cwd / "existing"
            existing.mkdir()
            sentinel = existing / "sentinel"
            sentinel.write_text("unchanged", encoding="utf-8")
            relative = self.run_command("--check", "--output-dir", "existing", cwd=cwd)
            self.assertEqual(relative.returncode, 0, relative.stderr)
            self.assertEqual(json.loads(relative.stdout)["output_dir"], str(existing.resolve()))
            absolute = cwd / "new-output"
            result = self.run_command("--check", "--output-dir", absolute, cwd=cwd)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["output_dir"], str(absolute.resolve()))
            self.assertFalse(absolute.exists())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "unchanged")

    def test_default_without_check_exits_three_cleanly(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "deliverables"
            output.mkdir()
            sentinel = output / "sentinel.txt"
            sentinel.write_text("preserve me", encoding="utf-8")
            result = self.run_command("--output-dir", output, cwd=ROOT)
            self.assertEqual(result.returncode, 3)
            self.assertEqual(result.stdout, "")
            self.assertTrue(result.stderr.strip())
            self.assertIn("--check", result.stderr)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve me")

    def test_missing_and_corrupt_prerequisites_fail_cleanly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / "event-planning-coordination-brief/scripts/run.py"
            script.parent.mkdir(parents=True)
            shutil.copy2(SCRIPT, script)
            (root / "event-planning-coordination-brief/references").mkdir(parents=True)
            missing = self.run_command("--check", script=script)
            self.assertEqual(missing.returncode, 1)
            self.assertEqual(missing.stdout, "")
            self.assertTrue(missing.stderr.strip())
            self.assertNotIn("Traceback", missing.stderr)

            shutil.copy2(ROOT / "snapshot.schema.json", root / "snapshot.schema.json")
            shutil.copy2(
                ROOT / "event-planning-coordination-brief/references/sheets.json",
                root / "event-planning-coordination-brief/references/sheets.json",
            )
            (root / "event-planning-coordination-brief/references/sheets.json").write_text(
                "{}", encoding="utf-8"
            )
            malformed_map = self.run_command("--check", script=script)
            self.assertEqual(malformed_map.returncode, 1)
            self.assertEqual(malformed_map.stdout, "")
            self.assertTrue(malformed_map.stderr.strip())
            self.assertNotIn("Traceback", malformed_map.stderr)

            (root / "snapshot.schema.json").write_text("{broken", encoding="utf-8")
            corrupt = self.run_command("--check", script=script)
            self.assertEqual(corrupt.returncode, 1)
            self.assertEqual(corrupt.stdout, "")
            self.assertTrue(corrupt.stderr.strip())
            self.assertNotIn("Traceback", corrupt.stderr)


if __name__ == "__main__":
    unittest.main()
