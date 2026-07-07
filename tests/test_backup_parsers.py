"""Parser tests against real osxphotos 0.76.1 output captured in Phase 1."""

from pathlib import Path

import pytest

from osxphotos_runner import backup

FIXTURES = Path(__file__).parent / "fixtures" / "smb_validation"


def test_parse_report_pass1_sample():
    counts = backup.parse_report(FIXTURES / "report_pass1_sample.json")
    assert counts == {
        "processed": 13,
        "exported": 18,
        "updated": 0,
        "skipped": 0,
        "missing": 0,
        "errors": 0,
        "touched": 27,
    }


def test_parse_report_pass2_sample_idempotent():
    counts = backup.parse_report(FIXTURES / "report_pass2_sample.json")
    assert counts["exported"] == 0
    assert counts["updated"] == 0
    assert counts["skipped"] == 19
    assert counts["errors"] == 0


def test_parse_summary_real_stdout_pass1():
    text = (FIXTURES / "stdout_pass1_tail.log").read_text()
    assert backup.parse_summary(text) == {
        "processed": 559,
        "exported": 758,
        "updated": 0,
        "skipped": 0,
        "missing": 0,
        "errors": 0,
        "touched": 1260,
    }


def test_parse_summary_real_stdout_pass2():
    counts = backup.parse_summary((FIXTURES / "stdout_pass2_tail.log").read_text())
    assert counts["exported"] == 0
    assert counts["skipped"] == 758


def test_parse_summary_strips_rich_markup():
    line = (
        "Processed: [num]12[/num] photos, exported: [num]3[/num], updated: [num]1[/num], "
        "skipped: [num]8[/num], updated EXIF data: [num]0[/num], missing: [num]0[/num], "
        "error: [num]0[/num], touched date: [num]4[/num]"
    )
    assert backup.parse_summary(line) == {
        "processed": 12,
        "exported": 3,
        "updated": 1,
        "skipped": 8,
        "missing": 0,
        "errors": 0,
        "touched": 4,
    }


def test_parse_summary_without_touch_date():
    line = (
        "Processed: 5 photos, exported: 5, updated: 0, skipped: 0, "
        "updated EXIF data: 0, missing: 0, error: 0"
    )
    counts = backup.parse_summary(line)
    assert counts["exported"] == 5
    assert counts["touched"] == 0


def test_parse_summary_takes_last_match():
    text = (
        "Processed: 1 photos, exported: 1, updated: 0, skipped: 0, "
        "updated EXIF data: 0, missing: 0, error: 0\nnoise\n"
        "Processed: 2 photos, exported: 2, updated: 0, skipped: 0, "
        "updated EXIF data: 0, missing: 0, error: 0"
    )
    assert backup.parse_summary(text)["processed"] == 2


def test_parse_summary_absent():
    assert backup.parse_summary("no summary here") is None


def test_cross_check_agreement_and_drift():
    report = backup.parse_report(FIXTURES / "report_pass1_sample.json")
    assert backup.cross_check(report, dict(report)) == ""
    drifted = dict(report, exported=report["exported"] + 1)
    msg = backup.cross_check(report, drifted)
    assert "exported" in msg
    assert backup.cross_check(report, None) == "no summary line found in stdout"


def test_build_export_command_flags():
    cmd = backup.build_export_command("/tmp/dest", "/tmp/report.json", from_date="2026-05-07", dry_run=True)
    joined = " ".join(cmd)
    for flag in (
        "--update",
        "--not-shared",
        "--not-shared-library",
        "--export-aae",
        "--touch-file",
        "--no-progress",
        "--dry-run",
        "--from-date 2026-05-07",
        "--sidecar xmp",
    ):
        assert flag in joined
    assert "--exiftool" not in joined
    cmd_prod = backup.build_export_command("/tmp/dest", "/tmp/report.json")
    assert "--dry-run" not in cmd_prod
    assert "--from-date" not in cmd_prod
