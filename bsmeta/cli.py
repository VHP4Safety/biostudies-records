"""bsmeta: fmt | check-terms | check-links | check-sheet | diff | login | upload | attach | submit."""
import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from . import biostudies, links, ols, sheet
from .pagetab import dumps, strip_unfilled

SESSION_FILE = Path.home() / ".config" / "bsmeta" / "session"


def _load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _session() -> str:
    tok = os.environ.get("BIOSTUDIES_SESSION") or (SESSION_FILE.read_text().strip() if SESSION_FILE.exists() else "")
    if not tok and os.environ.get("BIOSTUDIES_LOGIN") and os.environ.get("BIOSTUDIES_PASSWORD"):
        tok = biostudies.login(os.environ["BIOSTUDIES_LOGIN"], os.environ["BIOSTUDIES_PASSWORD"])
    if not tok:
        sys.exit("no BioStudies session: run `bsmeta login` first")
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
            _emit("error", path, "FORMAT not canonical; run `bsmeta fmt`")
            bad += 1
        else:
            Path(path).write_text(want)
            print(f"{path}: formatted")
    if args.check:
        print(f"{bad} error(s)")
        sys.exit(1 if bad else 0)


def cmd_check_terms(args) -> None:
    _report(args, ols.check_terms)


def cmd_check_links(args) -> None:
    _report(args, links.check_links)


def cmd_check_sheet(args) -> None:
    rows = sheet.rows()
    _report(args, lambda doc: sheet.check_sheet(doc, rows))


def cmd_diff(args) -> None:
    stale = 0
    for path in args.files:
        doc = _load(path)
        if "accno" not in doc:
            print(f"{path}: not submitted yet")
            continue
        lines = biostudies.diff(doc, biostudies.fetch_live(doc["accno"]))
        if lines:
            _emit("error", path, f"{doc['accno']} differs from BioStudies in {len(lines)} row(s)")
            print(*lines, sep="\n")
        else:
            print(f"{doc['accno']}: up to date")
        stale += bool(lines)
    sys.exit(1 if stale else 0)


def cmd_login(args) -> None:
    tok = biostudies.login(input("BioStudies login: "), getpass.getpass("BioStudies password: "))
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(tok)
    SESSION_FILE.chmod(0o600)
    print(f"session saved to {SESSION_FILE}")


def cmd_upload(args) -> None:
    session = _session()
    for path in args.files:
        biostudies.upload(path, session)
        print(f"{path}: uploaded")


def cmd_attach(args) -> None:
    doc = _load(args.record)
    files = doc["section"].get("files") or []
    doc["section"]["files"] = files
    session = _session()
    for path in args.files:
        biostudies.upload(path, session)
        name = os.path.basename(path)
        if not any(f.get("path") == name for f in files):
            files.append({"path": name, "size": os.path.getsize(path), "attributes": [{"name": "Description", "value": "RO-Crate"}, {"name": "Type", "value": "Dataset"}], "type": "file"})
        print(f"{path}: uploaded and listed in {args.record}")
    Path(args.record).write_text(dumps(doc))
    print(f"next: bsmeta submit {args.record}")


def _register(path: str, raw: dict, accno: str) -> Path:
    """First submission: write the accession and its DOI into the record and rename it after the accession."""
    doc = {"accno": accno, **raw}
    attrs = doc.setdefault("attributes", [])
    doi = next((a for a in attrs if a.get("name") == "DOI"), None)
    if doi:
        doi["value"] = f"10.6019/{accno}"
    else:
        after = next((n + 1 for n, a in enumerate(attrs) if a.get("name") == "Title"), len(attrs))
        attrs.insert(after, {"name": "DOI", "value": f"10.6019/{accno}"})
    new = Path(path).with_name(f"{accno}.json")
    new.write_text(dumps(doc))
    Path(path).unlink()
    return new


def cmd_submit(args) -> None:
    for path in args.files:
        raw = _load(path)
        doc = strip_unfilled(raw)
        errors = [i for i in ols.check_terms(doc) if i.level == "error"]
        if errors:
            sys.exit(f"{path}: {len(errors)} ontology error(s); run `bsmeta check-terms {path}`")
        if args.dry_run:
            print(f"{path}: would submit {doc.get('accno', '<new accession>')}")
            continue
        reply = biostudies.submit(doc, _session())
        if "accno" in raw:
            print(f"{path}: resubmitted {reply.get('accno')}")
        else:
            print(f"{path}: created {reply['accno']}, moved to {_register(path, raw, reply['accno'])}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="bsmeta")
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
    except biostudies.BioStudiesError as e:
        sys.exit(f"BioStudies error: {e}")
