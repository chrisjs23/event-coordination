# Draft publication and verification

Stage 5 renders the four required drafts from the verified Stage 7 shared model, writes the propagation manifest at Stage 8, and records actual file hashes and validation results at Stage 9. Publication here means local review artifacts.

## Setup and retained checks

From the repository root with Python 3.10 or later:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r event-planning-coordination-brief/requirements.txt
.venv/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
.venv/bin/python -B event-planning-coordination-brief/scripts/snapshots.py deliverables --through publication-validation
```

Expect 71 passing tests, followed by verification JSON with nine snapshots, seven evidence files and complete planning status for the inspected case. Owner approvals remain pending. Complete describes the validated planning drafts.

## Repeat from captured evidence

To reproduce publication locally, copy the verified seven-snapshot run and evidence into a temporary directory:

```sh
stage5_review_parent=$(mktemp -d)
mkdir -p "$stage5_review_parent/run/snapshots"
cp deliverables/snapshots/0[1-7]-*.json "$stage5_review_parent/run/snapshots/"
cp -R deliverables/snapshots/evidence "$stage5_review_parent/run/snapshots/"
.venv/bin/python -B event-planning-coordination-brief/scripts/run.py --through publication-validation --resume-review --output-dir "$stage5_review_parent/run"
.venv/bin/python -B event-planning-coordination-brief/scripts/snapshots.py "$stage5_review_parent/run" --through publication-validation
```

The output root receives `vendor-comparison.csv`, `event-plan.md`, `event-calendar.ics` and `draft-communications.md`, plus snapshots 08 and 09. Prior snapshots and source retrieval timestamps are preserved. The new draft timestamp is recorded in Stage 09 and in the calendar DTSTAMP.

To execute one fresh end-to-end run against the disclosed live sources, choose a new output path and omit the resume flag:

```sh
stage5_live_parent=$(mktemp -d)
.venv/bin/python -B event-planning-coordination-brief/scripts/run.py --through publication-validation --output-dir "$stage5_live_parent/run"
```

This requires outbound HTTPS. A later source revision or failed source can legitimately produce a partial/blocked result. Existing directories or completed publication files are rejected until Stage 6 implements replacement and recovery.

## Observable case results

The CSV has the required eleven columns and ten options. List-valued cells use JSON arrays. Costs are integer TWD, with unknown amounts left blank and explained. Tradeoff cells preserve quote identity, package amount, category, capacity, event date, validity and conditions.

The recommended City Pantry package is TWD 512,000 for 260 planning people. The Green Table alternative is TWD 494,000. Their remaining overall budget is TWD 8,000 and TWD 26,000 respectively. The plan includes all twelve demos and separate changeovers, all eight calendar constraints, category costs/limits, source retrieval states, floor-plan page/region locators, uncertainty, risks and owner review requests.

The calendar uses VERSION 2.0, METHOD PUBLISH, one tentative main event and a stable UID. Its UTC timestamps correspond to 17 October 2026 at 09:30–17:00 Asia/Taipei. Its description preserves all eight source constraints and qualifiers. Source constraints remain descriptive records within that draft event. They are also listed separately in the event plan. A deferred selection produces an empty valid calendar and an explanation in the plan.

Each communication has an UNSENT DRAFT heading, intended audience, purpose, conditions and approval owner. The messages include Operations, category owners, attendees and selected vendors through Operations.

## Tests and manual verification

| File | Coverage |
| --- | --- |
| `tests/test_calendar_draft.py` | Parsed UTC dates, tentative state, stable UID, source qualifiers, line folding, Unicode, injection escaping and empty-calendar behavior. |
| `tests/test_drafts.py` | Deterministic four-file rendering, amounts/headcounts, unknown-cost reasons, deferral, and individual CSV/Markdown/calendar/message corruption checks. |
| `tests/test_publication.py` | CLI publication and verification, preserved earlier snapshots, repeated-write rejection, invalid draft failure evidence, model mismatch rejection and blocked nine-stage output. |
| `tests/test_snapshots.py` | Extended nine-stage schema/link validation and artifact hash/identity checks across stages 08–09. |
| `tests/test_command.py` | Preflight now reports that the publication pipeline is available. |

Manually inspect the four artifacts. Independently add the seven category totals, compare selected and rejected alternatives, and check the twelve demo/changeover intervals against the keynote and venue hours. Compare page-region claims with the retained PDF. Read source failure conditions and confirm pending approvals and unsent labels. Inspect the calendar in a text viewer or an isolated local calendar preview without importing it into a production calendar.

The standalone verifier checks chain integrity and actual file hashes, then parses CSV and iCalendar content and checks complete controlled Markdown against the shared model. It rejects incorrect costs, dates, model/run bindings, recipients and delivery methods. The renderer and verifier share formatting helpers, while tests independently assert case amounts, dates, counts and rejected corruptions. Human review remains necessary for the interpretation of the source evidence and proposed tradeoffs.

## Limits and failure behavior

Automatic replacement, archival and recovery remain Stage 6 work. Current resume modes extend a verified run once. Publication stops before overwriting an existing draft or snapshot. If rendering or semantic validation fails after writing begins, the actual attempts remain and `failure.json` identifies the publication boundary. A failed Stage 09 never becomes a successful publication report.

The exercise business clock, live retrieval dates and actual draft timestamp remain distinct. Resuming a captured review preserves the captured basis. Changes to external sources require a fresh run and subsequent review.
