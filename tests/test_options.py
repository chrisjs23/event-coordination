import json
import re
import sys
import unittest
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "event-planning-coordination-brief" / "scripts"))
import options


FIXTURE = ROOT / "tests/fixtures/review-case.json"
POLICY = ROOT / "event-planning-coordination-brief/references/planning-policy.json"


def load_case():
    case = json.loads(FIXTURE.read_text())
    for row in case["rows"]["attendees"]:
        row["observed_at"] = date.fromisoformat(row["observed_at"])
    for row in case["rows"]["vendors"]:
        row["available_date"] = date.fromisoformat(row["available_date"])
        row["valid_until"] = date.fromisoformat(row["valid_until"])
    for row in case["rows"]["calendar"]:
        row["start_at"] = datetime.fromisoformat(row["start_at"])
        row["end_at"] = datetime.fromisoformat(row["end_at"])
    return case


def review(case=None, policy=None):
    case = case or load_case()
    policy = policy or json.loads(POLICY.read_text())
    return options.build_review(case["sources"], case["rows"], case["blocks"],
                                case["baseline"], case["constraints"], policy)


def result_for(results, quote_ids):
    return next(result for result in results
                if all(quote_id in result["option_id"] for quote_id in quote_ids))


class BuildReviewTests(unittest.TestCase):
    def test_canonical_feasible_options_costs_selection_and_schedule(self):
        options_state, results_state, decisions, _ = review()
        results = results_state["option_results"]
        green = result_for(results, {"Q-001", "Q-003", "Q-006"})
        city = result_for(results, {"Q-001", "Q-004", "Q-006"})
        self.assertEqual(green["feasibility"], "feasible")
        self.assertEqual(city["feasibility"], "feasible")
        by_id = {option["id"]: option for option in options_state["options"]}
        self.assertEqual(by_id[green["option_id"]]["cost_twd"], 494000)
        selected = by_id[city["option_id"]]
        self.assertEqual(selected["cost_twd"], 512000)
        self.assertEqual(selected["planning_people"], 260)
        self.assertEqual(decisions["recommendation"], city["option_id"])
        schedule = selected["schedule"]
        self.assertEqual(sum(event["kind"] == "demo" for event in schedule), 12)
        self.assertEqual(sum(event["kind"] == "changeover" for event in schedule), 12)
        self.assertEqual({event["id"] for event in schedule if event["kind"] == "demo"},
                         {f"DEMO-{n:02}" for n in range(1, 13)})
        self.assertEqual(sum((datetime.fromisoformat(event["end_at"]) -
                              datetime.fromisoformat(event["start_at"])).total_seconds() // 60
                             for event in schedule if event["kind"] in {"demo", "changeover"}), 156)
        ordered = sorted(schedule, key=lambda event: event["start_at"])
        for left, right in zip(ordered, ordered[1:]):
            self.assertLessEqual(datetime.fromisoformat(left["end_at"]), datetime.fromisoformat(right["start_at"]))

    def test_quiet_room_capacity_uses_service_demand_not_event_headcount(self):
        options_state, results_state, _, _ = review()
        selected_id = next(option["id"] for option in options_state["options"]
                           if option["cost_twd"] == 512000)
        result = next(result for result in results_state["option_results"] if result["option_id"] == selected_id)
        quiet_check = next(check for check in result["checks"] if check["id"].endswith("Q-010:capacity"))
        self.assertEqual(quiet_check["outcome"], "passed")
        self.assertEqual(next(row["capacity"] for row in next(o for o in options_state["options"] if o["id"] == selected_id)["quotes"]
                              if row["quote_id"] == "Q-010"), 20)

    def test_fallback_keynote_and_unsupported_packages_are_not_feasible(self):
        _, state, decisions, _ = review()
        results = state["option_results"]
        for result in results:
            ids = re.findall(r"Q-\d+", result["option_id"])
            if "Q-002" in ids or "Q-007" in ids or "Q-008" in ids:
                self.assertNotEqual(result["feasibility"], "feasible")
        self.assertIsNotNone(decisions["recommendation"])

    def test_price_commitments_category_limit_and_total_ceiling_are_recomputed(self):
        mutations = []
        case = load_case()
        next(q for q in case["rows"]["vendors"] if q["quote_id"] == "Q-003")["quote_amount_twd"] += 50000
        mutations.append((case, "price"))
        case = load_case()
        next(b for b in case["rows"]["budget"] if b["category"] == "venue")["committed_amount_twd"] = 30000
        mutations.append((case, "commitment"))
        case = load_case()
        next(b for b in case["rows"]["budget"] if b["category"] == "venue")["approval_limit_twd"] = 100000
        mutations.append((case, "category limit"))
        case = load_case()
        next(b for b in case["baseline"]["budget_baseline"] if b["id"] == "baseline:total-ceiling")["cost_twd"] = 400000
        mutations.append((case, "total ceiling"))
        for case, label in mutations:
            with self.subTest(mutation=label):
                options_state, result_state, decisions, _ = review(case)
                if label == "price":
                    target = result_for(result_state["option_results"], {"Q-003"})
                    self.assertEqual(target["feasibility"], "infeasible")
                    self.assertTrue(any(check["outcome"] == "failed" for check in target["checks"]))
                else:
                    self.assertTrue(all(r["feasibility"] != "feasible" for r in result_state["option_results"]))
                    self.assertIsNone(decisions["recommendation"])

    def test_conflicting_venue_price_requires_source_resolution(self):
        case = load_case()
        next(q for q in case["rows"]["vendors"] if q["quote_id"] == "Q-001")["quote_amount_twd"] = 170000
        _, state, decisions, _ = review(case)
        self.assertTrue(all(r["feasibility"] != "feasible" for r in state["option_results"]))
        self.assertIsNone(decisions["recommendation"])

    def test_expired_and_conditional_quotes_never_become_feasible(self):
        case = load_case()
        next(q for q in case["rows"]["vendors"] if q["quote_id"] == "Q-003")["valid_until"] = date(2026, 8, 25)
        _, state, _, _ = review(case)
        self.assertNotEqual(result_for(state["option_results"], {"Q-003"})["feasibility"], "feasible")
        case = load_case()
        next(q for q in case["rows"]["vendors"] if q["quote_id"] == "Q-003")["status"] = "conditional"
        _, state, _, _ = review(case)
        self.assertNotEqual(result_for(state["option_results"], {"Q-003"})["feasibility"], "feasible")

    def test_hold_expiry_and_changed_calendar_qualifier_are_not_trusted(self):
        case = load_case()
        next(row for row in case["rows"]["calendar"] if row["constraint_id"] == "CAL-003")["notes"] = "Hold expires 2026-08-25"
        _, state, _, _ = review(case)
        self.assertTrue(all(r["feasibility"] == "infeasible" for r in state["option_results"]))
        case = load_case()
        next(row for row in case["rows"]["calendar"] if row["constraint_id"] == "CAL-001")["notes"] += " revised"
        _, state, _, _ = review(case)
        self.assertTrue(all(r["feasibility"] != "feasible" for r in state["option_results"]))

    def test_unavailable_floor_and_changed_reviewed_claim_prevent_feasible_result(self):
        case = load_case()
        next(source for source in case["sources"] if source["id"] == "source:floorplan")["retrieval_status"] = "unavailable"
        _, state, _, _ = review(case)
        self.assertTrue(all(r["feasibility"] != "feasible" for r in state["option_results"]))
        case = load_case()
        block = next(block for block in case["blocks"] if block["id"] == "5adfbcd1-1ab9-4161-a22a-5d200888f65c")
        block["text"] += " changed"
        _, state, _, _ = review(case)
        self.assertTrue(all(r["feasibility"] != "feasible" for r in state["option_results"]))

    def test_missing_or_changed_dietary_support_demand_requires_review(self):
        case = load_case()
        case["rows"]["attendees"] = [row for row in case["rows"]["attendees"]
                                      if row["signal"] != "halal_meals"]
        _, state, _, _ = review(case)
        self.assertTrue(all(r["feasibility"] != "feasible" for r in state["option_results"]))
        case = load_case()
        vegetarian = next(row for row in case["rows"]["attendees"] if row["signal"] == "vegetarian_meals")
        vegetarian["value"] += 1
        _, state, _, _ = review(case)
        self.assertTrue(all(r["feasibility"] != "feasible" for r in state["option_results"]))

    def test_capacity_and_programme_overrun_block_recommendation(self):
        case = load_case()
        for quote in case["rows"]["vendors"]:
            if quote["category"] == "catering":
                quote["capacity"] = 259
        _, state, decisions, _ = review(case)
        self.assertIsNone(decisions["recommendation"])
        self.assertTrue(all(r["feasibility"] != "feasible" for r in state["option_results"]))
        case = load_case()
        next(row for row in case["baseline"]["schedule_dependencies"] if row["id"] == "baseline:demo_ids")["value"] = [f"DEMO-{n:02}" for n in range(1, 31)]
        _, state, decisions, _ = review(case)
        self.assertIsNone(decisions["recommendation"])
        self.assertTrue(all(r["feasibility"] != "feasible" for r in state["option_results"]))

    def test_missing_quote_or_budget_data_defers_with_unknown_cost(self):
        case = load_case()
        case["rows"]["vendors"] = [q for q in case["rows"]["vendors"] if q["quote_id"] != "Q-005"]
        options_state, state, decisions, _ = review(case)
        self.assertIsNone(decisions["recommendation"])
        self.assertTrue(all(option["cost_twd"] is None for option in options_state["options"]))
        case = load_case()
        case["rows"]["budget"] = [row for row in case["rows"]["budget"] if row["category"] != "contingency"]
        options_state, state, decisions, _ = review(case)
        self.assertIsNone(decisions["recommendation"])
        self.assertTrue(all(option["cost_twd"] is None for option in options_state["options"]))

    def test_invalid_headcount_defers_and_approvals_remain_pending(self):
        case = load_case()
        next(row for row in case["baseline"]["headcount_basis"]
             if row["id"] == "baseline:headcount")["unbuffered_people"] = None
        options_state, _, decisions, _ = review(case)
        self.assertIsNone(decisions["recommendation"])
        self.assertTrue(all(option["planning_people"] is None for option in options_state["options"]))
        _, _, decisions, _ = review()
        approvals = decisions["approval_requirements"]
        self.assertTrue(all(item["status"] == "pending" for item in approvals))
        category_ids = {item["id"] for item in approvals if item["id"].startswith("approval:category:")}
        operations = next(item for item in approvals if item["id"] == "approval:operations")
        self.assertEqual(set(operations["prerequisites"]), category_ids)


if __name__ == "__main__":
    unittest.main()
