"""CLI entry point: `python -m osxphotos_runner <command> ...`.

Commands: menubar (the LaunchAgent runs this), run-once, status. Only the
two plist arguments (dest, publish target) configure anything; the rest is
derived.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import mount, runner, status


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("dest", help="backup destination, e.g. '/Volumes/camera/Photo Library Backup/'")
    p.add_argument(
        "publish_target",
        nargs="?",
        default=None,
        help="rsync target for status publishing, e.g. 'kcamera@nas:/path' (also used to derive the SMB host)",
    )
    p.add_argument("--smb-url", default=None, help="override the derived SMB mount URL")
    p.add_argument("--from-date", default=None, help="bound the export (testing only, never in production)")


def _smb_url(args: argparse.Namespace) -> str | None:
    if args.smb_url:
        return args.smb_url
    if args.publish_target:
        try:
            return mount.derive_smb_url(args.dest, args.publish_target)
        except mount.MountError:
            return None
    return None


def cmd_run_once(args: argparse.Namespace) -> int:
    interrupted = runner.recover_interrupted()
    if interrupted:
        print(f"note: recorded previous run as interrupted ({interrupted['started_at']})", file=sys.stderr)
    result = runner.perform_run(
        args.dest,
        args.publish_target,
        smb_url=_smb_url(args),
        from_date=args.from_date,
        dry_run=args.dry_run,
        schedule=None,  # owned by the menu bar scheduler
        app_state="run-once",
    )
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.outcome == "succeeded" else 1


def cmd_menubar(args: argparse.Namespace) -> int:
    from . import app  # deferred: rumps/AppKit only load for the real app

    app.RunnerApp(
        args.dest,
        args.publish_target,
        interval_days=args.interval_days,
        smb_url=_smb_url(args),
        from_date=args.from_date,
    ).run()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    st = status.read_status()
    if st is None:
        print("no status recorded yet (no run has completed on this machine)", file=sys.stderr)
        return 1
    print(json.dumps(st, indent=2))
    history = status.read_history()
    if history:
        print(f"\n{len(history)} run(s) in history; last 5:", file=sys.stderr)
        for entry in history[-5:]:
            print(
                f"  {entry.get('started_at')}  {entry.get('outcome')}  "
                f"exported={entry.get('exported')} errors={entry.get('errors')}",
                file=sys.stderr,
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="osxphotos-runner")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run-once", help="run a single backup now and print the RunResult as JSON")
    _add_common(p_run)
    p_run.add_argument("--dry-run", action="store_true", help="pass --dry-run to osxphotos export; nothing is recorded")
    p_run.set_defaults(func=cmd_run_once)

    p_menubar = sub.add_parser("menubar", help="run the menu bar app + weekly scheduler (LaunchAgent entry point)")
    _add_common(p_menubar)
    p_menubar.add_argument("--interval-days", type=float, default=7.0, help="days between scheduled runs")
    p_menubar.set_defaults(func=cmd_menubar)

    p_status = sub.add_parser("status", help="print the local status.json and recent history")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
