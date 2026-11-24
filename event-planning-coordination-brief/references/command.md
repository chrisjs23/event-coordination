# Command setup and verification

Stage 2 provides the command interface and a local preflight. The planning pipeline is scheduled for stages 3–6. Its availability is exposed in the preflight JSON so callers can distinguish setup readiness from a completed event plan.

## Prerequisites and usage

Use Python 3.10 or later. This stage uses the Python standard library and requires no package installation, credentials or network connection. Keep the skill in this repository with `snapshot.schema.json` in the root. Snapshot validation dependencies will be selected when that implementation is added.

From the repository root, run the local setup check.

```sh
python3 event-planning-coordination-brief/scripts/run.py --check
```

Expect exit code 0 and JSON containing `mode` equal to `preflight`, `status` equal to `ready`, `pipeline_available` equal to false, the exercise business clock, and resolved paths for the schema, source map and proposed output directory. The check reads local metadata and validates the known schema identity and sheet map structure. It creates no output files. A preflight error exits 1. Argument errors exit 2.

Use `--help` to inspect available arguments. `--output-dir PATH` selects the eventual output root. The default is this repository's `deliverables/`, regardless of the current directory. Relative supplied paths are resolved from the caller's current directory.

```sh
python3 event-planning-coordination-brief/scripts/run.py --check --output-dir /tmp/demo-day-review
```

The reserved end-to-end entry point is the same script without `--check`.

```sh
python3 event-planning-coordination-brief/scripts/run.py
```

At stage 2, expect exit code 3 and a diagnostic that the pipeline is incomplete. Output generation will be wired into this entry point in subsequent approved stages. Until then, each invocation preserves existing outputs. The eventual pipeline writes local drafts, evidence and linked snapshots under the selected output directory, with prior runs retained under `history/`.

## Independent verification

From the repository root with Python 3.10 or later, run the retained regression suite.

```sh
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
```

`tests/test_command.py` exercises the command through subprocesses, including help, preflight from another directory, output path resolution, missing or malformed prerequisites, and preservation of existing files. `tests/test_source_csv.py` and `tests/test_source_inventory.py` retain the stage 1 source checks. All tests must pass without network access.

For manual verification, run `--help` and both preflight examples above. Confirm their exit codes and paths, and verify that the proposed output directories were not created. Run the reserved entry point and confirm its exit code 3. These checks establish the command contract. Live retrieval, business rules, artifact rendering and recovery will receive their own tests in later stages.
