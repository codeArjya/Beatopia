import copy
import json
import sys
from pathlib import Path

import httpx
import pytest
import yaml

from ingest import eval as evaluation


def queries() -> list[dict]:
    return evaluation.load_queries(evaluation.ROOT / "ingest/eval_queries.yaml")


def response() -> dict:
    body = evaluation.read_json(evaluation.ROOT / "shared/fixtures/search.json")
    body["query_id"] = "unit-test-query"
    body["results"] = [body["results"][0]]
    result = body["results"][0]
    result["audio_url"] = "https://audio.test/tracks/jam_1532881/mix.mp3"
    result["track"]["source_url"] = "https://source.test/1532881"
    return body


def run(body: dict | None = None) -> dict:
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body or response()))) as c:
        return evaluation.run_queries(c, "https://api.test", queries())


def reviews(report: dict) -> list[dict]:
    return [
        dict(
            reviewer=name,
            recorded_at="2026-11-15T00:00:00+00:00",
            run_id=report["run_id"],
            result_sha256=report["result_sha256"],
            ratings=[{**row, "grade": 1} for row in evaluation.rating_rows(report)],
        )
        for name in ("Test reviewer A", "Test reviewer B")
    ]


def test_dataset_is_twenty_representative_queries_with_real_chip_ids() -> None:
    dataset = queries()
    assert len(dataset) == 20
    assert len({q["id"] for q in dataset}) == 20
    assert set().union(*(set(q["covers"]) for q in dataset)) == evaluation.COVERAGE
    assert sum("stem" in q["covers"] for q in dataset) >= 3
    assert sum("tempo" in q["covers"] for q in dataset) >= 4


@pytest.mark.parametrize("damage", ["count", "duplicate", "chip", "coverage", "intent"])
def test_dataset_rejects_silent_weakening(tmp_path: Path, damage: str) -> None:
    dataset = queries()
    if damage == "count":
        dataset.pop()
    elif damage == "duplicate":
        dataset[-1]["id"] = dataset[0]["id"]
    elif damage == "chip":
        dataset[0]["chips"].append("inst.invented")
    elif damage == "coverage":
        for query in dataset:
            query["covers"] = [c for c in query["covers"] if c != "stem"]
    else:
        dataset[0]["listen_for"] = ""
    path = tmp_path / "queries.yaml"
    path.write_text(yaml.safe_dump(dict(version=1, queries=dataset)))
    with pytest.raises(ValueError):
        evaluation.load_queries(path)


def test_actual_post_contract_and_top_five_printed() -> None:
    requests = []
    body = response()
    body["results"] = [{**body["results"][0], "window_id": f"opaque-{i}"} for i in range(5)]

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=body)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        report = evaluation.run_queries(client, "https://api.test/prefix/", queries())
    assert len(requests) == 20
    assert all(r.method == "POST" and str(r.url) == "https://api.test/prefix/search" for r in requests)
    payload = json.loads(requests[0].content)
    assert payload["limit"] == 5
    assert payload["text"] == queries()[0]["text"] and payload["chips"] == queries()[0]["chips"]
    assert payload["session_id"] == report["run_id"]
    assert report["technical_failures"] == 0
    output = evaluation.markdown(report)
    assert "opaque-4" in output and "CC-BY-SA-3.0" in output and "rhodes" in output
    assert report["queries"][0]["response"] == body
    assert report["service_model_verified"] is False


@pytest.mark.parametrize("kind", ["timeout", "network", "http", "html", "schema", "redirect"])
def test_errors_are_retained_for_all_twenty_without_fixture_fallback(kind: str) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if kind == "timeout":
            raise httpx.ReadTimeout("sensitive provider text", request=request)
        if kind == "network":
            raise httpx.ConnectError("sensitive provider text", request=request)
        if kind == "http":
            return httpx.Response(503, json={"error": {"code": "upstream_error", "message": "sensitive"}})
        if kind == "redirect":
            return httpx.Response(302, headers={"Location": "https://elsewhere.test"})
        if kind == "html":
            return httpx.Response(200, text="<html>sensitive</html>")
        return httpx.Response(200, json={"query_id": "missing"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        report = evaluation.run_queries(client, "https://api.test", queries())
    assert report["technical_failures"] == 20
    assert all(row["response"] is None and row["error"] for row in report["queries"])
    assert "sensitive" not in json.dumps(report)
    assert evaluation.rating_rows(report) == []
    assert evaluation.review_summary(report, reviews(report))["two_complete_reviews"] is False


@pytest.mark.parametrize(
    "damage,issue",
    [
        ("fixture", "fixture_response"),
        ("import", "private_import_returned"),
        ("limit", "limit_5_ignored"),
        ("range", "invalid_range_or_score"),
        ("license", "missing_license_or_attribution"),
        ("empty", "empty_results"),
        ("nan", "nonfinite_result"),
    ],
)
def test_acceptance_failures_are_not_gradable(damage: str, issue: str) -> None:
    body = response()
    result = body["results"][0]
    if damage == "fixture":
        body = evaluation.read_json(evaluation.ROOT / "shared/fixtures/search.json")
    elif damage == "import":
        result["track"]["source"] = "import"
    elif damage == "limit":
        body["results"] *= 6
    elif damage == "range":
        result["end_s"] = 999
    elif damage == "license":
        result["track"]["license"] = ""
    elif damage == "nan":
        result["score"] = float("nan")
        assert issue in evaluation.response_issues(body)
        return
    else:
        body["results"] = []
    report = run(body)
    assert issue in report["queries"][0]["issues"]
    assert report["technical_failures"] == 20
    assert evaluation.rating_rows(report) == []


def test_run_files_are_immutable_and_reviewers_start_ungraded(tmp_path: Path) -> None:
    report = run()
    directory = tmp_path / "run"
    evaluation.save_run(report, directory)
    assert evaluation.read_json(directory / "results.json") == report
    for label in ("A", "B"):
        review = evaluation.read_json(directory / f"reviewer-{label}.json")
        assert review["reviewer"] == "" and review["recorded_at"] == ""
        assert all(r["grade"] is None for r in review["ratings"])
    page = (directory / "audition.html").read_text(encoding="utf-8")
    assert 'data-start="0.0"' in page and 'data-end="10.667"' in page
    assert "a.currentTime>=+a.dataset.end" in page
    with pytest.raises(FileExistsError):
        evaluation.save_run(report, directory)


@pytest.mark.parametrize("damage", ["identity", "stale", "duplicate", "unknown", "float", "boolean"])
def test_grade_provenance_and_identity_validation(damage: str) -> None:
    report = run()
    feedback = reviews(report)
    if damage == "identity":
        feedback[1]["reviewer"] = "  TEST REVIEWER A "
    elif damage == "stale":
        feedback[0]["result_sha256"] = "wrong snapshot"
    elif damage == "duplicate":
        feedback[0]["ratings"].append(feedback[0]["ratings"][0])
    elif damage == "unknown":
        feedback[0]["ratings"][0]["window_id"] = "not returned"
    elif damage == "float":
        feedback[0]["ratings"][0]["grade"] = 1.0
    else:
        feedback[0]["ratings"][0]["grade"] = True
    with pytest.raises(ValueError):
        evaluation.review_summary(report, feedback)


def test_partial_grades_and_before_after_have_no_fabricated_deltas() -> None:
    before, after = run(), run()
    feedback = reviews(before)
    feedback[0]["ratings"][0]["grade"] = None
    assert evaluation.review_summary(before, feedback)["two_complete_reviews"] is False
    comparison = evaluation.comparison(before, after, [], [])
    assert comparison["human_comparison_available"] is False
    assert comparison["query_grade_deltas"] == {}
    complete = evaluation.comparison(before, after, reviews(before), reviews(after))
    assert complete["human_comparison_available"] is True
    assert all(value == 0 for value in complete["query_grade_deltas"].values())
    changed = copy.deepcopy(after)
    changed["dataset_sha256"] = "different"
    with pytest.raises(ValueError, match="datasets differ"):
        evaluation.comparison(before, changed, [], [])


@pytest.mark.parametrize("value", ["file:///tmp/api", "https://user:secret@api.test", "https://api.test?key=secret"])
def test_api_url_rejects_embedded_secrets(value: str) -> None:
    with pytest.raises(ValueError):
        evaluation.base_url(value)


def test_nonfinite_http_json_becomes_explicit_error_in_serializable_evidence() -> None:
    body = response()
    body["results"][0]["score"] = float("nan")
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=json.dumps(body)))) as client:
        report = evaluation.run_queries(client, "https://api.test", queries())
    assert report["technical_failures"] == 20
    assert all(row["error"]["kind"] == "invalid_response" for row in report["queries"])
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("mode,exit_code", [("ungraded", 2), ("graded", 0), ("stale", 1), ("before_ungraded", 2)])
def test_cli_reviews_saved_results_without_network(
    tmp_path: Path, monkeypatch, capsys, mode: str, exit_code: int
) -> None:
    report = run()
    path = tmp_path / "results.json"
    evaluation.write_json(path, report)
    args = ["eval.py", "--report", str(path)]
    if mode != "ungraded":
        paths = [tmp_path / "A.json", tmp_path / "B.json"]
        for review, target in zip(reviews(report), paths, strict=True):
            evaluation.write_json(target, review)
        args.extend(["--grades", *map(str, paths)])
    if mode == "stale":
        report["queries"][0]["response"]["results"][0]["score"] = 0
        evaluation.write_json(path, report)
    if mode == "before_ungraded":
        args.extend(["--before", str(path)])
    monkeypatch.setattr(sys, "argv", args)

    def no_network(*args, **kwargs):
        raise AssertionError("Reviewing saved results must never repoll /search")

    monkeypatch.setattr(evaluation.httpx, "Client", no_network)
    with pytest.raises(SystemExit) as error:
        evaluation.main()
    assert error.value.code == exit_code
    output = capsys.readouterr().out
    if mode == "stale":
        assert "changed since the run" in output
    elif mode == "before_ungraded":
        assert '"human_comparison_available": false' in output
