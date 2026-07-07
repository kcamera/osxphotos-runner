"""Run one osxphotos export and turn its output into a RunResult.

The --report JSON is the machine interface (report-primary); the stdout
summary line is a cross-check only. When stdout is piped, osxphotos emits
plain text — the Rich-markup stripping is purely defensive.

Report row semantics, verified against osxphotos 0.76.1 (Phase 1 fixtures):
rows are per *file*, including .xmp sidecars. The stdout summary's
exported/updated/skipped/missing count only non-XMP rows; "processed" is
the number of distinct photo UUIDs; "touched date" sums over all rows.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import mount

RICH_MARKUP_RE = re.compile(r"\[/?\w[^\]]*\]")
SUMMARY_RE = re.compile(
    r"Processed:\s*(?P<processed>\d+)\s*photos?,\s*"
    r"exported:\s*(?P<exported>\d+),\s*"
    r"updated:\s*(?P<updated>\d+),\s*"
    r"skipped:\s*(?P<skipped>\d+),\s*"
    r"updated EXIF data:\s*(?P<exif_updated>\d+),\s*"
    r"missing:\s*(?P<missing>\d+),\s*"
    r"errors?:\s*(?P<errors>\d+)"
    r"(?:,\s*touched date:\s*(?P<touched>\d+))?"
)

# Settled in the project brief; do not re-derive. {uuid|chop(28)} keeps the
# first 8 hex chars of the UUID — enough to disambiguate same-second captures.
FILENAME_TEMPLATE = "IMG_{created.date}_{created.hour}-{created.min}-{created.sec}_{uuid|chop(28)}"
DIRECTORY_TEMPLATE = "{created.year}"

COUNT_FIELDS = ("processed", "exported", "updated", "skipped", "missing", "errors", "touched")


@dataclass
class RunResult:
    outcome: str  # succeeded | failed | interrupted
    started_at: str  # ISO 8601 with offset
    duration_s: int = 0
    processed: int = 0
    exported: int = 0  # counts FILES (media + AAE), not photos
    updated: int = 0
    skipped: int = 0
    missing: int = 0
    errors: int = 0
    touched: int = 0
    failure_reason: str = ""
    summary_mismatch: str = ""  # non-empty if the stdout cross-check disagreed
    report_path: str = ""
    log_path: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def build_export_command(
    dest: str | Path,
    report_path: str | Path,
    *,
    from_date: str | None = None,
    dry_run: bool = False,
) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "osxphotos",
        "export",
        str(dest),
        "--update",
        "--not-shared",
        "--not-shared-library",
        "--export-aae",
        "--sidecar",
        "xmp",
        "--touch-file",
        "--filename",
        FILENAME_TEMPLATE,
        "--directory",
        DIRECTORY_TEMPLATE,
        "--report",
        str(report_path),
        "--no-progress",
        "--verbose",
    ]
    if from_date:
        cmd += ["--from-date", from_date]
    if dry_run:
        cmd += ["--dry-run"]
    return cmd


def parse_report(report_path: str | Path) -> dict[str, int]:
    """Aggregate the per-file report rows into summary-equivalent counts."""
    rows = json.loads(Path(report_path).read_text())
    media = [r for r in rows if not r["filename"].lower().endswith(".xmp")]
    return {
        "processed": len({r["uuid"] for r in rows if r.get("uuid")}),
        "exported": sum(bool(r["exported"]) for r in media),
        "updated": sum(bool(r["updated"]) for r in media),
        "skipped": sum(bool(r["skipped"]) for r in media),
        "missing": sum(bool(r["missing"]) for r in media),
        "errors": sum(bool(r["error"]) for r in rows),
        "touched": sum(bool(r["touched"]) for r in rows),
    }


def parse_summary(stdout_text: str) -> dict[str, int] | None:
    """Extract the last 'Processed: ...' summary line; None if absent."""
    plain = RICH_MARKUP_RE.sub("", stdout_text)
    match = None
    for match in SUMMARY_RE.finditer(plain):
        pass
    if match is None:
        return None
    counts = {k: int(v) for k, v in match.groupdict(default="0").items()}
    counts.pop("exif_updated", None)
    return counts


def cross_check(report_counts: dict[str, int], summary_counts: dict[str, int] | None) -> str:
    """Compare report (primary) against stdout summary; describe any drift.

    A mismatch is recorded, not fatal — e.g. the library can gain a photo
    between the scan and the report being written.
    """
    if summary_counts is None:
        return "no summary line found in stdout"
    diffs = [
        f"{k}: report={report_counts[k]} stdout={summary_counts[k]}"
        for k in COUNT_FIELDS
        if k in summary_counts and report_counts.get(k) != summary_counts[k]
    ]
    return "; ".join(diffs)


def run_backup(
    dest: str | Path,
    *,
    smb_url: str | None = None,
    report_path: str | Path,
    log_path: str | Path,
    from_date: str | None = None,
    dry_run: bool = False,
) -> RunResult:
    """One full backup run: mount preflight, export subprocess, parse, verdict."""
    started = datetime.now().astimezone()
    t0 = time.monotonic()
    result = RunResult(
        outcome="failed",
        started_at=started.isoformat(timespec="seconds"),
        report_path=str(report_path),
        log_path=str(log_path),
    )

    def _done() -> RunResult:
        result.duration_s = round(time.monotonic() - t0)
        return result

    try:
        mount.preflight(dest, smb_url)
    except mount.MountError as e:
        result.failure_reason = f"mount preflight: {e}"
        return _done()

    cmd = build_export_command(dest, report_path, from_date=from_date, dry_run=dry_run)
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w") as log:
        log.write(f"# {' '.join(cmd)}\n")
        log.flush()
        proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, text=True)

    summary_counts = parse_summary(Path(log_path).read_text())
    if proc.returncode != 0:
        result.failure_reason = f"osxphotos export exited {proc.returncode} (see log)"
        return _done()

    try:
        counts = parse_report(report_path)
        result.summary_mismatch = cross_check(counts, summary_counts)
    except (OSError, json.JSONDecodeError, KeyError) as e:
        if summary_counts is None:
            result.failure_reason = f"export exited 0 but report unreadable ({e}) and no stdout summary"
            return _done()
        counts = summary_counts
        result.summary_mismatch = f"report unreadable ({e}); stdout summary used as fallback"

    for k in COUNT_FIELDS:
        setattr(result, k, counts.get(k, 0))
    result.outcome = "succeeded" if result.errors == 0 else "failed"
    if result.errors:
        result.failure_reason = f"{result.errors} file(s) reported errors (see report)"
    return _done()
