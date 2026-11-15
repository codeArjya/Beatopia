"""Evaluate the actual /search endpoint. No fixture fallback or machine relevance grades.

Run from the repository root: uv run --project ingest python -m ingest.eval --help
Exit 1: request/contract/fixture failures. Exit 2: human grading incomplete. Exit 0:
two complete attributed reviews supplied (still not a semantic pass threshold).
"""

import argparse
import hashlib
import html
import importlib.util
import json
import math
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
COVERAGE = {"instrument", "mood", "genre", "tempo", "sparse", "stem", "chips", "text_only"}


def search_response_model() -> type[BaseModel]:
    """Read the binding models without depending on the WS2 application package."""
    spec = importlib.util.spec_from_file_location("eval_contract", ROOT / "api/app/models/api.py")
    if spec is None or spec.loader is None:
        raise ValueError("Contract models unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SearchResponse


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def load_queries(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Expected query dataset version 1")
    queries = data.get("queries")
    if not isinstance(queries, list) or len(queries) != 20:
        raise ValueError("Exactly twenty queries are required")
    chips = read_json(ROOT / "shared/fixtures/chips.json")
    chip_ids = {c["id"] for category in chips["categories"] for c in category["chips"]}
    seen, covered = set(), set()
    for query in queries:
        if not isinstance(query, dict) or set(query) != {"id", "text", "chips", "covers", "listen_for"}:
            raise ValueError("Each query needs id, text, chips, covers and listen_for")
        if not isinstance(query["id"], str) or not query["id"] or query["id"] in seen:
            raise ValueError("Query IDs must be nonempty and unique")
        seen.add(query["id"])
        if not all(isinstance(query[k], str) and query[k].strip() for k in ("text", "listen_for")):
            raise ValueError("Query text/listening intent must be nonempty")
        for key, allowed in (("chips", chip_ids), ("covers", COVERAGE)):
            values = query[key]
            if not isinstance(values, list) or any(not isinstance(v, str) or v not in allowed for v in values):
                raise ValueError(f"Unknown {key} in {query['id']}")
        covered.update(query["covers"])
    if covered != COVERAGE:
        raise ValueError("Missing representative query coverage")
    return queries


def base_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("API URL must use http or https")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("API URL must not contain credentials, query or fragment")
    return value.rstrip("/")


def response_issues(body: dict) -> list[str]:
    issues = []
    results = body["results"]
    if not results:
        issues.append("empty_results")
    if len(results) > 5:
        issues.append("limit_5_ignored")
    if len({r["window_id"] for r in results}) != len(results):
        issues.append("duplicate_windows")
    fixture = read_json(ROOT / "shared/fixtures/search.json")
    if (
        body == fixture
        or body["query_id"] == fixture["query_id"]
        or any("/fixtures/" in r["audio_url"] or "/fixtures/" in (r["track"]["source_url"] or "") for r in results)
    ):
        issues.append("fixture_response")
    for result in results:
        track = result["track"]
        if track["source"] == "import":
            issues.append("private_import_returned")
        if not track["license"].strip() or not track["attribution"].strip():
            issues.append("missing_license_or_attribution")
        start, end, duration, score = (result["start_s"], result["end_s"], track["duration_s"], result["score"])
        if not all(math.isfinite(x) for x in (start, end, duration, score)):
            issues.append("nonfinite_result")
        elif not (0 <= start < end <= duration and 0 <= score <= 1):
            issues.append("invalid_range_or_score")
    return sorted(set(issues))


def run_queries(client: httpx.Client, endpoint: str, queries: list[dict]) -> dict:
    run_id = str(uuid.uuid4())
    model = search_response_model()
    report = dict(
        run_id=run_id,
        recorded_at=datetime.now(UTC).isoformat(),
        base_url=base_url(endpoint),
        dataset_sha256=digest(queries),
        expected_clap=read_json(ROOT / "ingest/vocab-freeze.json")["model"],
        expected_clap_revision=read_json(ROOT / "ingest/vocab-freeze.json")["revision"],
        service_model_verified=False,
        live_service_provenance="Requires WS2 confirmation; absence of fixture markers does not prove live DB search",
        queries=[],
    )
    for query in queries:
        request = dict(text=query["text"], chips=query["chips"], limit=5, session_id=run_id)
        row = dict(
            query=query, request=request, response=None, raw_response=None, http_status=None, issues=[], error=None
        )
        started = time.monotonic()
        try:
            response = client.post(report["base_url"] + "/search", json=request)
            row["http_status"] = response.status_code
            if response.status_code != 200:
                # Do not log provider bodies that may echo credentials or internal details.
                code = None
                try:
                    error = response.json().get("error", {})
                    candidate = error.get("code") if isinstance(error, dict) else None
                    if isinstance(candidate, str) and candidate.replace("_", "").isalnum() and len(candidate) <= 64:
                        code = candidate
                except (ValueError, AttributeError):
                    pass
                row["error"] = dict(kind="http_error", code=code)
            else:
                body = response.json()
                # Python's JSON decoder accepts NaN/Infinity; evidence files must not.
                json.dumps(body, allow_nan=False)
                # Preserve actual response fields, including unrecognized additions, for WS2 diagnosis.
                row["raw_response"] = body
                row["response"] = model.model_validate(body).model_dump(mode="json")
                row["issues"] = response_issues(row["response"])
        except httpx.TimeoutException:
            row["error"] = dict(kind="timeout")
        except httpx.RequestError:
            row["error"] = dict(kind="network_error")
        except (ValueError, TypeError, KeyError):
            row["error"] = dict(kind="invalid_response")
        row["elapsed_s"] = time.monotonic() - started
        report["queries"].append(row)
    report["result_sha256"] = digest(report["queries"])
    report["technical_failures"] = sum(bool(r["error"] or r["issues"]) for r in report["queries"])
    report["relevance_acceptance"] = "unverified; requires two human reviews and live service confirmation"
    return report


def rating_rows(report: dict) -> list[dict]:
    return [
        dict(query_id=row["query"]["id"], rank=rank, window_id=result["window_id"], grade=None, notes="")
        for row in report["queries"]
        if row["response"] is not None and not row["error"] and not row["issues"]
        for rank, result in enumerate(row["response"]["results"][:5], 1)
    ]


def review_summary(report: dict, reviews: list[dict]) -> dict:
    expected = {(r["query_id"], r["rank"], r["window_id"]) for r in rating_rows(report)}
    identities, summaries = set(), []
    for review in reviews:
        name = review.get("reviewer")
        if not isinstance(name, str) or not name.strip() or not review.get("recorded_at"):
            raise ValueError("Each human review needs reviewer and recorded_at")
        identity = name.strip().casefold()
        if identity in identities:
            raise ValueError("Two distinct human reviewers required")
        identities.add(identity)
        if review.get("run_id") != report["run_id"] or review.get("result_sha256") != report["result_sha256"]:
            raise ValueError("Human review belongs to different results")
        seen, scores, per_query = set(), [], {}
        for rating in review.get("ratings", []):
            key = (rating.get("query_id"), rating.get("rank"), rating.get("window_id"))
            if key not in expected or key in seen:
                raise ValueError("Unknown or duplicate reviewed result")
            seen.add(key)
            grade = rating.get("grade")
            if grade is None:
                continue
            if type(grade) is not int or grade not in {0, 1, 2}:
                raise ValueError("Grades must be null or integer 0, 1, 2")
            scores.append(grade)
            per_query.setdefault(key[0], []).append(grade)
        summaries.append(
            dict(
                reviewer=name.strip(),
                graded=len(scores),
                expected=len(expected),
                complete=bool(expected) and len(scores) == len(expected) and not report["technical_failures"],
                mean_grade=sum(scores) / len(scores) if scores else None,
                query_means={k: sum(v) / len(v) for k, v in per_query.items()},
            )
        )
    return dict(
        reviews=summaries,
        two_complete_reviews=len(summaries) == 2 and all(r["complete"] for r in summaries),
        semantic_pass="No numerical pass threshold was specified; human grades are evidence, not an automatic pass",
    )


def markdown(report: dict) -> str:
    lines = [
        "# Search evaluation",
        "",
        f"Run: `{report['run_id']}`; recorded {report['recorded_at']}; API: {report['base_url']}",
        f"Technical failures: {report['technical_failures']}/{len(report['queries'])}.",
        "Live service/model and human relevance remain unverified unless separately documented.",
        "",
        "Human rubric: 0 = irrelevant; 1 = partial match; 2 = useful match to the stated listening intent.",
        "Listen to the exact returned window; record timbre, mood, tempo and bleed failures in notes.",
        "",
    ]
    for row in report["queries"]:
        query = row["query"]
        lines.extend([f"## {query['id']}: {query['text']}", "", query["listen_for"], ""])
        lines.append(
            f"HTTP {row['http_status']}; {row['elapsed_s']:.3f}s; errors: {row['error']}; issues: {row['issues']}"
        )
        if row["response"]:
            lines.append(f"Plan: `{json.dumps(row['response']['plan'], ensure_ascii=False)}`")
            lines.append(f"Fallback used: {row['response']['fallback_used']}")
            for rank, result in enumerate(row["response"]["results"][:5], 1):
                track = result["track"]
                lines.extend(
                    [
                        f"{rank}. `{result['window_id']}` / `{track['id']}` / {result['stem']} "
                        f"[{result['start_s']}, {result['end_s']}] s; score {result['score']}",
                        f"   Tags: {', '.join(result['tags'])}; license: {track['license']}; "
                        f"BPM: {track['bpm']}; attribution: {track['attribution']}",
                        f"   Audio: {result['audio_url']}",
                    ]
                )
        lines.append("")
    return "\n".join(lines)


def audition_html(report: dict) -> str:
    # These are search windows on full-track/full-hero URLs. Range-job offsets require
    # separate Stems.range_start_s metadata and are explicitly outside this player.
    parts = [
        '<!doctype html><meta charset="utf-8"><title>Search relevance auditions</title>',
        "<h1>Search relevance auditions</h1><p>0 irrelevant; 1 partial; 2 useful. "
        "Save independent grades in the reviewer JSON files. No grades are prefilled.</p>",
    ]

    def esc(value: object) -> str:
        return html.escape(str(value), quote=True)

    for row in report["queries"]:
        parts.append(f"<h2>{esc(row['query']['id'])}: {esc(row['query']['text'])}</h2>")
        parts.append(f"<p>{esc(row['query']['listen_for'])}</p>")
        if row["error"] or row["issues"]:
            parts.append(f"<p>NOT GRADABLE: {esc(row['error'])} {esc(row['issues'])}</p>")
            continue
        for rank, result in enumerate(row["response"]["results"][:5], 1):
            url = result["audio_url"]
            if urlsplit(url).scheme not in {"http", "https"}:
                parts.append("<p>Non-public audio URL; playback unavailable.</p>")
                continue
            parts.append(
                f"<p>{rank}. {esc(result['window_id'])}; tags: {esc(', '.join(result['tags']))}; "
                f"{esc(result['track']['license'])}; {esc(result['track']['attribution'])}; "
                f"{result['start_s']}–{result['end_s']} s</p>"
                f'<audio controls preload="none" src="{esc(url)}" '
                f'data-start="{result["start_s"]}" data-end="{result["end_s"]}"></audio>'
            )
    parts.append(
        "<script>document.querySelectorAll('audio').forEach(a=>{"
        "a.addEventListener('play',()=>{document.querySelectorAll('audio').forEach(b=>{if(b!==a)b.pause()});"
        "if(a.currentTime<+a.dataset.start||a.currentTime>=+a.dataset.end)a.currentTime=+a.dataset.start});"
        "a.addEventListener('timeupdate',()=>{if(a.currentTime>=+a.dataset.end)a.pause()})});</script>"
    )
    return "\n".join(parts)


def save_run(report: dict, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=False)  # Never overwrite a before run or human feedback.
    write_json(directory / "results.json", report)
    (directory / "results.md").write_text(markdown(report), encoding="utf-8")
    (directory / "audition.html").write_text(audition_html(report), encoding="utf-8")
    for label in ("A", "B"):
        write_json(
            directory / f"reviewer-{label}.json",
            dict(
                run_id=report["run_id"],
                result_sha256=report["result_sha256"],
                reviewer="",
                recorded_at="",
                rubric={"0": "irrelevant", "1": "partial match", "2": "useful match"},
                ratings=rating_rows(report),
            ),
        )


def comparison(before: dict, after: dict, before_reviews: list[dict], after_reviews: list[dict]) -> dict:
    if before["dataset_sha256"] != after["dataset_sha256"]:
        raise ValueError("Before/after datasets differ")
    old, new = review_summary(before, before_reviews), review_summary(after, after_reviews)
    ready = old["two_complete_reviews"] and new["two_complete_reviews"]
    if ready and {r["reviewer"].casefold() for r in old["reviews"]} != {
        r["reviewer"].casefold() for r in new["reviews"]
    }:
        raise ValueError("Before/after need the same human reviewers")
    return dict(
        before_run=before["run_id"],
        after_run=after["run_id"],
        before_failures=before["technical_failures"],
        after_failures=after["technical_failures"],
        before_grades=old,
        after_grades=new,
        human_comparison_available=ready,
        query_grade_deltas={
            row["query"]["id"]: sum(r["query_means"][row["query"]["id"]] for r in new["reviews"]) / 2
            - sum(r["query_means"][row["query"]["id"]] for r in old["reviews"]) / 2
            for row in after["queries"]
        }
        if ready
        else {},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("NEXT_PUBLIC_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--queries", type=Path, default=ROOT / "ingest/eval_queries.yaml")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("ingest/data/session6") / f"eval-{uuid.uuid4().hex[:8]}"
    )
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--report", type=Path, help="Review saved results without requesting /search again")
    parser.add_argument("--grades", nargs=2, type=Path, help="Two independent human review JSON files")
    parser.add_argument("--before", type=Path, help="Compare this saved results.json to the current run")
    parser.add_argument("--before-grades", nargs=2, type=Path)
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    if args.before_grades and not args.before:
        parser.error("--before-grades requires --before")
    try:
        if args.report:
            report = read_json(args.report)
        else:
            queries = load_queries(args.queries)
            endpoint = base_url(args.base_url)
            if args.output_dir.exists():
                raise ValueError("Output directory already exists; choose a new run directory")
            with httpx.Client(timeout=args.timeout, follow_redirects=False, trust_env=False) as client:
                report = run_queries(client, endpoint, queries)
            save_run(report, args.output_dir)
        # Verify saved snapshots before attaching human feedback.
        if digest(report["queries"]) != report["result_sha256"]:
            raise ValueError("Saved results have changed since the run")
        grades = [read_json(p) for p in args.grades or []]
        summary = review_summary(report, grades)
        reviews_complete = summary["two_complete_reviews"]
        print(markdown(report))
        print(json.dumps({"grading": summary}, indent=2))
        if args.before:
            before = read_json(args.before)
            if digest(before["queries"]) != before["result_sha256"]:
                raise ValueError("Before results have changed since the run")
            result = comparison(before, report, [read_json(p) for p in args.before_grades or []], grades)
            reviews_complete = reviews_complete and result["human_comparison_available"]
            print(json.dumps({"comparison": result}, indent=2))
        raise SystemExit(1 if report["technical_failures"] else 0 if reviews_complete else 2)
    except (ValueError, OSError, KeyError, TypeError) as error:
        # CLI errors are explicit but never include raw network exceptions.
        print(json.dumps({"eval_error": type(error).__name__, "message": str(error)}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
