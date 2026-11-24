# Command setup and verification

The command supports local preflight and source capture through the planning baseline. Stage 3 writes the first four snapshots. Stage 4 adds options, feasibility and review requests through snapshot 07. Stage 5 adds all four drafts and publication checks through snapshot 09. Stage 6 adds verified archival, transactional full reruns and recovery.

## Setup

Use Python 3.10 or later from the repository root. Install the pinned validator and date-time checker in a local virtual environment.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r event-planning-coordination-brief/requirements.txt
```

The installed dependencies are jsonschema 4.26.0, rfc3339-validator 0.1.4 and icalendar 7.3.0. Snapshot checks use Draft 2020-12 with date-time format checking enabled. The library's validation interface is documented by its maintainers. [jsonschema validation documentation](https://python-jsonschema.readthedocs.io/en/stable/validate/)

Local review of an existing capture uses `--through decision-and-approval --resume-baseline`. This preserves the captured run and its retrieval timestamps.

Live capture requires outbound HTTPS to the disclosed Notion, Google Sheets and TICC hosts and their normal redirects. The inspected sources need no credentials. Offline tests use synthetic responses injected into the capture function.

## Commands

Inspect help or run the local metadata preflight.

```sh
.venv/bin/python event-planning-coordination-brief/scripts/run.py --help
.venv/bin/python event-planning-coordination-brief/scripts/run.py --check
```

Expect exit code 0 and preflight JSON with `status: ready`, `mode: preflight`, `pipeline_available: true`, the exercise business clock, and resolved paths. This checks local schema identity and the sheet map. It creates no files and does not test source access.

To independently repeat Stage 3, choose a fresh output path. The checked-in `deliverables/` already contains a live baseline run.

```sh
stage3_review_parent=$(mktemp -d)
.venv/bin/python -B event-planning-coordination-brief/scripts/run.py --through planning-baseline --output-dir "$stage3_review_parent/run"
.venv/bin/python -B event-planning-coordination-brief/scripts/snapshots.py "$stage3_review_parent/run"
```

Both commands should exit 0 and report `status: partial`, four snapshots, and seven evidence files when all sources remain available. Seven includes the local interview-policy extract alongside the six remote sources. The execution report also gives the new run ID and output path. Successful scoped execution reports a partial planning run because the remaining five snapshots and drafts are future stages.

The default output root is this repository's `deliverables/`. An explicit relative `--output-dir` is resolved from the caller's working directory. The planning-baseline endpoint requires a fresh directory. Full publication runs archive and replace an existing recognized planning run, with fresh source capture and validation. See [recovery](recovery.md).

To verify the retained current run without network access, use:

```sh
.venv/bin/python -B event-planning-coordination-brief/scripts/snapshots.py deliverables
```

The verifier checks schema and timestamp formats, run/record identities, predecessor bytes and paths, evidence hashes and path containment, and evidence references. A successful integrity check can also report partial status for unresolved source or planning conditions.

The entry point without `--check` or `--through` remains reserved for the full pipeline and exits 3. CLI/preflight/capture failures exit 1, and argument errors exit 2. A failed execution in a new output directory preserves actual evidence and writes `failure.json`. If the brief or calendar deadline is unavailable, it withholds scope snapshots instead of supplying an unsupported deadline.

## Independent tests and manual checks

From the repository root after setup, run:

```sh
.venv/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
```

Expect 115 passing tests. For the Stage 4 endpoint and its independent repeat procedure, read [option comparison and review](options.md).

| Test file | What it verifies |
| --- | --- |
| `tests/test_command.py` | Existing preflight/help, output paths, invocation from another directory and setup failures. |
| `tests/test_records.py` | Header/row permutations with extras, permitted-column extracts, duplicate identities, numeric/date/unit meanings and calendar intervals. |
| `tests/test_capture.py` | Four-stage offline integration, headcount arithmetic, calendar preservation, pending budgets, privacy filtering, source failure isolation, invalid inputs, changed PDF handling and existing-output protection. |
| `tests/test_snapshots.py` | Schema/hash-linked serialization, record/evidence references, timestamps, path containment, corruption detection and overwrite protection. |
| `tests/test_source_csv.py`, `tests/test_source_inventory.py` | Stage 1 regression checks using the shared structural parser and disclosed source links. |

For manual review, inspect the retained evidence under `deliverables/snapshots/evidence/`. Compare the CSV records and brief blocks with their Stage 02 observations. Inspect the official PDF's legend and the regions cited in `venue-evidence.json`. Spatial observations are reused only when the newly retrieved PDF has the reviewed hash. Changed PDF bytes are retained as unverified, and spatial observations are withheld pending a new visual review.

In Stage 04, confirm 180 registered people, 30 required staff/speakers and 35 forecast walk-ins, yielding 245 before a buffer decision. Support requests remain separate demand measures. Confirm all eight calendar records, category limits and commitments, and pending approval statuses.

## Limitations

The Notion content route is a site implementation detail. Pagination, missing linked blocks or unsupported block types produce an invalid source outcome. Changed or ambiguous prose quantities remain unresolved rather than inheriting earlier values.

CSV evidence retains declared aggregate columns in source order, preserving cell values and row order. Unrelated column values are omitted for privacy. Metadata records the original response hash, retained extract hash and ignored-column count. Review changes to declared free-text fields for privacy before sharing artifacts.

The exercise clock governs dated planning inputs. Actual capture timestamps describe the live reads. Venue coordination statements remain fictional exercise evidence, and the drawing supplies spatial observations with separate operational limits. Full artifact validation and transactional reruns are implemented. See the recovery guide for interruption and filesystem limits.

For the full nine-stage endpoint, independent publication repeat commands, manual checks and remaining limits, read [draft publication](publication.md). Calendar serialization uses the maintained [icalendar library](https://icalendar.readthedocs.io/en/stable/how-to/usage.html).
