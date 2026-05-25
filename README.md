# VHP4Safety BioStudies metadata

Curated [BioStudies](https://www.ebi.ac.uk/biostudies/) **PageTab** metadata records for
VHP4Safety case-study datasets.

## Contents

| File | description |
|---|---|
| `bs_records/S-VHPSxx.json` | One BioStudies PageTab submission per study record. Usually corresponds to one publication. |
| `template/TEMPLATE.pagetab.json` / `template/TEMPLATE.README.md` | Template for creating a new record. |

## Status

Several records still contain `[DRAFT]` placeholders. 

## Conventions 

See `template/TEMPLATE.README.md` for conventions on how to fill in the metadata fields, and the [BioStudies submission guidelines](https://www.ebi.ac.uk/biostudies/submission-guide) for more general guidance.

## Validation

```sh
python3 -m json.tool bs_records/S-VHPSxx.json > /dev/null   # JSON is valid
grep -c '\[DRAFT\]' bs_records/S-VHPSxx.json                # count remaining drafts
```

## Related

- BioStudies VHP4Safety collection (where these records are submitted).
- `rocrate-wizard` builds the ISA-Tox RO-Crates these records project onto.

