"""status.json / history.jsonl schema and durability tests."""

import json

import pytest

from osxphotos_runner import status
from osxphotos_runner.backup import RunResult
from osxphotos_runner.stats import coverage_counts


def _run(**overrides) -> RunResult:
    defaults = dict(outcome="succeeded", started_at="2026-07-07T08:00:00-07:00", duration_s=42)
    return RunResult(**{**defaults, **overrides})


def test_build_status_schema():
    st = status.build_status(
        _run().to_dict(),
        library={"library_total": 20315, "missing": 0},
        coverage={"exported_in_library": 758, "library_total": 20315},
        schedule={"interval_days": 7, "next_run": "2026-07-14T08:00:00-07:00"},
        app={"state": "idle", "version": "0.1.0"},
    )
    assert st["schema_version"] == 1
    assert set(st) == {"schema_version", "last_run", "library", "coverage", "schedule", "app"}
    assert st["last_run"]["outcome"] == "succeeded"


def test_write_and_read_status_roundtrip(tmp_path):
    path = tmp_path / "status.json"
    st = status.build_status(_run().to_dict())
    status.write_status(st, path)
    assert status.read_status(path) == st
    assert not path.with_suffix(".json.tmp").exists()  # atomic write cleaned up


def test_read_status_missing(tmp_path):
    assert status.read_status(tmp_path / "nope.json") is None


def test_history_append_and_last_run(tmp_path):
    path = tmp_path / "history.jsonl"
    status.append_history(_run(), path)
    status.append_history(_run(outcome="failed", failure_reason="boom"), path)
    history = status.read_history(path)
    assert len(history) == 2
    assert history[0]["outcome"] == "succeeded"
    assert status.last_run(path)["failure_reason"] == "boom"


def test_history_every_outcome_recorded_including_failures(tmp_path):
    path = tmp_path / "history.jsonl"
    for outcome in ("succeeded", "failed", "interrupted"):
        status.append_history(_run(outcome=outcome), path)
    assert [e["outcome"] for e in status.read_history(path)] == ["succeeded", "failed", "interrupted"]


def test_history_tolerates_torn_final_line(tmp_path):
    path = tmp_path / "history.jsonl"
    status.append_history(_run(), path)
    with open(path, "a") as f:
        f.write('{"outcome": "succe')  # crash mid-append
    assert len(status.read_history(path)) == 1
    assert status.last_run(path)["outcome"] == "succeeded"


def test_history_empty_when_missing(tmp_path):
    assert status.read_history(tmp_path / "none.jsonl") == []
    assert status.last_run(tmp_path / "none.jsonl") is None


def test_coverage_counts_intersects_with_library():
    # ExportDB remembers deleted photos; they must not inflate coverage.
    exported = {"a", "b", "deleted-1", "deleted-2"}
    library = {"a", "b", "c"}
    assert coverage_counts(exported, library) == {"exported_in_library": 2, "library_total": 3}


def test_coverage_counts_when_export_db_unavailable():
    assert coverage_counts(None, {"a"}) == {"exported_in_library": None, "library_total": 1}
