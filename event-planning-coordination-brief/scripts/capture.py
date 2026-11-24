"""Capture the disclosed sources as inspectable, permitted evidence."""

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from records import SourceError, permitted_extract, read_sheet, validate_sheet
from snapshots import sha256

BRIEF_URL = "https://private-pecorino-70e.notion.site/Project-3-Event-Coordination-Event-Brief-3ba0b700541e81d0af55dc1a8f49f5af"
PAGE_ID = "3ba0b700-541e-81d0-af55-dc1a8f49f5af"
BRIEF_API = "https://private-pecorino-70e.notion.site/api/v3/loadPageChunk"
INTERVIEW = "interviews/project-c-event-coordination-interview2.md"
ROLES = {"attendees": "attendee-signals", "budget": "budget",
         "vendors": "vendor-record", "calendar": "calendar"}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def json_bytes(value):
    def date_string(obj):
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        raise TypeError("unsupported evidence value")
    return (json.dumps(value, ensure_ascii=False, indent=2, default=date_string) + "\n").encode()


def fetch_public(url, body=None):
    """One bounded request, with no credentials and no automatic retries."""
    request = Request(url, data=json.dumps(body).encode() if body else None,
                      headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json",
                               "Referer": BRIEF_URL})
    try:
        with urlopen(request, timeout=30) as response:
            data = response.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024:
                raise SourceError("source exceeds the 8 MiB capture limit")
            metadata = {"response_url": response.geturl(),
                        "etag": response.headers.get("ETag"),
                        "last_modified": response.headers.get("Last-Modified")}
            return data, response.headers.get_content_type(), metadata
    except HTTPError as exc:
        raise SourceError(f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SourceError("network retrieval failed") from exc


def brief_blocks(data):
    """Walk the page's child order, requiring a complete response."""
    try:
        document = json.loads(data)
        if document.get("cursor", {}).get("stack") != []:
            raise SourceError("brief response has unconsumed pagination")
        entries = document["recordMap"]["block"]
        blocks, visited = [], set()

        def visit(block_id):
            if block_id in visited:
                raise SourceError("brief has a duplicate or cyclic block reference")
            visited.add(block_id)
            value = entries[block_id]["value"]
            value = value.get("value", value)
            if value.get("type") not in {"page", "header", "sub_header", "sub_sub_header", "text"}:
                raise SourceError("brief contains an unsupported block type")
            text = "".join(piece[0] for piece in value.get("properties", {}).get("title", []))
            if text:
                blocks.append({"id": block_id, "text": text, "type": value["type"],
                               "last_edited_time": value.get("last_edited_time")})
            for child in value.get("content", []):
                visit(child)
        visit(PAGE_ID)
        if len(blocks) < 2 or not any(b["text"] == "Event brief" for b in blocks):
            raise SourceError("brief sections are missing")
        return blocks
    except SourceError:
        raise
    except (ValueError, KeyError, TypeError, IndexError, RecursionError) as exc:
        raise SourceError("invalid or incomplete brief content") from exc


def _source(name, role, locator):
    return {"id": "source:" + name, "summary": "Captured " + name, "evidence_ids": [],
            "source_role": role, "locator": locator, "retrieved_at": utcnow(),
            "retrieval_status": "unverified", "content_type": "application/octet-stream",
            "version_metadata": {}, "content_hash": None, "local_reference": None,
            "observations": []}


def _save(output, source, filename, content):
    path = output / "snapshots" / "evidence" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    source["local_reference"] = path.relative_to(output).as_posix()
    source["content_hash"] = sha256(content)


def capture_sources(root, output, fetch=fetch_public):
    """Return source records and validated in-memory rows; never fall back to old captures."""
    root, output = Path(root), Path(output)
    sheets = json.loads((root / "event-planning-coordination-brief/references/sheets.json").read_text())
    venue = json.loads((root / "event-planning-coordination-brief/references/venue-evidence.json").read_text())
    sources, rows, blocks = [], {}, []

    brief = _source("brief", "event-brief", BRIEF_URL)
    sources.append(brief)
    try:
        body = dict(pageId=PAGE_ID, limit=100, cursor={"stack": []},
                    chunkNumber=0, verticalColumns=False)
        data, brief["content_type"], metadata = fetch(BRIEF_API, body)
        brief["version_metadata"] = {**metadata, "response_sha256": sha256(data)}
        blocks = brief_blocks(data)
        _save(output, brief, "brief.json", json_bytes({"page_id": PAGE_ID, "blocks": blocks}))
        brief["version_metadata"]["representation"] = "permitted ordered block extract"
        brief["version_metadata"]["revisions"] = [
            b["text"] for b in blocks if b["text"].startswith(
                ("Brief version:", "Record:", "Coordination clarification:", "Programme clarification:"))]
        brief["observations"] = [
            {"id": "obs:brief:" + b["id"], "summary": b["text"],
             "locator": {"kind": "section", "value": "block " + b["id"]}} for b in blocks]
        brief["retrieval_status"] = "retrieved"
    except SourceError as exc:
        brief["retrieval_status"] = "invalid" if brief["version_metadata"] else "unavailable"
        brief["version_metadata"]["error"] = str(exc)

    for name, spec in sheets.items():
        source = _source(name, ROLES[name], spec["url"])
        sources.append(source)
        url = spec["url"] + "/gviz/tq?" + urlencode({"tqx": "out:csv", "sheet": spec["tab"]})
        source["version_metadata"]["request_url"] = url
        received = False
        try:
            data, source["content_type"], metadata = fetch(url)
            received = True
            source["version_metadata"].update(metadata)
            source["version_metadata"]["response_sha256"] = sha256(data)
            # Retain known aggregate columns even when structural/value validation fails.
            extract = permitted_extract(data, spec)
            _save(output, source, name + ".csv", extract)
            parsed = read_sheet(data, spec)
            validated = validate_sheet(name, parsed["records"])
            rows[name] = validated
            source["version_metadata"].update(
                representation="permitted CSV columns in source order; original values retained",
                tab=spec["tab"], columns=parsed["columns"], ignored_columns=parsed["ignored_columns"])
            if name in {"calendar", "budget"}:
                source["version_metadata"]["record_version"] = validated[0]["record_version"]
            source["observations"] = [
                {"id": "obs:" + name + ":" + row[spec["key"]].strip(),
                 "summary": "Aggregate record " + row[spec["key"]].strip(),
                 "locator": {"kind": "cell-range",
                             "value": f"{spec['tab']}, row {row['_row']}, fields {', '.join(parsed['columns'])}"},
                 "data": row} for row in validated]
            source["retrieval_status"] = "retrieved"
        except SourceError as exc:
            source["retrieval_status"] = "invalid" if received else "unavailable"
            source["version_metadata"]["error"] = str(exc)

    floor = _source("floorplan", "floor-plan-or-image", venue["url"])
    sources.append(floor)
    try:
        data, floor["content_type"], metadata = fetch(venue["url"])
        floor["version_metadata"] = {**metadata, "response_sha256": sha256(data)}
        if not data.startswith(b"%PDF-"):
            raise SourceError("floor plan response is not a PDF")
        _save(output, floor, "floorplan.pdf", data)
        if sha256(data) == venue["reviewed_sha256"]:
            floor["retrieval_status"] = "retrieved"
            floor["version_metadata"]["review_basis"] = venue["review_basis"]
            floor["observations"] = venue["observations"]
        else:
            floor["retrieval_status"] = "unverified"
            floor["version_metadata"]["error"] = "PDF changed; visual review required before spatial claims"
    except SourceError as exc:
        floor["retrieval_status"] = "invalid" if floor["version_metadata"] else "unavailable"
        floor["version_metadata"]["error"] = str(exc)

    interview = _source("interview", "other", INTERVIEW)
    sources.append(interview)
    try:
        # Only the planning policies needed here enter general run evidence.
        text = (root / INTERVIEW).read_text(encoding="utf-8")
        policies = {
            "supplier-preference": "using familiar suppliers",
            "buffer-policy": "standard policy for how many extra",
            "approval-order": "and then Operations gives the final approval",
        }
        paragraphs = []
        for marker in policies.values():
            matches = [p for p in text.split("\n\n") if marker in p]
            if len(matches) != 1:
                raise SourceError("interview planning policy passages need review")
            paragraphs.append(matches[0])
        if len(paragraphs) != len(policies):
            raise SourceError("interview planning policy passages need review")
        _save(output, interview, "interview-policies.txt", "\n\n".join(paragraphs).encode())
        interview["content_type"] = "text/plain"
        interview["version_metadata"] = {"representation": "permitted planning-policy paragraphs",
                                          "response_sha256": sha256(text.encode())}
        interview["observations"] = [
            {"id": "obs:interview:" + name, "summary": passage,
             "locator": {"kind": "section", "value": passage[:70]}}
            for name, passage in zip(policies, paragraphs)]
        interview["retrieval_status"] = "retrieved"
    except (OSError, SourceError, UnicodeError):
        interview["retrieval_status"] = "unavailable"
        interview["version_metadata"]["error"] = "interview policy extract unavailable"
    return sources, rows, blocks
