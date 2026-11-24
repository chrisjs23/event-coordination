"""Immutable archival helpers for prior event-planning runs."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import re
import shutil
import tempfile
import uuid


_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\Z")
_MANIFEST = "archive-manifest.json"


def _check_root(path: Path) -> Path:
    path = Path(path)
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ValueError(f"archive root is unavailable: {path}") from exc
    import stat
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise ValueError(f"archive root must be a real directory: {path}")
    return path


def _inventory(path: Path, *, archived=False) -> dict:
    root = _check_root(path)
    result = {}

    def visit(directory: Path, relative: Path):
        for entry in os.scandir(directory):
            rel = relative / entry.name
            if not relative.parts and entry.name == "history":
                continue
            if archived and not relative.parts and entry.name == "attempts":
                continue
            if archived and not relative.parts and entry.name == _MANIFEST:
                continue
            name = rel.as_posix()
            if entry.is_symlink():
                result[name] = {"symlink": os.readlink(entry.path)}
            elif entry.is_dir(follow_symlinks=False):
                visit(Path(entry.path), rel)
            elif entry.is_file(follow_symlinks=False):
                data = Path(entry.path).read_bytes()
                result[name] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            else:
                raise ValueError(f"unsupported filesystem entry: {name}")

    visit(root, Path())
    return result


def inventory(path: Path) -> dict:
    """Inventory files and links without following any symbolic link."""
    return _inventory(Path(path))


def _copy_tree(source: Path, target: Path):
    target.mkdir()
    for entry in os.scandir(source):
        src, dst = Path(entry.path), target / entry.name
        if entry.is_symlink():
            os.symlink(os.readlink(src), dst)
        elif entry.is_dir(follow_symlinks=False):
            _copy_tree(src, dst)
        elif entry.is_file(follow_symlinks=False):
            shutil.copy2(src, dst, follow_symlinks=False)
        else:
            raise ValueError(f"unsupported filesystem entry: {entry.name}")


def _write_manifest(path: Path, files: dict):
    document = {"files": files, "recorded_at": datetime.now(timezone.utc).isoformat()}
    (path / _MANIFEST).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def verify_archive(path: Path) -> dict:
    """Validate archive manifest against exact archived files and links."""
    path = _check_root(Path(path))
    manifest_path = path / _MANIFEST
    if manifest_path.is_symlink():
        raise ValueError("archive manifest must not be a symbolic link")
    try:
        if not manifest_path.is_file():
            raise ValueError("archive manifest is missing or not a regular file")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"archive manifest is missing or invalid: {manifest_path}") from exc
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, dict):
        raise ValueError("archive manifest has no valid files inventory")
    actual = _inventory(path, archived=True)
    if actual != files:
        raise ValueError("archive contents do not match archive manifest")
    return files


def verify_history_link(output: Path) -> None:
    """Verify a current stage-01 reference to an immutable historical archive."""
    output = _check_root(Path(output))
    snapshots = output / "snapshots"
    stage_one = snapshots / "01-scope-and-approval-gates.json"

    def failure_only():
        try:
            return stat.S_ISREG((output / "failure.json").lstat().st_mode)
        except OSError:
            return False

    try:
        snapshots_mode = snapshots.lstat().st_mode
    except FileNotFoundError:
        snapshots_mode = None
    if snapshots_mode is None:
        if failure_only():
            return
        raise ValueError("current stage-01 snapshot is missing")
    if stat.S_ISLNK(snapshots_mode) or not stat.S_ISDIR(snapshots_mode):
        raise ValueError("snapshots path must be a real directory")
    try:
        stage_mode = stage_one.lstat().st_mode
    except FileNotFoundError as exc:
        if failure_only():
            return
        raise ValueError("current stage-01 snapshot is missing") from exc
    if stat.S_ISLNK(stage_mode) or not stat.S_ISREG(stage_mode):
        raise ValueError("current stage-01 snapshot must be a regular file")
    try:
        document = json.loads(stage_one.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("current stage-01 snapshot is invalid") from exc
    state = document.get("state") if isinstance(document, dict) else None
    if not isinstance(state, dict) or "predecessor_history" not in state:
        return
    reference = state.get("predecessor_history")
    digest = state.get("predecessor_archive_sha256")
    if not isinstance(reference, str) or not reference.startswith("history/"):
        raise ValueError("predecessor history path must be relative under history/")
    parts = reference.split("/")
    valid_run = len(parts) in {2, 4} and parts[0] == "history" and _RUN_ID.fullmatch(parts[1])
    valid_attempt = (len(parts) == 2 or
                     (len(parts) == 4 and parts[2] == "attempts"
                      and re.fullmatch(r"attempt-[0-9a-f]{32}", parts[3])))
    if (not valid_run or not valid_attempt or "\\" in reference
            or reference != "/".join(parts)):
        raise ValueError("predecessor history path is invalid")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise ValueError("predecessor archive hash is required")
    marker = output / _MANIFEST
    archived_output = marker.exists() or marker.is_symlink()
    if archived_output:
        if marker.is_symlink():
            raise ValueError("archive manifest must not be a symbolic link")
        history_root = next((parent for parent in output.parents if parent.name == "history"), None)
        if history_root is None:
            raise ValueError("predecessor history namespace is unavailable for archived output")
        namespace = history_root
        target = namespace.parent.joinpath(*parts)
    else:
        namespace = output / "history"
        target = output.joinpath(*parts)
    if namespace.is_symlink():
        raise ValueError("history path must not be a symbolic link")
    if not namespace.is_dir():
        raise ValueError("predecessor history directory is missing")
    try:
        real_history = namespace.resolve(strict=True)
        # Check every component without following links, including attempt paths.
        relative_target = target.relative_to(namespace)
        cursor = namespace
        for index, component in enumerate(relative_target.parts):
            cursor = cursor / component
            mode = cursor.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ValueError("predecessor archive path contains a symbolic link")
            if index < len(relative_target.parts) - 1 and not stat.S_ISDIR(mode):
                raise ValueError("predecessor archive path has a non-directory component")
        real_target = target.resolve(strict=True)
        if not real_target.is_relative_to(real_history):
            raise ValueError("predecessor archive escapes history directory")
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError("predecessor archive path is unavailable") from exc
    verify_archive(target)
    manifest_bytes = (target / _MANIFEST).read_bytes()
    actual_hash = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
    if actual_hash != digest:
        raise ValueError("predecessor archive hash does not match manifest")


def archive_current(output: Path, run_id: str | None) -> Path | None:
    """Copy current output into immutable history, retaining collisions as attempts."""
    output = _check_root(Path(output))
    if (output / _MANIFEST).exists() or (output / _MANIFEST).is_symlink():
        raise ValueError(f"reserved archive manifest exists in source root: {_MANIFEST}")
    current = inventory(output)
    if not current:
        return None
    safe_id = run_id if isinstance(run_id, str) and _RUN_ID.fullmatch(run_id) and run_id not in {".", ".."} else "unidentified-" + uuid.uuid4().hex
    history = output / "history"
    if history.is_symlink():
        raise ValueError("history destination must not be a symbolic link")
    if history.exists() and not history.is_dir():
        raise ValueError("history destination must be a directory")
    history.mkdir(exist_ok=True)
    dest = history / safe_id
    if dest.exists() or dest.is_symlink():
        _check_root(dest)
        try:
            existing = verify_archive(dest)
        except (ValueError, OSError):
            # Preserve an unverifiable archive and create a distinct current observation.
            existing = None
        if existing == current:
            return dest
        attempts = dest / "attempts"
        if attempts.is_symlink():
            raise ValueError("archive attempts destination must not be a symbolic link")
        if attempts.exists() and not attempts.is_dir():
            raise ValueError("archive attempts destination must be a directory")
        dest = attempts / ("attempt-" + uuid.uuid4().hex)
    parent = dest.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".archive-", dir=parent))
    # mkdtemp creates the destination root; copy children into it.
    try:
        for entry in os.scandir(output):
            if entry.name == "history":
                continue
            src, dst = Path(entry.path), temp / entry.name
            if entry.name == _MANIFEST:
                raise ValueError(f"reserved archive manifest exists in source root: {_MANIFEST}")
            if entry.is_symlink():
                os.symlink(os.readlink(src), dst)
            elif entry.is_dir(follow_symlinks=False):
                _copy_tree(src, dst)
            elif entry.is_file(follow_symlinks=False):
                shutil.copy2(src, dst, follow_symlinks=False)
            else:
                raise ValueError(f"unsupported filesystem entry: {entry.name}")
        if _inventory(temp, archived=True) != current:
            raise ValueError("source changed while creating archive")
        _write_manifest(temp, current)
        if dest.exists():
            raise FileExistsError(f"archive destination already exists: {dest}")
        temp.rename(dest)
        return dest
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
