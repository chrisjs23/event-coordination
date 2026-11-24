import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "event-planning-coordination-brief/scripts/snapshots.py"
spec = importlib.util.spec_from_file_location("snapshots", SCRIPT)
snapshots = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshots)


def fixture_chain(tmp_path):
    output = tmp_path / "deliverables"
    evidence = output / "snapshots/evidence/source.txt"
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(b"captured source")
    digest = snapshots.sha256(b"captured source")
    writer = snapshots.SnapshotWriter(output, ROOT / "snapshot.schema.json", "run-test")
    states = [
        {"objective": "Demo event", "decision_deadline": "2026-08-26T12:00:00+08:00",
         "owners": ["Operations"], "approval_gates": ["review"],
         "records": [{"id": "scope-1", "summary": "Scope captured", "evidence_ids": []}]},
        {"sources": [{"id": "source-1", "summary": "Brief", "evidence_ids": [],
                      "source_role": "event-brief", "locator": "local test",
                      "retrieved_at": "2026-11-23T12:00:00Z", "retrieval_status": "retrieved",
                      "content_type": "text/plain", "version_metadata": None,
                      "content_hash": digest, "local_reference": "snapshots/evidence/source.txt",
                      "observations": [{"id": "obs-1", "summary": "Evidence",
                                        "locator": {"kind": "section", "value": "A"}}]}]},
        {"hard_constraints": [], "preferences": [], "assumptions": [], "unknowns": [],
         "conflicts": [], "notes": [{"id": "constraint-1", "summary": "Based on source",
                                      "evidence_ids": ["obs-1"]}]},
        {"headcount_basis": [], "schedule_dependencies": [], "budget_baseline": [],
         "accessibility_baseline": []},
        {"options": [{"id": "option-1", "summary": "Candidate",
                       "evidence_ids": []}], "rejected_early": []},
        {"option_results": [{"id": "result-1", "option_id": "option-1",
                              "summary": "Feasible candidate", "evidence_ids": [],
                              "feasibility": "feasible"}], "unresolved_conditions": []},
        {"recommendation": "option-1", "tradeoffs": [], "learner_decisions": [],
         "approval_requirements": [{"id": "approval-1", "summary": "Human review",
                                    "evidence_ids": [], "status": "pending"}]},
    ]
    consumed = ([], ["scope-1"], ["source-1"], ["constraint-1"],
                ["constraint-1"], ["option-1"], ["result-1"])
    produced = (["scope-1"], ["source-1", "obs-1"], ["constraint-1"], [],
                ["option-1"], ["result-1"], ["approval-1"])
    for i, state in enumerate(states, 1):
        writer.write(i, state, consumed[i - 1], produced[i - 1], [])
    return output


def fixture_publication(tmp_path):
    output = fixture_chain(tmp_path)
    writer = snapshots.SnapshotWriter(output, ROOT / "snapshot.schema.json", "run-test")
    artifacts = []
    for name in snapshots.PUBLICATION_ARTIFACTS:
        content = f"placeholder: {name}\n".encode()
        (output / name).write_bytes(content)
        artifacts.append({"id": f"artifact:{name}", "path": name,
                          "sha256": snapshots.sha256(content), "validation_status": "valid"})
    writer.write(8, {"artifact_drafts": artifacts, "affected_dependencies": [],
                     "unresolved_items": []}, ["approval-1"],
                 [item["id"] for item in artifacts], [])
    writer.write(9, {"artifacts": artifacts,
                     "validation_checks": [{"id": "validation:artifact-checks",
                                            "summary": "Artifact structure and hashes checked",
                                            "evidence_ids": [], "outcome": "passed"}],
                     "publication_status": "validated"},
                 [item["id"] for item in artifacts], ["validation:artifact-checks"], [],
                 status="complete")
    return output


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp_path = Path(self.temp.name)

    def test_first_four_round_trip(self):
        output = fixture_chain(self.tmp_path)
        result = snapshots.verify_baseline(output, ROOT / "snapshot.schema.json")
        self.assertEqual(result, {"run_id": "run-test", "status": "partial", "snapshots": 4,
                                  "evidence_files": 1})

    def test_seven_snapshot_review_round_trip(self):
        output = fixture_chain(self.tmp_path)
        result = snapshots.verify_review(output, ROOT / "snapshot.schema.json")
        self.assertEqual(result["snapshots"], 7)

    def test_nine_snapshot_publication_round_trip_and_writer_limit(self):
        output = fixture_publication(self.tmp_path)
        result = snapshots.verify_publication(output, ROOT / "snapshot.schema.json")
        self.assertEqual(result["snapshots"], 9)
        self.assertEqual(result["status"], "complete")
        writer = snapshots.SnapshotWriter(output, ROOT / "snapshot.schema.json", "run-test")
        with self.assertRaisesRegex(ValueError, "1 through 9"):
            writer.write(10, {}, [], [], [])

    def test_publication_rejects_artifact_and_validation_failures(self):
        for mutation in ("missing", "corrupt", "false-validation", "changed-metadata"):
            with self.subTest(mutation=mutation):
                case = self.tmp_path / mutation
                case.mkdir()
                output = fixture_publication(case)
                artifact = snapshots.PUBLICATION_ARTIFACTS[0]
                final = output / "snapshots" / snapshots.FILENAMES[8]
                if mutation == "missing":
                    (output / artifact).unlink()
                elif mutation == "corrupt":
                    (output / artifact).write_bytes(b"corrupt")
                else:
                    data = json.loads(final.read_text())
                    if mutation == "false-validation":
                        data["state"]["validation_checks"][0]["outcome"] = "failed"
                    else:
                        data["state"]["artifacts"][0]["sha256"] = snapshots.sha256(b"other")
                    # Rebind stage 09 to stage 08 to reach artifact semantic checks.
                    data["predecessor"]["sha256"] = snapshots.sha256(
                        (output / "snapshots" / snapshots.FILENAMES[7]).read_bytes())
                    final.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    snapshots.verify_publication(output, ROOT / "snapshot.schema.json")

    def test_review_requires_all_seven_snapshots(self):
        output = fixture_chain(self.tmp_path)
        (output / "snapshots" / snapshots.FILENAMES[4]).unlink()
        with self.assertRaises(OSError):
            snapshots.verify_review(output, ROOT / "snapshot.schema.json")

    def test_review_rejects_bad_option_links_and_recommendations(self):
        for mutation in ("unknown-option", "duplicate-option", "duplicate-result",
                         "non-feasible-recommendation", "unknown-recommendation", "missing-result"):
            with self.subTest(mutation=mutation):
                case = self.tmp_path / mutation
                case.mkdir()
                output = fixture_chain(case)
                option_results = output / "snapshots" / snapshots.FILENAMES[5]
                options = output / "snapshots" / snapshots.FILENAMES[4]
                decision = output / "snapshots" / snapshots.FILENAMES[6]
                if mutation == "unknown-option":
                    data = json.loads(option_results.read_text())
                    data["state"]["option_results"][0]["option_id"] = "missing"
                    option_results.write_text(json.dumps(data))
                elif mutation == "duplicate-option":
                    data = json.loads(options.read_text())
                    data["state"]["options"].append(dict(data["state"]["options"][0]))
                    options.write_text(json.dumps(data))
                elif mutation == "duplicate-result":
                    data = json.loads(options.read_text())
                    data["state"]["options"].append({"id": "option-2", "summary": "Second",
                                                       "evidence_ids": []})
                    options.write_text(json.dumps(data))
                    data = json.loads(option_results.read_text())
                    data["state"]["option_results"].append({
                        "id": "result-2", "option_id": "option-1", "summary": "Duplicate",
                        "evidence_ids": [], "feasibility": "feasible"})
                    option_results.write_text(json.dumps(data))
                elif mutation == "missing-result":
                    data = json.loads(option_results.read_text())
                    data["state"]["option_results"] = []
                    option_results.write_text(json.dumps(data))
                    data = json.loads(decision.read_text())
                    data["state"]["recommendation"] = None
                    decision.write_text(json.dumps(data))
                else:
                    data = json.loads(decision.read_text())
                    data["state"]["recommendation"] = "missing" if mutation == "unknown-recommendation" else "option-1"
                    if mutation == "non-feasible-recommendation":
                        data6 = json.loads(option_results.read_text())
                        data6["state"]["option_results"][0]["feasibility"] = "conditional"
                        option_results.write_text(json.dumps(data6))
                    else:
                        decision.write_text(json.dumps(data))
                # Rebind predecessor hashes so this reaches semantic checks.
                for index, filename in enumerate(snapshots.FILENAMES[1:7], 1):
                    path = output / "snapshots" / filename
                    data = json.loads(path.read_text())
                    previous = output / "snapshots" / snapshots.FILENAMES[index - 1]
                    data["predecessor"]["sha256"] = snapshots.sha256(previous.read_bytes())
                    path.write_text(json.dumps(data))
                expected = {
                    "unknown-option": "unknown option",
                    "duplicate-option": "option IDs are not unique",
                    "duplicate-result": "duplicate option result",
                    "non-feasible-recommendation": "existing feasible",
                    "unknown-recommendation": "existing feasible",
                    "missing-result": "Every generated option",
                }
                with self.assertRaisesRegex(ValueError, expected[mutation]):
                    snapshots.verify_review(output, ROOT / "snapshot.schema.json")

    def test_writer_does_not_overwrite(self):
        output = fixture_chain(self.tmp_path)
        target = output / "snapshots" / snapshots.FILENAMES[0]
        original = target.read_bytes()
        writer = snapshots.SnapshotWriter(output, ROOT / "snapshot.schema.json", "run-test")
        with self.assertRaises(FileExistsError):
            writer.write(1, {}, [], [], [])
        self.assertEqual(target.read_bytes(), original)

    def test_verifier_rejects_corruption(self):
        for mutation in ("predecessor", "evidence", "unresolved", "consumed", "timestamp"):
            with self.subTest(mutation=mutation):
                case = self.tmp_path / mutation
                case.mkdir()
                output = fixture_chain(case)
                files = [output / "snapshots" / f for f in snapshots.FILENAMES]
                if mutation == "predecessor":
                    data = json.loads(files[2].read_text())
                    data["predecessor"]["sha256"] = "sha256:" + "0" * 64
                    files[2].write_text(json.dumps(data))
                elif mutation == "evidence":
                    (output / "snapshots/evidence/source.txt").write_bytes(b"tampered")
                elif mutation == "unresolved":
                    data = json.loads(files[2].read_text())
                    data["state"]["notes"][0]["evidence_ids"] = ["missing-evidence"]
                    files[2].write_text(json.dumps(data))
                elif mutation == "consumed":
                    data = json.loads(files[2].read_text())
                    data["consumed_record_ids"] = ["absent-record"]
                    files[2].write_text(json.dumps(data))
                else:
                    data = json.loads(files[0].read_text())
                    data["created_at"] = "2026-11-23T12:00:00"
                    files[0].write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    snapshots.verify_baseline(output, ROOT / "snapshot.schema.json")

    def test_rejects_duplicate_snapshot_and_observation_ids(self):
        for duplicate in ("snapshot", "observation"):
            with self.subTest(duplicate=duplicate):
                case = self.tmp_path / duplicate
                case.mkdir()
                output = fixture_chain(case)
                files = [output / "snapshots" / f for f in snapshots.FILENAMES]
                if duplicate == "snapshot":
                    data = json.loads(files[1].read_text())
                    data["snapshot_id"] = "run-test:01"
                    files[1].write_text(json.dumps(data))
                else:
                    data = json.loads(files[3].read_text())
                    data["state"]["accessibility_baseline"] = [{"id": "obs-1", "summary": "x",
                                                                    "evidence_ids": []}]
                    data["produced_record_ids"] = ["obs-1"]
                    files[3].write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    snapshots.verify_baseline(output, ROOT / "snapshot.schema.json")

    def test_retrieved_source_requires_hash_and_contained_path(self):
        for field, value in (("content_hash", None), ("local_reference", "../../outside")):
            with self.subTest(field=field):
                case = self.tmp_path / field
                case.mkdir()
                output = fixture_chain(case)
                path = output / "snapshots" / snapshots.FILENAMES[1]
                data = json.loads(path.read_text())
                data["state"]["sources"][0][field] = value
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    snapshots.verify_baseline(output, ROOT / "snapshot.schema.json")


    def test_missing_retrieved_evidence_fails(self):
        output = fixture_chain(self.tmp_path)
        (output / "snapshots/evidence/source.txt").unlink()
        with self.assertRaisesRegex(ValueError, "missing source evidence"):
            snapshots.verify_baseline(output, ROOT / "snapshot.schema.json")


if __name__ == "__main__":
    unittest.main()
