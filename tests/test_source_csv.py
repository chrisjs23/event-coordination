import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import check_source_csv


class SourceCsvTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.contract_path = self.root / "sheets.json"
        self.contract_path.write_text(
            json.dumps({
                "attendees": {
                    "fields": {"Attendee ID": "identity", "Name": "name"},
                    "key": "Attendee ID",
                    "ignored_metadata": "ok",
                }
            }),
            encoding="utf-8",
        )
        self.contract_patch = patch.object(check_source_csv, "CONTRACT_PATH", self.contract_path)
        self.contract_patch.start()
        self.addCleanup(self.contract_patch.stop)

    def write_csv(self, content):
        path = self.root / "source.csv"
        path.write_text(content, encoding="utf-8-sig")
        return path

    def test_permuted_headers_records_and_extra_column_are_valid(self):
        path = self.write_csv("Name,Extra,Attendee ID\nAda,x,A1\nLin,y,A2\n")
        self.assertEqual(check_source_csv.validate("attendees", path), 2)

    def test_missing_required_header_is_rejected(self):
        path = self.write_csv("Attendee ID,Extra\nA1,x\n")
        with self.assertRaisesRegex(check_source_csv.ContractError, "missing required"):
            check_source_csv.validate("attendees", path)

    def test_duplicate_header_is_rejected(self):
        path = self.write_csv("Attendee ID,Attendee ID,Name\nA1,A2,Ada\n")
        with self.assertRaisesRegex(check_source_csv.ContractError, "duplicate column"):
            check_source_csv.validate("attendees", path)

    def test_blank_identity_is_rejected(self):
        path = self.write_csv("Attendee ID,Name\n  ,Ada\n")
        with self.assertRaisesRegex(check_source_csv.ContractError, "blank identity"):
            check_source_csv.validate("attendees", path)

    def test_duplicate_identity_is_rejected(self):
        path = self.write_csv("Attendee ID,Name\nA1,Ada\nA1,Lin\n")
        with self.assertRaisesRegex(check_source_csv.ContractError, "duplicate identity"):
            check_source_csv.validate("attendees", path)

    def test_malformed_row_width_is_rejected(self):
        path = self.write_csv("Attendee ID,Name\nA1,Ada,extra\n")
        with self.assertRaisesRegex(check_source_csv.ContractError, "malformed width"):
            check_source_csv.validate("attendees", path)

    def test_empty_records_are_rejected(self):
        path = self.write_csv("Attendee ID,Name\n")
        with self.assertRaisesRegex(check_source_csv.ContractError, "no records"):
            check_source_csv.validate("attendees", path)


if __name__ == "__main__":
    unittest.main()
