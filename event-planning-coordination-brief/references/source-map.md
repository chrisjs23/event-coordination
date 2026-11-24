# Fellowship Demo Day source map

Use the six links in the [complete interview export](../../interviews/project-c-event-coordination-interview2.md). The working clock for quotes and holds is 26 August 2026 at 12:00 Asia/Taipei. The times below record a separate, live inspection. These observations establish the mapping for the runner. Each future run must fetch and identify its own evidence.

## Inventory and access decision

All six reads succeeded without credentials. Use Google Sheets' CSV export for the mapped tab. Each workbook's XLSX sheet list contained exactly the tab named in [sheets.json](sheets.json). If tabs change, explicitly select the intended tab and verify its headers before consuming records. The JSON maps every observed header to its meaning, with a key per source. Reordering rows or fields preserves identity. Hold an affected interpretation on ambiguous keys, missing fields or incompatible values.

| Source | Observed UTC on 24 Nov 2026 | Representation and identity | Version or SHA-256 of the bytes inspected |
| --- | --- | --- | --- |
| Event brief and venue note | 02:01:07 | Public Notion page with the interview page ID. The public page's content request returned 25 titled blocks. Locate observations by section, revision and block ID. | EVENT-BRIEF-2026-08-26, VEN-2026-08-26, VEN-2026-08-26-R2, PROG-2026-08-26-R3. Content response SHA-256 `9fab47894809fb622174ad3f085861933b743c077f51551376b490951cb3977f` |
| Attendee Signals | 02:01:07 | CSV, 13 aggregate signals keyed by signal_id. Use observed_at per row and export hash for revision comparisons. | `36bf8ee344dc115a7eacc3b80d1221c4f47e7fb60512cc25091f81fb4a5a1201` |
| Budget | 02:01:08 | CSV, 7 categories keyed by category within the revision. | budget-2026-08-26 · `a7c02fca7e4d703c8e6cc6cb9b2e2b119e5d220a23de05fb07f4c75b888361f0` |
| Vendor Quotes | 02:01:08 | CSV, 10 quotes keyed by quote_id. Identify the export by hash and retrieval time. | `9d0174ec53a01f6d167aa376beab87486d960a6b77aa3705372c1063ffb0b4b4` |
| Calendar Constraints | 02:01:07 | CSV, 8 records keyed by constraint_id. | calendar-2026-08-26 · `1fc9c1cb0a3da2710fac415de1b603d2def09e5d55986c2793d743cabdfa0842` |
| Official 4F floor plan | 02:01:10 | TICC PDF, 522,512 bytes, one page. Locate observations by page and named region. | `8805ab527b7bb202a70534120ed4037dbde633301f1935e80bd04f12a7c70367` |

The Notion share link and the interview link identify the same page. The static HTML can contain only the app shell. In a browser open the [public brief](https://private-pecorino-70e.notion.site/Project-3-Event-Coordination-Event-Brief-3ba0b700541e81d0af55dc1a8f49f5af). For the inspected revision the site's read-only page load used POST to its own `/api/v3/loadPageChunk` with pageId `3ba0b700-541e-81d0-af55-dc1a8f49f5af`, limit 100, cursor `{"stack":[]}`, chunkNumber 0 and verticalColumns false. This is a site implementation detail. Verify actual section text and completeness when choosing the runtime route. Response metadata can change independently of the authored blocks. A heading or HTTP success alone is insufficient.

## Interpretation boundaries

- **Headcount.** SIG-001/002 measure registered groups. SIG-003/004 count required staff and speakers. SIG-005 is a walk-in forecast. SIG-006 through SIG-013 measure support or meal demand with their own units. Adding these latter signals to attendance would double-count people without evidence. Preserve confidence and observation dates. The forecast buffer is a later planning decision.
- **Privacy.** Use aggregate demand, coordination state and responsible teams. Operations holds individual contacts and medical details. Review any new fields before retaining extracts or exposing them in drafts. The structural checker reads locally and reports counts and errors without printing row contents.
- **Costs.** Compare proposed spending and existing commitments with each category's approval limit and the brief's overall ceiling. Planned allocations provide a comparison baseline. Communications and contingency appear as allowances. Read package scope, validity, date, notes and prerequisites together. In particular, Q-008 requires further confirmation, and Q-010's capacity applies to the quiet room. Use the dated exercise coordination note for the scope of the fictional venue and supplier arrangements.
- **Authority.** The brief and the later readiness and programme clarifications describe the exercise scenario. Category owners review spending and Operations reviews the whole plan. Preserve the actor, revision, scope and time of an actual approval. A vendor hold provides availability evidence only.

### Calendar reconciliation

All eight records currently use +08:00. Keep both endpoints, priority and qualifiers with each ID.

| ID | Owner and priority | Meaning in the plan |
| --- | --- | --- |
| CAL-001 | Operations, hard | Preferred event window, 17 Oct 09:30–17:00. |
| CAL-002 | Operations, soft | Fallback window, 24 Oct 09:30–17:00. Evaluate its dependencies separately. |
| CAL-003 | TICC, hard | 17 Oct venue hold 07:30–18:30, expires 5 Sep. |
| CAL-004 | Programme, hard | Keynote 17 Oct 10:00–11:00, unavailable on fallback date. |
| CAL-005 | Operations, hard | Plan and budget decision deadline, 4 Sep 17:00. A point in time. |
| CAL-006 | Learner Experience, hard | Accessibility walkthrough 25 Sep 14:00–16:00, subject to venue confirmation first. |
| CAL-007 | Programme, soft | Rehearsal 16 Oct 15:00–18:00, remote backup acceptable. |
| CAL-008 | TICC, hard | Teardown 17 Oct 17:00–18:30. All vendors clear by 18:30. |

### Floor-plan observations

Open [TICC's 4F plan](https://www.ticc.com.tw/wSite/public/Attachment/f1710485827023.pdf), page 1, with the legend on the left. The right half shows blue wheelchair-area symbols in the seating area beside the Plenary Hall Stage. The lower centre near JOY shows accessible-elevator symbols. The lower restroom cluster beside stairs A/B shows the accessible-restroom symbol. The V.I.P. ROOM is labelled in the lower-left wing. Use these regions for spatial references. Use the exercise venue note for the six-place allocation, quiet-room designation and route readiness. Current elevator operation, clearance and room setup require separate operational evidence.

## Independent stage 1 verification

From the repository root with Python 3, run the offline tests. They verify the link-to-key mapping against the interview and exercise the CSV checker with synthetic data, including reordered fields, extra columns, ambiguous identities and malformed rows.

```sh
python3 -B -m unittest discover -s tests -p 'test_source*.py' -v
```

To repeat the live sheet check, use Python 3 with HTTPS access to Google and its export hosts. Run the following from the same directory. Downloads stay in a temporary directory.

```sh
python3 - <<'PY'
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen

contract = json.loads(Path('event-planning-coordination-brief/references/sheets.json').read_text())
with tempfile.TemporaryDirectory() as tmp:
    for name, sheet in contract.items():
        with urlopen(sheet['url'] + '/export?format=csv', timeout=30) as response:
            data = response.read()
        path = Path(tmp) / (name + '.csv')
        path.write_bytes(data)
        print(name, hashlib.sha256(data).hexdigest(), flush=True)
        subprocess.run([sys.executable, 'tests/check_source_csv.py', name, str(path)], check=True)
PY
```

At the inspected revision, expect successful exits and counts of 13, 7, 10 and 8 in inventory order. Compare digests with the inventory. A changed digest calls for inspecting the current export, even if it has the same headers and record count. The checker tests structure and identities only. Business value validation and evidence capture belong to stage 3.

For manual verification, open each mapped sheet and confirm its tab and key column. Compare CAL-001 through CAL-008 with the table above, including the deadline and conditional walkthrough. Open the public brief and find the four revision markers listed in the inventory. Open the official PDF and match the named regions to the legend. To compare the exact PDF bytes on Linux with curl and sha256sum, run:

```sh
(set -eu; pdf=$(mktemp); trap 'rm -f "$pdf"' EXIT; curl -fsSL 'https://www.ticc.com.tw/wSite/public/Attachment/f1710485827023.pdf' -o "$pdf"; sha256sum "$pdf")
```

The initial sandboxed network attempt failed DNS resolution. All six reads subsequently succeeded with outbound HTTPS. Historical digests identify this inspection, while a future run must record the actual new outcome if a host, page or tab changes.
