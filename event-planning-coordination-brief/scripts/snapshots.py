#!/usr/bin/env python3
"""Write and verify event-planning stage snapshots."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import jsonschema
from rfc3339_validator import validate_rfc3339

if not hasattr(jsonschema, "Draft202012Validator"):
    raise ImportError("Install the pinned JSON Schema dependencies")


STAGES = (
    "scope-and-approval-gates",
    "source-capture",
    "constraint-model",
    "planning-baseline",
    "option-generation",
    "feasibility-testing",
    "decision-and-approval",
)
FILENAMES = (
    "01-scope-and-approval-gates.json",
    "02-source-capture.json",
    "03-constraint-model.json",
    "04-planning-baseline.json",
    "05-option-generation.json",
    "06-feasibility-testing.json",
    "07-decision-and-approval.json",
)


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read valid JSON from {path}: {exc}") from exc


def _validator(schema_path: Path):
    schema = _load_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    checker = jsonschema.FormatChecker()
    checker.checks("date-time")(validate_rfc3339)
    return jsonschema.Draft202012Validator(schema, format_checker=checker)


def _validate(validator, document):
    errors = sorted(validator.iter_errors(document), key=lambda err: list(map(str, err.path)))
    if errors:
        err = errors[0]
        where = ".".join(map(str, err.path)) or "snapshot"
        raise ValueError(f"schema validation failed at {where} ({err.validator})")


class SnapshotWriter:
    def __init__(self, output_dir: Path, schema_path: Path, run_id: str):
        self.output_dir = Path(output_dir)
        self.schema_path = Path(schema_path)
        self.run_id = run_id
        self.snapshot_dir = self.output_dir / "snapshots"
        self.validator = _validator(self.schema_path)

    def write(self, sequence: int, state: dict, consumed: list[str], produced: list[str],
              unresolved: list[dict], *, status="partial", decisions=None) -> Path:
        if not isinstance(sequence, int) or isinstance(sequence, bool) or not 1 <= sequence <= 7:
            raise ValueError("sequence must be an integer from 1 through 7")
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        target = self.snapshot_dir / FILENAMES[sequence - 1]
        if target.exists():
            raise FileExistsError(f"snapshot already exists: {target}")
        if any((self.snapshot_dir / name).exists() for name in FILENAMES[sequence:]):
            raise ValueError("cannot append a snapshot before an existing later sequence")
        for previous_sequence, filename in enumerate(FILENAMES[:sequence - 1], 1):
            previous = self.snapshot_dir / filename
            if not previous.is_file():
                raise ValueError(f"sequence {sequence} requires prior snapshot {previous}")
            prior_doc = json.loads(previous.read_bytes())
            _validate(self.validator, prior_doc)
            if prior_doc.get("run_id") != self.run_id or prior_doc.get("sequence") != previous_sequence:
                raise ValueError(f"prior snapshot has wrong run_id or sequence: {previous}")
        predecessor = None
        if sequence > 1:
            prev_path = self.snapshot_dir / FILENAMES[sequence - 2]
            if not prev_path.is_file():
                raise ValueError(f"sequence {sequence} requires previous snapshot {prev_path}")
            raw = prev_path.read_bytes()
            prev = json.loads(raw)
            _validate(self.validator, prev)
            if prev.get("run_id") != self.run_id or prev.get("sequence") != sequence - 1:
                raise ValueError("previous snapshot has wrong run_id or sequence")
            predecessor = {"snapshot_id": prev["snapshot_id"],
                           "path": prev_path.relative_to(self.output_dir).as_posix(),
                           "sha256": sha256(raw)}
        document = {
            "schema_version": "event-coordination-stage-snapshot/2",
            "snapshot_id": f"{self.run_id}:{sequence:02d}",
            "run_id": self.run_id,
            "stage": STAGES[sequence - 1],
            "sequence": sequence,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "predecessor": predecessor,
            "consumed_record_ids": consumed,
            "produced_record_ids": produced,
            "state": state,
            "unresolved": unresolved,
            "decisions": decisions or [],
        }
        _validate(self.validator, document)
        payload = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        with target.open("xb") as stream:
            stream.write(payload)
        return target


def _local_evidence_path(output_dir: Path, reference: str) -> Path:
    path = (output_dir / reference).resolve()
    root = output_dir.resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"evidence path escapes output directory: {reference}")
    return path


def _verify(output_dir: Path, schema_path: Path, snapshot_count: int) -> dict:
    output_dir = Path(output_dir)
    snapdir = output_dir / "snapshots"
    validator = _validator(Path(schema_path))
    docs, raws = [], []
    filenames = FILENAMES[:snapshot_count]
    stages = STAGES[:snapshot_count]
    for seq, filename in enumerate(filenames, 1):
        path = snapdir / filename
        raw = path.read_bytes()
        doc = json.loads(raw)
        _validate(validator, doc)
        if doc["sequence"] != seq or doc["stage"] != stages[seq - 1]:
            raise ValueError(f"wrong sequence or stage in {path}")
        try:
            created = datetime.fromisoformat(doc["created_at"].replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid timestamp in {path}") from exc
        if created.utcoffset() is None:
            raise ValueError(f"timestamp lacks timezone in {path}")
        docs.append(doc)
        raws.append(raw)
    run_id = docs[0]["run_id"]
    if any(d["run_id"] != run_id for d in docs):
        raise ValueError("snapshots do not share a run_id")
    snapshot_ids = [d["snapshot_id"] for d in docs]
    if len(set(snapshot_ids)) != len(snapshot_ids):
        raise ValueError("snapshot IDs are not unique")
    for idx, doc in enumerate(docs):
        expected = None if idx == 0 else {
            "snapshot_id": docs[idx - 1]["snapshot_id"],
            "path": (Path("snapshots") / filenames[idx - 1]).as_posix(),
            "sha256": sha256(raws[idx - 1]),
        }
        if doc["predecessor"] != expected:
            raise ValueError(f"invalid predecessor link in {filenames[idx]}")
    produced = set()
    options = {}
    results = {}
    for doc in docs:
        if doc["sequence"] == 5:
            for option in doc["state"]["options"]:
                if option["id"] in options:
                    raise ValueError("option IDs are not unique")
                options[option["id"]] = option
        elif doc["sequence"] == 6:
            seen_options = set()
            for result in doc["state"]["option_results"]:
                option_id = result.get("option_id")
                if option_id not in options:
                    raise ValueError(f"option result references unknown option: {option_id}")
                if option_id in seen_options:
                    raise ValueError(f"duplicate option result for {option_id}")
                seen_options.add(option_id)
                results[option_id] = result
            if seen_options != set(options):
                raise ValueError("Every generated option needs a feasibility result")
        elif doc["sequence"] == 7:
            recommendation = doc["state"]["recommendation"]
            if recommendation is not None and (
                recommendation not in results
                or results[recommendation]["feasibility"] != "feasible"
            ):
                raise ValueError("recommendation must reference an existing feasible option result")

    for doc in docs:
        if any(record_id not in produced for record_id in doc["consumed_record_ids"]):
            raise ValueError(f"consumed record ID has no earlier producer in {doc['snapshot_id']}")
        if any(record_id in produced for record_id in doc["produced_record_ids"]):
            raise ValueError(f"duplicate produced record ID in {doc['snapshot_id']}")
        record_ids = set()

        def collect_ids(value):
            if isinstance(value, dict):
                record_id = value.get("id")
                if isinstance(record_id, str):
                    record_ids.add(record_id)
                for child in value.values():
                    collect_ids(child)
            elif isinstance(value, list):
                for child in value:
                    collect_ids(child)

        collect_ids(doc["state"])
        collect_ids(doc["unresolved"])
        collect_ids(doc["decisions"])
        missing_records = set(doc["produced_record_ids"]) - record_ids
        if missing_records:
            raise ValueError(f"produced record ID has no record object in {doc['snapshot_id']}")
        produced.update(doc["produced_record_ids"])

    sources, observations = {}, set()
    evidence_id_set = set()
    for doc in docs:
        for source in doc["state"].get("sources", []):
            if source["id"] in evidence_id_set:
                raise ValueError("source or observation IDs are not unique")
            evidence_id_set.add(source["id"])
            sources[source["id"]] = source
            for observation in source["observations"]:
                if observation["id"] in evidence_id_set:
                    raise ValueError("source or observation IDs are not unique")
                evidence_id_set.add(observation["id"])
                observations.add(observation["id"])
    valid_evidence = set(sources) | observations
    evidence_count = 0
    for source in sources.values():
        reference, content_hash = source["local_reference"], source["content_hash"]
        if source["retrieval_status"] == "retrieved" and (not reference or not content_hash):
            raise ValueError(f"retrieved source {source['id']} requires evidence path and hash")
        if reference:
            path = _local_evidence_path(output_dir, reference)
            try:
                content = path.read_bytes()
            except OSError as exc:
                raise ValueError(f"missing source evidence for {source['id']}: {reference}") from exc
            evidence_count += 1
            if content_hash is not None and sha256(content) != content_hash:
                raise ValueError(f"source evidence hash mismatch for {source['id']}")

    def check_evidence(value):
        if isinstance(value, dict):
            ids = value.get("evidence_ids", [])
            for evidence_id in ids:
                if evidence_id not in valid_evidence:
                    raise ValueError(f"unresolved evidence ID: {evidence_id}")
            for child in value.values():
                check_evidence(child)
        elif isinstance(value, list):
            for child in value:
                check_evidence(child)

    for doc in docs:
        check_evidence(doc["state"])
        check_evidence(doc["unresolved"])
        check_evidence(doc["decisions"])
    statuses = [d["status"] for d in docs]
    overall_status = next((s for s in ("failed", "blocked", "partial") if s in statuses), "complete")
    return {"run_id": run_id,
            "status": overall_status,
            "snapshots": snapshot_count, "evidence_files": evidence_count}


def verify_baseline(output_dir: Path, schema_path: Path) -> dict:
    """Verify the original four-snapshot planning baseline contract."""
    return _verify(output_dir, schema_path, 4)


def verify_review(output_dir: Path, schema_path: Path) -> dict:
    """Verify the seven-snapshot review contract."""
    return _verify(output_dir, schema_path, 7)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify event-planning snapshots")
    parser.add_argument("output", type=Path)
    parser.add_argument("--through", choices=("planning-baseline", "decision-and-approval"),
                        default="planning-baseline")
    args = parser.parse_args(argv)
    schema_path = Path(__file__).resolve().parents[2] / "snapshot.schema.json"
    try:
        verifier = verify_review if args.through == "decision-and-approval" else verify_baseline
        print(json.dumps(verifier(args.output, schema_path), indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, jsonschema.ValidationError) as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
