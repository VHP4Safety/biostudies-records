# VHP4Safety BioStudies metadata

PageTab records for the [VHP4Safety collection](https://www.ebi.ac.uk/biostudies/vhp4safety/) and `bsmeta`, which checks and submits them.

| path | what |
|---|---|
| `bs_records/` | one JSON per accession, `<dataset>.pagetab.json` until BioStudies issues one; unfilled fields in `bs_records/README.md` |
| `template/` | skeleton and conventions for a new record |
| `bsmeta.py` | the tool, standard library only: `python3 bsmeta.py --help` |

## Typical changes

- **New record:** copy `template/TEMPLATE.pagetab.json` to `bs_records/<dataset>.pagetab.json`, fill the `[DRAFT]` values, `check-terms`, `submit`; the file is renamed to its accession.
- **Edit a record:** change the JSON, `fmt`, `check-terms`, commit, PR, then `submit`.
- **Attach an RO-Crate:** `attach`, then `submit`. The crate is stored as `<accession>_rocrate_<YYYYMMDD>.zip` whatever the local file is called.

```sh
python3 bsmeta.py fmt [--check] bs_records/*.json           # canonical JSON layout
python3 bsmeta.py check-terms bs_records/*.json             # ontology terms resolve in OLS4
python3 bsmeta.py check-links bs_records/*.json             # method slugs, CompoundCloud ids, DOIs, bioassay names
python3 bsmeta.py check-sheet bs_records/S-VHPS*.json       # RO inventory tracker matches the records
python3 bsmeta.py diff bs_records/S-VHPS*.json              # differences from the live record
python3 bsmeta.py login                                     # session id -> ~/.config/bsmeta/session
python3 bsmeta.py attach bs_records/<acc>.json <crate>.zip  # upload to your user area and list under section.files
python3 bsmeta.py submit bs_records/<acc>.json              # blank and [DRAFT] attributes are dropped; no accno = new record
```

Python 3.9 or newer, nothing to install. The tests need pytest: `python3 -m pip install pytest`, then `python3 -m pytest -q`.

CI runs the tests, format check and term check on every push, the full freshness check monthly, and submits only from the manual "Run workflow" trigger (`biostudies` environment with `BIOSTUDIES_LOGIN` and `BIOSTUDIES_PASSWORD`). Findings appear as annotations on the run.
