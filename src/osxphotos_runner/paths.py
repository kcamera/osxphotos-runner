"""Well-known local directories for the runner.

Canonical status/history lives locally (Application Support), never in the
backup destination, so failures are still recorded when the share is down.
"""

from pathlib import Path

APP_NAME = "osxphotos-runner"


def app_support_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / APP_NAME


def runs_dir() -> Path:
    return app_support_dir() / "runs"


def logs_dir() -> Path:
    return Path.home() / "Library" / "Logs" / APP_NAME


def ensure_dirs() -> None:
    for d in (app_support_dir(), runs_dir(), logs_dir()):
        d.mkdir(parents=True, exist_ok=True)
