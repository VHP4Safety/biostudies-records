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
