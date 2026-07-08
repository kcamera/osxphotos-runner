#!/usr/bin/env bash
# Install (or update) the osxphotos-runner LaunchAgent on this Mac.
# Run from the repo root on the Mini, after `git clone` or `git pull`:
#   ./scripts/install.sh [dest] [publish-target]
#
# Re-running is safe: it re-syncs the venv, re-renders the plist, and
# reloads the agent. uv is a host prerequisite — this script never
# installs tooling. ./scripts/uninstall.sh reverses everything done here.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-/Volumes/camera/Photo Library Backup/}"
PUBLISH_TARGET="${2:-kcamera@nas:Websites/osxphotos-dashboard/data}"

LABEL="com.kcamera.osxphotos-runner"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
TEMPLATE="$REPO_ROOT/scripts/$LABEL.plist.template"
LOGS_DIR="$HOME/Library/Logs/osxphotos-runner"

# Non-interactive shells (SSH, LaunchAgent) don't get Homebrew on PATH.
UV="$(command -v uv || true)"
for candidate in /opt/homebrew/bin/uv /usr/local/bin/uv "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
    [ -n "$UV" ] && break
    [ -x "$candidate" ] && UV="$candidate"
done
if [ -z "$UV" ]; then
    echo "FAIL: uv not found. It is a host prerequisite — install it first (e.g. 'brew install uv')." >&2
    exit 1
fi

echo "==> Syncing Python environment ($UV sync)"
(cd "$REPO_ROOT" && "$UV" sync)

echo "==> Rendering LaunchAgent plist -> $PLIST"
mkdir -p "$HOME/Library/LaunchAgents" "$LOGS_DIR"
sed -e "s|__REPO__|$REPO_ROOT|g" \
    -e "s|__DEST__|$DEST|g" \
    -e "s|__PUBLISH_TARGET__|$PUBLISH_TARGET|g" \
    -e "s|__HOME__|$HOME|g" \
    "$TEMPLATE" > "$PLIST"
plutil -lint "$PLIST" >/dev/null

echo "==> (Re)loading LaunchAgent"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo
echo "Installed. The menu bar app is now running and will start at every login."
echo
echo "One-time manual prerequisites (not scriptable — verify each):"
echo "  1. Full Disk Access for: $REPO_ROOT/.venv/bin/python"
echo "     (System Settings > Privacy & Security > Full Disk Access; re-check after"
echo "      any Python interpreter upgrade — TCC grants detach when the binary changes)"
echo "  2. Automatic login enabled (LaunchAgents load at login, not boot)."
echo "  3. System sleep disabled (display sleep is fine): System Settings > Energy."
echo "  4. One manual Finder mount of smb://nas/camera with 'remember in Keychain',"
echo "     so the app's own mounts are credentialed."
