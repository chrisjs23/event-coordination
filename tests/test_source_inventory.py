"""Keep the sheet map tied to sources actually disclosed by the stakeholder."""

import json
import re
import unittest
from pathlib import Path

from check_source_csv import CONTRACT_PATH

ROOT = Path(__file__).resolve().parents[1]


class InventoryTests(unittest.TestCase):
    def test_disclosed_sheets_use_the_correct_record_identity(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        interview = (ROOT / "interviews/project-c-event-coordination-interview2.md").read_text(encoding="utf-8")
        links = dict(re.findall(r"\[([^\]]+)\]\((https://docs\.google\.com/spreadsheets/[^)]+)\)", interview))
        expected = {
            "attendees": ("Attendee signals", "signal_id"),
            "budget": ("Budget", "category"),
            "vendors": ("Vendor register", "quote_id"),
            "calendar": ("Calendar constraints", "constraint_id"),
        }
        self.assertEqual(set(contract), set(expected))
        self.assertEqual({sheet["url"] for sheet in contract.values()}, set(links.values()))
        for name, (label, identity) in expected.items():
            with self.subTest(name=name):
                self.assertEqual(contract[name]["url"], links[label])
                self.assertEqual(contract[name]["key"], identity)
                self.assertIn(identity, contract[name]["fields"])
