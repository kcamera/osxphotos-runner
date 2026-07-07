"""Canonical local status.json + history.jsonl.

These live in Application Support, never in the backup destination, so a
failed run (share down, NAS offline) is still recorded and publishable.
history.jsonl gets one line per run, every outcome, kept forever
(~52 lines/year — truncation would only destroy information).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import paths
from .backup import RunResult

SCHEMA_VERSION = 1


def status_path() -> Path:
    return paths.app_support_dir() / "status.json"


def history_path() -> Path:
    return paths.app_support_dir() / "history.jsonl"


def build_status(
    run: dict | None,
    *,
    library: dict | None = None,
    coverage: dict | None = None,
    schedule: dict | None = None,
    app: dict | None = None,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "last_run": run,
        "library": library,
        "coverage": coverage,
        "schedule": schedule,
        "app": app,
    }


def write_status(status: dict, path: Path | None = None) -> Path:
    """Atomic write: the publisher and dashboard must never see a torn file."""
    path = path or status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(status, indent=2) + "\n")
    os.replace(tmp, path)
    return path


def read_status(path: Path | None = None) -> dict | None:
    path = path or status_path()
    if not path.exists():
        return None
    return json.loads(path.read_text())


def append_history(run: RunResult | dict, path: Path | None = None) -> Path:
    path = path or history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = run.to_dict() if isinstance(run, RunResult) else run
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return path


def read_history(path: Path | None = None) -> list[dict]:
    """All runs, oldest first. Tolerates a torn final line (crash mid-append)."""
    path = path or history_path()
    if not path.exists():
        return []
    entries = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def last_run(path: Path | None = None) -> dict | None:
    history = read_history(path)
    return history[-1] if history else None
