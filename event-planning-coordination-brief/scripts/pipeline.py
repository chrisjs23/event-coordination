"""Execute only the currently implemented source-to-baseline stages."""

import json
from pathlib import Path
import uuid

from baseline import build_baseline
from capture import capture_sources, fetch_public, json_bytes, utcnow
from snapshots import SnapshotWriter, verify_baseline


def record_ids(value):
    """Enumerate defined records, preserving first occurrence for transition metadata."""
    ids = []
    if isinstance(value, dict):
        if isinstance(value.get("id"), str):
            ids.append(value["id"])
        for child in value.values():
            ids.extend(record_ids(child))
    elif isinstance(value, list):
        for child in value:
            ids.extend(record_ids(child))
    return list(dict.fromkeys(ids))


def run_baseline(root, output, fetch=fetch_public):
    root, output = Path(root), Path(output)
    # Until history/recovery is implemented, a fresh directory preserves all earlier work.
    output.mkdir(parents=True, exist_ok=False)
    run_id = "run-" + uuid.uuid4().hex
    sources = []
    try:
        sources, rows, blocks = capture_sources(root, output, fetch)
        sources = json.loads(json_bytes(sources))
        attempts = output / "snapshots/evidence/capture-attempts.json"
        attempts.write_bytes(json_bytes({"run_id": run_id, "sources": sources}))
        scope, constraints, baseline, unresolved = build_baseline(sources, rows, blocks)
        states = [scope, {"sources": sources}, constraints, baseline]
        states = json.loads(json_bytes(states))
        writer = SnapshotWriter(output, root / "snapshot.schema.json", run_id)
        earlier = []
        for sequence, state in enumerate(states, 1):
            produced = [identity for identity in record_ids(state) if identity not in earlier]
            writer.write(sequence, state, earlier, produced,
                         json.loads(json_bytes(unresolved)), status="partial")
            earlier.extend(produced)
        result = verify_baseline(output, root / "snapshot.schema.json")
        result.update(completed_through="planning-baseline", pipeline_available=False,
                      output_dir=str(output.resolve()))
        return result
    except Exception as exc:
        # Keep actual source/output attempts and make the incomplete boundary explicit.
        evidence = [p.relative_to(output).as_posix()
                    for p in sorted(output.glob("snapshots/evidence/*")) if p.is_file()]
        failure = {"run_id": run_id, "observed_at": utcnow(),
                   "error": str(exc) if isinstance(exc, (ValueError, OSError)) else type(exc).__name__,
                   "affected_stage": "source-to-planning-baseline",
                   "available_evidence": evidence,
                   "affected_artifacts": [p.relative_to(output).as_posix()
                                          for p in sorted(output.glob("snapshots/*.json"))],
                   "next_owner": "Operations",
                   "recovery_action": "Inspect retained attempts and source validation; retry in a fresh output directory"}
        (output / "failure.json").write_bytes(json_bytes(failure))
        raise ValueError("baseline execution failed; inspect " + str(output / "failure.json")) from exc
