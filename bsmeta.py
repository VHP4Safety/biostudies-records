"""bsmeta: check and submit VHP4Safety BioStudies PageTab records. Standard library only."""
from __future__ import annotations

import argparse
import csv
import getpass
import io
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path


DRAFT = "[DRAFT]"


def dumps(doc) -> str:
    """The one JSON layout every record uses."""
    return json.dumps(doc, indent=2, separators=(",", " : "), ensure_ascii=False) + "\n"


@dataclass(frozen=True)
class Issue:
    level: str  # "error" | "info"
    code: str
    where: str
    message: str


def _unfilled(value) -> bool:
    s = "" if value is None else str(value).strip()
    return not s or s.startswith(DRAFT)


def strip_unfilled(node):
    """Copy without blank or [DRAFT] attributes and valquals."""
    if isinstance(node, list):
        return [strip_unfilled(x) for x in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for key, val in node.items():
        if key in ("attributes", "valqual"):
            kept = [strip_unfilled(a) for a in val if not _unfilled(a.get("value"))]
            if kept:
                out[key] = kept
        else:
            out[key] = strip_unfilled(val)
    return out


def attrs(node, path="") -> Iterator[tuple[str, dict]]:
    """(section path, attribute) for every attribute, depth first."""
    if isinstance(node, list):
        for x in node:
            yield from attrs(x, path)
    elif isinstance(node, dict):
        here = f"{path}/{node['type']}" if node.get("type") else path
        for a in node.get("attributes", []):
            yield here, a
        for key in ("section", "subsections"):
            if key in node:
                yield from attrs(node[key], here)


def valquals(a: dict) -> dict:
    return {q.get("name"): q.get("value") for q in a.get("valqual", [])}


@dataclass(frozen=True)
class TermRef:
    path: str
    name: str
    value: str | None
    ontology: str | None
    term_id: str | None


def iter_terms(doc) -> Iterator[TermRef]:
    for path, a in attrs(doc):
        vq = valquals(a)
        if "Ontology" in vq or "TermId" in vq:
            yield TermRef(path, a.get("name"), a.get("value"), vq.get("Ontology"), vq.get("TermId"))


def flatten(doc) -> set[tuple]:
    return {(p, a.get("name"), a.get("value"), tuple(sorted(valquals(a).items()))) for p, a in attrs(doc)}


OLS = "https://www.ebi.ac.uk/ols4/api/terms?obo_id="


@dataclass(frozen=True)
class OlsTerm:
    short_form: str
    label: str
    obsolete: bool
    replaced_by: str | None


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "bsmeta", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


@cache
def lookup(term_id: str) -> OlsTerm | None:
    prefix, _, local = term_id.replace(":", "_", 1).partition("_")
    if not local:
        return None
    hits = get_json(OLS + urllib.parse.quote(f"{prefix}:{local}", safe="")).get("_embedded", {}).get("terms", [])
    own = [t for t in hits if t.get("ontology_name") == prefix.lower()] or hits
    time.sleep(0.1)
    if not own:
        return None
    t = own[0]
    return OlsTerm(t["short_form"], t["label"], bool(t.get("is_obsolete")), t.get("term_replaced_by"))


def check_terms(doc, lookup=lookup) -> list[Issue]:
    """Errors: HALF_TAGGED, UNRESOLVED, OBSOLETE, SHORT_FORM. Info: LABEL (local names may differ)."""
    out = []
    for t in iter_terms(doc):
        where = f"{t.path} {t.name}={t.value!r}"
        if not (t.ontology and t.term_id):
            out.append(Issue("error", "HALF_TAGGED", where, f"Ontology={t.ontology!r} TermId={t.term_id!r}"))
            continue
        hit = lookup(t.term_id)
        if hit is None:
            out.append(Issue("error", "UNRESOLVED", where, f"{t.term_id} is not in OLS4"))
            continue
        if hit.obsolete:
            out.append(Issue("error", "OBSOLETE", where, f"{t.term_id} replaced by {hit.replaced_by}"))
        if hit.short_form != t.term_id:
            out.append(Issue("error", "SHORT_FORM", where, f"write {t.term_id} as {hit.short_form}"))
        if (t.value or "").strip().lower() != hit.label.lower():
            out.append(Issue("info", "LABEL", where, f"OLS label is {hit.label!r}"))
    return out


PUBLIC = "https://www.ebi.ac.uk/biostudies/api/v1/studies/"
API = "https://www.ebi.ac.uk/biostudies/submissions/api"


class BioStudiesError(RuntimeError):
    pass


def _request(url: str, data=None, headers=None, timeout=300) -> dict:
    body = json.dumps(data).encode() if data is not None else None
    hdrs = {"Accept": "application/json", "User-Agent": "bsmeta", **(headers or {})}
    if body is not None:
        hdrs["Content-Type"] = "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=hdrs), timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise BioStudiesError(f"{e.code} {url}\n{e.read().decode(errors='replace')[:2000]}") from None


def fetch_live(accno: str) -> dict:
    return _request(PUBLIC + accno)


def login(user: str, password: str) -> str:
    return _request(f"{API}/auth/login", {"login": user, "password": password})["sessid"]


def upload(path: str, session: str) -> None:
    """Stream a file into the user area (curl, so size is not held in memory)."""
    subprocess.run(["curl", "-sSf", "-H", f"X-SESSION-TOKEN: {session}", "-F", f"files=@{path}", f"{API}/files/user"], check=True)


def submit(doc: dict, session: str) -> dict:
    return _request(f"{API}/submissions", doc, {"X-SESSION-TOKEN": session, "Submission_Type": "application/json"})


def diff(authored: dict, live: dict) -> list[str]:
    a, l = flatten(strip_unfilled(authored)), flatten(live)
    return [f"- {r}" for r in sorted(l - a, key=str)] + [f"+ {r}" for r in sorted(a - l, key=str)]


METHODS_INDEX = "https://raw.githubusercontent.com/VHP4Safety/cloud/refs/heads/main/cap/methods_index.json"
METHODS = "https://platform.vhp4safety.nl/methods/"
COMPOUND = "https://compoundcloud.wikibase.cloud/wiki/Item:"


@cache
def method_slugs() -> set[str]:
    return set(get_json(METHODS_INDEX))


def status(url: str) -> int:
    """HTTP status of a HEAD request; 0 when the host cannot be reached or verified."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "bsmeta"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return 0


def check_links(doc, slugs=method_slugs, status=status) -> list[Issue]:
    out, study, used = [], set(), []
    for path, a in attrs(doc):
        name, value, url = a.get("name"), a.get("value"), valquals(a).get("URL")
        where = f"{path} {name}={value!r}"
        if name == "Bioassay" and value:
            if path.count("/") == 2:  # the study section itself, not a subsection
                study.add(value.strip().lower())
            else:
                used.append((where, value.strip().lower()))
        if url and url.startswith(METHODS) and url.removeprefix(METHODS).strip("/") not in slugs():
            out.append(Issue("error", "METHOD_SLUG", where, f"{url} is not in methods_index.json"))
        if name == "CompoundCloudID" and value and status(COMPOUND + value) == 404:
            out.append(Issue("error", "COMPOUND_ID", where, f"{COMPOUND}{value} does not exist"))
        if name == "DOI" and value and status(f"https://doi.org/{value}") >= 400:
            out.append(Issue("error", "DOI", where, f"https://doi.org/{value} does not resolve"))
    out += [Issue("error", "BIOASSAY_REF", w, "no study-level Bioassay with this name") for w, v in used if v not in study]
    return out


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


SESSION_FILE = Path.home() / ".config" / "bsmeta" / "session"


def _load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _session() -> str:
    tok = os.environ.get("BIOSTUDIES_SESSION") or (SESSION_FILE.read_text().strip() if SESSION_FILE.exists() else "")
    if not tok and os.environ.get("BIOSTUDIES_LOGIN") and os.environ.get("BIOSTUDIES_PASSWORD"):
        tok = login(os.environ["BIOSTUDIES_LOGIN"], os.environ["BIOSTUDIES_PASSWORD"])
    if not tok:
        sys.exit("no BioStudies session: run `python3 bsmeta.py login` first")
    return tok


def _emit(level: str, path: str, text: str) -> None:
    """Print a finding; inside GitHub Actions also raise it as an annotation and in the job summary."""
    print(f"{path}: {level.upper()} {text}")
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{'error' if level == 'error' else 'warning'} file={path}::{text}")
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(summary, "a") as f:
                f.write(f"- {level}: `{path}` {text}\n")


def _report(args, check) -> None:
    errors = 0
    for path in args.files:
        for i in check(strip_unfilled(_load(path))):
            if i.level == "error" or args.verbose:
                _emit(i.level, path, f"{i.code} {i.where}: {i.message}")
            errors += i.level == "error"
    print(f"{errors} error(s)")
    sys.exit(1 if errors else 0)


def cmd_fmt(args) -> None:
    bad = 0
    for path in args.files:
        want = dumps(_load(path))
        if Path(path).read_text() == want:
            continue
        if args.check:
            _emit("error", path, "FORMAT not canonical; run `python3 bsmeta.py fmt`")
            bad += 1
        else:
            Path(path).write_text(want)
            print(f"{path}: formatted")
    if args.check:
        print(f"{bad} error(s)")
        sys.exit(1 if bad else 0)


def cmd_check_terms(args) -> None:
    _report(args, check_terms)


def cmd_check_links(args) -> None:
    _report(args, check_links)


def cmd_check_sheet(args) -> None:
    sheet_rows = rows()
    _report(args, lambda doc: check_sheet(doc, sheet_rows))


def cmd_diff(args) -> None:
    stale = 0
    for path in args.files:
        doc = _load(path)
        if "accno" not in doc:
            print(f"{path}: not submitted yet")
            continue
        lines = diff(doc, fetch_live(doc["accno"]))
        if lines:
            _emit("error", path, f"{doc['accno']} differs from BioStudies in {len(lines)} row(s)")
            print(*lines, sep="\n")
        else:
            print(f"{doc['accno']}: up to date")
        stale += bool(lines)
    sys.exit(1 if stale else 0)


def cmd_login(args) -> None:
    tok = login(input("BioStudies login: "), getpass.getpass("BioStudies password: "))
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(tok)
    SESSION_FILE.chmod(0o600)
    print(f"session saved to {SESSION_FILE}")


def cmd_upload(args) -> None:
    session = _session()
    for path in args.files:
        upload(path, session)
        print(f"{path}: uploaded")


def cmd_attach(args) -> None:
    doc = _load(args.record)
    files = doc["section"].get("files") or []
    doc["section"]["files"] = files
    session = _session()
    for path in args.files:
        upload(path, session)
        name = os.path.basename(path)
        if not any(f.get("path") == name for f in files):
            files.append({"path": name, "size": os.path.getsize(path), "attributes": [{"name": "Description", "value": "RO-Crate"}, {"name": "Type", "value": "Dataset"}], "type": "file"})
        print(f"{path}: uploaded and listed in {args.record}")
    Path(args.record).write_text(dumps(doc))
    print(f"next: python3 bsmeta.py submit {args.record}")


def _register(path: str, raw: dict, accno: str) -> Path:
    """First submission: write the accession and its DOI into the record and rename it after the accession."""
    doc = {"accno": accno, **raw}
    top = doc.setdefault("attributes", [])
    doi = next((a for a in top if a.get("name") == "DOI"), None)
    if doi:
        doi["value"] = f"10.6019/{accno}"
    else:
        after = next((n + 1 for n, a in enumerate(top) if a.get("name") == "Title"), len(top))
        top.insert(after, {"name": "DOI", "value": f"10.6019/{accno}"})
    new = Path(path).with_name(f"{accno}.json")
    new.write_text(dumps(doc))
    Path(path).unlink()
    return new


def cmd_submit(args) -> None:
    for path in args.files:
        raw = _load(path)
        doc = strip_unfilled(raw)
        errors = [i for i in check_terms(doc) if i.level == "error"]
        if errors:
            sys.exit(f"{path}: {len(errors)} ontology error(s); run `python3 bsmeta.py check-terms {path}`")
        if args.dry_run:
            print(f"{path}: would submit {doc.get('accno', '<new accession>')}")
            continue
        reply = submit(doc, _session())
        if "accno" in raw:
            print(f"{path}: resubmitted {reply.get('accno')}")
        else:
            print(f"{path}: created {reply['accno']}, moved to {_register(path, raw, reply['accno'])}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python3 bsmeta.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn, help_ in [
        ("check-terms", cmd_check_terms, "resolve every Ontology/TermId against OLS4"),
        ("check-links", cmd_check_links, "method slugs, CompoundCloud ids, DOIs, bioassay cross-references"),
        ("check-sheet", cmd_check_sheet, "RO inventory tracker rows match the records"),
        ("diff", cmd_diff, "compare records with what is live on BioStudies"),
        ("upload", cmd_upload, "upload files (RO-Crate zips) to the BioStudies user area"),
        ("submit", cmd_submit, "(re)submit records; blank and [DRAFT] attributes are dropped"),
    ]:
        s = sub.add_parser(name, help=help_)
        s.add_argument("files", nargs="+")
        s.add_argument("-v", "--verbose", action="store_true")
        s.add_argument("--dry-run", action="store_true")
        s.set_defaults(fn=fn)
    sub.add_parser("login", help="store a BioStudies session token").set_defaults(fn=cmd_login)
    s = sub.add_parser("fmt", help="rewrite records in the canonical JSON layout (--check only reports)")
    s.add_argument("files", nargs="+")
    s.add_argument("--check", action="store_true")
    s.set_defaults(fn=cmd_fmt)
    s = sub.add_parser("attach", help="upload RO-Crate zips to the user area and list them in the record")
    s.add_argument("record")
    s.add_argument("files", nargs="+")
    s.set_defaults(fn=cmd_attach)
    args = p.parse_args(argv)
    try:
        args.fn(args)
    except BioStudiesError as e:
        sys.exit(f"BioStudies error: {e}")



if __name__ == "__main__":
    main()
