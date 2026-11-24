"""Interpret captured records through the planning-baseline boundary."""

import re
from datetime import date

BUSINESS_CLOCK = "2026-08-26T12:00:00+08:00"


def record(identity, summary, evidence, **fields):
    return {"id": identity, "summary": summary, "evidence_ids": evidence, **fields}


def observation(name, identity):
    return f"obs:{name}:{identity}"


def build_baseline(sources, rows, blocks):
    """Keep unsupported facts unresolved; return states for snapshots 01, 03 and 04."""
    unresolved = []
    for source in sources:
        if source["retrieval_status"] != "retrieved":
            unresolved.append(record(
                "issue:" + source["id"], source["retrieval_status"] + ": " +
                source["version_metadata"].get("error", "source needs verification"),
                [source["id"]], owner="Operations"))

    facts = {}

    def fact(name, pattern, convert=int):
        matches = [(b, m) for b in blocks for m in re.finditer(pattern, b["text"])]
        if len(matches) == 1:
            block, match = matches[0]
            facts[name] = {"value": convert(match.group(1)),
                           "evidence_ids": [observation("brief", block["id"])]}
        else:
            unresolved.append(record("issue:" + name,
                                     name + " needs an unambiguous source observation",
                                     ["source:brief"], owner="Operations"))

    fact("checkin_target_percent", r"at least (\d+) percent of registered attendees check in")
    fact("brief_people", r"Plan for (\d+) people")
    fact("budget_ceiling_twd", r"planning ceiling is TWD ([\d,]+)", lambda s: int(s.replace(",", "")))
    fact("audience_places", r"allocates (\d+) usable audience places")
    numbers = {"six": 6}
    fact("wheelchair_spaces", r"including (six|\d+) wheelchair spaces",
         lambda s: numbers[s] if s in numbers else int(s))
    fact("quiet_room_places", r"occupancy up to (\d+) people")
    fact("demo_minutes", r"Each demonstration needs (\d+) minutes of presentation")
    fact("changeover_minutes", r"a separate (\d+)-minute changeover allowance")
    roster_blocks = [b for b in blocks if "Programme has scheduled" in b["text"]]
    if len(roster_blocks) == 1:
        ids = re.findall(r"DEMO-\d+", roster_blocks[0]["text"])
        if ids and len(set(ids)) == len(ids):
            facts["demo_ids"] = {"value": ids,
                                 "evidence_ids": [observation("brief", roster_blocks[0]["id"])]}
    if "demo_ids" not in facts:
        unresolved.append(record("issue:demo-roster", "Programme roster needs clarification",
                                 ["source:brief"], owner="Programme"))

    calendar = rows.get("calendar", [])
    deadlines = [r for r in calendar if r["constraint_type"] == "decision_deadline"]
    if not blocks or len(deadlines) != 1:
        raise ValueError("Scope needs a readable brief and one valid calendar decision deadline")
    introductions = [b for b in blocks if b["text"].startswith(("Plan the ", "Plan for "))]
    if len(introductions) != 1:
        raise ValueError("Scope needs one unambiguous brief objective")
    introduction = introductions[0]
    deadline = deadlines[0]
    owners = sorted({"Operations", "Programme", "Learner Experience"} |
                    {r["owner"] for r in rows.get("budget", [])})
    scope_records = [
        record("scope:objective", introduction["text"],
               [observation("brief", introduction["id"])], owner="Operations"),
        record("scope:deadline", "Plan and budget decision deadline",
               [observation("calendar", deadline["constraint_id"])],
               value=deadline["start_at"].isoformat(), owner=deadline["owner"]),
    ]
    approvals = [
        record("scope:category-approval", "Category owners review spending before Operations review",
               ["source:brief", "source:interview"], status="pending", owner="Category budget owners"),
        record("scope:operations-approval", "Operations reviews the overall plan",
               ["source:brief"], status="pending", owner="Operations"),
    ]
    scope = {"objective": introduction["text"],
             "decision_deadline": deadline["start_at"].isoformat(), "owners": owners,
             "approval_gates": [r["summary"] for r in approvals],
             "scope_records": scope_records, "approval_requirements": approvals,
             "business_clock": BUSINESS_CLOCK}

    hard, preferences, conflicts = [], [], []
    for block in blocks:
        if block["text"].startswith("Hard requirements are"):
            hard.append(record("constraint:brief-hard", block["text"],
                               [observation("brief", block["id"])], owner="Operations"))
    if not hard:
        unresolved.append(record("issue:hard-constraints", "Brief hard requirements need review",
                                 ["source:brief"], owner="Operations"))
    for block in blocks:
        if block["text"].startswith("Success means"):
            hard.append(record("constraint:success", block["text"],
                               [observation("brief", block["id"])], owner="Operations"))
    for row in calendar:
        item = record("constraint:calendar:" + row["constraint_id"],
                      row["constraint_type"] + ": " + row["notes"],
                      [observation("calendar", row["constraint_id"])],
                      owner=row["owner"], start_at=row["start_at"].isoformat(),
                      end_at=row["end_at"].isoformat(), priority=row["priority"])
        (hard if row["priority"] == "hard" else preferences).append(item)
    interview = next(s for s in sources if s["id"] == "source:interview")
    if interview["retrieval_status"] == "retrieved":
        preferences.append(record("preference:familiar-suppliers",
                                  "Prefer familiar suppliers when constraints permit",
                                  ["obs:interview:supplier-preference"], owner="Operations"))
    unresolved.append(record("issue:buffer-policy",
                             "A headcount buffer has yet to be chosen with cost/shortage reasoning",
                             ["source:interview"], owner="Planner"))

    headcount = []
    signals = rows.get("attendees", [])
    measures = {}
    for row in signals:
        key = (row["signal"], row["segment"])
        if key in measures:
            conflicts.append(record("conflict:signal:" + row["signal"] + ":" + row["segment"],
                                    "Multiple observations have the same measure and segment",
                                    [observation("attendees", measures[key]["signal_id"]),
                                     observation("attendees", row["signal_id"])], owner="Learner Experience"))
        measures[key] = row
    if any(r["observed_at"] > date.fromisoformat(BUSINESS_CLOCK[:10]) for r in signals):
        conflicts.append(record("conflict:future-signal",
                                "Attendee observation postdates the exercise business clock",
                                ["source:attendees"], owner="Learner Experience"))
    expected_measures = {("registered_attendees", "fellows"), ("registered_attendees", "partners"),
                         ("required_on_site", "staff"), ("required_on_site", "speakers"),
                         ("expected_attendees", "walk_ins")}
    complete_signals = expected_measures.issubset(measures) and not conflicts
    if complete_signals:
        planning_rows = [measures[key] for key in sorted(expected_measures)]
        registered = sum(r["value"] for r in planning_rows if r["signal"] == "registered_attendees")
        required = sum(r["value"] for r in planning_rows if r["signal"] == "required_on_site")
        forecast = sum(r["value"] for r in planning_rows if r["signal"] == "expected_attendees")
        total = registered + required + forecast
        headcount.append(record("baseline:headcount", "Unbuffered attendance basis",
                                [observation("attendees", r["signal_id"]) for r in planning_rows],
                                registered_people=registered, required_people=required,
                                forecast_people=forecast, unbuffered_people=total,
                                chosen_buffer=None, planning_people=None,
                                owner="Learner Experience"))
        if "checkin_target_percent" in facts:
            target = facts["checkin_target_percent"]["value"]
            headcount.append(record("baseline:checkin-target", "Registered check-in success target",
                                    facts["checkin_target_percent"]["evidence_ids"],
                                    target_percent=target, registered_people=registered,
                                    target_people=(registered * target + 99) // 100,
                                    owner="Learner Experience"))
        if "brief_people" in facts and total != facts["brief_people"]["value"]:
            conflicts.append(record("conflict:brief-headcount",
                                    "Attendee basis differs from the brief planning figure",
                                    ["source:attendees"] + facts["brief_people"]["evidence_ids"],
                                    owner="Operations"))
    else:
        unresolved.append(record("issue:headcount-basis", "Attendance components are missing or ambiguous",
                                 ["source:attendees"], owner="Learner Experience"))

    schedule = [record("baseline:calendar:" + r["constraint_id"],
                       r["constraint_type"] + ": " + r["notes"],
                       [observation("calendar", r["constraint_id"])],
                       owner=r["owner"], constraint_type=r["constraint_type"],
                       priority=r["priority"], start_at=r["start_at"].isoformat(),
                       end_at=r["end_at"].isoformat(), notes=r["notes"])
                for r in calendar]
    for name in ("demo_ids", "demo_minutes", "changeover_minutes"):
        if name in facts:
            schedule.append(record("baseline:" + name, name, facts[name]["evidence_ids"],
                                   value=facts[name]["value"], owner="Programme"))
    # Preserve readiness and prerequisite statements as observed exercise knowledge.
    readiness = [b for b in blocks if
                 b["text"].startswith(("For the 17 October 2026 exercise plan", "The planner may choose"))]
    for index, block in enumerate(readiness):
        schedule.append(record(f"baseline:readiness:{index}", block["text"],
                               [observation("brief", block["id"])], owner="Operations"))

    budgets = []
    for row in rows.get("budget", []):
        budgets.append(record("baseline:budget:" + row["category"], row["category"] + " allocation",
                              [observation("budget", row["category"])],
                              owner=row["owner"], category=row["category"],
                              planned_amount_twd=row["planned_amount_twd"],
                              committed_amount_twd=row["committed_amount_twd"],
                              approval_limit_twd=row["approval_limit_twd"],
                              remaining_limit_twd=row["approval_limit_twd"] - row["committed_amount_twd"],
                              approval_status="pending"))
        if row["committed_amount_twd"] > row["approval_limit_twd"]:
            conflicts.append(record("conflict:budget:" + row["category"],
                                    "Existing commitments exceed the category approval limit",
                                    [observation("budget", row["category"])], owner=row["owner"]))
    if "budget_ceiling_twd" in facts:
        budgets.append(record("baseline:total-ceiling", "Overall planning ceiling",
                              facts["budget_ceiling_twd"]["evidence_ids"],
                              cost_twd=facts["budget_ceiling_twd"]["value"], owner="Operations"))

    access = []
    for row in signals:
        if row["segment"] == "all":
            access.append(record("baseline:demand:" + row["signal_id"], row["signal"],
                                 [observation("attendees", row["signal_id"])],
                                 value=row["value"], unit=row["unit"], confidence=row["confidence"],
                                 owner="Learner Experience"))
    for name in ("audience_places", "wheelchair_spaces", "quiet_room_places"):
        if name in facts:
            access.append(record("baseline:" + name, "Exercise coordination " + name,
                                 facts[name]["evidence_ids"], value=facts[name]["value"],
                                 owner="Operations"))
    floor = next(s for s in sources if s["id"] == "source:floorplan")
    if floor["retrieval_status"] == "retrieved":
        for obs in floor["observations"]:
            access.append(record("baseline:" + obs["id"], obs["summary"], [obs["id"]],
                                 locator=obs["locator"], owner="Operations"))
    for index, block in enumerate(b for b in blocks if b["text"].startswith(
            ("For this case, venue coordination", "The package includes setup"))):
        access.append(record(f"baseline:coordination:{index}", block["text"],
                             [observation("brief", block["id"])], owner="Operations"))
    constraints = {"hard_constraints": hard, "preferences": preferences, "assumptions": [],
                   "unknowns": unresolved, "conflicts": conflicts}
    baseline = {"headcount_basis": headcount, "schedule_dependencies": schedule,
                "budget_baseline": budgets, "accessibility_baseline": access,
                "conflicts": conflicts, "business_clock": BUSINESS_CLOCK}
    return scope, constraints, baseline, unresolved + conflicts
