# Event planning handoff

All seven implementation stages are complete and manually verified. The user approved the final handoff, Stage 7 commit and push to origin. No new runtime code or tests were needed for this stage; the retained regression suite and standalone verifier cover the final execution.

## Setup and one end-to-end command

From the repository root, use Python 3.10+ on Linux/WSL and a local POSIX filesystem:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r event-planning-coordination-brief/requirements.txt
.venv/bin/python -B event-planning-coordination-brief/scripts/run.py --through publication-validation --output-dir deliverables
```

Dependencies are pinned in the skill's `requirements.txt`: jsonschema 4.26.0, rfc3339-validator 0.1.4 and icalendar 7.3.0. The command reads disclosed Notion, Google Sheets and TICC sources over HTTPS. It requires no credentials for the inspected public sources. Use the [recovery guide](event-planning-coordination-brief/references/recovery.md) to repeat execution on a temporary copy or repair a draft. Retain the whole output directory, including history, when copying a run.

## Reviewed result and decisions

The live run `run-00f5d021edca4438a6f42aa7a74dcdbd` completed on 2026-11-24 with nine linked snapshots, seven retained evidence files and all four validated drafts. Actual retrieval times are in Stage 02; the exercise business clock remains 2026-08-26 12:00 Asia/Taipei.

- Headcount: 180 registered + 30 required staff/speakers + 35 forecast walk-ins = 245; a proposed 15-person buffer gives 260. The check-in target is at least 144 registered people. Operations must review the buffer; it has no statistical guarantee.
- Comparison: ten bundles, two feasible. City Pantry with SoundArc totals TWD 512,000, leaving TWD 8,000 under the TWD 520,000 ceiling. It provides catering capacity 300, or 40 spare places. Green Table totals TWD 494,000 with capacity 260 and no spare catering capacity. The documented planner preference spends TWD 18,000 for additional coverage; owner approval remains pending.
- Programme: twelve ten-minute demos and twelve separate three-minute changeovers, the 10:00–11:00 keynote, lunch and breaks fit the 09:30–17:00 preferred event window. Setup begins at 07:30; teardown ends by 18:30. All eight source calendar records retain their qualifiers.
- Access: the retained official PDF supports page/region spatial observations. The fictional exercise coordination records supply operational readiness and allocation. Current route clearance, elevator operation, acoustic performance and seating setup still require confirmation in a real event.
- Review: seven category requests precede Operations' overall approval. Programme owns programme changes; Learner Experience coordinates access needs; Operations holds individual contacts and handles supplier/dietary follow-up. The venue-confirmation prerequisite for the walkthrough remains explicit. Every approval is pending, all fifteen messages are unsent drafts and the calendar event is tentative.

The full rebuild uses a shared planning model for all drafts, plus schema, evidence, hash and semantic validation. Fresh reruns favor straightforward recomputation over a cache. Unknown or changed source meanings stop dependent interpretation; they do not inherit convenient earlier facts. See [policy choices](event-planning-coordination-brief/references/planning-policy.json), [source meanings](event-planning-coordination-brief/references/source-map.md) and [publication limits](event-planning-coordination-brief/references/publication.md).

## Independent verification

With setup complete, from the repository root:

```sh
.venv/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
.venv/bin/python -B event-planning-coordination-brief/scripts/snapshots.py deliverables --through publication-validation
```

Observed and expected for the retained case: 115 tests pass; verification exits 0 and reports `status: complete`, `snapshots: 9`, `evidence_files: 7`. These commands are offline. A fresh live execution may legitimately produce another state after remote changes or access failures.

| Retained tests | What they establish |
| --- | --- |
| `tests/test_capture.py`, `tests/test_records.py`, `tests/test_source_csv.py`, `tests/test_source_inventory.py` | Disclosed sources, privacy-filtered capture, field identities/meanings, reordering and invalid/unavailable input handling. |
| `tests/test_schedule.py`, `tests/test_options.py`, `tests/test_review_pipeline.py` | Programme intervals/dependencies, arithmetic, rejected alternatives and pending review gates. |
| `tests/test_calendar_draft.py`, `tests/test_drafts.py`, `tests/test_publication.py`, `tests/test_snapshots.py` | Calendar parsing, consistent four-file rendering, nine-stage chain/evidence/artifact integrity and corruption rejection. |
| `tests/test_history.py`, `tests/test_changes.py`, `tests/test_refresh.py`, `tests/test_command.py` | Archival, changed-input comparison, output repair, interrupted-run recovery and CLI behavior. |

Manual review complements those tests:

1. Open `deliverables/event-plan.md` and `vendor-comparison.csv`. Add category totals (60,000 + 126,000 + 25,000 + 40,000 + 78,000 + 28,000 + 155,000 = 512,000). Compare the lower-cost alternative and rejected reasons with the captured quote register. Treat the buffer and selection preference as proposals.
2. Follow selected quote evidence IDs from the CSV into Stage 02 and its captured vendor rows. Trace attendance through `obs:attendees:SIG-001`–`SIG-005`, the deadline through `obs:calendar:CAL-005`, and spatial claims through `obs:floorplan:*` to the retained PDF and named page regions. The verifier checks IDs/hashes; a person must assess source interpretation.
3. Read the run-of-show table in order: twelve demo/changeover pairs must not overlap; the keynote stays 10:00–11:00 and all event activities stay within the supported window. Check the eight calendar records, particularly the fallback keynote conflict and walkthrough dependency.
4. Inspect `event-calendar.ics` as text or in an isolated local preview. Expect VERSION 2.0, METHOD PUBLISH, one tentative event, explicit UTC dates corresponding to 09:30–17:00 Asia/Taipei, and no attendees. Inspect all fifteen `UNSENT DRAFT` messages for audience, conditions and approval owner.
5. Inspect Stage 01's recovery lineage and Stage 02's actual timestamps. The first Stage 7 source attempt was denied by the network sandbox and preserved as failed run `run-74ecce1c2b1a42a1b4f53f77a66ccd52`. The approved HTTPS rerun archived it and succeeded. Stage 01 correctly marks that immediate predecessor unverified; it does not infer unchanged historical evidence from that failed attempt. The earlier verified Stage 6 run is also retained under `history/run-6caf453ae6ab4299bbde8f18764ac26d/`.

No tests were added or modified in Stage 7. A separate final audit confirmed ten options, the two feasible amounts, category sum, twelve non-overlapping demo/changeover pairs, tentative calendar, fifteen unsent drafts and seven successfully retrieved sources.

## Session capture and submission boundary

Stage 6 commit `3cf9802` has local Entire checkpoint `01M873HHVKR3E4XV2PW2BM9E8S`. Host-level `entire status --detailed` confirmed an active session and checkpoint destination `origin`; `entire doctor` confirmed installed/approved Git and Codex hooks with no stuck sessions. A sandbox PID namespace can misleadingly report the host session as exited. Run these read-only checks in a normal host terminal:

```sh
entire status --detailed
entire doctor
entire checkpoint list --no-pager
```

The updated original interview export is `interviews/project-c-event-coordination-interview2.md`; use it as the final complete export for this session. The earlier export remains preserved unchanged as superseded material. The supplied schema, requirements and interview contents were not modified. The user manually verified the Stage 7 tests and reviewed this handoff and PLAN.md, then authorized commit and push to origin. The commit/push outcome and Entire synchronization can be checked with `git log -1`, `git ls-remote origin refs/heads/main` and `entire checkpoint list --outgoing`. Facilitator account access requires separate confirmation.

## Remaining limits

Public sources can change or fail. The Notion route depends on its current site structure. Changed floor-plan bytes require renewed visual review. Native Windows, network filesystems and physical power-loss recovery are untested. Directory replacement can briefly make the current path unavailable to unlocked readers. Human approval, actual access checks and external delivery remain outstanding owner actions. The recovery and publication guides document incomplete/failure states and retained evidence.
