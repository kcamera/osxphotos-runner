"""Publish status.json + history.jsonl to the dashboard data dir.

Runs after every backup outcome, success or failure, so the dashboard
always reflects reality. Only these two files are ever published. The
target is either 'user@host:/path' (rsync over ssh) or a plain local
path, distinguished by the ':' host syntax.

Headless discipline (same rule as the NoUI NetFS mount): everything must
fail fast rather than wait for input nobody can give — BatchMode ssh, a
connect timeout, and a hard subprocess timeout.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import status

SSH_OPTIONS = "ssh -o BatchMode=yes -o ConnectTimeout=10"


class PublishError(Exception):
    """Status files could not be delivered to the dashboard data dir."""


def is_remote(target: str) -> bool:
    """'kcamera@nas:/srv/data' -> True; '/srv/data' or 'relative/dir' -> False."""
    head, sep, _ = target.partition(":")
    return bool(sep) and "/" not in head


def publish(target: str, *, files: list[Path] | None = None, timeout_s: int = 120) -> None:
    """rsync the status files into *target* (a directory)."""
    files = files if files is not None else [status.status_path(), status.history_path()]
    missing = [str(f) for f in files if not f.exists()]
    if missing:
        raise PublishError(f"nothing to publish, missing: {', '.join(missing)}")

    # --ignore-times: always transfer. The files are tiny, and rsync's
    # size+mtime quick-check can wrongly skip a same-second status rewrite.
    cmd = ["rsync", "--times", "--ignore-times"]
    if is_remote(target):
        cmd += ["-e", SSH_OPTIONS]
    else:
        # The remote dir is Phase 8's setup job; a local dir we can make ourselves.
        try:
            Path(target).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise PublishError(f"cannot create local target dir {target}: {e}") from e
    cmd += [str(f) for f in files]
    cmd.append(target.rstrip("/") + "/")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        raise PublishError(f"rsync to {target} timed out after {timeout_s}s") from e
    except OSError as e:
        raise PublishError(f"could not run rsync: {e}") from e
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        raise PublishError(
            f"rsync to {target} exited {proc.returncode}: {detail[-1] if detail else 'no output'}"
        )
