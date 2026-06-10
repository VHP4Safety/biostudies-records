# BioStudies records — outstanding `[TODO]` punch-list

_Last updated: 2026-06-10._

Every former `[DRAFT]` marker in these PageTab records has been replaced with `[TODO]`.
This file lists the records that still carry open `[TODO]` fields and **who needs to supply
each value**. The `[TODO]` text in each record keeps a hint where one was known.

**Complete (no `[TODO]`):** S-VHPS20, S-VHPS21, **S-VHPS26**, **S-VHPS28**.

## Status at a glance

| Record | Topic | Open `[TODO]` | Owner |
|---|---|---|---|
| S-VHPS22 | Thyroid — neural cell screening | 4 | Nathalie Dierichs (RIVM) |
| S-VHPS27 | Parkinson — cell model comparison | 4 | Julia Meerman (RIVM) |
| S-VHPS16 | Exposure scenarios | 1 | — |
| S-VHPS23 | Tacrolimus — iPSC kidney organoids | 24 | Kate Liang |
| S-VHPS24 | Tacrolimus — sorted proximal tubule cells | 24 | Kate Liang |
| S-VHPS25 | Tacrolimus — tubuloids | 33 | Sendino Garvi / Masereeuw (UU) |

---

## S-VHPS22 — Thyroid (owner: Nathalie Dierichs)
*Instrument + replicates already filled from the `study_01_TH-DNT` assay Excels (QuantStudio 7 Flex / Applied Biosystems; deiodinase 2, metabolism 2, KLF9 3).*
- **Exposure concentration** (study-level) — heterogeneous across the 4 assays; can be summarised as `0.1–300` µM if a single value is acceptable.
- **Bioassay method-page URLs** (3): *Thyroid hormone uptake*, *Deiodinase activity (D3)*, *Whole-cell TH metabolism* — no VHP4Safety method page exists yet.

## S-VHPS27 — Parkinson (owner: Julia Meerman)
*Exposure concentration filled (`0.1–100` µM).*
- **hBMEC** `RRID` (+ its Cellosaurus `URL`) — Excel notes *"need to ask for details"*.
- **hBMEC** `Supplier` — likely **IRAS, Utrecht University** (per Excel comment "Cell line IRAS") — please confirm.
- **HepG2** `Supplier` — not recorded (HepG2 = CVCL_0027 is typically ATCC) — please confirm.

## S-VHPS16 — Exposure scenarios
- **Exposure concentration** (Alamar blue bioassay).

---

## S-VHPS23 — Tacrolimus, iPSC kidney organoids (owner: Kate Liang) — *deferred*
- Bioassay + BAO `TermId`; Funding `Agency`/`Grant_id`; cell line `RRID`/`Supplier`/`Cell type`; exposure `type`/`duration`/`concentration` (+ units); endpoint `AOP event` (+ aopwiki URL, AOP 622), `Time point`, `Replicates`, `Measured entity`, `Endpoint readout`; detection instrument `Name`/`Manufacturer`.

## S-VHPS24 — Tacrolimus, sorted proximal tubule cells (owner: Kate Liang) — *deferred*
- Same field set as S-VHPS23 (sibling record).

## S-VHPS25 — Tacrolimus, tubuloids (owner: Sendino Garvi / Masereeuw) — *deferred*
- Bioassay `Ontology`/`TermId` (CellTiter-Fluor, LCMS, RNA-sequencing); Tissue `TermId` (verify UBERON_0001231); author `E-mail`s (Sendino Garvi, Masereeuw, Slaats, Verhaar); Donor `Sex`/`Age`/`Tissue origin` (×2); `Differentiation protocol`; per-assay `Exposure concentration`, `AOP event` (+ URLs), `Replicates`; detection instrument `Name`/`Manufacturer` (×2).

---

_Tacrolimus records (S-VHPS23/24/25) were intentionally deferred — listed here for completeness only._
