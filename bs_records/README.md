# Records

_Updated 2026-10-27._ These are the authored records; `uv run bsmeta diff` shows whether BioStudies has the same.

## Status

| accession | unfilled | notes |
|---|---|---|
| S-VHPS16 | – | |
| S-VHPS17 | – | `CVCL_ZX55` on both the PTL and ELC lines is the parent iPSC (STBCi322-A), not either derivative |
| S-VHPS18 | – | |
| S-VHPS20 | `ORCID`, `Role` | |
| S-VHPS21 | `Issue`, `Role` | |
| S-VHPS22 | `Exposure concentration` | |
| S-VHPS23 | see below | tacrolimus, iPSC kidney organoids |
| S-VHPS24 | see below | tacrolimus, sorted proximal tubule cells |
| S-VHPS25 | see below | tacrolimus, tubuloids |
| S-VHPS26 | – | `Tissue` is *epithelium of female gonad* (UBERON_0004911) for CHO-K1, to be confirmed by the depositor. `Sulfobromophthalein sodium` cites CAS 71-67-0 but CompoundCloudID Q4750 is the hydrate (CAS 123359-42-2); Compound Wiki has no item for 71-67-0. Indocyanine green CID 5282412 is unverified (Wikidata lists several) |
| S-VHPS27 | `RRID`, `Supplier` (hBMEC) | |
| S-VHPS28 | – | |
| 2OC.pagetab.json | see below | held, see below |

Blank attributes are dropped at submit; they stay in these files only to show what is wanted.

### S-VHPS23, S-VHPS24
`AOP event`, `Bioassay`, `Cell line`, `Cell type`, `Endpoint readout`, `Exposure concentration`, `Exposure duration`, `Exposure type`, `Manufacturer`, `Measured entity`, `Name`, `RRID`, `Replicates`, `Role`, `Supplier`, `Time point`

### S-VHPS25
`AOP event`, `Age`, `Differentiation protocol`, `E-mail`, `Manufacturer`, `Name`, `Replicates`, `Sex`, `Tissue origin`

### 2OC — TempO-Seq transcriptomics of kidney-liver organ-on-a-chip co-cultures (Anja Wilmes, VU)
No `accno` or `DOI` until BioStudies issues them on first submission; without a `ReleaseDate` the record stays private. Still needed from the depositor: `ReleaseDate`; `Grant_id` (NWO, RiskHunt3R H2020, or both); co-authors; `RRID` for SIGi001-HC3x, PTL-SIGi001-A and HLC-SIGi001-HC3x (not the parent line's); Ifosfamide `CID` and `CompoundCloudID` (Compound Wiki has no item for CAS 3778-73-2 yet).

Held: the RO inventory tracker lists this dataset as BioStudies S-RHER381 (RiskHunt3R, not public). The depositor must confirm whether that is the same data; if so, S-RHER381 should carry `AttachTo: VHP4Safety` instead of a second record.

## Open decision

`Exposure concentration`: single value, range or dose series, and whether it lives at `Exposure information` or per `Exposure regimen`. Decide together with the crate mapping (one sample per concentration, concentration as a factor value).
