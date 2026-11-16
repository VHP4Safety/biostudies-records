"""bsmeta: check and submit VHP4Safety BioStudies PageTab records. Standard library only."""
from __future__ import annotations

import argparse
import csv
import getpass
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
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


def _hollow(node) -> bool:
    """A section left with nothing in it, an author without a name, or an emptied table."""
    if isinstance(node, list):
        return not node
    if not isinstance(node, dict) or "type" not in node or "path" in node or "url" in node:
        return False
    if node["type"].lower() == "author" and not any(a.get("name") == "Name" for a in node.get("attributes", [])):
        return True
    return not any(node.get(k) for k in ("attributes", "subsections", "files", "links"))


def strip_unfilled(node):
    """Copy without blank or [DRAFT] attributes and valquals, and without the sections that leaves empty."""
    if isinstance(node, list):
        return [x for x in map(strip_unfilled, node) if not _hollow(x)]
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


def _body(req, timeout: float, tries: int = 3) -> bytes:
    """The response body, asked for again when the connection fails or stalls: EBI does both now and then. A POST is sent once."""
    for left in range(tries - 1, -1, -1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError:
            raise
        except OSError:
            if not left or getattr(req, "data", None) is not None:
                raise
            time.sleep(2)


def get_json(url: str) -> dict:
    return json.loads(_body(urllib.request.Request(url, headers={"User-Agent": "bsmeta", "Accept": "application/json"}), 30))


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
        return json.loads(_body(urllib.request.Request(url, data=body, headers=hdrs), timeout))
    except urllib.error.HTTPError as e:
        raise BioStudiesError(f"{e.code} {url}\n{e.read().decode(errors='replace')[:2000]}") from None
    except OSError as e:
        raise BioStudiesError(f"{url}: {e}") from None


def fetch_live(accno: str) -> dict:
    return _request(PUBLIC + accno)


def login(user: str, password: str) -> str:
    return _request(f"{API}/auth/login", {"login": user, "password": password})["sessid"]


def upload(path: str, session: str, name: str | None = None) -> None:
    """Stream a file into the user area (curl, so size is not held in memory), optionally under another name."""
    part = f"files=@{path}" + (f";filename={name}" if name else "")
    subprocess.run(["curl", "-sSf", "-H", f"X-SESSION-TOKEN: {session}", "-F", part, f"{API}/files/user"], check=True)


def submit(doc: dict, session: str) -> dict:
    return _request(f"{API}/submissions", doc, {"X-SESSION-TOKEN": session, "Submission_Type": "application/json"})


def diff(authored: dict, live: dict) -> list[str]:
    doc = strip_unfilled(authored)
    a, l = flatten(doc), flatten(live)
    lines = [f"- {r}" for r in sorted(l - a, key=str)] + [f"+ {r}" for r in sorted(a - l, key=str)]
    return lines or ([] if doc == live else ["! the attributes agree, but files, links, sections or nested qualifiers differ"])


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


MODEL = json.loads(Path(__file__).with_name("tracker.json").read_text(encoding="utf-8"))
SHEET = f"https://docs.google.com/spreadsheets/d/{MODEL['sheet']}/export?format=csv&gid={MODEL['gid']}"
ACCESSION = re.compile(r"S-[A-Z]+\d+")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def rows(url: str = SHEET) -> dict[str, dict]:
    """Tracker rows by accession, headers and cells trimmed. The tracker must have every column of the model and one row per accession."""
    reader = csv.DictReader(io.StringIO(_body(url, 30).decode()))
    if missing := [c for c in MODEL["columns"] if c not in {k.strip() for k in reader.fieldnames or []}]:
        if len(missing) == len(MODEL["columns"]):
            sys.exit(f"{url} did not return the tracker: is the sheet still readable by anyone with the link?")
        sys.exit(f"the tracker has no column {', '.join(missing)}")
    out, line = {}, {}
    for n, row in enumerate(reader, 2):
        row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
        if acc := ACCESSION.search(row.get("identifier", "")):
            if acc.group() in out:
                sys.exit(f"{acc.group()} is in rows {line[acc.group()]} and {n} of the tracker")
            out[acc.group()], line[acc.group()] = row, n
    return out


def expected(doc: dict, row: dict, today: str) -> dict:
    """What tracker.json wants in the tracker row of a record; tracker.gs holds the same rules."""
    sec = doc["section"]
    facts = {}
    for attributes in (sec.get("attributes", []), doc.get("attributes", [])):
        found = {}
        for a in attributes:
            found.setdefault(a["name"], []).append(str(a.get("value") or "").strip())
        facts.update(found)
    facts["accno"] = [doc.get("accno") or ""]
    facts["files"] = [f.get("path") for x in sec.get("files") or [] for f in (x if isinstance(x, list) else [x])]
    out = {}
    for column, spec in MODEL["columns"].items():
        if "from" not in spec:
            continue
        values = [spec.get("labels", {}).get(v, v) for v in facts.get(spec["from"], []) if v]
        if values and "present" in spec:
            values = [spec["present"]]
        values = [spec.get("prefix", "") + v for v in dict.fromkeys(values)] or [spec.get("default", "")]
        out[column] = ", ".join(values) if spec.get("many") else values[0]
    embargo, have = row.get("embargoDate", ""), row.get("status", "")
    if embargo and not ISO_DATE.fullmatch(embargo):
        out["status"] = have
    else:
        out["status"] = "Public" if facts["files"] and embargo <= today else "Shared" if have == "Public" else have
    return out


def check_sheet(doc: dict, sheet: dict[str, dict], today: str | None = None, deposits: str | Path | None = None) -> list[Issue]:
    acc = doc.get("accno")
    row = sheet.get(acc)
    if row is None:
        return [Issue("error", "SHEET_ROW", acc, "no row with this accession in the tracker")]
    today = today or date.today().isoformat()
    out = []
    embargo = row.get("embargoDate", "")
    if embargo and not ISO_DATE.fullmatch(embargo):
        out.append(Issue("error", "SHEET_CELL", f"{acc} embargoDate", f"{embargo!r} is not YYYY-MM-DD"))
    elif embargo > today and doc["section"].get("files"):
        out.append(Issue("error", "EMBARGO", acc, f"a file is attached, but the data are under embargo until {embargo}"))
    wanted = expected(doc, row, today)
    for column, want in wanted.items():
        have = row.get(column, "")
        many = MODEL["columns"][column].get("many")
        if (set(have.split(", ")) != set(want.split(", "))) if many else have != want:
            out.append(Issue("error", "SHEET_CELL", f"{acc} {column}", f"sheet {have!r} vs record {want!r}"))
    if deposits is not None:
        out += check_deposit(doc, Path(deposits) / acc, row.get("status", ""), wanted["status"] == "Public")
    return out


def check_deposit(doc: dict, folder: Path, status: str, public: bool) -> list[Issue]:
    """A deposit is a folder with source files and a copy of the record; having one is what Shared means."""
    acc = doc.get("accno")
    held = any(f.is_file() and not f.name.startswith(".") for f in (folder / "source").rglob("*"))
    out = []
    if held and not public and status not in ("Shared", "Private"):
        out.append(Issue("error", "DEPOSIT", acc, f"{folder}/source has files, but the status is {status!r}, not Shared"))
    if not held and not public and status == "Shared":
        out.append(Issue("error", "DEPOSIT", acc, f"the status is Shared, but {folder}/source has no files"))
    if held:
        copy = folder / f"{acc}.biostudies.json"
        if not copy.is_file():
            out.append(Issue("error", "DEPOSIT", acc, f"{folder} has no copy of the record"))
        elif strip_unfilled(_load(copy)) != strip_unfilled(doc):
            out.append(Issue("error", "DEPOSIT", acc, f"{copy} is not the record"))
    return out


SESSION_FILE = Path.home() / ".config" / "bsmeta" / "session"


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
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
            with open(summary, "a", encoding="utf-8") as f:
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
        if Path(path).read_text(encoding="utf-8") == want:
            continue
        if args.check:
            _emit("error", path, "FORMAT not canonical; run `python3 bsmeta.py fmt`")
            bad += 1
        else:
            Path(path).write_text(want, encoding="utf-8")
            print(f"{path}: formatted")
    if args.check:
        print(f"{bad} error(s)")
        sys.exit(1 if bad else 0)


def cmd_check_terms(args) -> None:
    _report(args, check_terms)


def cmd_check_links(args) -> None:
    _report(args, check_links)


def cmd_check_sheet(args) -> None:
    deposits = args.deposits and Path(args.deposits).expanduser()
    if deposits and not deposits.is_dir():
        sys.exit(f"{deposits}: no such folder")
    sheet_rows = rows()
    _report(args, lambda doc: check_sheet(doc, sheet_rows, deposits=deposits))


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
    try:
        tok = login(input("BioStudies login: ").strip(), getpass.getpass("BioStudies password: "))
    except BioStudiesError as e:
        if "401" not in str(e):
            raise
        sys.exit(
            "BioStudies rejected that email and password. Retype them carefully; if the web tool signs you in\n"
            "another way, set a password with 'Forgot password' at https://www.ebi.ac.uk/biostudies/submissions/ and retry."
        )
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
    if "accno" not in doc:
        sys.exit(f"{args.record}: submit the record first; a crate is named after its accession")
    files = doc["section"].get("files") or []
    doc["section"]["files"] = files
    path = args.crate
    name = f"{doc['accno']}_rocrate_{date.today():%Y%m%d}{Path(path).suffix}"
    upload(path, _session(), name)
    entry = next((f for f in files if f.get("path") == name), None)
    if entry is None:
        entry = {"path": name, "size": 0, "attributes": [{"name": "Description", "value": "RO-Crate"}, {"name": "Type", "value": "Dataset"}], "type": "file"}
        files.append(entry)
    entry["size"] = os.path.getsize(path)
    print(f"{path}: uploaded as {name} and listed in {args.record}")
    Path(args.record).write_text(dumps(doc), encoding="utf-8")
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
    new.write_text(dumps(doc), encoding="utf-8")
    Path(path).unlink()
    return new


def embargo_hold(doc: dict, today: str | None = None) -> str | None:
    """Why a record with files may not go public yet: the tracker must hold a readable embargo date that has passed, or none."""
    row = rows().get(doc.get("accno"))
    if row is None:
        return "the tracker has no row for it"
    embargo = row.get("embargoDate", "")
    if embargo and not ISO_DATE.fullmatch(embargo):
        return f"its embargoDate {embargo!r} in the tracker is not YYYY-MM-DD"
    if embargo > (today or date.today().isoformat()):
        return f"a file is attached, but the data are under embargo until {embargo}"
    return None


def cmd_submit(args) -> None:
    for path in args.files:
        raw = _load(path)
        doc = strip_unfilled(raw)
        errors = [i for i in check_terms(doc) if i.level == "error"]
        if errors:
            sys.exit(f"{path}: {len(errors)} ontology error(s); run `python3 bsmeta.py check-terms {path}`")
        if doc["section"].get("files") and (why := embargo_hold(doc)):
            sys.exit(f"{path}: {why}; not submitted")
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
        if fn is cmd_check_sheet:
            s.add_argument("--deposits", metavar="DIR", help="also hold the Shared status to the deposit folders DIR/<accession>")
        s.set_defaults(fn=fn)
    sub.add_parser("login", help="store a BioStudies session token").set_defaults(fn=cmd_login)
    s = sub.add_parser("fmt", help="rewrite records in the canonical JSON layout (--check only reports)")
    s.add_argument("files", nargs="+")
    s.add_argument("--check", action="store_true")
    s.set_defaults(fn=cmd_fmt)
    s = sub.add_parser("attach", help="upload an RO-Crate zip to the user area and list it in the record")
    s.add_argument("record")
    s.add_argument("crate")
    s.set_defaults(fn=cmd_attach)
    args = p.parse_args(argv)
    try:
        args.fn(args)
    except BioStudiesError as e:
        sys.exit(f"BioStudies error: {e}")



if __name__ == "__main__":
    main()
