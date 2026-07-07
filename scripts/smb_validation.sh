#!/usr/bin/env bash
# Phase 1 validation experiment (see the project plan).
#
# Settles whether exporting directly to the SMB-mounted NAS share
# reproduces V1's "(1)" filename-suffix problem now that the library uses
# Download Originals. Exports a bounded ~2-month subset of the real
# library, directly to the real backup destination, twice in a row, and
# checks for suffix collisions, sidecar presence, and --touch-file mtime
# behavior.
#
# Run this ON the Mac Mini, from the repo root:
#   ./scripts/smb_validation.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DEST="/Volumes/camera/Photo Library Backup/"
MOUNT_MARKER="/Volumes/camera"
FROM_DATE="$(date -v-2m +%Y-%m-%d)"
RESULTS_DIR="$REPO_ROOT/tests/fixtures/smb_validation"
mkdir -p "$RESULTS_DIR"

if ! mount | grep -q "on ${MOUNT_MARKER} "; then
    echo "FAIL: ${MOUNT_MARKER} is not mounted. Refusing to export (would write to local disk instead)." >&2
    exit 1
fi

if [ ! -d "$DEST" ]; then
    echo "FAIL: destination does not exist: $DEST" >&2
    exit 1
fi

EXPORT_ARGS=(
    export "$DEST"
    --update
    --not-shared
    --not-shared-library
    --export-aae
    --sidecar xmp
    --touch-file
    --filename 'IMG_{created.date}_{created.hour}-{created.min}-{created.sec}_{uuid|chop(28)}'
    --directory '{created.year}'
    --no-progress
    --verbose
    --from-date "$FROM_DATE"
)

run_pass() {
    local n="$1"
    local report="$RESULTS_DIR/report_pass${n}.json"
    local stdout_log="$RESULTS_DIR/stdout_pass${n}.log"
    echo
    echo "=== Pass $n: exporting from $FROM_DATE to $DEST ==="
    local start end
    start=$(date +%s)
    uv run osxphotos "${EXPORT_ARGS[@]}" --report "$report" 2>&1 | tee "$stdout_log"
    end=$(date +%s)
    echo "Pass $n duration: $((end - start))s" | tee -a "$stdout_log"
}

run_pass 1
run_pass 2

echo
echo "=== Checking for V1's '(N)' filename-suffix problem ==="
SUFFIX_HITS=$(find "$DEST" -type f \( -name '* (1).*' -o -name '* (2).*' -o -name '* (3).*' \) 2>/dev/null || true)
if [ -n "$SUFFIX_HITS" ]; then
    echo "FAIL: found duplicate-suffixed files:"
    echo "$SUFFIX_HITS"
else
    echo "PASS: no '(N)'-style suffixed files found."
fi

echo
echo "=== Checking sidecar files exist ==="
AAE_COUNT=$(find "$DEST" -name '*.aae' | wc -l | tr -d ' ')
XMP_COUNT=$(find "$DEST" -name '*.xmp' | wc -l | tr -d ' ')
echo "AAE sidecars found: $AAE_COUNT"
echo "XMP sidecars found: $XMP_COUNT"
if [ "$AAE_COUNT" -eq 0 ] || [ "$XMP_COUNT" -eq 0 ]; then
    echo "WARNING: expected both AAE and XMP sidecars to be non-zero (unless the sample has no edited/RAW photos in range)."
fi

echo
echo "=== Checking --touch-file mtime behavior (heuristic) ==="
SAMPLE_FILE=$(find "$DEST" -type f \( -iname '*.jpg' -o -iname '*.heic' -o -iname '*.png' \) | head -1)
if [ -n "$SAMPLE_FILE" ]; then
    MTIME=$(stat -f '%Sm' -t '%Y-%m-%d' "$SAMPLE_FILE")
    TODAY=$(date +%Y-%m-%d)
    echo "Sample file: $SAMPLE_FILE"
    echo "  mtime: $MTIME   (today: $TODAY)"
    if [ "$MTIME" = "$TODAY" ]; then
        echo "  WARNING: mtime matches today's date - --touch-file may not be sticking on SMB. Verify manually against a few files' actual capture dates."
    else
        echo "  OK: mtime differs from today, consistent with --touch-file setting the capture date. Spot-check a few against Photos.app manually."
    fi
else
    echo "No sample image file found to check."
fi

echo
echo "=== Pass summary lines (Rich markup stripped) ==="
for n in 1 2; do
    echo "--- Pass $n ---"
    grep -oE 'Processed:.*' "$RESULTS_DIR/stdout_pass${n}.log" | sed -E 's/\[[^]]*\]//g' | tail -1
done

echo
echo "Fixtures and logs saved under: $RESULTS_DIR"
echo "Pass 2 should show ~0 exported and mostly skipped, confirming idempotency."
echo "Record the final verdict in plan/smb_validation_results.md (gitignored working note)."
