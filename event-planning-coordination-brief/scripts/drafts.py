"""Render the four local review drafts from one verified planning model."""

import csv
import html
import io
import json

from calendar_draft import render_calendar, supported_window

ARTIFACTS = ("vendor-comparison.csv", "event-plan.md", "event-calendar.ics", "draft-communications.md")
CSV_FIELDS = ("option_id", "quote_ids", "planning_people", "cost_twd", "currency",
              "feasibility", "availability_status", "evidence_ids", "tradeoffs",
              "unresolved", "approval_status")


def md(value):
    if value is None:
        return "unknown"
    return html.escape(str(value), quote=False).replace("|", "\\|").replace("\n", "<br>").replace("\r", "")


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(md(cell) for cell in row) + " |" for row in rows)
    return "\n".join(lines)


def planning_facts(context):
    review = context["review"]
    model = review["model"]
    selected = model.get("selected_option")
    return {
        "Run": context["run_id"],
        "Recommended option": review["recommendation"] or "deferred",
        "Event date": selected["event_date"] if selected else "deferred",
        "Planning people": model["headcount"].get("planning_people"),
        "Cost TWD": selected["cost_twd"] if selected else None,
        "Currency": "TWD",
        "Overall budget remaining TWD": selected["budget_remaining_twd"] if selected else None,
        "Approval status": "pending",
    }


def option_conditions(result):
    return [check["summary"] for check in result["checks"] if check["outcome"] != "passed"]


def comparison_rows(context):
    model = context["review"]["model"]
    results = {r["option_id"]: r for r in model["results"]}
    rows = []
    for option in model["options"]:
        result = results[option["id"]]
        conditions = option_conditions(result)
        if option["cost_twd"] is None:
            conditions.append("Cost unknown because required quote or budget scope is missing or ambiguous")
        coverage = {key: "unknown" if option[key] is None else str(option[key])
                    for key in ("catering_capacity", "catering_headroom", "budget_remaining_twd")}
        details = [
            f"Catering capacity {coverage['catering_capacity']}. Headroom {coverage['catering_headroom']}. "
            f"Remaining total budget TWD {coverage['budget_remaining_twd']}."
        ]
        for quote in option["quotes"]:
            details.append(
                f"{quote['quote_id']} | vendor={quote['vendor']} | category={quote['category']} | "
                f"scope={quote['option']} | package TWD={quote['quote_amount_twd']} | capacity={quote['capacity']} | "
                f"event date={quote['available_date']} | valid until={quote['valid_until']} | "
                f"state={quote['status']} | conditions={quote['notes']}"
            )
        rows.append({
            "option_id": option["id"], "quote_ids": json.dumps(option["quote_ids"], ensure_ascii=False),
            "planning_people": "" if option["planning_people"] is None else str(option["planning_people"]),
            "cost_twd": "" if option["cost_twd"] is None else str(option["cost_twd"]),
            "currency": option["currency"], "feasibility": result["feasibility"],
            "availability_status": option["availability_status"],
            "evidence_ids": json.dumps(list(dict.fromkeys(option["evidence_ids"] +
                [eid for check in result["checks"] for eid in check["evidence_ids"]])), ensure_ascii=False),
            "tradeoffs": json.dumps(details, ensure_ascii=False),
            "unresolved": json.dumps(conditions, ensure_ascii=False),
            "approval_status": option["approval_status"],
        })
    return rows


def render_csv(context):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(comparison_rows(context))
    return stream.getvalue().encode("utf-8")


def render_plan(context):
    review = context["review"]
    model = review["model"]
    baseline = model["baseline"]
    selected = model.get("selected_option")
    results = {r["option_id"]: r for r in model["results"]}
    lines = ["# Fellowship Demo Day — planning draft", "",
             "Review requested from Operations and the category owners.", "",
             "## Planning basis", "", table(("Item", "Value"), planning_facts(context).items()), "",
             "Prepared at " + md(context["created_at"]) + ". Exercise business clock " +
             md(baseline["business_clock"]) + ". Actual retrieval times are listed below.", "",
             "## Objective and success measures", "", md(context["scope"]["objective"]), "",
             "Run every scheduled team demonstration and document responses to accessibility requests before the event."]
    for target in baseline["headcount_basis"]:
        if target["id"] == "baseline:checkin-target":
            lines.append(f"Registered check-in target is {md(target['target_percent'])}% of "
                         f"{md(target['registered_people'])} registrations, or at least {md(target['target_people'])} people.")
    lines += ["", "## Headcount and uncertainty", "", md(model["headcount"]["rationale"]), ""]
    count_rows = []
    for basis in baseline["headcount_basis"]:
        if basis["id"] == "baseline:headcount":
            count_rows.extend((("Registered", basis["registered_people"]), ("Required on site", basis["required_people"]),
                               ("Forecast walk-ins", basis["forecast_people"]), ("Unbuffered basis", basis["unbuffered_people"])))
    count_rows.extend((("Proposed buffer", model["headcount"]["buffer_people"]),
                       ("Proposed planning headcount", model["headcount"]["planning_people"])))
    lines += [table(("Measure", "People"), count_rows), "",
              "Support requests and meal demand are separate measures. Keep confidence and observation dates with "
              "the source signals. The buffer has no probability guarantee and needs reconsideration after attendance changes.", "",
              "## Recommendation and alternatives", ""]
    if selected:
        lines.append("Recommend " + md(selected["summary"]) + " for owner review. Total TWD " +
                     md(selected["cost_twd"]) + ", leaving TWD " + md(selected["budget_remaining_twd"]) + ".")
    else:
        lines.append("Recommendation deferred. Resolve the option conditions with Operations before selecting an event.")
    for decision in review["learner_decisions"]:
        lines.append(md(decision["rationale"]))
        lines.extend("- " + md(item) for item in decision["tradeoffs"])
    lines += ["", table(("Feasible option", "Cost TWD", "Catering capacity", "Headroom", "Budget remaining TWD"),
                         [(o["id"], o["cost_twd"], o["catering_capacity"], o["catering_headroom"],
                           o["budget_remaining_twd"]) for o in model["options"]
                          if results[o["id"]]["feasibility"] == "feasible"]), ""]
    lines += ["", table(("Option", "Date", "Cost TWD", "Feasibility", "Conditions"),
                         [(o["id"], o["event_date"], o["cost_twd"], results[o["id"]]["feasibility"],
                           "\n".join(option_conditions(results[o["id"]])) or "Owner approvals pending")
                          for o in model["options"]]), "",
              "## Category budget", ""]
    if selected:
        lines.append(table(("Category", "Owner", "Proposed TWD", "Committed TWD", "Total TWD", "Limit TWD", "Remaining TWD"),
                           [(r["category"], r["owner"], r["proposed_twd"], r["committed_twd"],
                             r["cost_twd"], r["limit_twd"], r["remaining_twd"]) for r in selected["category_costs"]]))
    else:
        lines.append("Selected costs remain unknown until a supportable option is chosen.")
        lines.append(table(("Category", "Owner", "Planned TWD", "Committed TWD", "Limit TWD"),
                           [(r["category"], r["owner"], r["planned_amount_twd"], r["committed_amount_twd"],
                             r["approval_limit_twd"]) for r in baseline["budget_baseline"] if "category" in r]))
    lines += ["", "Package prices are used as quoted. Communications and contingency remain budget allowances. "
              "Existing commitments are carried alongside proposed spending. Owners must reconcile any overlap before authorizing spending.", "",
              "## Proposed run of show", "",
              "Times retain their explicit UTC offsets. Setup and readiness intervals are planner-proposed coordination choices."]
    if selected and supported_window(context):
        lines += ["", table(("Activity ID", "Activity", "Start", "End", "Basis"),
                            [(r["id"], r["label"], r["start_at"], r["end_at"], r["planning_basis"])
                             for r in selected["schedule"]])]
    else:
        lines.append("Programme and calendar are deferred pending a supportable event selection. The calendar contains no events.")
    lines += ["", "## Calendar dependencies", "",
              table(("Record", "Owner", "Type", "Start", "End", "Priority", "Qualifier"),
                    [(r["constraint_id"], r["owner"], r["constraint_type"], r["start_at"], r["end_at"],
                      r["priority"], r["notes"]) for r in model["calendar_records"]]), "",
              "The walkthrough remains subject to venue confirmation. Rehearsal, deadline and hold records retain their "
              "source meanings. Programme changes return to Programme and event parameters return to Operations.", "",
              "## Accessibility and safety", ""]
    lines.append(table(("Record", "Measure or observation", "Value", "Unit", "Locator", "Evidence"),
                       [(r["id"], r["summary"], r.get("value", "see observation"), r.get("unit", ""), r.get("locator", {}).get("value", "see source record"),
                         ", ".join(r["evidence_ids"])) for r in baseline["accessibility_baseline"]
                        if ":coordination:" not in r["id"] and
                        (selected or not r["id"].startswith("baseline:obs:floorplan:"))]))
    if selected:
        lines += ["", "The fictional exercise coordination record supplies step-free access, room allocations and base-service "
                  "readiness. The retained official drawing supplies spatial locators. Current elevator operation, route clearance, "
                  "seating setup and acoustic performance require current confirmation in a real deployment.",
                  "Operations holds individual contacts and coordinates dietary and accessibility responses before the event."]
    else:
        lines += ["", "Dependent spatial and accessibility feasibility claims remain unresolved. Inspect the source retrieval "
                  "states and option conditions before relying on venue routes or services."]
    lines += ["", "## Risks, unknowns and change impacts", "",
              "- Owner spending reviews and Operations approval remain pending.",
              "- Forecast error can exhaust the catering buffer. Extra coverage increases cost and potential waste.",
              "- Changes to attendance affect capacity, costs, comparisons, programme support and every draft.",
              "- Quote, venue, calendar or category changes require dependent checks and review requests to be regenerated.",
              "- Preserve earlier evidence and drafts when processing material changes.", ""]
    if selected:
        lines.append("Current remaining overall budget is TWD " + md(selected["budget_remaining_twd"]) +
                     ". Recheck affordability before adding optional services.")
    for issue in context.get("unresolved", []):
        lines.append("- " + md(issue["summary"]) + " Owner " + md(issue.get("owner", "Operations")) + ".")
    lines += ["", "## Review requests", "",
              table(("Request", "Owner", "Status", "Scope"),
                    [(r["id"], r.get("owner"), r["status"], r["summary"]) for r in review["approval_requirements"]]),
              "", "Category owners review their allocations and commitments before Operations reviews the full plan. "
              "Communications and calendar files remain local drafts pending review.", "",
              "## Sources and captured evidence", "",
              table(("Source ID", "Retrieval", "Actual retrieval time", "Version", "Captured file"),
                    [(s["id"], s["retrieval_status"], s["retrieved_at"],
                      s.get("version_metadata", {}).get("record_version", "see source-capture snapshot"),
                      s["local_reference"] or "unavailable") for s in context["sources"]]),
              "", "Inspect snapshots/02-source-capture.json for original URLs, response and extract hashes, block/cell locators "
              "and individual observations. Each comparison preserves its quote evidence IDs.", "",
              "## Quote register used in comparison", ""]
    quotes = {q["quote_id"]: q for o in model["options"] for q in o["quotes"]}
    lines.append(table(("Quote", "Vendor", "Category", "Package TWD", "Capacity", "Date", "Valid until", "Status", "Conditions"),
                       [(q["quote_id"], q["vendor"], q["category"], q["quote_amount_twd"], q["capacity"],
                         q["available_date"], q["valid_until"], q["status"], q["notes"]) for q in quotes.values()]))
    for rejected in context.get("rejected_early", []):
        lines.append("- " + md(rejected["summary"]) + " Evidence " + md(", ".join(rejected["evidence_ids"])) + ".")
    return ("\n".join(lines) + "\n").encode()


def render_messages(context):
    review = context["review"]
    selected = review["model"].get("selected_option")
    lines = ["# Draft communications", "", table(("Item", "Value"), planning_facts(context).items()), ""]
    if selected:
        basis = (f"Proposed date {selected['event_date']}, planning headcount {selected['planning_people']}, "
                 f"total TWD {selected['cost_twd']}.")
    else:
        basis = "Recommendation and event timing await resolution of the recorded option conditions."

    def message(audience, purpose, owner, conditions, body):
        lines.extend(["## UNSENT DRAFT — " + md(audience), "",
                      "Audience — " + md(audience), "Purpose — " + md(purpose),
                      "Conditions — " + md(conditions), "Approval owner — " + md(owner), "",
                      md(body), ""])

    message("Operations", "Review the plan and unresolved dependencies", "Operations",
            "Category owners review spending first",
            basis + " Please review date, venue, headcount policy, evidence limitations and the dependent calendar. "
            "Record your decision against this plan revision and identify any requested changes.")
    for item in review["approval_requirements"]:
        if "category" in item:
            message(item["owner"] + " / " + item["category"], "Review category allocation and commitments", item["owner"],
                    "Recorded quote scope and validity must remain supported",
                    f"Please review {item['category']} total TWD {item['cost_twd']} and remaining category limit "
                    f"TWD {item['remaining_twd']}. Reconcile existing commitments and proposed spending before approval. " + basis)
    message("Attendees", "Review proposed event information", "Operations",
            "Operations approval and documented accessibility responses before release",
            basis + " The proposed programme includes fellow demonstrations and the keynote. "
            "Operations will coordinate documented responses to accessibility and dietary requests before the event.")
    if selected:
        for quote in selected["quotes"]:
            message(quote["vendor"] + " via Operations", "Review quoted package and coordination dependencies",
                    "Operations and " + quote["category"] + " budget owner",
                    "Category and Operations approval before any supplier commitment",
                    f"Please confirm the {quote['quote_id']} package for {quote['available_date']}, scope {quote['option']}, "
                    f"capacity {quote['capacity']}, package amount TWD {quote['quote_amount_twd']} and validity "
                    f"through {quote['valid_until']}. Recorded conditions: {quote['notes']}. " + basis)
    else:
        message("Category owners via Operations", "Clarify evidence needed for a recommendation", "Operations",
                "Resolve the failed or unverified checks before selecting an option",
                "Please clarify the option conditions and the affected source records. Retain the responsible actor, "
                "revision, timestamp, scope and reasons with any response.")
    return ("\n".join(lines) + "\n").encode()


def render_drafts(context):
    return {
        "vendor-comparison.csv": render_csv(context),
        "event-plan.md": render_plan(context),
        "event-calendar.ics": render_calendar(context),
        "draft-communications.md": render_messages(context),
    }
