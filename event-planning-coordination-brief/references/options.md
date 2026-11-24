# Option comparison and review decisions

Stage 4 appends snapshots 05–07 to a verified captured run, or captures a new run through the same boundary. It produces the shared model that the draft renderers will consume in Stage 5.

## Planning choices

The proposed buffer is 15 people above the captured attendance basis, giving 260 for the inspected case. This is a plan-specific learner decision. It allows for some error in the medium-confidence walk-in forecast while preserving two comparable catering alternatives. It supplies no probability guarantee. Reconsider it after material attendance or service changes.

The selection rule prefers greater catering coverage among feasible options, then lower total cost. The captured case yields:

| Catering with supported base services | Full planning cost | Capacity above 260 | Remaining overall ceiling |
| --- | --- | --- | --- |
| Green Table | TWD 494,000 | 0 | TWD 26,000 |
| City Pantry | TWD 512,000 | 40 | TWD 8,000 |

City Pantry is the proposed recommendation. Its additional TWD 18,000 buys greater catering coverage while leaving less room for changes. Both totals include the venue, captions, hearing-loop AV, quiet-room staffing, security, TWD 25,000 communications and TWD 40,000 contingency. Package amounts are used as quoted. Existing commitments are added to proposed spending when checking remaining category and total room. Owners must reconcile any overlapping commitments before authorizing new spending.

The 24 October alternatives fail keynote availability and service-date checks. Basic AV lacks hearing-loop support. Livestream alternatives retain the network-confirmation dependency and exceed both the production and total limits. The model keeps all ten generated alternatives with their checks.

The proposed programme includes twelve 10-minute presentations, each followed by a separate 3-minute changeover. It retains the 10:00–11:00 keynote, two breaks and lunch. Planner-selected opening, overview, partner discussions and closing fill the event window. Setup and readiness checks occupy the supplied pre-opening access window, with clearance by 18:30. These intervals are proposed coordination choices, supported by the exercise readiness record.

## Interpretation and evidence

[planning-policy.json](planning-policy.json) records the buffer, selection rule and quote-role mappings. Its hashes bind reviewed scope/condition text and brief passages to their actual captured observations. Numeric costs, capacities, dates, demand and budget limits remain inputs to the checks. Changed scope prose, calendar qualifiers, dietary demand or a drawing requiring review remain unresolved until their meanings have been inspected. Update a review binding only after inspecting the actual changed source.

This distinguishes case evidence from planning decisions. Category spending and Operations approval remain pending. The Operations request identifies category-review prerequisites. A feasible planning option does not grant authority to book, pay or send messages.

## Independent verification

Use Python 3.10+ and the pinned virtual environment described in [command setup](command.md). From the repository root:

```sh
.venv/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
.venv/bin/python -B event-planning-coordination-brief/scripts/snapshots.py deliverables --through decision-and-approval
```

Expect 55 tests to pass and verification JSON showing seven snapshots, seven evidence files and partial planning status. Partial reflects the remaining draft/publication stages.

To independently repeat the review without refreshing sources, copy the captured baseline to a temporary output root and append the review there:

```sh
stage4_review_parent=$(mktemp -d)
mkdir -p "$stage4_review_parent/run/snapshots"
cp deliverables/snapshots/0[1-4]-*.json "$stage4_review_parent/run/snapshots/"
cp -R deliverables/snapshots/evidence "$stage4_review_parent/run/snapshots/"
if [ -d deliverables/history ]; then cp -R deliverables/history "$stage4_review_parent/run/"; fi
.venv/bin/python -B event-planning-coordination-brief/scripts/run.py --through decision-and-approval --resume-baseline --output-dir "$stage4_review_parent/run"
.venv/bin/python -B event-planning-coordination-brief/scripts/snapshots.py "$stage4_review_parent/run" --through decision-and-approval
```

Expect ten options, two feasible options, and recommendation `option:Q-001-Q-004-Q-005-Q-006-Q-009-Q-010`. This mode reviews the recorded observations and preserves their timestamps. To refresh sources, omit `--resume-baseline` and select a new, absent output directory. Later source changes can legitimately alter these case results.

| Test file | Retained coverage |
| --- | --- |
| `tests/test_options.py` | Frozen case arithmetic, selection, rejected alternatives, capacities, expiry, changed conditions, budgets, missing inputs and pending approvals. |
| `tests/test_schedule.py` | Individual demos/changeovers, ordering, valid setup/programme/teardown bounds and overfull or invalid schedules. |
| `tests/test_review_pipeline.py` | Fresh seven-stage capture, CLI resume preserving baseline bytes, invalid arguments and overwrite protection. |
| `tests/test_snapshots.py` | Four- and seven-stage integrity, option/result coverage, recommendation references and rejection of non-feasible recommendations. |

The frozen case in `tests/fixtures/review-case.json` derives from the manually verified Stage 3 evidence. It is test input. Live capture continues to use the disclosed remote sources.

For manual review, open snapshots 05–07. Independently total each category and the two allowances, compare category/overall limits, and inspect each failed or unverified check. Read the per-demo timestamps and confirm the keynote, breaks, lunch, setup and teardown fit. Check the source IDs against Stage 02 observations and retained evidence. Confirm that the recommendation's category approvals and Operations approval remain pending.

## Limits

Full-run archival and recovery are implemented. See [recovery](recovery.md) for independent checks. Captured review extensions preserve already-written review snapshots. Resume rejects already-existing review snapshots. Current output status stays partial until Stage 5 supplies the drafts and final publication checks. This is an exercise planning recommendation supported by the retained case records.
