"""Execute only the currently implemented source-to-baseline stages."""

import json
from pathlib import Path
import uuid

from baseline import build_baseline
from capture import capture_sources, fetch_public, json_bytes, utcnow
from snapshots import FILENAMES, SnapshotWriter, verify_baseline, verify_review
from options import build_review
from records import read_sheet, validate_sheet
from publication import publish_review


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


def run_baseline(root, output, fetch=fetch_public, *, through="planning-baseline"):
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
        if through in {"decision-and-approval", "publication-validation"}:
            review_result = append_review(root, output, sources, rows, blocks, baseline, constraints)
            if through == "publication-validation":
                return publish_review(root, output)
            return review_result
        result = verify_baseline(output, root / "snapshot.schema.json")
        result.update(completed_through="planning-baseline", pipeline_available=True,
                      output_dir=str(output.resolve()))
        return result
    except Exception as exc:
        # Keep actual source/output attempts and make the incomplete boundary explicit.
        evidence = [p.relative_to(output).as_posix()
                    for p in sorted(output.glob("snapshots/evidence/*")) if p.is_file()]
        failure = {"run_id": run_id, "observed_at": utcnow(),
                   "error": str(exc) if isinstance(exc, (ValueError, OSError)) else type(exc).__name__,
                   "affected_stage": through,
                   "available_evidence": evidence,
                   "affected_artifacts": [p.relative_to(output).as_posix()
                                          for p in sorted(output.glob("snapshots/*.json"))],
                   "next_owner": "Operations",
                   "recovery_action": "Inspect retained attempts and source validation; retry in a fresh output directory"}
        if not (output / "failure.json").exists():
            (output / "failure.json").write_bytes(json_bytes(failure))
        label = "baseline execution failed" if through == "planning-baseline" else "planning execution failed"
        raise ValueError(label + "; inspect " + str(output / "failure.json")) from exc


def append_review(root, output, sources, rows, blocks, baseline, constraints):
    """Append to an explicitly selected captured run after checking its integrity."""
    schema = root / "snapshot.schema.json"
    verified = verify_baseline(output, schema)
    if any((output / "snapshots" / name).exists() for name in FILENAMES[4:]):
        raise FileExistsError("Review snapshots already exist; choose a fresh run")
    policy = json.loads((root / "event-planning-coordination-brief/references/planning-policy.json").read_text())
    states = build_review(sources, rows, blocks, baseline, constraints, policy)
    earlier = []
    for name in FILENAMES[:4]:
        doc = json.loads((output / "snapshots" / name).read_text())
        earlier.extend(doc["produced_record_ids"])
    writer = SnapshotWriter(output, schema, verified["run_id"])
    unresolved = states[3]
    for sequence, state in enumerate(states[:3], 5):
        state = json.loads(json_bytes(state))
        produced = [identity for identity in record_ids(state) if identity not in earlier]
        writer.write(sequence, state, earlier, produced, unresolved, status="partial")
        earlier.extend(produced)
    result = verify_review(output, schema)
    result.update(option_count=len(states[0]["options"]),
                  feasible_options=sum(r["feasibility"] == "feasible" for r in states[1]["option_results"]),
                  recommendation=states[2]["recommendation"],
                  completed_through="decision-and-approval", pipeline_available=True,
                  output_dir=str(output.resolve()))
    return result


def resume_review(root, output):
    """Review retained source observations without changing their retrieval timestamps."""
    root, output = Path(root), Path(output)
    verified = verify_baseline(output, root / "snapshot.schema.json")
    if any((output / "snapshots" / name).exists() for name in FILENAMES[4:]):
        raise FileExistsError("Review snapshots already exist; choose a fresh run")
    docs = [json.loads((output / "snapshots" / name).read_text()) for name in FILENAMES[:4]]
    sources = docs[1]["state"]["sources"]
    contract = json.loads((root / "event-planning-coordination-brief/references/sheets.json").read_text())
    rows = {}
    blocks = []
    for source in sources:
        if source["retrieval_status"] != "retrieved":
            continue
        name = source["id"].removeprefix("source:")
        if name in contract:
            parsed = read_sheet((output / source["local_reference"]).read_bytes(), contract[name])
            rows[name] = validate_sheet(name, parsed["records"])
        elif name == "brief":
            blocks = json.loads((output / source["local_reference"]).read_text())["blocks"]
    try:
        result = append_review(root, output, sources, rows, blocks, docs[3]["state"], docs[2]["state"])
        result["basis"] = "captured-run-review"
        return result
    except Exception as exc:
        failure = {"run_id": verified["run_id"], "observed_at": utcnow(),
                   "error": str(exc) if isinstance(exc, (ValueError, OSError)) else type(exc).__name__,
                   "affected_stage": "option-generation-through-decision-and-approval",
                   "available_evidence": [s["local_reference"] for s in sources if s["local_reference"]],
                   "affected_artifacts": [p.relative_to(output).as_posix() for p in sorted(output.glob("snapshots/*.json"))],
                   "next_owner": "Operations", "recovery_action": "Inspect retained snapshots and review failure"}
        (output / "failure.json").write_bytes(json_bytes(failure))
        raise ValueError("review execution failed; inspect " + str(output / "failure.json")) from exc
