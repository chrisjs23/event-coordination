"""Inspect verified prior runs and describe changes to planning inputs."""

import json
import os
from pathlib import Path
import re

from snapshots import FILENAMES, verify_baseline, verify_publication, verify_review


_RUN_ID = re.compile(r"run-[a-f0-9]{32}\Z")


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def inspect_previous(root: Path, archived: Path) -> dict:
    """Return only metadata from a prior run that passes its boundary validator."""
    root, archived = Path(root), Path(archived)
    if archived.is_symlink():
        return {"run_id": None, "integrity": "unverified", "identity_verified": False,
                "sources": None, "policy": None,
                "integrity_errors": [{"stage": "archive", "error": "UnsafeSymlink"}]}
    for directory, dirnames, filenames in os.walk(archived, followlinks=False):
        if any((Path(directory) / name).is_symlink() for name in dirnames + filenames):
            return {"run_id": None, "integrity": "unverified", "identity_verified": False,
                    "sources": None, "policy": None,
                    "integrity_errors": [{"stage": "archive", "error": "UnsafeSymlink"}]}
    failure_path = archived / "failure.json"
    failure_present = failure_path.exists() or failure_path.is_symlink()
    failure = _read_json(failure_path)
    observed = _read_json(archived / "snapshots" / FILENAMES[0])
    fallback_id = observed.get("run_id") if isinstance(observed, dict) else None
    if not isinstance(fallback_id, str) or not _RUN_ID.fullmatch(fallback_id):
        fallback_id = failure.get("run_id") if isinstance(failure, dict) else None
    if not isinstance(fallback_id, str) or not _RUN_ID.fullmatch(fallback_id):
        fallback_id = None

    candidates = []
    if not failure_present:
        def validate_published(path, schema):
            result = verify_publication(path, schema)
            from publication import validate_existing
            validate_existing(path)
            return result
        candidates.append(("validated-publication", 9, validate_published))
    candidates.extend((("validated-review", 7, verify_review),
                       ("validated-baseline", 4, verify_baseline)))
    errors = ([{"stage": "publication", "error": "FailureRecord"}] if failure_present else [])
    for integrity, count, validator in candidates:
        try:
            result = validator(archived, root / "snapshot.schema.json")
            if not isinstance(result.get("run_id"), str) or not _RUN_ID.fullmatch(result["run_id"]):
                continue
            source_doc = _read_json(archived / "snapshots" / FILENAMES[1])
            if not isinstance(source_doc, dict):
                continue
            state = source_doc.get("state")
            sources = state.get("sources") if isinstance(state, dict) else None
            if not isinstance(sources, list):
                continue
            policy = None
            if count >= 7:
                review_doc = _read_json(archived / "snapshots" / FILENAMES[6])
                try:
                    policy = review_doc["state"]["model"]["planning_policy"]
                    if not isinstance(policy, dict):
                        policy = None
                except (TypeError, KeyError):
                    policy = None
            return {"run_id": result["run_id"], "integrity": integrity,
                    "identity_verified": True, "sources": sources, "policy": policy,
                    "integrity_errors": errors}
        except Exception as exc:
            # Keep diagnostics bounded; validator messages can contain untrusted paths/data.
            errors.append({"stage": integrity.removeprefix("validated-"),
                           "error": type(exc).__name__})
    if not errors:
        errors.append({"stage": "verification", "error": "NoValidSnapshotBoundary"})
    return {"run_id": fallback_id, "integrity": "unverified",
            "identity_verified": False, "sources": None, "policy": None,
            "integrity_errors": errors}


def _stable_observation(observation):
    data = observation.get("data")
    if isinstance(data, dict):
        data = {k: v for k, v in data.items() if k != "_row"}
    locator = observation.get("locator")
    if isinstance(locator, dict) and locator.get("kind") == "cell-range":
        locator = None
    return observation.get("summary"), data, locator


def _source_map(sources):
    return {source["id"]: source for source in sources if isinstance(source, dict) and isinstance(source.get("id"), str)}


def describe_change(previous: dict, new_sources: list, new_policy: dict) -> dict:
    """Compare known source and planning metadata without reconstructing absent history."""
    old_sources = previous.get("sources")
    known = isinstance(old_sources, list)
    old_map, new_map = _source_map(old_sources or []), _source_map(new_sources)
    changed_sources, unchanged_sources = [], []
    changed_records, unchanged_evidence = [], []
    if known:
        for source_id in sorted(old_map.keys() | new_map.keys()):
            old, new = old_map.get(source_id), new_map.get(source_id)
            old_metadata = (old.get("version_metadata") or {}) if old is not None else {}
            new_metadata = (new.get("version_metadata") or {}) if new is not None else {}
            old_fields = None if old is None else (old.get("retrieval_status"), old.get("content_hash"),
                                                    old.get("source_role"), old_metadata.get("record_version"),
                                                    old_metadata.get("revisions"))
            new_fields = None if new is None else (new.get("retrieval_status"), new.get("content_hash"),
                                                    new.get("source_role"), new_metadata.get("record_version"),
                                                    new_metadata.get("revisions"))
            if old_fields == new_fields:
                unchanged_sources.append(source_id)
            else:
                changed_sources.append(source_id)
            old_obs = {o.get("id"): _stable_observation(o) for o in (old or {}).get("observations", []) if isinstance(o, dict)}
            new_obs = {o.get("id"): _stable_observation(o) for o in (new or {}).get("observations", []) if isinstance(o, dict)}
            changed_before = len(changed_records)
            for record_id in old_obs.keys() | new_obs.keys():
                if old_obs.get(record_id) != new_obs.get(record_id):
                    changed_records.append(record_id)
                else:
                    unchanged_evidence.append(record_id)
            if len(changed_records) > changed_before and source_id not in changed_sources:
                changed_sources.append(source_id)
                if source_id in unchanged_sources:
                    unchanged_sources.remove(source_id)

    old_policy = previous.get("policy")
    changed_decisions = []
    if isinstance(old_policy, dict):
        for key, decision_id in (("buffer_people", "decision:headcount-buffer"),
                                 ("buffer_rationale", "decision:headcount-buffer")):
            if old_policy.get(key) != new_policy.get(key) and decision_id not in changed_decisions:
                changed_decisions.append(decision_id)
        if any(k not in {"buffer_people", "buffer_rationale"} and old_policy.get(k) != new_policy.get(k)
               for k in old_policy.keys() | new_policy.keys()):
            changed_decisions.append("decision:selection")

    comparison_status = "compared" if known else "unknown-previous-inputs"
    if old_policy is None:
        comparison_status = "comparison-unverified"
    source_changed = bool(changed_sources)
    affected = sorted(set(changed_decisions + (["decision:headcount-buffer", "decision:selection"] if source_changed else [])))
    if source_changed or changed_decisions:
        reason = "source or decision change"
    elif previous.get("integrity") != "validated-publication":
        reason = "output recovery after " + str(previous.get("integrity", "unverified"))
    elif known and isinstance(old_policy, dict) and not changed_records:
        reason = "unchanged inputs refreshed and revalidated"
    else:
        reason = "comparison could not establish unchanged inputs"
    return {"supersedes_run_id": previous.get("run_id"),
            "predecessor_history": previous.get("history_path"),
            "previous_integrity": previous.get("integrity", "unverified"),
            "comparison_status": comparison_status,
            "changed_source_ids": changed_sources if known else [],
            "unchanged_source_ids": unchanged_sources if known else [],
            "changed_record_ids": sorted(set(changed_records)) if known else [],
            "unchanged_evidence_ids": sorted(set(unchanged_evidence)) if known else [],
            "changed_decision_ids": changed_decisions,
            "affected_decision_ids": affected,
            "change_reason": reason}
