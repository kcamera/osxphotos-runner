#!/usr/bin/env bash
# Reverse everything install.sh does: unload + remove the LaunchAgent,
# remove the venv, remove the logs.
#   ./scripts/uninstall.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.kcamera.osxphotos-runner"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGS_DIR="$HOME/Library/Logs/osxphotos-runner"

echo "==> Unloading LaunchAgent"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || echo "    (was not loaded)"

echo "==> Removing $PLIST"
rm -f "$PLIST"

echo "==> Removing $REPO_ROOT/.venv"
rm -rf "$REPO_ROOT/.venv"

echo "==> Removing $LOGS_DIR"
rm -rf "$LOGS_DIR"

echo
echo "Uninstalled. Deliberately left in place:"
echo "  - this repo clone ($REPO_ROOT)"
echo "  - the backup data on the NAS share"
echo "  - status/history in '$HOME/Library/Application Support/osxphotos-runner/'"
echo "  - manual grants/settings (Full Disk Access, auto-login, pmset, Keychain)"
