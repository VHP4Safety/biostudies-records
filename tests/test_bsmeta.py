import argparse
import io
import json
import shutil
import subprocess
import urllib.error
from pathlib import Path

import pytest

import bsmeta
from bsmeta import OlsTerm, check_links, check_sheet, check_terms, diff, expected, iter_terms, strip_unfilled

DOC = {
    "type": "submission",
    "accno": "S-X",
    "attributes": [{"name": "ReleaseDate", "value": "[DRAFT]"}, {"name": "AttachTo", "value": "VHP4Safety"}],
    "section": {
        "type": "Study",
        "attributes": [
            {"name": "Organ", "value": "Ovary", "valqual": [{"name": "Ontology", "value": "UBERON"}, {"name": "TermId", "value": "UBERON_0000992"}]},
            {"name": "Bioassay", "value": "", "valqual": [{"name": "Ontology", "value": "BAO"}, {"name": "TermId", "value": ""}]},
            {"name": "Exposure type", "value": "continuous", "valqual": [{"name": "Ontology", "value": "EXO"}, {"name": "TermId", "value": "EXO_0000167"}]},
            {
                "name": "Bioassay",
                "value": "RNA-seq assay",
                "valqual": [
                    {"name": "Ontology", "value": "OBI"},
                    {"name": "TermId", "value": "OBI:0001271"},
                    {"name": "URL", "value": "https://platform.vhp4safety.nl/methods/rna_seq"},
                ],
            },
        ],
        "subsections": [
            {
                "type": "Exposure information",
                "attributes": [{"name": "Bioassay", "value": "rna-seq assay"}, {"name": "Bioassay", "value": "Missing assay"}],
            }
        ],
    },
}
FAKE = {
    "UBERON_0000992": OlsTerm("UBERON_0000992", "ovary", False, None),
    "OBI:0001271": OlsTerm("OBI_0001271", "transcription profiling by RNA sequencing assay", False, None),
}.get


def test_strip_unfilled_drops_blank_and_draft():
    s = strip_unfilled(DOC)
    assert [a["name"] for a in s["attributes"]] == ["AttachTo"]
    assert [a["name"] for a in s["section"]["attributes"]] == ["Organ", "Exposure type", "Bioassay"]
    assert DOC["section"]["attributes"][1]["value"] == ""


def test_strip_unfilled_drops_the_sections_it_empties():
    doc = {
        "accno": "S-X",
        "section": {
            "type": "Study",
            "attributes": [{"name": "Title", "value": "T"}],
            "subsections": [
                {"type": "Detection instrument", "attributes": [{"name": "Name", "value": ""}]},
                {"type": "author", "attributes": [{"name": "affiliation", "value": "o1", "reference": True}]},
                [{"type": "Software", "attributes": [{"name": "Name", "value": "[DRAFT]"}]}],
                {"type": "Funding", "attributes": [{"name": "Agency", "value": "NWO"}]},
                {"type": "Exposure", "attributes": [{"name": "Route", "value": "oral"}], "subsections": [{"type": "Regimen", "attributes": [{"name": "Dose", "value": ""}]}]},
            ],
            "files": [{"path": "a.zip", "type": "file"}],
            "links": [{"url": "https://example.org"}],
        },
    }
    out = strip_unfilled(doc)["section"]
    assert out["subsections"] == [
        {"type": "Funding", "attributes": [{"name": "Agency", "value": "NWO"}]},
        {"type": "Exposure", "attributes": [{"name": "Route", "value": "oral"}]},
    ]
    assert out["files"] == doc["section"]["files"] and out["links"] == doc["section"]["links"]


def test_iter_terms():
    t = next(iter_terms(DOC))
    assert (t.path, t.name, t.ontology, t.term_id) == ("/submission/Study", "Organ", "UBERON", "UBERON_0000992")


def test_check_terms_codes():
    issues = check_terms(strip_unfilled(DOC), lookup=FAKE)
    assert {(i.code, i.level) for i in issues} == {("UNRESOLVED", "error"), ("SHORT_FORM", "error"), ("LABEL", "info")}


def test_check_links_cross_refs_and_slugs():
    issues = check_links(strip_unfilled(DOC), slugs=lambda: {"rna_seq"}, status=lambda url: 200)
    assert [i.code for i in issues] == ["BIOASSAY_REF"]
    assert "Missing assay" in issues[0].where


def test_diff_lists_changed_rows_only():
    live = strip_unfilled(DOC)
    assert diff(DOC, live) == []
    live["section"]["attributes"][0]["value"] = "Organ"
    out = diff(DOC, live)
    assert len(out) == 2 and out[0].startswith("- ") and out[1].startswith("+ ")


def test_diff_sees_what_is_not_an_attribute():
    live = strip_unfilled(DOC)
    linked = {**DOC, "section": {**DOC["section"], "links": [{"url": "https://example.org"}]}}
    assert diff(linked, live) and not diff(DOC, live)


def refused(calls, body=b'{"ok": true}'):
    def urlopen(req, timeout=None):
        calls.append(req)
        if len(calls) < 3:
            raise urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))
        return io.BytesIO(body)
    return urlopen


def test_a_read_retries_a_refused_connection(monkeypatch):
    monkeypatch.setattr(bsmeta.time, "sleep", lambda seconds: None)
    for read in (lambda: bsmeta.get_json("https://example.org/a"), lambda: bsmeta.fetch_live("S-X")):
        calls = []
        monkeypatch.setattr(bsmeta.urllib.request, "urlopen", refused(calls))
        assert read() == {"ok": True} and len(calls) == 3
    calls = []
    monkeypatch.setattr(bsmeta.urllib.request, "urlopen", refused(calls, ",".join(HEAD).encode() + b"\n"))
    assert bsmeta.rows("https://example.org/tracker.csv") == {} and len(calls) == 3


def test_a_lost_connection_ends_a_command_with_a_message(tmp_path, monkeypatch):
    def lost():
        raise urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))
    monkeypatch.setattr(bsmeta, "tracker", lost)
    f = tmp_path / "S-VHPS99.json"
    f.write_text(json.dumps(TRACKED))
    with pytest.raises(SystemExit) as e:
        bsmeta.main(["check-sheet", str(f)])
    assert "Connection refused" in str(e.value.code)


def test_a_read_retries_a_timeout_while_reading(monkeypatch):
    class Stalled(io.BytesIO):
        def read(self, *args):
            raise TimeoutError("The read operation timed out")
    replies = [Stalled(), io.BytesIO(b'{"ok": true}')]
    monkeypatch.setattr(bsmeta.urllib.request, "urlopen", lambda req, timeout=None: replies.pop(0))
    monkeypatch.setattr(bsmeta.time, "sleep", lambda seconds: None)
    assert bsmeta.get_json("https://example.org/a") == {"ok": True}


def test_a_submission_is_sent_once(monkeypatch):
    calls = []
    monkeypatch.setattr(bsmeta.urllib.request, "urlopen", refused(calls))
    monkeypatch.setattr(bsmeta.time, "sleep", lambda seconds: None)
    with pytest.raises(bsmeta.BioStudiesError):
        bsmeta.submit({"accno": "S-X"}, "tok")
    assert len(calls) == 1


def test_report_annotates_github_actions(monkeypatch, capsys, tmp_path):
    import argparse
    import json

    import pytest


    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    f = tmp_path / "r.json"
    f.write_text(json.dumps(DOC))
    with pytest.raises(SystemExit) as e:
        bsmeta._report(argparse.Namespace(files=[str(f)], verbose=False), lambda d: check_terms(d, lookup=FAKE))
    assert e.value.code == 1
    assert f"::error file={f}::UNRESOLVED" in capsys.readouterr().out
    assert "UNRESOLVED" in (tmp_path / "summary.md").read_text()


def test_status_unreachable_is_unknown():
    from bsmeta import status

    assert status("https://localhost:1") == 0


def test_fmt_check_flags_and_fmt_rewrites(tmp_path, capsys):
    import argparse
    import json

    import pytest

    from bsmeta import dumps

    f = tmp_path / "r.json"
    f.write_text(json.dumps(DOC, indent=4))
    with pytest.raises(SystemExit) as e:
        bsmeta.cmd_fmt(argparse.Namespace(files=[str(f)], check=True))
    assert e.value.code == 1 and "FORMAT" in capsys.readouterr().out
    bsmeta.cmd_fmt(argparse.Namespace(files=[str(f)], check=False))
    assert f.read_text() == dumps(DOC)
    with pytest.raises(SystemExit) as e:
        bsmeta.cmd_fmt(argparse.Namespace(files=[str(f)], check=True))
    assert e.value.code == 0


def test_attach_uploads_under_the_naming_convention(tmp_path, monkeypatch):
    import argparse
    import json
    from datetime import date

    uploads = []
    monkeypatch.setattr(bsmeta, "upload", lambda path, session, name=None: uploads.append((path, name)))
    monkeypatch.setattr(bsmeta, "_session", lambda: "tok")
    rec = tmp_path / "S-X.json"
    rec.write_text(json.dumps(DOC))
    crate = tmp_path / "whatever_the_builder_called_it.zip"
    crate.write_bytes(b"zip")
    bsmeta.main(["attach", str(rec), str(crate)])
    crate.write_bytes(b"a corrected zip")
    bsmeta.main(["attach", str(rec), str(crate)])
    name = f"S-X_rocrate_{date.today():%Y%m%d}.zip"
    assert uploads == [(str(crate), name)] * 2
    assert json.loads(rec.read_text())["section"]["files"] == [
        {"path": name, "size": 15, "attributes": [{"name": "Description", "value": "RO-Crate"}, {"name": "Type", "value": "Dataset"}], "type": "file"}
    ]


def test_attach_takes_one_crate(tmp_path):
    with pytest.raises(SystemExit) as e:
        bsmeta.main(["attach", str(tmp_path / "S-X.json"), "a.zip", "b.zip"])
    assert e.value.code == 2


def test_attach_needs_an_accession(tmp_path, monkeypatch):
    import argparse
    import json

    import pytest

    monkeypatch.setattr(bsmeta, "_session", lambda: "tok")
    rec = tmp_path / "draft.pagetab.json"
    rec.write_text(json.dumps({k: v for k, v in DOC.items() if k != "accno"}))
    with pytest.raises(SystemExit) as e:
        bsmeta.cmd_attach(argparse.Namespace(record=str(rec), crate="x.zip"))
    assert "submit the record first" in str(e.value)


def test_submit_registers_a_new_accession(tmp_path, monkeypatch):
    import argparse
    import json


    monkeypatch.setattr(bsmeta, "submit", lambda doc, session: {"accno": "S-VHPS99"})
    monkeypatch.setattr(bsmeta, "_session", lambda: "tok")
    monkeypatch.setattr(bsmeta, "check_terms", lambda doc: [])
    new = {k: v for k, v in DOC.items() if k != "accno"}
    new["attributes"] = [{"name": "Title", "value": "T"}, {"name": "AttachTo", "value": "VHP4Safety"}]
    f = tmp_path / "dataset.pagetab.json"
    f.write_text(json.dumps(new))
    bsmeta.cmd_submit(argparse.Namespace(files=[str(f)], dry_run=False, verbose=False))
    out = json.loads((tmp_path / "S-VHPS99.json").read_text())
    assert not f.exists()
    assert list(out)[0] == "accno" and out["accno"] == "S-VHPS99"
    assert out["attributes"][1] == {"name": "DOI", "value": "10.6019/S-VHPS99"}


def test_submit_holds_back_a_file_under_embargo(tmp_path, monkeypatch):
    monkeypatch.setattr(bsmeta, "rows", lambda: {"S-VHPS99": {**ROW, "embargo_date": "2099-01-01"}})
    monkeypatch.setattr(bsmeta, "check_terms", lambda doc: [])
    monkeypatch.setattr(bsmeta, "submit", lambda doc, session: pytest.fail("submitted"))
    f = tmp_path / "S-VHPS99.json"
    f.write_text(json.dumps(CRATED))
    for dry_run in (True, False):
        with pytest.raises(SystemExit) as e:
            bsmeta.cmd_submit(argparse.Namespace(files=[str(f)], dry_run=dry_run, verbose=False))
        assert "2099-01-01" in str(e.value)


def submitted(tmp_path, monkeypatch, sheet):
    sent = []
    monkeypatch.setattr(bsmeta, "rows", lambda: sheet)
    monkeypatch.setattr(bsmeta, "check_terms", lambda doc: [])
    monkeypatch.setattr(bsmeta, "_session", lambda: "tok")
    monkeypatch.setattr(bsmeta, "submit", lambda doc, session: sent.append(doc["accno"]) or {"accno": doc["accno"]})
    f = tmp_path / "S-VHPS99.json"
    f.write_text(json.dumps(CRATED))
    try:
        bsmeta.cmd_submit(argparse.Namespace(files=[str(f)], dry_run=False, verbose=False))
    except SystemExit as e:
        return str(e)
    return sent


def test_submit_holds_back_files_without_a_readable_passed_embargo_date(tmp_path, monkeypatch):
    assert "01-01-2099" in submitted(tmp_path, monkeypatch, {"S-VHPS99": {**ROW, "embargo_date": "01-01-2099"}})
    assert "no row" in submitted(tmp_path, monkeypatch, {})
    assert submitted(tmp_path, monkeypatch, {"S-VHPS99": {**ROW, "embargo_date": "2026-01-01"}}) == ["S-VHPS99"]
    assert submitted(tmp_path, monkeypatch, {"S-VHPS99": ROW}) == ["S-VHPS99"]


def test_login_explains_a_rejected_password(monkeypatch, tmp_path):
    import argparse

    import pytest

    def rejected(user, password):
        raise bsmeta.BioStudiesError("401 https://example/auth/login\nInvalid email address or password.")

    monkeypatch.setattr(bsmeta, "login", rejected)
    monkeypatch.setattr("builtins.input", lambda prompt="": " someone@example.org ")
    monkeypatch.setattr(bsmeta.getpass, "getpass", lambda prompt="": "pw")
    monkeypatch.setattr(bsmeta, "SESSION_FILE", tmp_path / "session")
    with pytest.raises(SystemExit) as e:
        bsmeta.cmd_login(argparse.Namespace())
    assert "Forgot password" in str(e.value)
    assert not (tmp_path / "session").exists()


TODAY = "2026-11-16"
TRACKED = {
    "accno": "S-VHPS99",
    "attributes": [{"name": "Title", "value": "T "}, {"name": "ReleaseDate", "value": "2026-05-01"}],
    "section": {
        "type": "Study",
        "attributes": [
            {"name": "Title", "value": "T "},
            {"name": "Description", "value": "D, with a comma"},
            {"name": "License", "value": "CC-BY"},
            {"name": "Case study", "value": "Parkinson"},
            {"name": "Regulatory Question", "value": "reg_q_2a"},
            {"name": "Regulatory Question", "value": "reg_q_2b"},
            {"name": "Process Flow Step", "value": "Toxicodynamics"},
            {"name": "Process Flow Step", "value": "Adverse Outcome"},
        ],
    },
}
CRATED = {**TRACKED, "section": {**TRACKED["section"], "files": [{"path": "S-VHPS99_rocrate_20261101.zip"}]}}
BARE = {"accno": "S-VHPS98", "attributes": [{"name": "Title", "value": "T"}], "section": {"type": "Study", "attributes": []}}
ROW = {
    "name": "T",
    "description": "D, with a comma",
    "identifier": "https://www.ebi.ac.uk/biostudies/vhp4safety/studies/S-VHPS99",
    "case_study": "Parkinson",
    "regulatory_question": "Parkinson Q1, Parkinson Q2",
    "workflow_step": "Toxicodynamics, Adverse Outcome",
    "creative_work_status": "Shared",
    "embargo_date": "",
    "date_published": "2026-05-01",
    "license": "CC-BY-4.0",
    "has_ro_crate": "No",
}


def test_expected_follows_the_tracker_model():
    assert expected(TRACKED, ROW, TODAY) == {k: v for k, v in ROW.items() if k != "embargo_date"}


def test_expected_defaults_when_the_record_is_silent():
    want = expected(BARE, {}, TODAY)
    assert (want["case_study"], want["regulatory_question"], want["has_ro_crate"], want["license"]) == ("Other", "N/A", "No", "")


def test_status_is_public_once_a_crate_is_attached_and_the_embargo_has_passed():
    status = lambda doc, **cells: expected(doc, {**ROW, **cells}, TODAY)["creative_work_status"]
    assert status(CRATED) == "Public"
    assert status(CRATED, embargo_date=TODAY) == "Public"
    assert status(CRATED, embargo_date="2026-12-31", creative_work_status="Public") == "Shared"
    assert status(TRACKED, creative_work_status="Public") == "Shared"
    assert status(TRACKED, creative_work_status="Not shared") == "Not shared"


def test_status_waits_for_the_metadata_release():
    unreleased = {**CRATED, "attributes": [{"name": "Title", "value": "T "}, {"name": "ReleaseDate", "value": "2099-01-01"}]}
    assert expected(unreleased, {**ROW, "creative_work_status": "Public"}, TODAY)["creative_work_status"] == "Shared"


def test_status_is_left_alone_when_the_embargo_date_cannot_be_read():
    for unreadable in ("31-12-2026", "２０２６-１２-３１"):
        assert expected(CRATED, {**ROW, "embargo_date": unreadable, "creative_work_status": "Public"}, TODAY)["creative_work_status"] == "Public"
        issues = check_sheet(CRATED, {"S-VHPS99": {**ROW, "embargo_date": unreadable, "has_ro_crate": "Yes", "creative_work_status": "Public"}}, TODAY)
        assert [(i.code, i.where) for i in issues] == [("SHEET_CELL", "S-VHPS99 embargo_date")]


def test_check_sheet_reports_only_differing_cells():
    assert check_sheet(TRACKED, {"S-VHPS99": ROW}, TODAY) == []
    off = {**ROW, "license": "CC BY 4.0", "workflow_step": "Adverse Outcome, Toxicodynamics"}
    assert [(i.code, i.where) for i in check_sheet(TRACKED, {"S-VHPS99": off}, TODAY)] == [("SHEET_CELL", "S-VHPS99 license")]
    assert [i.code for i in check_sheet(TRACKED, {}, TODAY)] == ["SHEET_ROW"]


def test_check_sheet_reports_a_crate_attached_under_embargo():
    row = {**ROW, "has_ro_crate": "Yes", "embargo_date": "2026-12-31"}
    assert [i.code for i in check_sheet(CRATED, {"S-VHPS99": row}, TODAY)] == ["EMBARGO"]


def test_check_sheet_wants_an_iso_embargo_date():
    issues = check_sheet(TRACKED, {"S-VHPS99": {**ROW, "embargo_date": "31-12-2026"}}, TODAY)
    assert [(i.code, i.where) for i in issues] == [("SHEET_CELL", "S-VHPS99 embargo_date")]


def deposit(root, record=TRACKED, files=("data.csv",)):
    """A deposit folder as vitro-crate takes it: source files and a copy of the record."""
    folder = root / "S-VHPS99"
    (folder / "source").mkdir(parents=True)
    for name in files:
        (folder / "source" / name).write_text("x")
    if record:
        (folder / "S-VHPS99.biostudies.json").write_text(json.dumps(record))
    return root


def deposit_codes(doc, deposits, **cells):
    return [i.code for i in check_sheet(doc, {"S-VHPS99": {**ROW, **cells}}, TODAY, deposits)]


def test_check_sheet_holds_shared_to_the_deposit_folders(tmp_path):
    here = deposit(tmp_path / "here")
    assert deposit_codes(TRACKED, here) == []
    assert deposit_codes(TRACKED, here, creative_work_status="Not shared") == ["DEPOSIT"]
    assert deposit_codes(TRACKED, tmp_path / "elsewhere") == ["DEPOSIT"]
    assert deposit_codes(CRATED, tmp_path / "elsewhere", has_ro_crate="Yes", creative_work_status="Public") == []


def test_check_sheet_wants_files_in_a_deposit(tmp_path):
    assert deposit_codes(TRACKED, deposit(tmp_path, files=())) == ["DEPOSIT"]


def test_check_sheet_wants_the_current_record_in_a_deposit(tmp_path):
    old = {**TRACKED, "attributes": [{"name": "Title", "value": "An earlier title"}]}
    assert deposit_codes(TRACKED, deposit(tmp_path / "old", record=old)) == ["DEPOSIT"]
    assert deposit_codes(CRATED, deposit(tmp_path / "public", record=old), has_ro_crate="Yes", creative_work_status="Public") == ["DEPOSIT"]


def test_check_sheet_does_not_count_hidden_files_as_a_deposit(tmp_path):
    assert deposit_codes(TRACKED, deposit(tmp_path, files=(".DS_Store",))) == ["DEPOSIT"]


def test_check_sheet_wants_a_copy_of_the_record_in_a_deposit(tmp_path):
    assert deposit_codes(TRACKED, deposit(tmp_path, record=None)) == ["DEPOSIT"]


def test_check_sheet_compares_the_whole_record_copy(tmp_path):
    linked = {**TRACKED, "section": {**TRACKED["section"], "links": [{"url": "https://example.org"}]}}
    assert deposit_codes(TRACKED, deposit(tmp_path, record=linked)) == ["DEPOSIT"]


def test_check_values_holds_every_row_to_the_model():
    off = {**ROW, "workflow_step": "Toxicodynamics, External exposure", "license": "CC BY 4.0", "embargo_date": "31-12-2026", "partner_code": "XYZ"}
    issues = bsmeta.check_values([(2, ROW), (3, off), (4, {"name": "Planned", "creative_work_status": "Not shared"}), (5, {})])
    assert [(i.code, i.where) for i in issues] == [
        ("SHEET_VALUE", "row 3 workflow_step"),
        ("SHEET_VALUE", "row 3 embargo_date"),
        ("SHEET_VALUE", "row 3 license"),
        ("SHEET_VALUE", "row 3 partner_code"),
    ]


def test_only_a_ro_with_an_identifier_can_be_private_or_public():
    draft = {**ROW, "identifier": ""}
    rows = [(2, ROW), (3, {**draft, "creative_work_status": "Partially shared"}), (4, {**draft, "creative_work_status": "Public"}), (5, {**draft, "creative_work_status": "Private"}), (6, {"name": ""})]
    issues = bsmeta.check_values(rows)
    assert [(i.code, i.where) for i in issues] == [("SHEET_VALUE", "row 4 creative_work_status"), ("SHEET_VALUE", "row 5 creative_work_status")]


def test_draft_is_not_a_status():
    issues = bsmeta.check_values([(2, {**ROW, "identifier": "", "creative_work_status": "Draft"})])
    assert [(i.code, i.where) for i in issues] == [("SHEET_VALUE", "row 2 creative_work_status")]


def test_check_sheet_reports_cells_outside_the_vocabulary(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(bsmeta, "tracker", lambda: [(2, ROW), (3, {**ROW, "identifier": "", "workflow_step": "External exposure"})])
    f = tmp_path / "S-VHPS99.json"
    f.write_text(json.dumps(TRACKED))
    with pytest.raises(SystemExit) as e:
        bsmeta.main(["check-sheet", str(f)])
    assert e.value.code == 1 and "row 3 workflow_step" in capsys.readouterr().out


def test_every_column_of_the_model_says_what_it_holds():
    assert [c for c, spec in bsmeta.MODEL["columns"].items() if not spec.get("note")] == []


def check_sheet_cli(tmp_path, monkeypatch, deposits):
    monkeypatch.setattr(bsmeta, "tracker", lambda: [(2, ROW)])
    f = tmp_path / "S-VHPS99.json"
    f.write_text(json.dumps(TRACKED))
    with pytest.raises(SystemExit) as e:
        bsmeta.main(["check-sheet", "--deposits", deposits, str(f)])
    return e.value.code


def test_check_sheet_needs_an_existing_deposits_folder(tmp_path, monkeypatch):
    assert "nowhere" in str(check_sheet_cli(tmp_path, monkeypatch, str(tmp_path / "nowhere")))


def test_check_sheet_expands_the_home_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    deposit(tmp_path / "deposits")
    assert check_sheet_cli(tmp_path, monkeypatch, "~/deposits") == 0


def tracker_csv(path, *identifiers):
    """The tracker as its CSV export: every model column, one header with a trailing space."""
    head = [column + " " if column == "case_study" else column for column in HEAD]
    lines = [",".join(head)] + [",".join(found if column == "identifier" else "" for column in HEAD) for found in identifiers]
    path.write_text("\n".join(lines) + "\n")
    return path.as_uri()


def test_rows_refuses_a_tracker_without_a_model_column(tmp_path):
    sheet = tmp_path / "tracker.csv"
    sheet.write_text("name,identifier\nA,https://www.ebi.ac.uk/biostudies/vhp4safety/studies/S-VHPS21\n")
    with pytest.raises(SystemExit) as e:
        bsmeta.rows(sheet.as_uri())
    assert "embargo_date" in str(e.value)


def test_rows_says_when_the_export_is_not_the_sheet(tmp_path):
    page = tmp_path / "signin.html"
    page.write_text("<!DOCTYPE html><html><head><title>Sign in</title></head></html>\n")
    with pytest.raises(SystemExit) as e:
        bsmeta.rows(page.as_uri())
    assert "readable" in str(e.value)


def test_rows_refuses_two_rows_for_one_accession(tmp_path):
    url = "https://www.ebi.ac.uk/biostudies/vhp4safety/studies/S-VHPS21"
    with pytest.raises(SystemExit) as e:
        bsmeta.rows(tracker_csv(tmp_path / "tracker.csv", url, url))
    assert "S-VHPS21" in str(e.value)


def test_rows_are_keyed_by_accession_with_trimmed_headers(tmp_path):
    url = "https://www.ebi.ac.uk/biostudies/vhp4safety/studies/S-VHPS21"
    other = "https://www.ebi.ac.uk/biostudies/studies/S-RHER381"
    found = bsmeta.rows(tracker_csv(tmp_path / "tracker.csv", url, "https://doi.org/10.5281/zenodo.1", other))
    assert sorted(found) == ["S-RHER381", "S-VHPS21"]
    assert found["S-VHPS21"]["identifier"] == url and "case_study" in found["S-VHPS21"]


def test_the_sheet_script_derives_what_bsmeta_derives():
    node = shutil.which("node") or pytest.skip("node is not installed")
    cases = [
        (TRACKED, ROW),
        (CRATED, ROW),
        (CRATED, {**ROW, "embargo_date": "2026-12-31", "creative_work_status": "Public"}),
        (CRATED, {**ROW, "embargo_date": "31-12-2026", "creative_work_status": "Public"}),
        (CRATED, {**ROW, "embargo_date": "２０２６-１２-３１", "creative_work_status": "Public"}),
        (BARE, {}),
        ({**CRATED, "attributes": [{"name": "Title", "value": "T "}, {"name": "ReleaseDate", "value": "2099-01-01"}]}, {**ROW, "creative_work_status": "Public"}),
    ]
    run = (
        "const vm = require('vm'), fs = require('fs'), gs = vm.createContext({});"
        "vm.runInContext(fs.readFileSync('tracker.gs', 'utf8'), gs);"
        "const i = JSON.parse(fs.readFileSync(0, 'utf8'));"
        "console.log(JSON.stringify(i.cases.map(([study, row]) => gs.expected(i.model, study, row, i.today))));"
    )
    given = json.dumps({"model": bsmeta.MODEL, "cases": cases, "today": TODAY})
    out = subprocess.run([node, "-e", run], input=given, capture_output=True, text=True, check=True, cwd=Path(bsmeta.__file__).parent)
    assert json.loads(out.stdout) == [expected(study, row, TODAY) for study, row in cases]


def sync(table, studies, typed=(), model=bsmeta.MODEL, flaky=False, late=None, notes=None, stamp=False):
    """Run the sheet script's sync() under Node against a fake sheet, with model served as tracker.json on main; the raw values it writes.

    Typed columns refuse a number format, flaky fails every address's first request, and late is what the sheet holds
    once every study has been fetched. The header notes already match the model unless notes gives them; then the
    writes and the notes set are returned. With stamp the spreadsheet has a lastSync range, and what is written there is returned."""
    node = shutil.which("node") or pytest.skip("node is not installed")
    run = (
        "const vm = require('vm'), fs = require('fs'), i = JSON.parse(fs.readFileSync(0, 'utf8')), writes = [], notes = [], stamps = [], tried = new Set();"
        "let fetched = 0;"
        "const table = () => (i.late && fetched >= 2 + Object.keys(i.studies).length ? i.late : i.table);"
        "const cell = (r, c) => ({"
        "  setNumberFormat() { if (i.typed.includes(i.table[0][c - 1])) throw new Error('typed column'); return this; },"
        "  getNote: () => (r === 1 && i.notes[i.table[0][c - 1]]) || '',"
        "  setNote(n) { notes.push([i.table[0][c - 1], n]); },"
        "  setValue(v) { writes.push([r, i.table[0][c - 1], v]); } });"
        "const sheet = { getSheetId: () => i.gid, getDataRange: () => ({ getDisplayValues: () => table() }), getRange: cell };"
        "const reply = url => url === 'https://raw.githubusercontent.com/VHP4Safety/biostudies-records/main/tracker.json' ? i.model"
        "  : url.includes('/search') ? { hits: Object.keys(i.studies).map(accession => ({ accession })) } : i.studies[url.split('/').pop()];"
        "const fetch = url => {"
        "  if (i.flaky && !tried.has(url)) { tried.add(url); throw new Error('Address unavailable: ' + url); }"
        "  fetched++;"
        "  return { getContentText: () => JSON.stringify(reply(url)) }; };"
        "const gs = vm.createContext({"
        "  SpreadsheetApp: { getActive: () => ({ getSheets: () => [sheet],"
        "    getRangeByName: name => (i.stamp && name === 'lastSync' ? { setValue(v) { stamps.push(v); } } : null) }) },"
        "  UrlFetchApp: { fetch },"
        "  Utilities: { formatDate: () => i.today, sleep() {} } });"
        "vm.runInContext(fs.readFileSync('tracker.gs', 'utf8'), gs);"
        "gs.sync();"
        "console.log(JSON.stringify({ writes, notes, stamps }));"
    )
    noted = {column: spec.get("note", "") for column, spec in model["columns"].items()} if notes is None else notes
    given = json.dumps({"table": table, "studies": studies, "typed": list(typed), "model": model, "gid": model["gid"], "today": TODAY, "flaky": flaky, "late": late, "notes": noted, "stamp": stamp})
    out = json.loads(subprocess.run([node, "-e", run], input=given, capture_output=True, text=True, check=True, cwd=Path(bsmeta.__file__).parent).stdout)
    if stamp:
        return out["stamps"]
    return {"writes": out["writes"], "notes": out["notes"]} if notes is not None else out["writes"]


HEAD = list(bsmeta.MODEL["columns"])


def test_the_sheet_script_corrects_a_cell_in_a_typed_column():
    stale = ["" if column == "has_ro_crate" else ROW.get(column, "") for column in HEAD]
    assert sync([HEAD, stale], {"S-VHPS99": TRACKED}, typed=["has_ro_crate"]) == [[2, "has_ro_crate", "'No"]]


def test_the_sheet_script_adds_a_row_for_a_new_accession():
    writes = sync([HEAD, [ROW.get(column, "") for column in HEAD]], {"S-VHPS99": TRACKED, "S-VHPS98": BARE}, typed=["name"])
    assert [3, "identifier", "'https://www.ebi.ac.uk/biostudies/vhp4safety/studies/S-VHPS98"] in writes
    assert {row for row, _, _ in writes} == {3}


def test_the_sheet_script_follows_the_model_on_main():
    served = {**bsmeta.MODEL, "columns": {**bsmeta.MODEL["columns"], "license": {}}}
    stale = ["CC BY 4.0" if column == "license" else ROW.get(column, "") for column in HEAD]
    assert sync([HEAD, stale], {"S-VHPS99": TRACKED}, typed=[], model=served) == []
    assert sync([HEAD, stale], {"S-VHPS99": TRACKED}, typed=[]) == [[2, "license", "'CC-BY-4.0"]]


def stale_licence():
    return ["CC BY 4.0" if column == "license" else ROW.get(column, "") for column in HEAD]


def test_the_sheet_script_retries_a_failed_request():
    assert sync([HEAD, stale_licence()], {"S-VHPS99": TRACKED}, flaky=True) == [[2, "license", "'CC-BY-4.0"]]


def test_the_sheet_script_writes_where_the_row_is_after_fetching():
    moved = [HEAD, ["" for _ in HEAD], stale_licence()]
    assert sync([HEAD, stale_licence()], {"S-VHPS99": TRACKED}, late=moved) == [[3, "license", "'CC-BY-4.0"]]


def test_the_sheet_script_refuses_two_rows_for_one_accession():
    row = [ROW.get(column, "") for column in HEAD]
    with pytest.raises(subprocess.CalledProcessError) as e:
        sync([HEAD, row, row], {"S-VHPS99": TRACKED})
    assert "S-VHPS99" in e.value.stderr


def test_the_sheet_script_finds_a_row_for_any_biostudies_accession():
    other = {**TRACKED, "accno": "S-RHER381"}
    row = {**ROW, **expected(other, ROW, TODAY)}
    assert sync([HEAD, [row.get(column, "") for column in HEAD]], {"S-RHER381": other}) == []


def test_records_are_read_as_utf8_whatever_the_locale():
    record = Path(bsmeta.__file__).parent / "bs_records" / "S-VHPS26.json"
    run = "import json, bsmeta, sys; print(json.dumps(bsmeta._load(sys.argv[1])))"
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "en_US.ISO8859-1", "PYTHONUTF8": "0", "PYTHONIOENCODING": "utf-8"}
    out = subprocess.run(["python3", "-c", run, str(record)], capture_output=True, text=True, check=True, env=env, cwd=record.parent.parent)
    assert json.loads(out.stdout) == json.loads(record.read_bytes().decode("utf-8"))


def test_the_sheet_script_stamps_each_finished_sync():
    assert sync([HEAD, stale_licence()], {"S-VHPS99": TRACKED}, stamp=True) == [f"'{TODAY}: 1 cell corrected"]
    assert sync([HEAD, [ROW.get(column, "") for column in HEAD]], {"S-VHPS99": TRACKED}, stamp=True) == [f"'{TODAY}: 0 cells corrected"]
    assert sync([HEAD, stale_licence()], {"S-VHPS99": TRACKED}) == [[2, "license", "'CC-BY-4.0"]]


def test_the_sheet_script_writes_the_model_notes_into_the_header():
    row = [ROW.get(column, "") for column in HEAD]
    stale = {column: spec["note"] for column, spec in bsmeta.MODEL["columns"].items()} | {"name": "an old note"}
    out = sync([HEAD, row], {"S-VHPS99": TRACKED}, notes=stale)
    assert out == {"writes": [], "notes": [["name", bsmeta.MODEL["columns"]["name"]["note"]]]}
