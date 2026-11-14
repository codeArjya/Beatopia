"""Licensed source discovery, cached responses and durable request budgets."""

import hashlib
import json
import math
import re
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


@dataclass(frozen=True)
class Candidate:
    source: str
    source_id: str
    title: str
    artist: str
    license: str
    license_url: str
    source_url: str
    download_url: str
    duration_s: float

    @property
    def id(self) -> str:
        return f"{'fs' if self.source == 'freesound' else 'jam'}_{self.source_id}"

    def metadata(self) -> dict[str, object]:
        return asdict(self)


def cc_license(url: str, *, jamendo: bool = False) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or parsed.hostname not in {
        "creativecommons.org",
        "www.creativecommons.org",
    }:
        raise ValueError("Unrecognized license host")
    match = re.fullmatch(r"/licenses/(by|by-sa)/(\d\.\d)/?", parsed.path)
    if match and (jamendo or match[1] == "by"):
        return f"CC-{match[1].upper()}-{match[2]}"
    if not jamendo and re.fullmatch(r"/publicdomain/zero/1\.0/?", parsed.path):
        return "CC0"
    raise ValueError("Ineligible license")


def candidate(row: dict, source: str) -> Candidate:
    jam = source == "jamendo"
    license_url = str(row["license_ccurl" if jam else "license"])
    license_name = cc_license(license_url, jamendo=jam)
    if jam and row.get("audiodownload_allowed") is not True:
        raise ValueError("Download not permitted")
    download = row.get("audiodownload", "") if jam else row.get("previews", {}).get("preview-hq-mp3", "")
    source_url = row.get("shareurl" if jam else "url", "")
    artist = str(row.get("artist_name" if jam else "username", "")).strip()
    title = str(row.get("name", "")).strip()
    source_id = str(row["id"])
    duration = float(row["duration"])
    if (
        not source_id.isdecimal()
        or not title
        or not artist
        or not math.isfinite(duration)
        or duration < 4
        or (not jam and duration > 60)
        or any(urlsplit(str(url)).scheme not in {"http", "https"} for url in (download, source_url))
    ):
        raise ValueError("Incomplete source metadata")
    return Candidate(source, source_id, title, artist, license_name, license_url, source_url, download, duration)


class Discovery:
    """One sequential caller; CLI lock protects caches and the persisted API budget."""

    def __init__(self, root: Path, client: httpx.Client, keys: dict[str, str]) -> None:
        self.root, self.client, self.keys = root, client, keys
        self.budget_path = root / "request-budget.json"
        self.budget = json.loads(self.budget_path.read_text()) if self.budget_path.exists() else {}

    def request(self, source: str, params: dict[str, object]) -> dict:
        digest = hashlib.sha256(json.dumps([source, params], sort_keys=True).encode()).hexdigest()
        cache = self.root / "cache" / f"{digest}.json"
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        endpoint = (
            "https://api.jamendo.com/v3.0/tracks/" if source == "jamendo" else "https://freesound.org/apiv2/search/"
        )
        headers = {"Authorization": f"Token {self.keys[source]}"} if source == "freesound" else {}
        request_params = {**params, **({"client_id": self.keys[source]} if source == "jamendo" else {})}
        for attempt in range(3):
            budget = self.budget.setdefault(source, {"total": 0, "day": "", "daily": 0, "last": 0})
            day = datetime.now(UTC).date().isoformat()
            if budget["day"] != day:
                budget.update(day=day, daily=0)
            if budget["total"] >= 600 or budget["daily"] >= 600:
                raise RuntimeError("WS1 source API budget exhausted")
            cooldown = float(budget.get("not_before", 0)) - time.time()
            if cooldown > 60:
                raise RuntimeError("Source cooldown remains active; resume later")
            time.sleep(max(0, cooldown))
            time.sleep(max(0, float(budget["last"]) + 1.1 - time.time()))
            budget.update(total=budget["total"] + 1, daily=budget["daily"] + 1, last=time.time())
            write_json(self.budget_path, self.budget)
            try:
                response = self.client.get(endpoint, params=request_params, headers=headers)
                if response.status_code == 429 or response.status_code >= 500:
                    retry = response.headers.get("Retry-After", "")
                    # Long server cooldowns stop this run rather than violate the server's limit.
                    try:
                        delay = (
                            float(retry)
                            if retry.isdecimal()
                            else (parsedate_to_datetime(retry).timestamp() - time.time())
                        )
                    except (TypeError, ValueError):
                        delay = 2 ** (attempt + 1)
                    delay = max(0, delay)
                    budget["not_before"] = time.time() + delay
                    write_json(self.budget_path, self.budget)
                    if delay > 60:
                        raise RuntimeError("Source requested cooldown over 60 seconds; resume later")
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                data = response.json()
                if source == "jamendo" and data.get("headers", {}).get("status") != "success":
                    raise ValueError("Jamendo API returned an error")
                if not isinstance(data.get("results"), list):
                    raise ValueError("Invalid source response")
                write_json(cache, data)
                return data
            except httpx.TransportError:
                time.sleep(2**attempt)
        raise RuntimeError("Source request failed after three attempts")

    def discover(self, source: str, count: int) -> list[Candidate]:
        if not self.keys.get(source, "").strip():
            raise RuntimeError(f"Missing {source} credential")
        found: dict[str, Candidate] = {}
        queries = [
            "trumpet",
            "rhodes",
            "strings",
            "piano",
            "saxophone",
            "guitar",
            "bass",
            "drum loop",
            "flute",
            "organ",
            "choir",
            "soul",
            "jazz",
            "synth",
            "percussion",
            "",
        ]
        # Hard page ceiling in addition to the durable request budget.
        for page in range(1, 11):
            for query in queries:
                if source == "jamendo":
                    params = {
                        "format": "json",
                        "limit": 100,
                        "offset": (page - 1) * 100,
                        "include": "licenses+musicinfo",
                        "audioformat": "mp32",
                        "ccnc": "false",
                        "ccnd": "false",
                        "tags": query,
                        "order": "id",
                    }
                else:
                    params = {
                        "query": query,
                        "page": page,
                        "page_size": 50,
                        "filter": 'license:("Creative Commons 0" OR "Attribution") duration:[4 TO 60]',
                        "fields": "id,name,username,license,duration,tags,url,previews",
                    }
                data = self.request(source, params)
                for row in data["results"]:
                    try:
                        item = candidate(row, source)
                    except (KeyError, TypeError, ValueError):
                        continue
                    found[item.id] = item
                    if len(found) >= count:
                        return list(found.values())
        return list(found.values())
