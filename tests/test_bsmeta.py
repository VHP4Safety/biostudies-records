from bsmeta.biostudies import diff
from bsmeta.links import check_links
from bsmeta.ols import OlsTerm, check_terms
from bsmeta.pagetab import iter_terms, strip_unfilled

DOC = {
    "type": "Submission",
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
    assert (t.path, t.name, t.ontology, t.term_id) == ("/Submission/Study", "Organ", "UBERON", "UBERON_0000992")


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
    from bsmeta.sheet import check_sheet

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

    from bsmeta import cli

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    f = tmp_path / "r.json"
    f.write_text(json.dumps(DOC))
    with pytest.raises(SystemExit):
        cli._report(argparse.Namespace(files=[str(f)], verbose=False), lambda d: check_terms(d, lookup=FAKE))
    assert f"::error file={f}::UNRESOLVED" in capsys.readouterr().out
    assert "UNRESOLVED" in (tmp_path / "summary.md").read_text()


def test_status_unreachable_is_unknown():
    from bsmeta.links import status

    assert status("https://localhost:1") == 0


def test_fmt_check_flags_and_fmt_rewrites(tmp_path, capsys):
    import argparse
    import json

    import pytest

    from bsmeta import cli
    from bsmeta.pagetab import dumps

    f = tmp_path / "r.json"
    f.write_text(json.dumps(DOC, indent=4))
    with pytest.raises(SystemExit) as e:
        cli.cmd_fmt(argparse.Namespace(files=[str(f)], check=True))
    assert e.value.code == 1 and "FORMAT" in capsys.readouterr().out
    cli.cmd_fmt(argparse.Namespace(files=[str(f)], check=False))
    assert f.read_text() == dumps(DOC)
    with pytest.raises(SystemExit) as e:
        cli.cmd_fmt(argparse.Namespace(files=[str(f)], check=True))
    assert e.value.code == 0


def test_attach_uploads_and_lists_the_file_once(tmp_path, monkeypatch):
    import argparse
    import json

    from bsmeta import cli

    uploads = []
    monkeypatch.setattr(cli.biostudies, "upload", lambda path, session: uploads.append(path))
    monkeypatch.setattr(cli, "_session", lambda: "tok")
    rec = tmp_path / "S-X.json"
    rec.write_text(json.dumps(DOC))
    crate = tmp_path / "S-X_rocrate.zip"
    crate.write_bytes(b"zip")
    cli.cmd_attach(argparse.Namespace(record=str(rec), files=[str(crate)]))
    cli.cmd_attach(argparse.Namespace(record=str(rec), files=[str(crate)]))
    assert uploads == [str(crate)] * 2
    assert json.loads(rec.read_text())["section"]["files"] == [
        {"path": "S-X_rocrate.zip", "size": 3, "attributes": [{"name": "Description", "value": "RO-Crate"}, {"name": "Type", "value": "Dataset"}], "type": "file"}
    ]


def test_submit_registers_a_new_accession(tmp_path, monkeypatch):
    import argparse
    import json

    from bsmeta import cli

    monkeypatch.setattr(cli.biostudies, "submit", lambda doc, session: {"accno": "S-VHPS99"})
    monkeypatch.setattr(cli, "_session", lambda: "tok")
    monkeypatch.setattr(cli.ols, "check_terms", lambda doc: [])
    new = {k: v for k, v in DOC.items() if k != "accno"}
    new["attributes"] = [{"name": "Title", "value": "T"}, {"name": "AttachTo", "value": "VHP4Safety"}]
    f = tmp_path / "dataset.pagetab.json"
    f.write_text(json.dumps(new))
    cli.cmd_submit(argparse.Namespace(files=[str(f)], dry_run=False, verbose=False))
    out = json.loads((tmp_path / "S-VHPS99.json").read_text())
    assert not f.exists()
    assert list(out)[0] == "accno" and out["accno"] == "S-VHPS99"
    assert out["attributes"][1] == {"name": "DOI", "value": "10.6019/S-VHPS99"}
