"""
Domain model for a BioStudies PageTab study record (one S-VHPSxx record).

Covers the full record: Study core + Author / Organisation / Bioassay / Funding
/ Chemical / Publication / BiologicalModel / Exposure / EndpointReadout /
DataAnalysis and their sub-sections.

Reference for field names, which attributes carry ontology valquals, and the
cross-references: template/TEMPLATE.pagetab.json + template/TEMPLATE.README.md.

Validation philosophy — the model is a TOLERANT CONTAINER, not a gate.
  - Fields are plain/optional so *every* record loads, even a malformed or
    `[DRAFT]` one. That is what lets the linter inspect it and report on it.
  - Content rules (formats, controlled vocabularies, cross-references, drafts)
    are NOT enforced here; they live in `validate.py` as checks that return
    graded `Issue`s and never raise. Shared domain vocab (Role, ProcessFlowStep,
    doi_for) lives here since jsonld.py needs it too; the format regexes live
    with the checks in validate.py.
  - Pure Pydantic for now (no `table=True`); nesting is just lists. Classes are
    ordered so a model is defined before anything that nests it (we avoid
    `from __future__ import annotations` because it breaks SQLModel
    `Relationship()` once we go `table=True`). SQL is on the roadmap: when it
    lands, follow SQLModel's multi-model idiom — these classes become the shared
    `*Base`, add `*(table=True)` table models, and keep validation in validate.py
    (table models don't run it by design).

Building blocks:
    Term      -> a controlled/identifier value + url + ontology + term_id
    Quantity  -> a measurement value + unit (e.g. "24" + "hours")
"""

from enum import Enum

from pydantic import Field
from sqlmodel import SQLModel


def doi_for(accno: str) -> str:
    """The DOI derived from a study accno: ``10.6019/{accno}``."""
    return f"10.6019/{accno}"


def glossary_term(vhp_id: str) -> dict:
    """`json_schema_extra` tagging a field/property with the VHP glossary IRI that
    defines the *key itself* (e.g. "Regulatory Question" -> VHP0000151). Schema
    metadata about the property — not data stored per record."""
    return {"term_iri": f"https://glossary.vhp4safety.nl/#{vhp_id}"}


class Role(str, Enum):
    """Controlled vocabulary for an author's `Role` (extend as new roles appear)."""
    author = "Author"
    corresponding_author = "Corresponding author"
    contributor = "Contributor"
    data_producer = "Data producer"
    data_processor = "Data processor"


class ProcessFlowStep(str, Enum):
    """Controlled VHP glossary vocabulary for Process Flow Step values — the five
    stages of the VHP4Safety risk-assessment workflow, in pipeline order. Each
    step's glossary id is in PROCESS_FLOW_STEP_IRI.
    """
    chemical_characteristics = "Chemical Characteristics and Hazard Identification"
    exposure = "Exposure"
    toxicokinetics = "Toxicokinetics"
    toxicodynamics = "Toxicodynamics"
    adverse_outcome = "Adverse Outcome"


# Each step's own fixed glossary id (distinct from the "Process Flow Step"
# *property* id). Keep in sync with the enum above.
PROCESS_FLOW_STEP_IRI = {
    ProcessFlowStep.chemical_characteristics: "VHP0000153",
    ProcessFlowStep.exposure: "VHP0000154",
    ProcessFlowStep.toxicokinetics: "VHP0000155",
    ProcessFlowStep.toxicodynamics: "VHP0000156",
    ProcessFlowStep.adverse_outcome: "VHP0000158",
}


# ── Value objects ───────────────────────────────────────────────────────────


class Term(SQLModel):
    """A controlled/identifier value paired with the reference(s) that identify it.

    The PageTab `value` is the label; the `valqual` carries the coding — a `URL`
    and/or `Ontology` + `TermId`. Used for ontology-coded values (Cell type,
    Organ, ...) and identifier-with-URL values (RRID, references, CID, ...).
    """
    value: str
    url: str | None = None
    ontology: str | None = None
    term_id: str | None = None


class Quantity(SQLModel):
    """A measurement value with its unit, e.g. "24" + "hours" (PageTab `Unit`)."""
    value: str
    unit: str | None = None


# ── Study subsections ───────────────────────────────────────────────────────


class Organisation(SQLModel):
    """A PageTab `organisation` subsection.

    Its `accno` (e.g. "o1") is what `Author.affiliations` point at — that
    string-reference linkage is what `check_cross_references` verifies.
    """
    accno: str                      # PageTab subsection id, e.g. "o1"
    name: str
    ror_id: str | None = None       # ROR URL, e.g. https://ror.org/01cesdt21
    address: str | None = None
    country: str | None = None


class Author(SQLModel):
    """A PageTab `author` subsection.

    The affiliation is an attribute with `"reference": true` whose value is an
    Organisation `accno`. Some authors list two, so it's a list of accno strings.
    """
    name: str
    email: str | None = None        
    orcid: str 
    role: str | None = None         # "see Role vocabulary
    affiliations: list[str] = []    # organisation accnos this author cites


class Bioassay(SQLModel):
    """A section-level `Bioassay` attribute — the assay name is the linkage key.

    Endpoint readout / Exposure subsections reference a Bioassay by exact `name`
    match (like affiliations -> org accno); that string linkage is what
    `check_cross_references` verifies. Carries the ontology coding + a URL.
    """
    name: str                       # assay name — the cross-reference key
    url: str | None = None          # URL to the methods page on VHP4Safety
    ontology: str | None = None     # e.g. "BAO", "ENM"
    term_id: str | None = None      # e.g. "BAO_0013056"


class Funding(SQLModel):
    """A section-level `Funding` subsection: a funding agency and its grant id.

    Funders are distinct from the author-affiliation `Organisation`s (no overlap
    in the records), so a Funding entry is standalone — not a cross-reference.
    """
    name: str                    # "Agency", e.g. "Dutch Research Agenda (NWA)"
    grant_id: str | None = None  # "Grant_id", e.g. "1292.19.272"


class Chemical(SQLModel):
    """A section-level `Chemical information` subsection: a named chemical with
    external identifiers. CID and CompoundCloudID carry a resolvable URL in the
    records, so they reuse `Term` (value + url); CAS does not.
    """
    name: str                              # "Chemical", e.g. "Dinoseb"
    cid: Term | None = None                # PubChem CID (value + URL), e.g. 6950
    cas: str | None = None                 # CAS number, e.g. "88-85-7"
    compound_cloud_id: Term | None = None  # CompoundCloud id (value + URL), e.g. Q4723           # e.g. "hepatotoxic agent" — NOT test/control (contextual)


class Publication(SQLModel):
    """A `Publication` subsection — a cited reference (all plain strings)."""
    title: str
    authors: str | None = None
    year: str | None = None
    volume: str | None = None
    issue: str | None = None
    publication_type: str | None = None    # "Type"
    issn: str | None = None
    doi: str | None = None
    pmid: str | None = None


class Donor(SQLModel):
    """A `Donor` sub-subsection of Biological model information."""
    donor_id: str | None = None            # "ID"
    passage: str | None = None
    sex: str | None = None
    age: str | None = None
    tissue_origin: str | None = None


class CellLinePreparation(SQLModel):
    """A `Cell line preparation` sub-subsection of Biological model information."""
    preparation_type: Term | None = None   # ontology-coded
    cell_type: Term | None = None          # ontology-coded
    differentiation_protocol: str | None = None
    reference: Term | None = None          # value + DOI URL
    cell_name: str | None = None
    description: str | None = None


class BiologicalModel(SQLModel):
    """A `Biological model information` subsection (cell line + provenance)."""
    cell_line: str
    rrid: Term | None = None               # RRID code + Cellosaurus URL
    supplier: str | None = None
    cell_type: Term | None = None          # ontology-coded
    organ: Term | None = None              # ontology-coded
    tissue: Term | None = None             # ontology-coded
    description: str | None = None
    donors: list[Donor] = []
    cell_line_preparations: list[CellLinePreparation] = []


class ExposureRegimen(SQLModel):
    """An `Exposure regimen` sub-subsection of Exposure information."""
    exposure_type: Term | None = None      # ontology-coded (EXO)
    exposure_duration: Quantity | None = None
    exposure_concentration: Quantity | None = None
    exposure_measurement_interval: Quantity | None = None
    recovery_period: Quantity | None = None
    number_of_repeats: str | None = None
    co_treatment: str | None = None
    bioassays: list[str] = []              # referenced Bioassay names


class Exposure(SQLModel):
    """An `Exposure information` subsection."""
    exposure_type: Term | None = None      # plain here, ontology-coded in regimens
    exposure_duration: Quantity | None = None
    exposure_concentration: Quantity | None = None
    exposure_measurement_interval: Quantity | None = None
    time_between_exposures: Quantity | None = None
    vehicle: str | None = None
    bioassays: list[str] = []              # referenced Bioassay names
    exposure_regimens: list[ExposureRegimen] = []


class DetectionInstrument(SQLModel):
    """A `Detection instrument` sub-subsection of Endpoint readout information."""
    name: str
    manufacturer: str | None = None
    excitation_wavelength: Quantity | None = None
    emission_wavelength: Quantity | None = None
    absorbance_wavelength: Quantity | None = None
    reference_wavelength: Quantity | None = None
    ionization: str | None = None


class Substrate(SQLModel):
    """A `Substrate` sub-subsection of Endpoint readout information."""
    name: str
    cas: str | None = None
    concentration: Quantity | None = None
    radiolabel: str | None = None
    product: str | None = None
    manufacturer: str | None = None
    compound: str | None = None
    compound_cloud_id: Term | None = None  # value + URL


class EndpointReadout(SQLModel):
    """An `Endpoint readout information` subsection.

    References exactly one Bioassay by name (cross-ref). `endpoint_readout` /
    `measured_entity` pair a label with a unit, so they use `Quantity`.
    """
    bioassay: str | None = None            # single referenced Bioassay name;                                    # its method url + coding live on the Bioassay
    aop_events: list[Term] = []            # KE or MIE that is studies in readout
    endpoint_readout: Quantity | None = None   # label + unit
    measured_entity: Quantity | None = None    # label (+ unit)
    description: str | None = None
    replicates: str | None = None
    technical_replicates: str | None = None
    reference_gene: str | None = None
    vehicle_control: str | None = None
    internal_standard: str | None = None
    reagent_concentration: Quantity | None = None
    assay_incubation_time: Quantity | None = None
    positive_control: str | None = None    # referenced control Chemical name (in Study.chemicals)
    positive_control_concentration: Quantity | None = None       # dose used in this readout
    positive_control_exposure_duration: Quantity | None = None
    detection_instruments: list[DetectionInstrument] = []
    substrates: list[Substrate] = []


class Software(SQLModel):
    """A `Software` sub-subsection of Data & analysis (name + homepage URL)."""
    name: str
    url: str | None = None
    version: str | None = None


class DataAnalysis(SQLModel):
    """A `Data & analysis` subsection."""
    analysis_pipeline: Term | None = None  # value + URL
    analysis_code: Term | None = None      # value + URL
    reference_genome: str | None = None
    statistical_method: str | None = None
    significance_threshold: str | None = None
    software: list[Software] = []


class Study(SQLModel):
    """Top-level BioStudies PageTab submission — one S-VHPSxx record.

    Core scalars plus the nested collections. The Organism ontology tag is
    flattened into fields (value + ontology + term id).
    """
    accno: str                              # "S-VHPS16" — globally unique
    title: str
    doi: str | None = None                  # 10.6019/{accno}; see doi_for()
    release_date: str | None = None         # ISO date string, e.g. "2026-05-25"
    description: str | None = None
    organism: str | None = None
    organism_ontology: str | None = None    # e.g. "NCBITaxon"
    organism_term_id: str | None = None     # e.g. "NCBITaxon_9606"
    license: str | None = None              # open vocab (CC-BY, ...)

    files: list[str] = []                   # multi-valued; just the file names
    links: list[str] = []                   # multi-valued; just the link names


    # `json_schema_extra` tags each property with the VHP glossary IRI that
    # defines the key itself (schema metadata — not stored per record).
    case_study: Term | None = Field(
        default=None,
        json_schema_extra=glossary_term("VHP0000150"),
    )
    regulatory_questions: list[Term] = Field(
        default_factory=list,
        json_schema_extra=glossary_term("VHP0000151"),
    )
    process_flow_steps: list[str] = Field(
        default_factory=list,
        json_schema_extra=glossary_term("VHP0000152"),
    )

    authors: list[Author] = []
    organisations: list[Organisation] = []
    funding: list[Funding] = []
    publications: list[Publication] = []
    chemicals: list[Chemical] = []
    aop: Term | None = None                 # Adverse Outcome Pathway: value + aopwiki URL
    bioassays: list[Bioassay] = []          # multi-valued; referenced by name
    biological_models: list[BiologicalModel] = []
    exposures: list[Exposure] = []
    endpoint_readouts: list[EndpointReadout] = []
    data_analyses: list[DataAnalysis] = []
