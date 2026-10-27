import bsmeta
from bsmeta import OlsTerm, check_links, check_terms, diff, iter_terms, strip_unfilled

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


def test_check_sheet_reports_only_differing_cells():
    from bsmeta import check_sheet

    row = {
        "title": "T",
        "license": "CC BY 4.0",
        "releaseMetadata": "2026-05-01",
        "hasROCrate": "Yes",
        "caseStudy ": "Thyroid",
        "workflowStep": "Toxicodynamics, Chemical Characteristics and Hazard Indentification",
    }
    doc = {
        "type": "Submission",
        "accno": "S-Y",
        "attributes": [{"name": "Title", "value": "T"}, {"name": "ReleaseDate", "value": "2026-05-01"}],
        "section": {
            "type": "Study",
            "attributes": [
                {"name": "License", "value": "CC-BY"},
                {"name": "Case study", "value": "Thyroid"},
                {"name": "Process Flow Step", "value": "Toxicodynamics"},
                {"name": "Process Flow Step", "value": "Chemical Characteristics and Hazard Identification"},
            ],
        },
    }
    assert [(i.code, i.where) for i in check_sheet(doc, {"S-Y": row})] == [("SHEET_CELL", "S-Y hasROCrate")]
    assert [i.code for i in check_sheet(doc, {})] == ["SHEET_ROW"]


def test_report_annotates_github_actions(monkeypatch, capsys, tmp_path):
    import argparse
    import json

    import pytest


    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    f = tmp_path / "r.json"
    f.write_text(json.dumps(DOC))
    with pytest.raises(SystemExit):
        bsmeta._report(argparse.Namespace(files=[str(f)], verbose=False), lambda d: check_terms(d, lookup=FAKE))
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
    bsmeta.cmd_attach(argparse.Namespace(record=str(rec), files=[str(crate)]))
    bsmeta.cmd_attach(argparse.Namespace(record=str(rec), files=[str(crate)]))
    name = f"S-X_rocrate_{date.today():%Y%m%d}.zip"
    assert uploads == [(str(crate), name)] * 2
    assert json.loads(rec.read_text())["section"]["files"] == [
        {"path": name, "size": 3, "attributes": [{"name": "Description", "value": "RO-Crate"}, {"name": "Type", "value": "Dataset"}], "type": "file"}
    ]


def test_attach_needs_an_accession(tmp_path, monkeypatch):
    import argparse
    import json

    import pytest

    monkeypatch.setattr(bsmeta, "_session", lambda: "tok")
    rec = tmp_path / "draft.pagetab.json"
    rec.write_text(json.dumps({k: v for k, v in DOC.items() if k != "accno"}))
    with pytest.raises(SystemExit) as e:
        bsmeta.cmd_attach(argparse.Namespace(record=str(rec), files=["x.zip"]))
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


def test_check_sheet_treats_missing_case_study_as_other():
    from bsmeta import expected

    doc = {"attributes": [{"name": "Title", "value": "T"}], "section": {"type": "Study", "attributes": []}}
    assert expected(doc)["caseStudy"] == "Other"


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
