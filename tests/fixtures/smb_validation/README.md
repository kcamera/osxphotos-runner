# SMB validation fixtures (Phase 1)

Captured 2026-07-07 from a real bounded run of `scripts/smb_validation.sh` on
`mini.local` (osxphotos 0.76.1, Python 3.13), exporting `--from-date 2026-05-07`
directly to the SMB-mounted destination `/Volumes/camera/Photo Library Backup/`.

The full artifacts (1.2 MB reports, 400 KB logs) live untracked on the Mini at
`~/osxphotos-runner/tests/fixtures/smb_validation/`. The files here are trimmed
but structurally complete samples for parser unit tests.

## Files

- `report_pass1_sample.json` — first 30 rows of the pass-1 `--report` JSON plus
  the first AAE-written row and first XMP-sidecar row.
  Sample counts: rows=32, exported=32, new=18, updated=0, skipped=0, missing=0,
  errors=0, touched=27, aae_written=5, sidecar_xmp=14.
- `report_pass2_sample.json` — same trim of the pass-2 (idempotency) report.
  Sample counts: rows=33, exported=0, new=0, updated=0, skipped=33, missing=0,
  errors=0, touched=0, aae_written=0, sidecar_xmp=14.
- `stdout_pass1_tail.log` / `stdout_pass2_tail.log` — last 40 lines of each
  pass's stdout, including the `Processed: ...` summary line. Note: when stdout
  is piped (not a TTY), osxphotos/Rich emits plain text with no markup — the
  markup-stripping regex in the parser is defensive only.

## Full-run ground truth (for reference, not asserted in tests)

- Report rows per pass: 1382 (= 758 exported media/AAE files + 624 XMP rows).
- Pass 1 summary: `Processed: 559 photos, exported: 758, updated: 0, skipped: 0,
  updated EXIF data: 0, missing: 0, error: 0, touched date: 1260` (960s).
- Pass 2 summary: `Processed: 559 photos, exported: 0, updated: 0, skipped: 758,
  updated EXIF data: 0, missing: 0, error: 0, touched date: 0` (559s).
- AAE files on disk: 122 (uppercase `.AAE` extension), XMP: 624.
