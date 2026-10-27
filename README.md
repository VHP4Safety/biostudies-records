# VHP4Safety BioStudies metadata

PageTab records for the [VHP4Safety collection](https://www.ebi.ac.uk/biostudies/vhp4safety/) and `bsmeta`, which checks and submits them.

| path | what |
|---|---|
| `bs_records/` | one JSON per accession, `<dataset>.pagetab.json` until BioStudies issues one; unfilled fields in `bs_records/README.md` |
| `template/` | skeleton and conventions for a new record |
| `bsmeta/` | `uv run bsmeta --help` |

## Typical changes

- **New record:** copy `template/TEMPLATE.pagetab.json` to `bs_records/<dataset>.pagetab.json`, fill the `[DRAFT]` values, `check-terms`, `submit`; the file is renamed to its accession.
- **Edit a record:** change the JSON, `fmt`, `check-terms`, commit, PR, then `submit`.
- **Attach an RO-Crate:** `attach`, then `submit`.

```sh
uv run bsmeta fmt [--check] bs_records/*.json           # canonical JSON layout
uv run bsmeta check-terms bs_records/*.json             # ontology terms resolve in OLS4
uv run bsmeta check-links bs_records/*.json             # method slugs, CompoundCloud ids, DOIs, bioassay names
uv run bsmeta check-sheet bs_records/S-VHPS*.json       # RO inventory tracker matches the records
uv run bsmeta diff bs_records/S-VHPS*.json              # differences from the live record
uv run bsmeta login                                     # session id -> ~/.config/bsmeta/session
uv run bsmeta attach bs_records/<acc>.json <crate>.zip  # upload to your user area and list under section.files
uv run bsmeta submit bs_records/<acc>.json              # blank and [DRAFT] attributes are dropped; no accno = new record
```

CI runs the tests, format check and term check on every push, the full freshness check monthly, and submits only from the manual "Run workflow" trigger (`biostudies` environment with `BIOSTUDIES_LOGIN` and `BIOSTUDIES_PASSWORD`). Findings appear as annotations on the run.
