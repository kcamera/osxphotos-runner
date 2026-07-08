"""One full backup run — the orchestration shared by run-once and the app.

Sequence: run-in-progress marker, mount preflight + export (backup.py),
history + stats + status (every outcome), publish, marker cleanup. A marker
left behind by a crash is converted to an 'interrupted' history entry at the
next launch by recover_interrupted().
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from importlib.metadata import version as pkg_version
from pathlib import Path

from . import backup, paths, publish, stats, status


def marker_path() -> Path:
    return paths.app_support_dir() / "run-in-progress.json"


def recover_interrupted() -> dict | None:
    """Turn a stale run-in-progress marker into an 'interrupted' history entry.

    Call at every launch. If the last history entry matches the marker's
    timestamp the run actually completed (we died between history append and
    marker cleanup), so only the marker is removed.
    """
    mp = marker_path()
    if not mp.exists():
        return None
    try:
        marker = json.loads(mp.read_text())
    except (OSError, json.JSONDecodeError):
        marker = {}
    mp.unlink(missing_ok=True)
    started_at = marker.get("started_at", "")
    last = status.last_run()
    if last and started_at and last.get("started_at") == started_at:
        return None
    entry = backup.RunResult(
        outcome="interrupted",
        started_at=started_at,
        failure_reason="run never finished (app or machine died mid-run)",
    ).to_dict()
    status.append_history(entry)
    return entry


def perform_run(
    dest: str,
    publish_target: str | None = None,
    *,
    smb_url: str | None = None,
    from_date: str | None = None,
    dry_run: bool = False,
    schedule: dict | None = None,
    app_state: str = "run-once",
) -> backup.RunResult:
    paths.ensure_dirs()
    started = datetime.now().astimezone()
    run_id = started.strftime("%Y%m%d-%H%M%S")

    if not dry_run:  # dry runs are rehearsals: never recorded as backups
        marker_path().write_text(
            json.dumps({"started_at": started.isoformat(timespec="seconds"), "run_id": run_id})
        )

    result = backup.run_backup(
        dest,
        smb_url=smb_url,
        report_path=paths.runs_dir() / f"run-{run_id}-report.json",
        log_path=paths.logs_dir() / f"run-{run_id}.log",
        from_date=from_date,
        dry_run=dry_run,
        started_at=started,
    )
    if dry_run:
        return result

    try:
        status.append_history(result)
        library = coverage = None
        if result.outcome == "succeeded":
            try:
                gathered = stats.gather(dest)
                library, coverage = gathered["library"], gathered["coverage"]
            except Exception as e:  # stats are best-effort; the backup already ran
                print(f"warning: stats refresh failed: {e}", file=sys.stderr)
        if library is None and (prev := status.read_status()):
            library, coverage = prev.get("library"), prev.get("coverage")
        status.write_status(
            status.build_status(
                result.to_dict(),
                library=library,
                coverage=coverage,
                schedule=schedule,
                app={"state": app_state, "version": pkg_version("osxphotos-runner")},
            )
        )
    finally:
        marker_path().unlink(missing_ok=True)

    if publish_target:
        try:
            publish.publish(publish_target)
        except publish.PublishError as e:
            # The backup itself already ran; a publish failure must not
            # change the run's outcome, only be visible.
            print(f"warning: publish failed: {e}", file=sys.stderr)
    return result
