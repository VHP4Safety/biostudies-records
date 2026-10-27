"""BioStudies: public read, login, upload, submit, diff."""
import json
import subprocess
import urllib.error
import urllib.request

from .pagetab import flatten, strip_unfilled

PUBLIC = "https://www.ebi.ac.uk/biostudies/api/v1/studies/"
API = "https://www.ebi.ac.uk/biostudies/submissions/api"


class BioStudiesError(RuntimeError):
    pass


def _request(url: str, data=None, headers=None, timeout=300) -> dict:
    body = json.dumps(data).encode() if data is not None else None
    hdrs = {"Accept": "application/json", "User-Agent": "bsmeta", **(headers or {})}
    if body is not None:
        hdrs["Content-Type"] = "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=hdrs), timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise BioStudiesError(f"{e.code} {url}\n{e.read().decode(errors='replace')[:2000]}") from None


def fetch_live(accno: str) -> dict:
    return _request(PUBLIC + accno)


def login(user: str, password: str) -> str:
    return _request(f"{API}/auth/login", {"login": user, "password": password})["sessid"]


def upload(path: str, session: str) -> None:
    """Stream a file into the user area (curl, so size is not held in memory)."""
    subprocess.run(["curl", "-sSf", "-H", f"X-SESSION-TOKEN: {session}", "-F", f"files=@{path}", f"{API}/files/user"], check=True)


def submit(doc: dict, session: str) -> dict:
    return _request(f"{API}/submissions", doc, {"X-SESSION-TOKEN": session, "Submission_Type": "application/json"})


def diff(authored: dict, live: dict) -> list[str]:
    a, l = flatten(strip_unfilled(authored)), flatten(live)
    return [f"- {r}" for r in sorted(l - a, key=str)] + [f"+ {r}" for r in sorted(a - l, key=str)]
