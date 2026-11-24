"""Compare the reviewed exercise packages without granting spending authority."""

from datetime import date, datetime
import itertools
import json
import re

from baseline import BUSINESS_CLOCK, observation, record
from schedule import build_schedule
from snapshots import sha256


def scope_hash(quote):
    meaning = {key: quote[key] for key in ("category", "option", "notes")}
    return sha256(json.dumps(meaning, sort_keys=True, ensure_ascii=False).encode())


def build_review(sources, rows, blocks, baseline, constraints, policy):
    source_ids = {s["id"]: s for s in sources}
    block_map = {b["id"]: b for b in blocks}
    quotes = {r["quote_id"]: r for r in rows.get("vendors", [])}
    calendar = rows.get("calendar", [])
    budgets = {r["category"]: r for r in rows.get("budget", [])}
    demands = {r["signal"]: r["value"] for r in rows.get("attendees", []) if r["segment"] == "all"}
    counts = [r for r in baseline["headcount_basis"] if r["id"] == "baseline:headcount"]
    headcount = counts[0]["unbuffered_people"] if len(counts) == 1 else None
    buffer = policy["buffer_people"]
    if not isinstance(buffer, int) or isinstance(buffer, bool) or buffer < 0:
        raise ValueError("planning buffer must be a nonnegative integer")
    planning_people = headcount + buffer if headcount is not None else None
    clock = date.fromisoformat(BUSINESS_CLOCK[:10])

    def claim(name):
        spec = policy["claims"][name]
        block = block_map.get(spec["block_id"])
        valid = block is not None and sha256(block["text"].encode()) == spec["sha256"]
        evidence = [observation("brief", block["id"])] if block else ["source:brief"]
        return valid, evidence

    def calendar_record(kind, day=None):
        found = [r for r in calendar if r["constraint_type"] == kind and
                 (day is None or r["start_at"].date() == day)]
        return found[0] if len(found) == 1 else None

    def baseline_value(identity):
        for field in ("schedule_dependencies", "accessibility_baseline", "budget_baseline"):
            found = [r for r in baseline[field] if r["id"] == identity]
            if len(found) == 1:
                return found[0].get("value", found[0].get("cost_twd"))
        return None

    roles = {role: [quotes[q] for q in ids if q in quotes]
             for role, ids in policy["roles"].items()}
    rejected = []
    classified = set(itertools.chain.from_iterable(policy["roles"].values()))
    for q in quotes.values():
        if q["quote_id"] not in classified:
            rejected.append(record("rejected:" + q["quote_id"],
                                   "Quote role/scope needs review before combining it into a package",
                                   [observation("vendors", q["quote_id"])], owner="Operations"))
    for role, ids in policy["roles"].items():
        if not roles[role] and role != "livestream":
            rejected.append(record("missing-role:" + role,
                                   role + " has no supported quote in the captured register",
                                   ["source:vendors"], owner="Operations"))
    fixed_roles = ("captions", "security", "quiet_room")
    fixed = [roles[role][0] for role in fixed_roles if len(roles[role]) == 1]
    preferred = calendar_record("preferred_event_window")
    candidates = []
    for venue, catering, av in itertools.product(roles["venue"], roles["catering"], roles["av"]):
        base = [venue, catering, av] + fixed
        candidates.append((base, venue, catering, av, False))
        if preferred and venue["available_date"] == preferred["start_at"].date() and av["quote_id"] in policy["hearing_loop_quotes"]:
            for stream in roles["livestream"]:
                candidates.append((base + [stream], venue, catering, av, True))

    options, results = [], []
    for package, venue, catering, av, streaming in candidates:
        quote_ids = sorted(q["quote_id"] for q in package)
        option_id = "option:" + "-".join(quote_ids)
        evidence = [observation("vendors", qid) for qid in quote_ids]
        checks = []

        def check(key, outcome, summary, evidence_ids):
            checks.append(record(f"check:{option_id}:{key}", summary, evidence_ids,
                                 outcome=outcome, owner="Operations"))

        missing = [role for role in fixed_roles if len(roles[role]) != 1]
        check("services", "unverified" if missing else "passed",
              "Missing or ambiguous required services: " + ", ".join(missing) if missing else
              "Captioning, quiet-room staffing and security quotes are identified", ["source:vendors"])
        for quote in package:
            qid = quote["quote_id"]
            ev = [observation("vendors", qid)]
            reviewed = scope_hash(quote) == policy["quote_scope_hashes"].get(qid)
            check(qid + ":scope", "passed" if reviewed else "unverified",
                  "Service scope and conditions match the reviewed interpretation" if reviewed else
                  "Changed quote scope or conditions require review", ev)
            expired = quote["valid_until"] < clock
            expiry_today = quote["valid_until"] == clock
            outcome = "failed" if expired else "unverified" if expiry_today else "passed"
            check(qid + ":validity", outcome,
                  "Quote expired at the exercise clock" if expired else
                  "Expiry time needs confirmation" if expiry_today else "Quote remains within its stated date validity", ev)
            availability = "passed" if quote["status"] == "available" or (
                quote["status"] == "held" and quote["category"] == "venue") else (
                "failed" if quote["status"] == "unavailable" else "unverified")
            check(qid + ":availability", availability,
                  "Captured availability state: " + quote["status"] + "; subject to recorded conditions", ev)
            check(qid + ":date", "passed" if quote["available_date"] == venue["available_date"] else "failed",
                  "Service date matches venue date" if quote["available_date"] == venue["available_date"] else
                  "Service quote applies to a different date", ev)

        day = venue["available_date"]
        window = calendar_record("preferred_event_window", day) or calendar_record("fallback_event_window", day)
        keynote = calendar_record("keynote_availability", day)
        hold = calendar_record("venue_hold", day)
        end_access = calendar_record("teardown_deadline", day)
        calendar_ev = [observation("calendar", r["constraint_id"]) for r in
                       (window, keynote, hold, end_access) if r]
        check("keynote", "passed" if keynote else "failed",
              "Keynote is supported on this date" if keynote else
              "No keynote availability is supported on this event date", calendar_ev or ["source:calendar"])
        for row in (window, keynote, hold, end_access):
            if row:
                reviewed = sha256(row["notes"].encode()) == policy["calendar_note_hashes"].get(row["constraint_id"])
                check("calendar-note:" + row["constraint_id"], "passed" if reviewed else "unverified",
                      "Calendar qualifiers match reviewed meanings" if reviewed else "Changed calendar qualifiers require review",
                      [observation("calendar", row["constraint_id"])])
        expiry = re.findall(r"expires (\d{4}-\d{2}-\d{2})", hold["notes"]) if hold else []
        try:
            hold_expiry = date.fromisoformat(expiry[0]) if len(expiry) == 1 else None
        except ValueError:
            hold_expiry = None
        outcome = "unverified" if hold_expiry is None or hold_expiry == clock else (
            "failed" if hold_expiry < clock else "passed")
        check("venue-hold", outcome, "Hold expiry evaluated against the exercise clock",
              [observation("calendar", hold["constraint_id"])] if hold else ["source:calendar"])
        programme = []
        inputs = [window, keynote, hold, end_access]
        demo_ids = baseline_value("baseline:demo_ids")
        demo_minutes = baseline_value("baseline:demo_minutes")
        changeover = baseline_value("baseline:changeover_minutes")
        if all(inputs) and demo_ids and demo_minutes and changeover:
            try:
                programme = build_schedule(window["start_at"], window["end_at"],
                                           keynote["start_at"], keynote["end_at"], demo_ids,
                                           demo_minutes, changeover, hold["start_at"], end_access["end_at"])
                check("programme", "passed", "Proposed programme fits without overlaps", calendar_ev)
            except ValueError:
                check("programme", "failed", "Programme cannot fit the recorded windows", calendar_ev)
        else:
            check("programme", "unverified", "Programme or access dependencies are missing",
                  calendar_ev or ["source:calendar"])

        # Confirmation applies to the reviewed base services, with the stated date and scope.
        for name in ("hard-requirements", "venue-allocation", "step-free", "dietary-and-services", "readiness", "setup-choice", "programme"):
            valid, ev = claim(name)
            if name == "venue-allocation":
                allocation = block_map.get(policy["claims"][name]["block_id"], {}).get("text", "")
                amounts = re.findall(r"quoted TWD ([\d,]+) package", allocation)
                coordinated_price = int(amounts[0].replace(",", "")) if len(amounts) == 1 else None
                valid = valid and coordinated_price == venue["quote_amount_twd"]
            check(name, "passed" if valid else "unverified",
                  name + (" matches reviewed exercise evidence" if valid else " needs renewed source review"), ev)
        readiness_block = block_map.get(policy["claims"]["readiness"]["block_id"], {})
        readiness_text = readiness_block.get("text", "")
        dates = re.findall(r"For the (\d+ \w+ \d{4}) exercise plan", readiness_text)
        try:
            ready_date = datetime.strptime(dates[0], "%d %B %Y").date() if len(dates) == 1 else None
        except ValueError:
            ready_date = None
        base_supported = (av["quote_id"] in policy["hearing_loop_quotes"] and not streaming and ready_date == day)
        check("service-readiness", "passed" if base_supported else "unverified",
              "Base-bundle setup and clearance are supported by the exercise record" if base_supported else
              "This bundle needs additional readiness or network confirmation", ["source:brief"])
        check("hearing-loop", "passed" if demands.get("hearing_loop_requests") == 0 or
              av["quote_id"] in policy["hearing_loop_quotes"] else
              "unverified" if "hearing_loop_requests" not in demands else "failed",
              "AV must support the recorded hearing-loop demand", ["source:attendees"] + evidence)
        support_signals = {"wheelchair_spaces", "mobility_companions", "live_caption_requests",
                           "hearing_loop_requests", "quiet_room_requests", "vegetarian_meals",
                           "halal_meals", "severe_allergy_follow_up"}
        check("support-demand", "passed" if support_signals.issubset(demands) else "unverified",
              "All disclosed support and dietary demand measures remain present", ["source:attendees"])
        dietary_text = block_map.get(policy["claims"]["dietary-and-services"]["block_id"], {}).get("text", "")
        covered = {}
        for signal, pattern in (
                ("vegetarian_meals", r"(\d+) vegetarian meals"),
                ("halal_meals", r"(\d+) halal meals"),
                ("severe_allergy_follow_up", r"(four|\d+) severe-allergy requests")):
            values = re.findall(pattern, dietary_text)
            covered[signal] = (4 if values[0] == "four" else int(values[0])) if len(values) == 1 else None
        coordinated = all(covered[signal] is not None and covered[signal] == demands.get(signal)
                          for signal in covered)
        check("dietary-coordination", "passed" if coordinated else "unverified",
              "Dietary response covers the current recorded demand" if coordinated else
              "Dietary demand needs renewed Operations coordination", ["source:brief", "source:attendees"])
        for signal in ("vegetarian_meals", "halal_meals"):
            demand = demands.get(signal)
            check("meal-capacity:" + signal,
                  "unverified" if demand is None else "passed" if demand <= catering["capacity"] else "failed",
                  "Catering capacity covers the individual meal-demand measure",
                  [observation("vendors", catering["quote_id"]), "source:attendees"])
        floor = source_ids.get("source:floorplan", {})
        check("spatial-evidence", "passed" if floor.get("retrieval_status") == "retrieved" and
              len(floor.get("observations", [])) == 4 else "unverified",
              "Spatial evidence requires the reviewed official floor plan", ["source:floorplan"])
        for key, available, required in (
                ("audience", baseline_value("baseline:audience_places"), planning_people),
                ("wheelchair", baseline_value("baseline:wheelchair_spaces"), demands.get("wheelchair_spaces")),
                ("quiet-room", baseline_value("baseline:quiet_room_places"), demands.get("quiet_room_requests"))):
            outcome = "unverified" if available is None or required is None else (
                "passed" if available >= required else "failed")
            check(key, outcome, f"{key} allocation compared with planning demand",
                  ["source:brief", "source:attendees"])
        for quote in package:
            required = demands.get("quiet_room_requests") if quote["quote_id"] in policy["roles"]["quiet_room"] else planning_people
            outcome = "unverified" if required is None else "passed" if quote["capacity"] >= required else "failed"
            check(quote["quote_id"] + ":capacity", outcome,
                  "Service-specific capacity compared with its applicable demand",
                  [observation("vendors", quote["quote_id"]), "source:attendees"])

        totals = {}
        for quote in package:
            category = quote["category"]
            totals[category] = totals.get(category, 0) + quote["quote_amount_twd"]
        for category in policy["allowance_categories"]:
            if category in budgets:
                totals[category] = budgets[category]["planned_amount_twd"]
        expected_categories = {"venue", "catering", "accessibility", "production", "security"} | set(policy["allowance_categories"])
        cost_known = not missing and set(budgets) == expected_categories and set(totals) == expected_categories
        cost_known = cost_known and all(q["category"] in budgets for q in package)
        category_costs = []
        for category, proposed in sorted(totals.items()):
            budget = budgets.get(category)
            if budget is None:
                continue
            combined = proposed + budget["committed_amount_twd"]
            category_costs.append({"category": category, "owner": budget["owner"],
                                   "proposed_twd": proposed, "committed_twd": budget["committed_amount_twd"],
                                   "cost_twd": combined, "limit_twd": budget["approval_limit_twd"],
                                   "remaining_twd": budget["approval_limit_twd"] - combined})
            check("budget:" + category, "passed" if combined <= budget["approval_limit_twd"] else "failed",
                  "Proposed spending plus commitments compared with category limit",
                  [observation("budget", category)] + evidence)
        total = sum(x["cost_twd"] for x in category_costs) if cost_known else None
        ceiling = baseline_value("baseline:total-ceiling")
        outcome = "unverified" if total is None or ceiling is None else "passed" if total <= ceiling else "failed"
        check("total-budget", outcome, "All category costs including allowances compared with overall ceiling",
              ["source:budget", "source:brief"])
        model_conflicts = constraints.get("conflicts", [])
        unknowns = [r for r in constraints.get("unknowns", []) if r["id"] != "issue:buffer-policy"]
        check("baseline-integrity", "unverified" if model_conflicts or unknowns or headcount is None else "passed",
              "Baseline conflicts and unknowns require owner resolution", ["source:attendees", "source:brief"])
        outcomes = {r["outcome"] for r in checks}
        feasibility = "infeasible" if "failed" in outcomes else "conditional" if "unverified" in outcomes else "feasible"
        summary = f"{catering['vendor']} with {av['vendor']} on {day.isoformat()}" + (" plus livestream" if streaming else "")
        option = record(option_id, summary, evidence, quote_ids=quote_ids, event_date=day.isoformat(),
                        planning_people=planning_people, buffer_people=buffer,
                        cost_twd=total, currency="TWD", category_costs=category_costs,
                        catering_capacity=catering["capacity"],
                        catering_headroom=catering["capacity"] - planning_people if planning_people is not None else None,
                        quotes=package, schedule=programme,
                        availability_status="supported-by-exercise-record" if feasibility == "feasible" else "see-conditions",
                        approval_status="pending", budget_remaining_twd=ceiling-total if ceiling is not None and total is not None else None)
        options.append(option)
        results.append(record("result:" + option_id, summary, evidence,
                              option_id=option_id, feasibility=feasibility, checks=checks))

    feasible_ids = {r["option_id"] for r in results if r["feasibility"] == "feasible"}
    feasible = [o for o in options if o["id"] in feasible_ids]
    chosen = min(feasible, key=lambda o: (-o["catering_capacity"], o["cost_twd"], o["id"])) if feasible else None
    selection = record("decision:selection", "Recommend a supported option or defer", ["source:vendors", "source:budget"],
                       rationale=policy["selection_rule"] if chosen else "No option passed every hard-constraint check",
                       tradeoffs=["Greater catering coverage reduces shortage exposure but costs more",
                                  "Retain the lower-cost alternative and its remaining budget for review"],
                       selected_option_id=chosen["id"] if chosen else None)
    buffer_decision = record("decision:headcount-buffer", "Proposed attendance buffer for this plan",
                             ["source:attendees", "source:interview"], rationale=f"Propose {buffer} additional people above the captured basis of {headcount}. " + policy["buffer_rationale"],
                             tradeoffs=["A larger buffer protects against forecast error and can increase waste",
                                        "The chosen buffer requires both catering and venue capacity"],
                             buffer_people=buffer, unbuffered_people=headcount, planning_people=planning_people,
                             approval_status="pending")
    approvals = []
    if chosen:
        for item in chosen["category_costs"]:
            approvals.append(record("approval:category:" + item["category"],
                                    "Review category spending and remaining limit", [observation("budget", item["category"])],
                                    status="pending", owner=item["owner"], option_id=chosen["id"], **{
                                        key: item[key] for key in ("category", "cost_twd", "remaining_twd")}))
    approvals.append(record("approval:operations", "Review date, venue, headcount policy and option conditions",
                            ["source:brief", "source:interview"], status="pending", owner="Operations",
                            prerequisites=[r["id"] for r in approvals], option_id=chosen["id"] if chosen else None))
    tradeoffs = [record("tradeoff:" + o["id"], "Package cost, capacity and unresolved conditions",
                        o["evidence_ids"], option_id=o["id"], cost_twd=o["cost_twd"],
                        catering_headroom=o["catering_headroom"], remaining_budget_twd=o["budget_remaining_twd"])
                for o in options]
    unresolved = [record("condition:" + r["id"], "Option needs resolution of hard-constraint dependencies",
                         r["evidence_ids"], option_id=r["option_id"], owner="Operations")
                  for r in results if r["feasibility"] == "conditional"]
    if not chosen:
        unresolved.append(record("issue:recommendation", "Recommendation deferred until a supported option is feasible",
                                 ["source:vendors", "source:brief"], owner="Operations"))
    state5 = {"options": options, "rejected_early": rejected}
    state6 = {"option_results": results, "unresolved_conditions": unresolved}
    state7 = {"recommendation": chosen["id"] if chosen else None, "tradeoffs": tradeoffs,
              "learner_decisions": [buffer_decision, selection], "approval_requirements": approvals,
              "model": {"headcount": buffer_decision, "options": options, "results": results,
                        "selected_option": chosen, "calendar_records": calendar,
                        "baseline": baseline, "constraints": constraints,
                        "planning_policy": policy}}
    return state5, state6, state7, unresolved
