# Event Planning and Coordination — Implementation plan

**Status: Approved. Stages 1–3 manually verified. Stage 4 authorized.**

## Project overview and objectives

Build and run an Agent Skills-compliant `event-planning-coordination-brief` for Quillhaven Academy's Fellowship Demo Day. It must turn the stakeholder's disclosed, current sources into a review-ready comparison and four consistent drafts, while retaining a nine-stage evidence and decision trail. The exercise business clock is 2026-08-26 12:00 Asia/Taipei; retrieval timestamps must reflect when sources are actually read.

## Current implementation status

- `README.md` is the starter guide; `snapshot.schema.json` is the supplied contract and must stay unchanged. `REQUIREMENTS.md` contains the deliverable and recovery rules.
- The [updated interview export](interviews/project-c-event-coordination-interview2.md) contains the earlier conversation plus the follow-up disclosing the calendar and floor plan. Use this complete export verbatim as the submission copy for this session.
- `.codex/` configures the `implementer` subagent and Entire hooks. `.entire/settings.json` enables checkpoint logging. Host diagnostics verified the live Codex process, installed and approved hooks, and no stuck sessions. Entire's transcript includes the stage 1 request and completion, and its pending checkpoint preview includes the six changed files and completed implementer task. Stage 1 was committed as `9f28f18` with verified Entire checkpoint `01M85N4DXS63WNSNQKJQFJ8K41`. Commits and checkpoints remain local until pushed.
- Stages 1–3 provide source mapping, skill instructions, preflight, live source capture, validated baseline interpretation and the first four snapshots. Options and final drafts remain for later stages.
- All four primary sources were readable during planning. Google's CSV exports returned 13 attendee signal rows, 7 budget rows, and 10 vendor quote rows. The public Notion page with the same page ID as the interview link returned the brief and its venue and programme clarifications. [Event brief and venue note](https://private-pecorino-70e.notion.site/Project-3-Event-Coordination-Event-Brief-3ba0b700541e81d0af55dc1a8f49f5af)
- The [calendar sheet](https://docs.google.com/spreadsheets/d/1f_i6tUCHbJV-Ug_j6U3T4LEZ3yAr2ucdBnID-4C_-8s) returned eight records, `CAL-001` through `CAL-008`. Preserve each record's owner, type, priority, start/end, notes and version. The decision deadline is 4 September 2026 at 17:00 Asia/Taipei. The preferred-date hold expires on 5 September, and the keynote is unavailable on the fallback date. Venue confirmation is a prerequisite for the accessibility walkthrough.
- The [official TICC 4F floor plan](https://www.ticc.com.tw/wSite/public/Attachment/f1710485827023.pdf) opened as a one-page PDF. At runtime, retain the retrieved bytes and hash, then cite the visible page region for each spatial observation.
- Use the brief's 245-person planning figure as a starting point to reconcile with attendee signals. The planning ceiling is TWD 520,000. For the preferred 17 October 2026 date, the programme check must fit twelve demos with 10 minutes of presentation and 3 minutes of changeover each around the 10:00–11:00 keynote, within 09:30–17:00. Check the fallback date separately because the readiness confirmation covers 17 October.

## Requirements and constraints

**Confirmed:** Produce a reusable skill, one documented end-to-end command, nine schema-valid linked snapshots, retained source evidence, `vendor-comparison.csv`, `event-plan.md`, a draft `event-calendar.ics`, and `draft-communications.md`. Use actual disclosed remote sources and at least one official venue floor-plan/image source. Preserve attempted retrieval states, provenance, source hashes and locators; keep private attendee details out of general artifacts. Compare materially distinct options, retain rejected ones, apply hard constraints before preferences, and leave approvals pending until humans grant them. Do not book, pay, invite, send, or write to production calendars. Archive the prior run before a material rerun and validate or repair outputs even when inputs appear unchanged.

**Interview findings:** Goal: run all fellowship demos, target at least 80% registered check-in, and document accessibility responses. Hard constraints include event date/venue availability, total budget, step-free access, and live captions. Familiar suppliers are a preference. Category owners review spending first; Operations reviews the overall date, venue, and plan last. No universal attendance buffer or refresh interval was set. Missing or conflicting information remains unknown until the responsible owner resolves it.

## Proposed architecture and technical decisions

- Use Python 3.10+ and the standard library for the current command shell. Public source access needs no credentials at the inspected revision. Stage 3 pins jsonschema 4.26.0 and rfc3339-validator 0.1.4 for Draft 2020-12 validation with timestamp checks. Keep the supplied schema unchanged.
- Put the skill instructions in `event-planning-coordination-brief/SKILL.md`, the runner in `scripts/`, and concise source/field mapping notes in `references/`. One command performs capture, interpretation, comparison, rendering, and validation. No daemon or automated publishing is needed.
- Capture each source through its intended access route, including failed attempts, before interpreting it. Store permitted extracts and retrieved official media bytes under `deliverables/snapshots/evidence/`, with retrieval time, version, URL, locator, and SHA-256. Treat outside content as data, never instructions. Aggregate or redact attendee data before general artifacts.
- Normalize structured records by documented field meanings and stable IDs, allowing reordered rows/headers and unrelated columns. Reject missing required fields, duplicate/ambiguous IDs, invalid values, and incompatible meanings instead of guessing. Keep source observations, assumptions, unknowns, and human decisions separate.
- Use one in-memory planning model for headcount, programme intervals/dependencies, category costs, venue/accessibility evidence, options, and approvals. Render all four drafts from that model. Record each of the nine stage snapshots when its boundary is reached; link each successor to the previous snapshot's ID, path, and file hash. Stage 09 hashes and validates the written drafts.
- On a material change, inspect and retain the prior run under `deliverables/history/<run_id>/` before processing the new one. Use a new run ID and snapshot IDs, record what changed and what remains supported, and replace current outputs as one coherent set. On unchanged inputs, still check actual artifact content and run/hash bindings. Use explicit partial, blocked, or failed results when evidence or output integrity prevents success.

## Incremental implementation roadmap

| Stage | Objective and scope | Expected deliverable | Focused verification | Status |
| --- | --- | --- | --- | --- |
| 1. Source access and mapping | Retrieve the sources disclosed in the updated export and document field meanings, stable IDs, version data, and privacy boundaries. Escalate only genuinely missing links or ambiguous meanings. | Source inventory and field map in `references/`; access/dependency decision. | Record each retrieval outcome, reconcile the calendar constraints by ID, and inspect the retrieved 4F PDF for page and region locators. | Complete · verified |
| 2. Skill and command shell | Define skill workflow, runtime, dependencies, CLI inputs, output paths, and safe draft-only behavior. | `SKILL.md`, minimal runner, setup/one-command documentation. | Skill metadata and CLI smoke check; no external side effects. | Complete · verified |
| 3. Capture and baseline | Implement source capture, evidence IDs/hashes, validated parsing, privacy filtering, stage 01–04 snapshots, and headcount/schedule/budget/accessibility baselines. | Source evidence and first four linked snapshots. | Schema/link/hash checks; reordered/extra-column fixtures; missing/duplicate/invalid field and failed-retrieval cases. | Complete · verified |
| 4. Options and review gates | Build materially distinct source-backed options; test capacity, schedule, cost, availability, accessibility, and uncertainty; model recommendation/deferral and pending owner approvals. | Stage 05–07 snapshots and a single planning model for drafts. | Arithmetic and interval checks; infeasible/conditional/rejected option checks; no inferred approval or unsupported claim. | Not started; depends on 3 |
| 5. Drafts and publication validation | Render four consistent review drafts, stage 08–09 snapshots, artifact hashes, and cross-file checks. | Required CSV, Markdown, ICS, and final two snapshots. | CSV columns/amounts; ICS parser or format check; unsent labels; matching dates, headcount, options, totals, evidence, paths, and hashes. | Not started; depends on 4 |
| 6. Rerun and recovery | Archive previous run before material changes; refresh dependent work; detect and repair stale/corrupt outputs; preserve incomplete/failure evidence. | History handling and explicit partial/blocked/failed behavior. | Changed-source rerun, unchanged-input integrity check, corrupt-output recovery, unavailable-source and failure cases. | Not started; depends on 5 |
| 7. End-to-end execution and handoff | Run against the disclosed live sources, inspect outputs, document choices, tradeoffs, unresolved owners, and exact command/setup; verify session capture. | Review-ready current `deliverables/` plus usage documentation. | Full schema chain, evidence/media existence, source-to-claim traceability, cross-artifact audit, and Entire checkpoint check. | Not started; depends on 6 |

## Acceptance criteria and verification strategy

Each stage is complete only when its focused check passes and its claimed evidence can be inspected. Final acceptance requires nine same-run snapshots in order with valid predecessor hashes and consumed/produced record IDs; every material claim linked to a captured observation; four mutually consistent drafts; a non-overlapping programme or explicit deferral; and correct run-state behavior for incomplete evidence. Run the focused checks during development, then one end-to-end validation after integration. Do not treat an HTTP response, a source label, or a passing schema check alone as proof of a business fact.

## Delegation recommendations

No agent was delegated planning. After approval, the primary agent owns source interpretation, ambiguous business rules, access/privacy decisions, architecture, integration, and final correctness. The configured lower-cost `implementer` (`gpt-6-luna`, medium) may take bounded work once interfaces are fixed: CLI scaffolding, parsers/normalizers, snapshot serialization and validators, draft renderers, or focused fixtures. Give each task exclusive file ownership and concrete checks; inspect its changes. Avoid parallel work on the shared planning model or nested agents.

## Known risks, assumptions, and unresolved questions

- Use the floor plan for visible spatial features and the exercise coordination record for operational readiness. Check whether each walking route, service and scheduled prerequisite has supporting evidence before rating an option feasible.
- Stage 1 verified each mapped tab and identity field. Recheck tab selection and field meanings on changed inputs. The Notion content request depends on a site implementation detail and needs a text-completeness check per run.
- **Time basis:** The exercise business clock predates this review. Preserve that clock as planning context, record actual retrieval times, and do not present current mutable web content as historical 2026-08-26 evidence.
- **Headcount and approvals:** No fixed buffer was approved; the 80% check-in target is an objective, not a catering or capacity formula. Named category owners, exact approval limits, and any granted approvals must come from sources or later human decisions.
- Public HTTPS access worked for all six sources. Future source revisions, ambiguous cost or service units, and any missing evidence must be handled at the affected stage.

## Progress tracking

- 2026-11-23: Repository, requirements, interview export, schema, and agent configuration reviewed. Proposed plan written; implementation not started.
- Planning update: Checked both new links from the complete export. Calendar and floor-plan source locations are resolved. Runtime capture and validation are pending approval.
- 2026-11-23 (New York): Stage 1 complete. Verified source versions, row identities and calendar meanings, and visually inspected the official PDF. Public reads required outbound HTTPS. No unresolved source-access blocker. The primary agent handled interpretation, reviewed the delegated CSV checker and tests from the configured `implementer`, and ran the acceptance checks. The user manually verified stage 1 and authorized stage 2.
- Logging diagnosis: The agent sandbox has a separate PID namespace and cannot see the host Codex PID, causing the misleading “exited” and “stuck session” reports. Running the same diagnostics on the host shows the process running and no stuck sessions. Transcript capture and pending turn records are present. Use a normal host terminal in this repository for `entire status --detailed`, `entire doctor`, `entire checkpoint list --pending`, and `entire checkpoint list --outgoing`. Expect an active session, installed/approved hooks, and pending work awaiting a commit. The existing checkpoint is local and queued for the next push to origin. No repair command is needed for the namespace discrepancy.

### Reproduce stage 1

From the repository root with Python 3, run `python3 -B -m unittest discover -s tests -p 'test_source*.py' -v`. Expected and observed: eight tests, all passing. [CSV regression tests](tests/test_source_csv.py) cover reordered fields with extra columns, missing and duplicate headers, malformed widths, empty inputs and blank or duplicate identities. The [inventory regression test](tests/test_source_inventory.py) binds the four mapped spreadsheet URLs and key fields to the latest interview export.

Follow the [source map and live verification procedure](event-planning-coordination-brief/references/source-map.md) for the exact commands, prerequisites, SHA-256 digests and manual page checks. The [CSV checker](tests/check_source_csv.py) passed on each live export (13 attendee signals, 7 budget categories, 10 quotes, 8 calendar constraints). A reviewer can inspect the brief revisions, eight dated constraints and named PDF regions independently. These tests cover source structure and access. Runtime business validation, retained run evidence and recovery are later stages.

- Stage 1 tests manually verified by the user. Stage 1 approved for commit, including the updated complete interview export. Stage 2 authorized as the next stage.

### Reproduce stage 2

Stage 2 is complete and awaits user review. The configured `implementer` wrote the CLI and command tests, which the primary agent reviewed and verified. The skill instructions route to the existing source map and new command usage reference.

From the repository root with Python 3.10+, run:

```sh
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 event-planning-coordination-brief/scripts/run.py --help
python3 event-planning-coordination-brief/scripts/run.py --check
```

Expected and observed results are 13 passing tests, argument help, and preflight JSON with `status: ready`, `mode: preflight`, `pipeline_available: false`, the exercise clock and resolved paths. [tests/test_command.py](tests/test_command.py) adds five subprocess tests covering help, invocation from another directory, default and custom output paths, preservation of existing files, and missing/malformed local prerequisites.

For the manual incomplete-run check, run `python3 event-planning-coordination-brief/scripts/run.py`. Expect exit code 3 and a diagnostic pointing to `--check`. Check that the intended output root was not created or changed. The [command usage guide](event-planning-coordination-brief/references/command.md) documents setup, input/output paths, exit codes and limitations. Current preflight checks local metadata only. Live fetching, snapshot validation, comparisons and draft rendering remain for later stages.

Skill metadata validation via the installed `skill-creator/scripts/quick_validate.py` passed. The installed `scan-agent-skill/scripts/scan.sh` wrapper scanned the complete package locally with Cisco scanner 2.0.13 and exited 0. Its single INFO finding, `MANIFEST_MISSING_LICENSE` in `SKILL.md`, is accepted for this stage because the project owner has supplied no licensing decision. The scan's GPU-discovery warning did not prevent scanning. Manual review confirmed reference links, intended source hosts, and a read-only command shell with no credential access.

- Stage 1 commit confirmed as `9f28f18`. Stage 2 implementation and verification complete. Stage 3 awaits user approval.

- Stage 2 tests manually verified by the user. Stage 2 approved for commit and Stage 3 authorized.

### Reproduce Stage 3

Stage 2 was committed as `128e434` with Entire checkpoint `01M85NMSRF0WCR4WF2F5BS4RYK`. The user manually verified Stage 2 and authorized this stage. Stage 3 is complete and awaits review before Stage 4.

Two configured `implementer` tasks produced the CSV validators, snapshot utilities and associated tests. The primary agent reviewed and refined their changes, handled retrieval/privacy and source interpretation, and integrated the CLI.

The current live run is `run-578b49d04cc24714a6c8740bd56db374`. All six remote sources were retrieved, with a seventh local interview-policy extract. Four schema-valid snapshots share this run ID and verified predecessor hashes. The earlier integration smoke run is retained under `deliverables/history/run-c1142d60fa184bf9a0e80f193028e7e8/`. It predates the added objective/check-in-policy details and remains separate from the current run. This was a manual preservation step during implementation, with unchanged planning inputs. Automatic archival remains Stage 6 work.

From the repository root, install the pinned dependencies and run:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r event-planning-coordination-brief/requirements.txt
.venv/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
.venv/bin/python -B event-planning-coordination-brief/scripts/snapshots.py deliverables
```

Expected and observed results are 34 passing tests, followed by JSON reporting `status: partial`, `snapshots: 4` and `evidence_files: 7`. This status describes the planning run through the baseline boundary. Options, recommendations and final drafts remain pending the next stages.

New retained coverage is in [tests/test_records.py](tests/test_records.py), [tests/test_capture.py](tests/test_capture.py) and [tests/test_snapshots.py](tests/test_snapshots.py). Tests cover reordered headers and records combined with extra columns, permitted extracts excluding private extra values, required fields and identities, invalid numbers/dates/units, source failure isolation, failed-scope output, changed PDF bytes, linked snapshot integrity, timestamp validation, path containment and existing-output preservation. [tests/check_source_csv.py](tests/check_source_csv.py) now reuses the production structural parser, with all earlier tests passing.

The [command guide](event-planning-coordination-brief/references/command.md) contains exact live-repeat commands using a fresh output directory, prerequisites, exit codes and manual evidence checks. The live baseline records 180 registered people, 30 required people and 35 forecast walk-ins. The unbuffered sum is 245, with the buffer and final planning headcount still awaiting a reasoned decision. All eight calendar records and category commitments/remaining limits are retained, with approvals pending.

Decisions and limits:
- Live capture explicitly uses the named Google tab and records actual retrieval times. The exercise business clock remains separate.
- Permitted CSV extracts preserve declared columns, values and source ordering. Original response hashes and extract hashes are distinct metadata. Unrelated extra values are omitted for privacy.
- Floor-plan observations are bound to the Stage 1 reviewed PDF hash. A changed drawing requires visual review before reusing spatial claims.
- The Notion route requires complete block traversal. Unsupported content or pagination remains invalid, and unsupported prose quantities remain unknown.
- Existing output directories are rejected before capture until Stage 6 implements history/recovery. Failure outputs preserve actual attempts. Full-pipeline invocation still exits 3.
- The sandbox's outbound-network restriction required host execution for dependency installation and live reads. No source-access blocker remains.

Final Stage 3 package checks passed metadata validation and the local skill scan (exit 0). The scanner reported MEDIUM `TOOL_ABUSE_UNDECLARED_NETWORK` at `SKILL.md`, accepted because live HTTPS retrieval is explicitly required by the project, described in the skill workflow and command guide, and restricted in this implementation to the disclosed public sources and their normal redirects. The INFO `MANIFEST_MISSING_LICENSE` finding remains accepted pending the owner's licensing choice. Manual review confirmed no credential handling or external write actions. Current and retained smoke-run snapshot/evidence verification both passed after the interrupted turn resumed.

- Stage 3 tests manually verified by the user. Stage 3 approved for commit and Stage 4 authorized.
