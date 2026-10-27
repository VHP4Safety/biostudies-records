"""Pure helpers over a raw PageTab JSON document."""
import json
from collections.abc import Iterator
from dataclasses import dataclass

DRAFT = "[DRAFT]"


def dumps(doc) -> str:
    """The one JSON layout every record uses."""
    return json.dumps(doc, indent=2, separators=(",", " : "), ensure_ascii=False) + "\n"


@dataclass(frozen=True)
class Issue:
    level: str  # "error" | "info"
    code: str
    where: str
    message: str


def _unfilled(value) -> bool:
    s = "" if value is None else str(value).strip()
    return not s or s.startswith(DRAFT)


def strip_unfilled(node):
    """Copy without blank or [DRAFT] attributes and valquals."""
    if isinstance(node, list):
        return [strip_unfilled(x) for x in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for key, val in node.items():
        if key in ("attributes", "valqual"):
            kept = [strip_unfilled(a) for a in val if not _unfilled(a.get("value"))]
            if kept:
                out[key] = kept
        else:
            out[key] = strip_unfilled(val)
    return out


def attrs(node, path="") -> Iterator[tuple[str, dict]]:
    """(section path, attribute) for every attribute, depth first."""
    if isinstance(node, list):
        for x in node:
            yield from attrs(x, path)
    elif isinstance(node, dict):
        here = f"{path}/{node['type']}" if node.get("type") else path
        for a in node.get("attributes", []):
            yield here, a
        for key in ("section", "subsections"):
            if key in node:
                yield from attrs(node[key], here)


def valquals(a: dict) -> dict:
    return {q.get("name"): q.get("value") for q in a.get("valqual", [])}


@dataclass(frozen=True)
class TermRef:
    path: str
    name: str
    value: str | None
    ontology: str | None
    term_id: str | None


def iter_terms(doc) -> Iterator[TermRef]:
    for path, a in attrs(doc):
        vq = valquals(a)
        if "Ontology" in vq or "TermId" in vq:
            yield TermRef(path, a.get("name"), a.get("value"), vq.get("Ontology"), vq.get("TermId"))


def flatten(doc) -> set[tuple]:
    return {(p, a.get("name"), a.get("value"), tuple(sorted(valquals(a).items()))) for p, a in attrs(doc)}
