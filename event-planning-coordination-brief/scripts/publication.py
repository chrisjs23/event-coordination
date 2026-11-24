"""Write and validate local planning drafts at the publication boundary."""

import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re

from icalendar import Calendar

from baseline import record
from calendar_draft import UID, supported_window
from capture import json_bytes, utcnow
from drafts import ARTIFACTS, CSV_FIELDS, comparison_rows, md, planning_facts, render_drafts
from snapshots import FILENAMES, SnapshotWriter, sha256, verify_review, verify_publication


def load_context(output, *, created_at):
    output = Path(output)
    docs = [json.loads((output / "snapshots" / name).read_text()) for name in FILENAMES[:7]]
    review = docs[6]["state"]
    model = review["model"]
    if (model["options"] != docs[4]["state"]["options"]
            or model["results"] != docs[5]["state"]["option_results"]
            or model["baseline"] != docs[3]["state"]
            or model["constraints"] != docs[2]["state"]):
        raise ValueError("Shared planning model disagrees with its prior snapshots")
    by_id = {option["id"]: option for option in model["options"]}
    selected = model.get("selected_option")
    recommendation = review["recommendation"]
    if selected != by_id.get(recommendation) or (recommendation is not None and selected is None):
        raise ValueError("Selected option disagrees with the reviewed recommendation")
    buffer_decisions = [r for r in review["learner_decisions"] if r["id"] == "decision:headcount-buffer"]
    if len(buffer_decisions) != 1 or model["headcount"] != buffer_decisions[0]:
        raise ValueError("Headcount policy disagrees with its recorded decision")
    return {"run_id": docs[0]["run_id"], "created_at": created_at,
            "scope": docs[0]["state"], "sources": docs[1]["state"]["sources"],
            "review": docs[6]["state"], "unresolved": docs[5]["state"]["unresolved_conditions"],
            "rejected_early": docs[4]["state"]["rejected_early"]}


def _csv_checks(output, context):
    with (output / "vendor-comparison.csv").open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if reader.fieldnames != list(CSV_FIELDS):
            raise ValueError("CSV columns differ from the required contract")
        rows = list(reader)
    expected = comparison_rows(context)
    if len(rows) != len(expected) or len({r["option_id"] for r in rows}) != len(rows):
        raise ValueError("CSV options are missing or duplicated")
    by_id = {row["option_id"]: row for row in rows}
    for row in expected:
        actual = by_id.get(row["option_id"])
        if actual != row:
            raise ValueError("CSV comparison disagrees with the planning model")
        if actual["cost_twd"] and not re.fullmatch(r"[0-9]+", actual["cost_twd"]):
            raise ValueError("CSV costs must be integer TWD")
        for field in ("quote_ids", "evidence_ids", "tradeoffs", "unresolved"):
            if not isinstance(json.loads(actual[field]), list):
                raise ValueError("CSV list field must be a JSON array")
        if not actual["cost_twd"] and not json.loads(actual["unresolved"]):
            raise ValueError("Unknown cost requires an unresolved reason")


def _markdown_checks(output, context, filename):
    text = (output / filename).read_text(encoding="utf-8")
    for label, value in planning_facts(context).items():
        if f"| {label} | {md(value)} |" not in text:
            raise ValueError("Draft planning facts disagree with the model")
    # This binds the whole controlled prose, including amounts outside the facts table.
    expected = render_drafts(context)[filename].decode("utf-8")
    if text != expected:
        raise ValueError("Draft content differs from its planning model")
    if filename == "draft-communications.md":
        messages = text.split("## UNSENT DRAFT — ")[1:]
        if not messages:
            raise ValueError("Communications require labelled unsent messages")
        for message in messages:
            if any(label not in message for label in
                   ("Audience — ", "Purpose — ", "Conditions — ", "Approval owner — ")):
                raise ValueError("A draft message is missing review information")


def _calendar_checks(output, context):
    raw = (output / "event-calendar.ics").read_bytes()
    if b"\n" in raw.replace(b"\r\n", b""):
        raise ValueError("Calendar requires CRLF line endings")
    if any(len(line) > 75 for line in raw.split(b"\r\n")):
        raise ValueError("Calendar content lines exceed the folding limit")
    calendar = Calendar.from_ical(raw)
    if str(calendar.get("VERSION")) != "2.0" or str(calendar.get("METHOD")) != "PUBLISH":
        raise ValueError("Calendar version or draft method is invalid")
    if any(component.errors for component in calendar.walk()):
        raise ValueError("Calendar parser reported invalid content")
    if any(component.name not in {"VCALENDAR", "VEVENT"} for component in calendar.walk()):
        raise ValueError("Calendar contains an unsupported delivery or alarm component")
    if any("ATTENDEE" in component or "ORGANIZER" in component for component in calendar.walk()):
        raise ValueError("Calendar contains recipient or organizer properties")
    events = calendar.walk("VEVENT")
    window = supported_window(context)
    if window is None:
        if events:
            raise ValueError("Deferred calendar must have no events")
        return
    if len(events) != 1:
        raise ValueError("Calendar must contain one supported main event")
    event = events[0]
    selected = context["review"]["model"]["selected_option"]
    for field, value in (("UID", UID), ("STATUS", "TENTATIVE"),
                         ("X-RUN-ID", context["run_id"]), ("X-OPTION-ID", selected["id"])):
        if str(event.get(field)) != value:
            raise ValueError("Calendar identity or draft state disagrees with the model")
    for field, expected in (("DTSTART", window["start_at"]), ("DTEND", window["end_at"]),
                             ("DTSTAMP", context["created_at"])):
        actual = event.decoded(field)
        wanted = datetime.fromisoformat(expected).astimezone(timezone.utc).replace(microsecond=0)
        if actual.utcoffset() is None or actual != wanted:
            raise ValueError("Calendar timestamps disagree with the model")
    if event.decoded("DTEND") <= event.decoded("DTSTART"):
        raise ValueError("Calendar event has a nonpositive duration")
    description = str(event.get("DESCRIPTION", ""))
    for row in context["review"]["model"]["calendar_records"]:
        if any(f"{key}={row[key]}" not in description for key in
               ("constraint_id", "owner", "constraint_type", "start_at", "end_at", "priority", "notes", "record_version")):
            raise ValueError("Calendar constraint meaning was lost")
    if f"Planning people: {selected['planning_people']}" not in description or f"Cost: {selected['cost_twd']} {selected['currency']}" not in description:
        raise ValueError("Calendar planning quantities disagree with the model")


def validate_drafts(output, context):
    """Inspect the written files; checks retain safe errors and never report guessed success."""
    output = Path(output)
    checks = []
    actions = {
        "vendor-comparison.csv": lambda: _csv_checks(output, context),
        "event-plan.md": lambda: _markdown_checks(output, context, "event-plan.md"),
        "event-calendar.ics": lambda: _calendar_checks(output, context),
        "draft-communications.md": lambda: _markdown_checks(output, context, "draft-communications.md"),
    }
    for name, action in actions.items():
        outcome, summary = "passed", "Written " + name + " agrees with the planning model and format"
        try:
            action()
        except Exception:
            outcome, summary = "failed", "Written " + name + " failed model or format validation"
        checks.append(record("validation:" + name, summary, [], outcome=outcome,
                             artifact_ids=["artifact:" + name]))
    return checks


def publication_state(context):
    model = context["review"]["model"]
    if model.get("selected_option") is None:
        return "partial" if model["options"] else "blocked"
    source_incomplete = any(s["retrieval_status"] != "retrieved" for s in context["sources"])
    unknowns = [r for r in model["constraints"].get("unknowns", []) if r["id"] != "issue:buffer-policy"]
    return "partial" if source_incomplete or unknowns or model["constraints"].get("conflicts") else "complete"


def validate_existing(output):
    output = Path(output)
    if (output / "failure.json").exists() or (output / "failure.json").is_symlink():
        raise ValueError("Current run has an unresolved failure record")
    final = json.loads((output / "snapshots" / FILENAMES[8]).read_text())
    context = load_context(output, created_at=final["state"]["rendered_at"])
    checks = validate_drafts(output, context)
    if any(check["outcome"] != "passed" for check in checks):
        raise ValueError("Publication content failed model/format verification")
    if final["status"] != publication_state(context):
        raise ValueError("Publication run state differs from the model")
    return checks


def publish_review(root, output):
    root, output = Path(root), Path(output)
    schema = root / "snapshot.schema.json"
    verified = verify_review(output, schema)
    targets = [output / name for name in ARTIFACTS] + [output / "snapshots" / name for name in FILENAMES[7:]]
    if any(path.exists() for path in targets):
        raise FileExistsError("Drafts or publication snapshots already exist; choose a fresh run")
    created_at = utcnow()
    context = load_context(output, created_at=created_at)
    try:
        payloads = render_drafts(context)
        artifacts = []
        for name in ARTIFACTS:
            path = output / name
            with path.open("xb") as stream:
                stream.write(payloads[name])
            actual = path.read_bytes()
            if actual != payloads[name]:
                raise ValueError("Draft write verification failed")
            artifacts.append({"id": "artifact:" + name, "path": name, "sha256": sha256(actual),
                              "validation_status": "valid"})
        earlier = []
        for name in FILENAMES[:7]:
            earlier.extend(json.loads((output / "snapshots" / name).read_text())["produced_record_ids"])
        writer = SnapshotWriter(output, schema, verified["run_id"])
        dependencies = [record("dependency:" + topic, "Propagated " + topic + " into the four written drafts",
                               ["source:" + source], artifact_ids=[r["id"] for r in artifacts])
                        for topic, source in (("attendance", "attendees"), ("budget", "budget"),
                                               ("quotes", "vendors"), ("timing", "calendar"),
                                               ("accessibility", "floorplan"))]
        unresolved = context["unresolved"]
        state8 = {"artifact_drafts": artifacts, "affected_dependencies": dependencies,
                  "unresolved_items": unresolved,
                  "validation_scope": "Draft byte-write checks passed; semantic publication checks follow"}
        produced8 = [r["id"] for r in artifacts + dependencies]
        writer.write(8, state8, earlier, produced8, unresolved, status="partial")
        checks = validate_drafts(output, context)
        passed = all(check["outcome"] == "passed" for check in checks)
        finals = [dict(r, validation_status="valid" if checks[index]["outcome"] == "passed" else "invalid")
                  for index, r in enumerate(artifacts)]
        state9 = {"artifacts": finals, "validation_checks": checks,
                  "publication_status": "validated" if passed else "failed", "rendered_at": created_at}
        writer.write(9, state9, earlier + produced8, [r["id"] for r in checks], unresolved,
                     status=publication_state(context) if passed else "failed")
        if not passed:
            raise ValueError("Written drafts failed publication checks")
        result = verify_publication(output, schema)
        validate_existing(output)
        result.update(completed_through="publication-validation", pipeline_available=True,
                      output_dir=str(output.resolve()), artifacts=list(ARTIFACTS))
        return result
    except Exception as exc:
        failure = {"run_id": verified["run_id"], "observed_at": utcnow(),
                   "error": str(exc) if isinstance(exc, (ValueError, OSError)) else type(exc).__name__,
                   "affected_stage": "draft-propagation-or-publication-validation",
                   "available_evidence": [s["local_reference"] for s in context["sources"] if s["local_reference"]],
                   "affected_artifacts": [str(path.relative_to(output)) for path in targets if path.is_file()],
                   "next_owner": "Operations",
                   "recovery_action": "Inspect retained draft attempts and validation results before recovery"}
        (output / "failure.json").write_bytes(json_bytes(failure))
        raise ValueError("publication failed; inspect " + str(output / "failure.json")) from exc
