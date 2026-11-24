import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "event-planning-coordination-brief" / "scripts"))
import records


CONTRACT = json.loads((Path(__file__).resolve().parents[1] / "event-planning-coordination-brief/references/sheets.json").read_text())


class ReadSheetTests(unittest.TestCase):
    def test_bom_permuted_header_and_extras_preserve_only_required_extract(self):
        spec = {"fields": {"id": "", "name": ""}, "key": "id"}
        result = records.read_sheet("\ufeffname,extra,id\nAda,private,A1\n".encode(), spec)
        self.assertEqual(result["columns"], ["name", "id"])
        self.assertEqual(result["ignored_columns"], 1)
        self.assertEqual(result["records"], [{"name": "Ada", "id": "A1", "_row": 2}])
        self.assertEqual(result["extract"], b"name,id\nAda,A1\n")

    def test_duplicate_and_blank_keys_rejected(self):
        spec = {"fields": {"id": "", "x": ""}, "key": "id"}
        for data, message in ((b"id,x\n,ok\n", "blank identity"), (b"id,x\na,1\na,2\n", "duplicate identity")):
            with self.subTest(message=message), self.assertRaisesRegex(records.SourceError, message):
                records.read_sheet(data, spec)

    def test_invalid_structure_rejected(self):
        spec = {"fields": {"id": "", "x": ""}, "key": "id"}
        cases = [(b"id,id,x\na,b,c\n", "duplicate column"), (b"id\na\n", "missing required"), (b"id,x\na,b,c\n", "malformed width")]
        for data, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(records.SourceError, message):
                records.read_sheet(data, spec)

    def test_permitted_extract_survives_duplicate_and_missing_headers_without_extras(self):
        spec = {"fields": {"id": "", "x": ""}, "key": "id"}
        duplicate = b"id,private,id,x\na,SECRET,b,c\n"
        extract = records.permitted_extract(duplicate, spec)
        self.assertEqual(extract, b"id,id,x\na,b,c\n")
        self.assertNotIn(b"private", extract)
        self.assertNotIn(b"SECRET", extract)
        with self.assertRaisesRegex(records.SourceError, "duplicate column"):
            records.read_sheet(duplicate, spec)

        missing = b"id,private\na,SECRET\n"
        extract = records.permitted_extract(missing, spec)
        self.assertEqual(extract, b"id\na\n")
        self.assertNotIn(b"private", extract)
        self.assertNotIn(b"SECRET", extract)
        with self.assertRaisesRegex(records.SourceError, "missing required"):
            records.read_sheet(missing, spec)


class ValueTests(unittest.TestCase):
    def check(self, name, header, row):
        structural = records.read_sheet((header + "\n" + row + "\n").encode(), CONTRACT[name])
        return records.validate_sheet(name, structural["records"])

    def test_typed_attendee_and_bad_amount_date_and_meaning(self):
        result = self.check("attendees", "signal_id,source,segment,signal,value,unit,observed_at,confidence", "s1,form,fellows,registered_attendees,12,people,2026-08-01,high")
        self.assertEqual(result[0]["value"], 12)
        self.assertEqual(str(result[0]["observed_at"]), "2026-08-01")
        for row in ("s1,form,fellows,registered_attendees,-1,people,2026-08-01,high", "s1,form,fellows,registered_attendees,1,people,2026-02-30,high", "s1,form,fellows,unknown,1,people,2026-08-01,high"):
            with self.subTest(row=row), self.assertRaises(records.SourceError):
                self.check("attendees", "signal_id,source,segment,signal,value,unit,observed_at,confidence", row)

    def test_calendar_deadline_point_allowed_and_other_point_rejected(self):
        header = "constraint_id,owner,constraint_type,start_at,end_at,priority,notes,record_version"
        good = "c1,Ops,decision_deadline,2026-09-04T17:00:00+08:00,2026-09-04T17:00:00+08:00,hard,review,v1"
        self.assertEqual(self.check("calendar", header, good)[0]["start_at"].utcoffset().total_seconds(), 28800)
        bad = good.replace("decision_deadline", "venue_hold")
        with self.assertRaisesRegex(records.SourceError, "invalid interval"):
            self.check("calendar", header, bad)

    def test_mixed_versions_and_expired_quote(self):
        budget_header = "category,planned_amount_twd,approval_limit_twd,committed_amount_twd,owner,record_version"
        data = (budget_header + "\na,1,2,3,Ops,v1\nb,1,2,3,Ops,v2\n").encode()
        with self.assertRaisesRegex(records.SourceError, "mixed record versions"):
            records.validate_sheet("budget", records.read_sheet(data, CONTRACT["budget"])["records"])
        vendor_header = "quote_id,vendor,category,option,quote_amount_twd,capacity,available_date,valid_until,status,notes"
        expired = "q1,V,C,O,0,1,2026-10-17,2026-01-01,conditional,expired"
        self.assertEqual(self.check("vendors", vendor_header, expired)[0]["quote_amount_twd"], 0)


if __name__ == "__main__":
    unittest.main()
