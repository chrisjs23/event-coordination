# Refresh, archival and recovery

A full run fetches the disclosed sources again and regenerates the complete planning output. The same command handles a new directory, a prior successful run, a partial result, or damaged current artifacts.

## Prerequisites and commands

Use Python 3.10+ on a local POSIX filesystem, including Linux/WSL, with the dependencies installed as described in [publication setup](publication.md). Writer locking uses the standard-library fcntl module. Native Windows and network filesystem behavior have not been tested.

From the repository root:

```sh
.venv/bin/python -m pip install -r event-planning-coordination-brief/requirements.txt
.venv/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
.venv/bin/python -B event-planning-coordination-brief/scripts/snapshots.py deliverables --through publication-validation
```

Expect 115 passing tests and a complete nine-snapshot result for the retained case. The standalone verifier also checks the predecessor archive manifest and its exact file hashes.

To independently repeat a live refresh using a copy:

```sh
stage6_review_parent=$(mktemp -d)
cp -R deliverables "$stage6_review_parent/run"
.venv/bin/python -B event-planning-coordination-brief/scripts/run.py --through publication-validation --output-dir "$stage6_review_parent/run"
.venv/bin/python -B event-planning-coordination-brief/scripts/snapshots.py "$stage6_review_parent/run" --through publication-validation
```

Expect a new run ID, a predecessor archive under `history/<prior_run_id>/`, new actual retrieval times and nine consistent snapshots. If the remote inputs remain unchanged, Stage 1 records empty changed-source/decision lists and identifies the unchanged observations. A source failure or material update can legitimately produce partial, blocked or failed output.

The same full-run command can operate directly on the repository's current `deliverables/` after review. The narrower `--resume-baseline` and `--resume-review` modes remain one-time extensions of retained captured inputs.

## Transaction behavior

1. A nonblocking writer lock prevents overlapping writes to the selected output root.
2. The current files are copied into history before source processing starts. The archive manifest records exact file hashes and link targets. Existing histories are preserved.
3. The preceding run is inspected at the strongest valid snapshot boundary. Unverified observations are excluded from comparison. Only actual retained identities and hashes are used.
4. Fresh source capture and all nine stages run in a sibling candidate directory. Stage 1 records supersession, archive identity, source/record/decision changes, unchanged evidence and the reason.
5. The candidate is validated before the root switch. Current files are checked against the archive before replacement. The whole output directory is switched, preserving the history namespace.
6. Installed files are verified again. Old transaction backups are removed only after matching their verified archives.

Each refresh gets a new run and new snapshot IDs, even when inputs are unchanged. This keeps source attempts and validation explicit. All dependent planning and review requests are recalculated. Media bytes are retained with each run.

A failed fresh source attempt becomes an explicit current failure or incomplete result, with actual evidence preserved. Earlier successful drafts remain in history. Recovery establishes no completed venue test, owner approval or sent communication.

## Reproduce output repair

Use the temporary copy above, then delete one copied draft and repeat the full command:

```sh
.venv/bin/python - "$stage6_review_parent/run/event-plan.md" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).unlink()
PY
.venv/bin/python -B event-planning-coordination-brief/scripts/run.py --through publication-validation --output-dir "$stage6_review_parent/run"
.venv/bin/python -B event-planning-coordination-brief/scripts/snapshots.py "$stage6_review_parent/run" --through publication-validation
```

Expect a regenerated plan and new run ID. The archived damaged predecessor preserves the actual missing-file state. Stage 1 reports that its input review was verified while publication required recovery. Other corruption is preserved as actual bytes rather than reconstructed as a historical successful artifact.

## Interrupted transactions

A journal and candidate/backup directories live beside the output root with names beginning `.event-coordination-`. They are excluded from Git. Rerunning the same full command reconciles the interrupted transaction and then performs a fresh attempt. An incomplete interrupted candidate receives a failure record that lists only files actually present.

Tests inject interruption after partial capture, after moving history and after renaming the old root. Directory replacement can briefly make the current path unavailable to an unlocked reader. Readers should use the verifier and retry if a writer is switching roots. Concurrent manual edits or mismatched transaction files cause an explicit refusal with the retained files available for inspection.

## Retained tests and manual checks

| File | Verification |
| --- | --- |
| `tests/test_history.py` | Exact archival, manifest hashes, collision attempts, predecessor links, path containment and symlink boundaries. |
| `tests/test_changes.py` | Verified-boundary inspection, source and record differences, reordered representations, policy changes and unavailable historical data. |
| `tests/test_refresh.py` | Fresh and unchanged runs, price/policy changes, each damaged draft, failed sources, subsequent recovery, locks and interrupted directory switches. |
| `tests/test_publication.py` | An unresolved failure record prevents a stale success report. Publication fixtures are independent of mutable current deliverables. |

Manually compare the archived manifest with the prior bytes, inspect Stage 1 change lists and Stage 2 retrieval times, and confirm all nine current snapshots share the new run ID and form one hash-linked chain. Review the change section in the plan, current totals and programme, and pending approval requests across all drafts.

Pre-existing legacy histories are retained. An unverifiable existing archive is preserved without reuse. A distinct current copy receives its own manifest under an attempts subdirectory. The implementation tests process interruption and ordinary local I/O failure paths. Physical power loss and arbitrary external changes to private transaction directories have not been tested. Automatic reuse of old business observations is deliberately excluded from refresh.
