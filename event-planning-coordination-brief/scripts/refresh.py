"""Archive, rebuild and install one coherent current planning run."""

import json
import os
from pathlib import Path
import re
import shutil
import uuid

from capture import fetch_public, json_bytes, utcnow
from changes import inspect_previous
from history import archive_current, inventory, verify_archive, verify_history_link
from locking import output_lock
from pipeline import run_baseline
from publication import validate_existing
from drafts import ARTIFACTS
from snapshots import FILENAMES, sha256, verify_publication


def _identity(output):
    for path in (output / "snapshots" / FILENAMES[0], output / "failure.json"):
        if path.is_symlink() or path.parent.is_symlink():
            continue
        try:
            value = json.loads(path.read_text()).get("run_id")
            if isinstance(value, str) and re.fullmatch(r"run-[a-f0-9]{32}", value):
                return value
        except (OSError, UnicodeError, ValueError, AttributeError):
            pass
    return None


def _journal_path(output):
    return output.parent / (".event-coordination-" + output.name + ".json")


def _paths(output, token):
    if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{32}", token):
        raise ValueError("Invalid refresh transaction identity")
    return (output.parent / (".event-coordination-" + token + ".new"),
            output.parent / (".event-coordination-" + token + ".old"))


def _save_journal(output, journal):
    target = _journal_path(output)
    temporary = target.with_suffix(".tmp")
    if target.is_symlink() or temporary.is_symlink():
        raise ValueError("Refresh journal must be a regular local file")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(json_bytes(journal).decode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)


def _check_output(output):
    if output.is_symlink():
        raise ValueError("Output root must be a real directory")
    if not output.exists():
        return
    if not output.is_dir() or (output / ".git").exists():
        raise ValueError("Output is not a planning run directory")
    entries = [p for p in output.iterdir() if p.name != "history"]
    recognized = ((output / "failure.json").is_file()
                  or any((output / name).is_file() for name in ARTIFACTS)
                  or any((output / "snapshots" / name).is_file() for name in FILENAMES)
                  or (output / "snapshots/evidence/capture-attempts.json").is_file())
    if entries and not recognized:
        raise ValueError("Existing output lacks a recognized planning run")
    if (output / "history").is_symlink():
        raise ValueError("History must be a real directory")


def _failed_candidate(stage, previous):
    """Retain only actual files from an interrupted attempt."""
    stage.mkdir(exist_ok=True)
    if (stage / "failure.json").is_file():
        return
    failure = {
        "run_id": _identity(stage) or "interrupted-" + uuid.uuid4().hex,
        "observed_at": utcnow(), "error": "Interrupted refresh did not produce a verified publication",
        "affected_stage": "refresh", "available_evidence": [
            p.relative_to(stage).as_posix() for p in sorted(stage.glob("snapshots/evidence/*"))
            if p.is_file() and not p.is_symlink()],
        "affected_artifacts": [p.relative_to(stage).as_posix() for p in sorted(stage.glob("*"))
                               if p.is_file() and not p.is_symlink()],
        "next_owner": "Operations",
        "recovery_action": "Retry fresh sources; retained partial files do not establish completed prerequisites",
        "supersedes_run_id": previous.get("run_id") if previous else None,
        "predecessor_history": previous.get("history_path") if previous else None,
    }
    (stage / "failure.json").write_bytes(json_bytes(failure))


def _validate_candidate(root, stage):
    if (stage / "failure.json").exists():
        return False
    try:
        verify_publication(stage, root / "snapshot.schema.json")
        validate_existing(stage)
        return True
    except Exception:
        return False


def _archive_path(output, journal):
    relative = journal.get("archive_path")
    if relative is None:
        return None
    if not isinstance(relative, str):
        raise ValueError("Invalid refresh archive reference")
    path = output / relative
    history = output / "history"
    if history.is_symlink() or not path.resolve().is_relative_to(history.resolve()):
        raise ValueError("Refresh archive reference escapes history")
    return path


def _install(root, output, journal):
    stage, backup = _paths(output, journal["token"])
    if stage.is_symlink() or backup.is_symlink():
        raise ValueError("Refresh transaction directories must be real")
    if stage.exists():
        if (stage / "history").is_symlink():
            raise ValueError("Candidate history must be a real directory")
        if journal.get("candidate_inventory") != inventory(stage):
            raise ValueError("Candidate changed after verification; transaction retained")
        if not _validate_candidate(root, stage):
            _failed_candidate(stage, journal.get("previous"))
            journal["candidate_inventory"] = inventory(stage)
            _save_journal(output, journal)
        if output.exists() and backup.exists():
            raise ValueError("Both prior and replacement roots exist; preserve the transaction for inspection")
        if output.exists():
            archive_root = stage if (stage / "history").exists() and not (output / "history").exists() else output
            archive = _archive_path(archive_root, journal)
            if archive is not None and inventory(output) != verify_archive(archive):
                raise ValueError("Current files changed during refresh; new attempt remains staged")
            old_history, new_history = output / "history", stage / "history"
            if old_history.exists() and new_history.exists():
                raise ValueError("History exists in both roots; preserve transaction for inspection")
            if old_history.exists():
                os.replace(old_history, new_history)
            # A crash here is recoverable from the journal and the actual directory locations.
            os.replace(output, backup)
        if not output.exists():
            os.replace(stage, output)
    if not output.exists():
        raise ValueError("Refresh replacement is missing; transaction retained")
    if inventory(output) != journal.get("candidate_inventory"):
        raise ValueError("Installed candidate differs from its verified transaction")
    if backup.exists():
        archive = _archive_path(output, journal)
        backup_files = inventory(backup)
        if backup_files and (archive is None or backup_files != verify_archive(archive)):
            raise ValueError("Prior backup differs from its archive; backup retained")
        shutil.rmtree(backup)
    _journal_path(output).unlink(missing_ok=True)


def _recover(root, output):
    path = _journal_path(output)
    if not path.exists():
        return None
    if path.is_symlink():
        raise ValueError("Refresh journal must be a regular file")
    journal = json.loads(path.read_text())
    stage, backup = _paths(output, journal.get("token"))
    if journal.get("output") != str(output):
        raise ValueError("Refresh journal belongs to another output directory")
    if not stage.exists() and not backup.exists() and journal.get("phase") == "building":
        # The interrupted request created no candidate files.
        path.unlink()
        return "Interrupted transaction had no candidate files"
    if journal.get("phase") == "building":
        if stage.exists() and not _validate_candidate(root, stage):
            _failed_candidate(stage, journal.get("previous"))
        if stage.exists():
            journal["candidate_inventory"] = inventory(stage)
            journal["candidate_run_id"] = _identity(stage)
            journal["phase"] = "ready"
            _save_journal(output, journal)
    _install(root, output, journal)
    return "Completed the retained interrupted transaction before this fresh attempt"


def refresh_run(root, output, fetch=fetch_public):
    root, output = Path(root).resolve(), Path(output).absolute()
    with output_lock(output):
        _check_output(output)
        recovered = _recover(root, output)
        _check_output(output)
        previous = None
        archive = None
        if output.exists():
            archive = archive_current(output, _identity(output))
            if archive is not None:
                previous = inspect_previous(root, archive)
                previous["history_path"] = archive.relative_to(output).as_posix()
                previous["archive_manifest_sha256"] = sha256((archive / "archive-manifest.json").read_bytes())
        token = uuid.uuid4().hex
        stage, backup = _paths(output, token)
        journal = {"token": token, "output": str(output), "phase": "building",
                   "archive_path": archive.relative_to(output).as_posix() if archive else None,
                   "previous": {key: previous.get(key) for key in
                                ("run_id", "history_path", "integrity")} if previous else None}
        _save_journal(output, journal)
        success = False
        result = None
        try:
            result = run_baseline(root, stage, fetch=fetch, through="publication-validation", previous=previous)
            success = _validate_candidate(root, stage)
        except Exception:
            _failed_candidate(stage, previous)
        if not success:
            _failed_candidate(stage, previous)
        journal["phase"] = "ready"
        journal["candidate_run_id"] = _identity(stage)
        journal["candidate_inventory"] = inventory(stage)
        _save_journal(output, journal)
        _install(root, output, journal)
        if not success:
            raise ValueError("Fresh planning attempt failed; inspect " + str(output / "failure.json"))
        # Check the installed paths too, after the root switch.
        verify_publication(output, root / "snapshot.schema.json")
        validate_existing(output)
        verify_history_link(output)
        if previous:
            verify_archive(output / previous["history_path"])
        result["output_dir"] = str(output)
        result["basis"] = "fresh-source-refresh"
        result["supersedes_run_id"] = previous.get("run_id") if previous else None
        result["history_path"] = previous.get("history_path") if previous else None
        if recovered:
            result["recovery"] = recovered
        return result
