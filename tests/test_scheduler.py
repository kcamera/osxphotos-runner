"""Scheduler math and interrupted-run recovery."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from osxphotos_runner import paths, runner, status
from osxphotos_runner.app import FIRST_RUN_SETTLE, next_run_at

TZ = timezone.utc
NOW = datetime(2026, 7, 8, 12, 0, tzinfo=TZ)
WEEK = timedelta(days=7)


def test_next_run_first_ever_is_soon_after_launch():
    assert next_run_at(None, WEEK, launched_at=NOW) == NOW + FIRST_RUN_SETTLE


def test_next_run_is_last_start_plus_interval():
    last = NOW - timedelta(days=3)
    assert next_run_at(last, WEEK, launched_at=NOW) == last + WEEK


def test_next_run_overdue_stays_in_past():
    # Mini was off for two weeks: due date is in the past, so the first tick fires.
    last = NOW - timedelta(days=14)
    assert next_run_at(last, WEEK, launched_at=NOW) < NOW


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_support_dir", lambda: tmp_path)
    return tmp_path


def test_recover_no_marker_is_noop(isolated_state):
    assert runner.recover_interrupted() is None


def test_recover_stale_marker_records_interrupted(isolated_state):
    runner.marker_path().write_text(json.dumps({"started_at": "2026-07-01T03:00:00-07:00"}))
    entry = runner.recover_interrupted()
    assert entry["outcome"] == "interrupted"
    assert not runner.marker_path().exists()
    history = status.read_history()
    assert len(history) == 1
    assert history[0]["outcome"] == "interrupted"
    assert history[0]["started_at"] == "2026-07-01T03:00:00-07:00"


def test_recover_marker_matching_completed_run_is_noop(isolated_state):
    # Died between history append and marker cleanup: run completed, no extra entry.
    started = "2026-07-01T03:00:00-07:00"
    status.append_history({"outcome": "succeeded", "started_at": started})
    runner.marker_path().write_text(json.dumps({"started_at": started}))
    assert runner.recover_interrupted() is None
    assert not runner.marker_path().exists()
    assert len(status.read_history()) == 1


def test_recover_corrupt_marker_still_records(isolated_state):
    runner.marker_path().write_text("not json{")
    entry = runner.recover_interrupted()
    assert entry["outcome"] == "interrupted"
    assert not runner.marker_path().exists()
