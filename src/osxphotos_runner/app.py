"""Menu bar app: rumps UI wrapped around the scheduler.

The app IS the scheduler. A 60-second rumps.Timer (kept honest by an
NSProcessInfo activity so App Nap can't stretch it) fires a run whenever
now >= last run started + interval, with the last run read from local
history — so the schedule survives restarts and reboots. Runs happen in a
background thread; a non-blocking lock makes scheduled runs and Back Up
Now mutually exclusive. UI state is only touched from the main-thread tick.
"""

from __future__ import annotations

import subprocess
import threading
from datetime import datetime, timedelta

import rumps

from . import paths, runner, status

TICK_SECONDS = 60.0
FIRST_RUN_SETTLE = timedelta(minutes=5)

TITLES = {"idle": "📷", "running": "📷◉", "error": "📷⚠"}


def next_run_at(
    last_started: datetime | None,
    interval: timedelta,
    launched_at: datetime,
    settle: timedelta = FIRST_RUN_SETTLE,
) -> datetime:
    """When the next scheduled run is due. First run ever: soon after launch."""
    if last_started is None:
        return launched_at + settle
    return last_started + interval


def last_started_from_history() -> datetime | None:
    entry = status.last_run()
    if not entry or not entry.get("started_at"):
        return None
    try:
        return datetime.fromisoformat(entry["started_at"])
    except ValueError:
        return None


def _fmt_age(dt: datetime, now: datetime) -> str:
    seconds = (now - dt).total_seconds()
    if seconds < 90 * 60:
        return f"{max(0, round(seconds / 60))} min ago"
    if seconds < 36 * 3600:
        return f"{round(seconds / 3600)} h ago"
    return f"{round(seconds / 86400)} d ago"


class RunnerApp(rumps.App):
    def __init__(
        self,
        dest: str,
        publish_target: str | None = None,
        *,
        interval_days: float = 7.0,
        smb_url: str | None = None,
        from_date: str | None = None,
    ):
        super().__init__(TITLES["idle"], quit_button=rumps.MenuItem("Quit"))
        self.dest = dest
        self.publish_target = publish_target
        self.smb_url = smb_url
        self.from_date = from_date  # testing only; production exports are unbounded
        self.interval = timedelta(days=interval_days)
        self.launched_at = datetime.now().astimezone()

        self._run_lock = threading.Lock()
        self._state = "idle"

        self.mi_last = rumps.MenuItem("Last backup: …")
        self.mi_coverage = rumps.MenuItem("Coverage: …")
        self.mi_next = rumps.MenuItem("Next run: …")
        self.mi_backup_now = rumps.MenuItem("Back Up Now", callback=self.on_backup_now)
        self.mi_open_logs = rumps.MenuItem("Open Logs", callback=self.on_open_logs)
        self.menu = [self.mi_last, self.mi_coverage, self.mi_next, None, self.mi_backup_now, self.mi_open_logs]

        paths.ensure_dirs()
        interrupted = runner.recover_interrupted()
        if interrupted:
            self._state = "error"

        self._keep_awake()
        self.timer = rumps.Timer(self.tick, TICK_SECONDS)
        self.timer.start()
        self.tick()

    def _keep_awake(self) -> None:
        """Opt out of App Nap (idle *system* sleep stays allowed — pmset owns that)."""
        from Foundation import NSActivityUserInitiatedAllowingIdleSystemSleep, NSProcessInfo

        self._activity = NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
            NSActivityUserInitiatedAllowingIdleSystemSleep, "osxphotos-runner backup schedule"
        )

    # --- scheduling (main thread) -------------------------------------------

    def tick(self, _timer=None) -> None:
        now = datetime.now().astimezone()
        due = next_run_at(last_started_from_history(), self.interval, self.launched_at)
        if self._state != "running" and now >= due:
            self._start_run()
        self._refresh_menu(now, due)

    def _start_run(self) -> None:
        if not self._run_lock.acquire(blocking=False):
            return
        self._state = "running"
        threading.Thread(target=self._run_thread, name="backup-run", daemon=True).start()

    def _run_thread(self) -> None:
        try:
            started = datetime.now().astimezone()
            result = runner.perform_run(
                self.dest,
                self.publish_target,
                smb_url=self.smb_url,
                from_date=self.from_date,
                schedule={
                    "interval_days": self.interval.days + self.interval.seconds / 86400,
                    "next_run": (started + self.interval).isoformat(timespec="seconds"),
                },
                app_state="menubar",
            )
            self._state = "idle" if result.outcome == "succeeded" else "error"
        except Exception:
            self._state = "error"
        finally:
            self._run_lock.release()

    # --- menu (main thread) ---------------------------------------------------

    def _refresh_menu(self, now: datetime, due: datetime) -> None:
        self.title = TITLES[self._state]
        last = status.last_run()
        if last:
            started = last_started_from_history()
            age = _fmt_age(started, now) if started else "?"
            if last.get("outcome") == "succeeded":
                self.mi_last.title = f"Last backup: {age} — {last.get('exported', 0)} files exported"
            else:
                self.mi_last.title = f"Last backup: {last.get('outcome')} {age}"
        else:
            self.mi_last.title = "Last backup: never"

        st = status.read_status() or {}
        cov = st.get("coverage") or {}
        if cov.get("exported_in_library") is not None:
            self.mi_coverage.title = f"Coverage: {cov['exported_in_library']} / {cov['library_total']} photos"
        else:
            self.mi_coverage.title = "Coverage: unknown"

        if self._state == "running":
            self.mi_next.title = "Backup running…"
        else:
            self.mi_next.title = f"Next run: {due.astimezone().strftime('%a %b %-d %H:%M')}"

    # --- menu actions -----------------------------------------------------------

    def on_backup_now(self, _item) -> None:
        self._start_run()

    def on_open_logs(self, _item) -> None:
        subprocess.Popen(["open", str(paths.logs_dir())])
