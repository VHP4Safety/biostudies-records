"""Links and cross-references: method slugs, CompoundCloud ids, DOIs, bioassay names."""
import urllib.error
import urllib.request
from functools import cache

from .ols import get_json
from .pagetab import Issue, attrs, valquals

METHODS_INDEX = "https://raw.githubusercontent.com/VHP4Safety/cloud/refs/heads/main/cap/methods_index.json"
METHODS = "https://platform.vhp4safety.nl/methods/"
COMPOUND = "https://compoundcloud.wikibase.cloud/wiki/Item:"


@cache
def method_slugs() -> set[str]:
    return set(get_json(METHODS_INDEX))


def status(url: str) -> int:
    """HTTP status of a HEAD request; 0 when the host cannot be reached or verified."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "bsmeta"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return 0


def check_links(doc, slugs=method_slugs, status=status) -> list[Issue]:
    out, study, used = [], set(), []
    for path, a in attrs(doc):
        name, value, url = a.get("name"), a.get("value"), valquals(a).get("URL")
        where = f"{path} {name}={value!r}"
        if name == "Bioassay" and value:
            if path == "/Submission/Study":
                study.add(value.strip().lower())
            else:
                used.append((where, value.strip().lower()))
        if url and url.startswith(METHODS) and url.removeprefix(METHODS).strip("/") not in slugs():
            out.append(Issue("error", "METHOD_SLUG", where, f"{url} is not in methods_index.json"))
        if name == "CompoundCloudID" and value and status(COMPOUND + value) == 404:
            out.append(Issue("error", "COMPOUND_ID", where, f"{COMPOUND}{value} does not exist"))
        if name == "DOI" and value and status(f"https://doi.org/{value}") >= 400:
            out.append(Issue("error", "DOI", where, f"https://doi.org/{value} does not resolve"))
    out += [Issue("error", "BIOASSAY_REF", w, "no study-level Bioassay with this name") for w, v in used if v not in study]
    return out
