"""bsmeta: check-terms | check-links | diff | login | upload | submit."""
import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from . import biostudies, links, ols
from .pagetab import strip_unfilled

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


def _report(args, check) -> None:
    errors = 0
    for path in args.files:
        for i in check(strip_unfilled(_load(path))):
            if i.level == "error" or args.verbose:
                print(f"{path}: {i.level.upper()} {i.code} {i.where}: {i.message}")
            errors += i.level == "error"
    print(f"{errors} error(s)")
    sys.exit(1 if errors else 0)


def cmd_check_terms(args) -> None:
    _report(args, ols.check_terms)


def cmd_check_links(args) -> None:
    _report(args, links.check_links)


def cmd_diff(args) -> None:
    stale = 0
    for path in args.files:
        doc = _load(path)
        if "accno" not in doc:
            print(f"{path}: not submitted yet")
            continue
        lines = biostudies.diff(doc, biostudies.fetch_live(doc["accno"]))
        print(f"{doc['accno']}: {'up to date' if not lines else f'{len(lines)} difference(s)'}", *lines, sep="\n")
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


def cmd_submit(args) -> None:
    for path in args.files:
        doc = strip_unfilled(_load(path))
        errors = [i for i in ols.check_terms(doc) if i.level == "error"]
        if errors:
            sys.exit(f"{path}: {len(errors)} ontology error(s); run `bsmeta check-terms {path}`")
        if args.dry_run:
            print(f"{path}: would submit {doc.get('accno', '<new accession>')}")
            continue
        reply = biostudies.submit(doc, _session())
        print(f"{path}: submitted as {reply.get('accno')}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="bsmeta")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn, help_ in [
        ("check-terms", cmd_check_terms, "resolve every Ontology/TermId against OLS4"),
        ("check-links", cmd_check_links, "method slugs, CompoundCloud ids, DOIs, bioassay cross-references"),
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
    args = p.parse_args(argv)
    try:
        args.fn(args)
    except biostudies.BioStudiesError as e:
        sys.exit(f"BioStudies error: {e}")
