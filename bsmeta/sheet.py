"""Compare records with their rows in the RO inventory tracker (CSV export)."""
import csv
import io
import urllib.request

from .pagetab import Issue

SHEET = "https://docs.google.com/spreadsheets/d/1UfcQIZaGBU11n6jZtI6BmpCBZLy8IbWMBKr5pAqUwq0/export?format=csv&gid=1572306711"
LICENSE = {"cc by 4.0": "CC-BY", "cc-by": "CC-BY", "cc0": "CC0", "cc-by-nc-nd": "CC-BY-NC-ND"}


def rows(url: str = SHEET) -> dict[str, dict]:
    with urllib.request.urlopen(url, timeout=30) as r:
        text = r.read().decode()
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        ident = row.get("identifier", "")
        if "/studies/S-VHPS" in ident:
            out[ident.rsplit("/", 1)[1].strip()] = row
    return out


def expected(doc: dict) -> dict:
    top = {a["name"]: a.get("value") for a in doc.get("attributes", [])}
    sec = doc["section"]
    st = {}
    for a in sec.get("attributes", []):
        st.setdefault(a["name"], []).append(a.get("value"))
    return {
        "title": (top.get("Title") or st.get("Title", [""])[0]).strip(),
        "license": st.get("License", [""])[0],
        "releaseMetadata": top.get("ReleaseDate") or st.get("ReleaseDate", [""])[0],
        "hasROCrate": "Yes" if sec.get("files") else "No",
        "caseStudy": ", ".join(st.get("Case study", [])) or "Other",
        "workflowStep": set(st.get("Process Flow Step", [])),
    }


def check_sheet(doc: dict, sheet: dict[str, dict]) -> list[Issue]:
    acc = doc.get("accno")
    row = sheet.get(acc)
    if row is None:
        return [Issue("error", "SHEET_ROW", acc, "no row with this accession in the tracker")]
    want = expected(doc)
    have = {
        "title": row["title"].strip(),
        "license": LICENSE.get(row["license"].strip().lower(), row["license"].strip()),
        "releaseMetadata": row["releaseMetadata"].strip(),
        "hasROCrate": row["hasROCrate"].strip() or "No",
        "caseStudy": row["caseStudy "].strip(),
        "workflowStep": {s.strip().replace("Indentification", "Identification") for s in row["workflowStep"].split(",") if s.strip()},
    }
    return [Issue("error", "SHEET_CELL", f"{acc} {col}", f"sheet {have[col]!r} vs record {want[col]!r}") for col in want if want[col] != have[col]]
