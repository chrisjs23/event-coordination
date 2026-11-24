import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "event-planning-coordination-brief/scripts/history.py"
spec = importlib.util.spec_from_file_location("history", SCRIPT)
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "deliverables"
        self.root.mkdir()

    def test_copy_inventory_and_history_exclusion(self):
        (self.root / "nested").mkdir()
        (self.root / "nested/data.bin").write_bytes(b"\x00original\xff")
        (self.root / "notes.txt").write_text("keep", encoding="utf-8")
        (self.root / "nested/link").symlink_to("../notes.txt")
        (self.root / "history").mkdir()
        (self.root / "history/old.txt").write_text("older")
        expected = history.inventory(self.root)
        archived = history.archive_current(self.root, "run-one")
        self.assertEqual(archived, self.root / "history/run-one")
        self.assertEqual(history.verify_archive(archived), expected)
        self.assertEqual((archived / "nested/data.bin").read_bytes(), b"\x00original\xff")
        self.assertEqual((archived / "nested/link").readlink(), Path("../notes.txt"))
        self.assertFalse((archived / "history").exists())
        self.assertEqual((self.root / "history/old.txt").read_text(), "older")

    def test_identical_run_reuses_archive_and_changed_content_goes_to_attempt(self):
        source = self.root / "draft.md"
        source.write_text("first")
        first = history.archive_current(self.root, "same-run")
        self.assertEqual(history.archive_current(self.root, "same-run"), first)
        source.write_text("changed")
        attempt = history.archive_current(self.root, "same-run")
        self.assertTrue(attempt.is_relative_to(first / "attempts"))
        self.assertEqual(history.verify_archive(attempt), history.inventory(self.root))
        self.assertEqual((first / "draft.md").read_text(), "first")

    def test_corrupted_existing_archive_is_preserved_without_reuse(self):
        current = self.root / "draft.md"
        current.write_text("current")
        archived = history.archive_current(self.root, "run")
        (archived / "draft.md").write_text("corrupt")
        current_before = current.read_bytes()
        archive_before = (archived / "draft.md").read_bytes()
        attempt = history.archive_current(self.root, "run")
        self.assertTrue(attempt.is_relative_to(archived / "attempts"))
        self.assertEqual(history.verify_archive(attempt), history.inventory(self.root))
        with self.assertRaisesRegex(ValueError, "contents do not match"):
            history.verify_archive(archived)
        self.assertEqual(current.read_bytes(), current_before)
        self.assertEqual((archived / "draft.md").read_bytes(), archive_before)

    def test_invalid_run_id_is_confined_to_generated_name(self):
        (self.root / "x").write_text("x")
        archived = history.archive_current(self.root, "../../outside")
        self.assertEqual(archived.parent, self.root / "history")
        self.assertTrue(archived.name.startswith("unidentified-"))

    def test_symlink_is_inventoried_without_following(self):
        external = Path(self.temp.name) / "external"
        external.write_text("secret")
        (self.root / "link").symlink_to(external)
        self.assertEqual(history.inventory(self.root), {"link": {"symlink": str(external)}})
        archived = history.archive_current(self.root, "links")
        self.assertTrue((archived / "link").is_symlink())
        self.assertEqual((archived / "link").readlink(), external)

    def test_missing_archived_file_is_detected(self):
        (self.root / "file").write_text("data")
        archived = history.archive_current(self.root, "missing")
        (archived / "file").unlink()
        with self.assertRaisesRegex(ValueError, "contents do not match"):
            history.verify_archive(archived)

    def test_source_manifest_collision_and_bad_root_are_rejected(self):
        (self.root / "archive-manifest.json").write_text("source")
        with self.assertRaisesRegex(ValueError, "reserved archive manifest"):
            history.archive_current(self.root, "collision")
        with self.assertRaisesRegex(ValueError, "real directory"):
            history.inventory(self.root / "archive-manifest.json")
        link = Path(self.temp.name) / "root-link"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "real directory"):
            history.inventory(link)

    def test_history_symlink_is_rejected_without_touching_outside(self):
        outside = Path(self.temp.name) / "outside-history"
        outside.mkdir()
        sentinel = outside / "sentinel"
        sentinel.write_text("unchanged")
        (self.root / "draft").write_text("current")
        (self.root / "history").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "history destination.*symbolic link"):
            history.archive_current(self.root, "run")
        self.assertEqual(sentinel.read_text(), "unchanged")
        self.assertEqual(list(outside.iterdir()), [sentinel])

    def test_attempts_symlink_is_rejected_without_touching_outside(self):
        (self.root / "draft").write_text("first")
        archive = history.archive_current(self.root, "run")
        outside = Path(self.temp.name) / "outside-attempts"
        outside.mkdir()
        sentinel = outside / "sentinel"
        sentinel.write_text("unchanged")
        (archive / "attempts").symlink_to(outside, target_is_directory=True)
        (self.root / "draft").write_text("changed")
        with self.assertRaisesRegex(ValueError, "attempts destination.*symbolic link"):
            history.archive_current(self.root, "run")
        self.assertEqual(sentinel.read_text(), "unchanged")
        self.assertEqual(list(outside.iterdir()), [sentinel])

    def test_archive_manifest_symlink_is_rejected_without_reading_target(self):
        archive = self.root / "archive"
        archive.mkdir()
        outside = Path(self.temp.name) / "outside-manifest.json"
        payload = json.dumps({"files": {}, "recorded_at": "now"})
        outside.write_text(payload)
        (archive / "archive-manifest.json").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "manifest.*symbolic link"):
            history.verify_archive(archive)
        self.assertEqual(outside.read_text(), payload)

    def _linked_run(self, reference="history/prior", include_hash=True, hash_value=None):
        (self.root / "history").mkdir(exist_ok=True)
        prior = self.root / "history/prior"
        prior.mkdir(exist_ok=True)
        (prior / "old.txt").write_text("old run")
        (prior / "archive-manifest.json").unlink(missing_ok=True)
        files = history.inventory(prior)
        (prior / "archive-manifest.json").write_text(json.dumps({
            "files": files, "recorded_at": "2026-11-24T12:00:00+00:00"
        }, indent=2) + "\n", encoding="utf-8")
        manifest_hash = "sha256:" + hashlib.sha256(
            (prior / "archive-manifest.json").read_bytes()).hexdigest()
        state = {"predecessor_history": reference}
        if include_hash:
            state["predecessor_archive_sha256"] = hash_value or manifest_hash
        snapshots = self.root / "snapshots"
        snapshots.mkdir(exist_ok=True)
        (snapshots / "01-scope-and-approval-gates.json").write_text(
            json.dumps({"state": state}), encoding="utf-8")
        return manifest_hash

    def test_verify_history_link_accepts_matching_archive_hash(self):
        self._linked_run()
        self.assertIsNone(history.verify_history_link(self.root))

    def test_verify_history_link_rejects_escaping_path_and_missing_hash(self):
        self._linked_run(reference="history/../outside")
        with self.assertRaisesRegex(ValueError, "path is invalid"):
            history.verify_history_link(self.root)
        self._linked_run(include_hash=False)
        with self.assertRaisesRegex(ValueError, "hash is required"):
            history.verify_history_link(self.root)

    def test_verify_history_link_rejects_mismatched_manifest_hash(self):
        self._linked_run(hash_value="sha256:" + "0" * 64)
        with self.assertRaisesRegex(ValueError, "hash does not match"):
            history.verify_history_link(self.root)

    def test_verify_history_link_rejects_symlinked_history(self):
        outside = Path(self.temp.name) / "outside-history-link"
        outside.mkdir()
        (outside / "prior").mkdir()
        sentinel = outside / "sentinel"
        sentinel.write_text("unchanged")
        (self.root / "history").symlink_to(outside, target_is_directory=True)
        snapshots = self.root / "snapshots"
        snapshots.mkdir()
        (snapshots / "01-scope-and-approval-gates.json").write_text(json.dumps({
            "state": {"predecessor_history": "history/prior",
                      "predecessor_archive_sha256": "sha256:" + "0" * 64}
        }))
        with self.assertRaisesRegex(ValueError, "history path.*symbolic link"):
            history.verify_history_link(self.root)
        self.assertEqual(sentinel.read_text(), "unchanged")

    def _point_stage_one_to(self, reference, manifest_path):
        digest = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        snapshots = self.root / "snapshots"
        snapshots.mkdir(exist_ok=True)
        (snapshots / "01-scope-and-approval-gates.json").write_text(json.dumps({
            "state": {"predecessor_history": reference,
                      "predecessor_archive_sha256": digest}
        }), encoding="utf-8")

    def test_archived_run_resolves_predecessor_in_sibling_namespace(self):
        (self.root / "draft").write_text("older")
        first = history.archive_current(self.root, "older")
        self._point_stage_one_to("history/older", first / "archive-manifest.json")
        (self.root / "draft").write_text("newer")
        second = history.archive_current(self.root, "newer")
        history.verify_history_link(second)

    def test_collision_attempt_path_can_be_verified(self):
        (self.root / "draft").write_text("initial")
        first = history.archive_current(self.root, "same")
        self._point_stage_one_to("history/same", first / "archive-manifest.json")
        (self.root / "draft").write_text("changed")
        attempt = history.archive_current(self.root, "same")
        reference = attempt.relative_to(self.root).as_posix()
        self.assertRegex(reference, r"^history/same/attempts/attempt-[0-9a-f]{32}$")
        history.verify_history_link(attempt)

    def test_empty_output_returns_none(self):
        self.assertIsNone(history.archive_current(self.root, "empty"))


if __name__ == "__main__":
    unittest.main()
