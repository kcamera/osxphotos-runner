"""CLI entry point: `python -m osxphotos_runner <command> ...`.

Commands: menubar (Phase 5), run-once, status (Phase 3). Only the two plist
arguments (dest, publish target) configure anything; the rest is derived.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from . import backup, mount, paths


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("dest", help="backup destination, e.g. '/Volumes/camera/Photo Library Backup/'")
    p.add_argument(
        "publish_target",
        nargs="?",
        default=None,
        help="rsync target for status publishing, e.g. 'kcamera@nas:/path' (also used to derive the SMB host)",
    )
    p.add_argument("--smb-url", default=None, help="override the derived SMB mount URL")


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
    paths.ensure_dirs()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    result = backup.run_backup(
        args.dest,
        smb_url=_smb_url(args),
        report_path=paths.runs_dir() / f"run-{run_id}-report.json",
        log_path=paths.logs_dir() / f"run-{run_id}.log",
        from_date=args.from_date,
        dry_run=args.dry_run,
    )
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.outcome == "succeeded" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="osxphotos-runner")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run-once", help="run a single backup now and print the RunResult as JSON")
    _add_common(p_run)
    p_run.add_argument("--from-date", default=None, help="bound the export (testing only, never in production)")
    p_run.add_argument("--dry-run", action="store_true", help="pass --dry-run to osxphotos export")
    p_run.set_defaults(func=cmd_run_once)

    for name, phase in (("menubar", "Phase 5"), ("status", "Phase 3")):
        p = sub.add_parser(name, help=f"not yet implemented ({phase})")
        p.set_defaults(func=lambda a, n=name: (print(f"{n}: not implemented yet", file=sys.stderr), 2)[1])

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
