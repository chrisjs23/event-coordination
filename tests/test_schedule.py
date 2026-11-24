import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "event-planning-coordination-brief/scripts"))
from schedule import build_schedule


TZ = ZoneInfo("Asia/Taipei")


def at(hour, minute=0):
    return datetime(2026, 10, 17, hour, minute, tzinfo=TZ)


class BuildScheduleTests(unittest.TestCase):
    def schedule(self, **overrides):
        args = dict(
            event_start=at(9, 30), event_end=at(17),
            keynote_start=at(10), keynote_end=at(11),
            demo_ids=[f"demo-{i}" for i in range(1, 13)],
            presentation_minutes=10, changeover_minutes=3,
            venue_start=at(7, 30), venue_end=at(18, 30),
        )
        args.update(overrides)
        return build_schedule(**args)

    def test_canonical_schedule_is_complete_and_non_overlapping(self):
        rows = self.schedule()
        programme = [row for row in rows if row["kind"] not in {"setup", "readiness", "teardown"}]
        self.assertEqual(sum(row["kind"] == "demo" for row in rows), 12)
        self.assertEqual(sum(row["kind"] == "changeover" for row in rows), 12)
        self.assertEqual({row["id"] for row in rows if row["kind"] == "demo"}, {f"demo-{i}" for i in range(1, 13)})
        self.assertEqual(sum((datetime.fromisoformat(row["end_at"]) - datetime.fromisoformat(row["start_at"])).total_seconds() // 60 for row in rows if row["kind"] in {"demo", "changeover"}), 156)
        self.assertEqual(datetime.fromisoformat(programme[0]["start_at"]), at(9, 30))
        self.assertEqual(datetime.fromisoformat(programme[-1]["end_at"]), at(17))
        for row in rows:
            start, end = datetime.fromisoformat(row["start_at"]), datetime.fromisoformat(row["end_at"])
            self.assertGreater(end, start)
            self.assertEqual(row["planning_basis"], "planner-proposed")
        for group, expected in ((programme, None), ([r for r in rows if r["kind"] in {"setup", "readiness"}], at(9, 30))):
            ordered = sorted(group, key=lambda row: row["start_at"])
            for left, right in zip(ordered, ordered[1:]):
                self.assertLessEqual(datetime.fromisoformat(left["end_at"]), datetime.fromisoformat(right["start_at"]))
            if expected:
                self.assertEqual(datetime.fromisoformat(ordered[-1]["end_at"]), expected)
        setup, checks = next(r for r in rows if r["id"] == "setup"), next(r for r in rows if r["id"] == "readiness-checks")
        self.assertEqual(datetime.fromisoformat(setup["start_at"]), at(7, 30))
        self.assertEqual(datetime.fromisoformat(checks["end_at"]), at(9, 30))
        teardown = next(r for r in rows if r["kind"] == "teardown")
        self.assertEqual((datetime.fromisoformat(teardown["start_at"]), datetime.fromisoformat(teardown["end_at"])), (at(17), at(18, 30)))

    def test_rejects_overfull_or_shifted_keynote(self):
        with self.assertRaises(ValueError):
            self.schedule(demo_ids=[f"demo-{i}" for i in range(30)])
        with self.assertRaises(ValueError):
            self.schedule(keynote_start=at(9, 40))

    def test_rejects_invalid_demo_ids_and_durations(self):
        for ids in ([], ["x", "x"], [" "]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.schedule(demo_ids=ids)
        with self.assertRaises(ValueError):
            self.schedule(presentation_minutes=0)
        with self.assertRaises(ValueError):
            self.schedule(changeover_minutes=0)


if __name__ == "__main__":
    unittest.main()
