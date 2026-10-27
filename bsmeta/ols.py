"""Resolve term ids against EMBL-EBI OLS4."""
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from functools import cache

from .pagetab import Issue, iter_terms

OLS = "https://www.ebi.ac.uk/ols4/api/terms?obo_id="


@dataclass(frozen=True)
class OlsTerm:
    short_form: str
    label: str
    obsolete: bool
    replaced_by: str | None


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "bsmeta", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


@cache
def lookup(term_id: str) -> OlsTerm | None:
    prefix, _, local = term_id.replace(":", "_", 1).partition("_")
    if not local:
        return None
    hits = get_json(OLS + urllib.parse.quote(f"{prefix}:{local}", safe="")).get("_embedded", {}).get("terms", [])
    own = [t for t in hits if t.get("ontology_name") == prefix.lower()] or hits
    time.sleep(0.1)
    if not own:
        return None
    t = own[0]
    return OlsTerm(t["short_form"], t["label"], bool(t.get("is_obsolete")), t.get("term_replaced_by"))


def check_terms(doc, lookup=lookup) -> list[Issue]:
    """Errors: HALF_TAGGED, UNRESOLVED, OBSOLETE, SHORT_FORM. Info: LABEL (local names may differ)."""
    out = []
    for t in iter_terms(doc):
        where = f"{t.path} {t.name}={t.value!r}"
        if not (t.ontology and t.term_id):
            out.append(Issue("error", "HALF_TAGGED", where, f"Ontology={t.ontology!r} TermId={t.term_id!r}"))
            continue
        hit = lookup(t.term_id)
        if hit is None:
            out.append(Issue("error", "UNRESOLVED", where, f"{t.term_id} is not in OLS4"))
            continue
        if hit.obsolete:
            out.append(Issue("error", "OBSOLETE", where, f"{t.term_id} replaced by {hit.replaced_by}"))
        if hit.short_form != t.term_id:
            out.append(Issue("error", "SHORT_FORM", where, f"write {t.term_id} as {hit.short_form}"))
        if (t.value or "").strip().lower() != hit.label.lower():
            out.append(Issue("info", "LABEL", where, f"OLS label is {hit.label!r}"))
    return out
