# VHP4Safety BioStudies metadata

PageTab records for the [VHP4Safety collection](https://www.ebi.ac.uk/biostudies/vhp4safety/) and `bsmeta`, which checks and submits them.

| path | what |
|---|---|
| `bs_records/` | one JSON per accession, `<dataset>.pagetab.json` until BioStudies issues one; unfilled fields in `bs_records/README.md` |
| `template/` | skeleton and conventions for a new record |
| `bsmeta/` | `uv run bsmeta --help` |

```sh
uv run bsmeta check-terms bs_records/*.json        # ontology terms resolve in OLS4
uv run bsmeta check-links bs_records/*.json        # method slugs, CompoundCloud ids, DOIs, bioassay names
uv run bsmeta check-sheet bs_records/S-VHPS*.json  # RO inventory tracker matches the records
uv run bsmeta diff bs_records/S-VHPS*.json         # differences from the live record
uv run bsmeta login                                # session id -> ~/.config/bsmeta/session
uv run bsmeta upload <crate>.zip                   # to your BioStudies user area; then list it under section.files
uv run bsmeta submit bs_records/<accession>.json   # blank and [DRAFT] attributes are dropped; no accno = new record
```

CI runs the tests and term check on every push, the full freshness check monthly, and submits only from the manual "Run workflow" trigger (`biostudies` environment with `BIOSTUDIES_LOGIN` and `BIOSTUDIES_PASSWORD`). Findings appear as annotations on the run.
