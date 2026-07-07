"""SMB mount preflight for the backup destination.

The one rule that matters: never let an export run against an unmounted
/Volumes path — osxphotos would silently re-export the whole library onto
the local disk. So before every run we verify, via statfs, that the
destination sits on a live smbfs mount whose share matches, and if not we
mount it ourselves with NetFS (the same service Finder uses, so it reuses
the Keychain credentials saved by the one-time manual Finder mount).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

VOLUMES = "/Volumes"


class MountError(Exception):
    """Destination is not (and could not be made) a verified, writable SMB mount."""


# --- statfs(2) via ctypes ---------------------------------------------------

_MFSTYPENAMELEN = 16
_MAXPATHLEN = 1024


class _StatFS(ctypes.Structure):
    # struct statfs, 64-bit-inode layout (the only one on modern macOS)
    _fields_ = [
        ("f_bsize", ctypes.c_uint32),
        ("f_iosize", ctypes.c_int32),
        ("f_blocks", ctypes.c_uint64),
        ("f_bfree", ctypes.c_uint64),
        ("f_bavail", ctypes.c_uint64),
        ("f_files", ctypes.c_uint64),
        ("f_ffree", ctypes.c_uint64),
        ("f_fsid", ctypes.c_int32 * 2),
        ("f_owner", ctypes.c_uint32),
        ("f_type", ctypes.c_uint32),
        ("f_flags", ctypes.c_uint32),
        ("f_fssubtype", ctypes.c_uint32),
        ("f_fstypename", ctypes.c_char * _MFSTYPENAMELEN),
        ("f_mntonname", ctypes.c_char * _MAXPATHLEN),
        ("f_mntfromname", ctypes.c_char * _MAXPATHLEN),
        ("f_flags_ext", ctypes.c_uint32),
        ("f_reserved", ctypes.c_uint32 * 7),
    ]


@dataclass(frozen=True)
class MountInfo:
    fstype: str  # e.g. "smbfs", "apfs"
    source: str  # e.g. "//kcamera@NAS._smb._tcp.local/camera"
    mountpoint: str  # e.g. "/Volumes/camera"


def statfs(path: str | Path) -> MountInfo:
    """Return filesystem info for the mount containing *path*."""
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    try:
        fn = libc["statfs$INODE64"]  # x86_64 symbol name
    except AttributeError:
        fn = libc.statfs  # arm64: plain statfs is already the 64-bit layout
    fn.argtypes = [ctypes.c_char_p, ctypes.POINTER(_StatFS)]
    buf = _StatFS()
    if fn(os.fsencode(str(path)), ctypes.byref(buf)) != 0:
        err = ctypes.get_errno()
        raise MountError(f"statfs({path}) failed: {os.strerror(err)}")
    return MountInfo(
        fstype=buf.f_fstypename.decode(),
        source=buf.f_mntfromname.decode(),
        mountpoint=buf.f_mntonname.decode(),
    )


# --- share/URL derivation ---------------------------------------------------


def share_name_from_dest(dest: str | Path) -> str:
    """'/Volumes/camera/Photo Library Backup/' -> 'camera'."""
    vparts = Path(VOLUMES).parts
    parts = Path(dest).parts
    if len(parts) <= len(vparts) or parts[: len(vparts)] != vparts:
        raise MountError(f"destination is not under {VOLUMES}: {dest}")
    return parts[len(vparts)]


def host_from_publish_target(publish_target: str) -> str:
    """'kcamera@nas:/srv/dashboard/data' -> 'nas'. Local paths have no host."""
    head = publish_target.split(":", 1)[0]
    if ":" not in publish_target or "/" in head:
        raise MountError(f"publish target has no ssh host to derive from: {publish_target}")
    return head.rsplit("@", 1)[-1]


def derive_smb_url(dest: str | Path, publish_target: str) -> str:
    return f"smb://{host_from_publish_target(publish_target)}/{share_name_from_dest(dest)}"


# --- verification + mounting ------------------------------------------------


def verify_smb_dest(dest: str | Path) -> MountInfo:
    """Check that *dest*'s volume is a live smbfs mount of the expected share.

    Guards the failure modes seen in V1: a stale local directory left at the
    mountpoint (fstype would be apfs, not smbfs) and the share remounted at
    /Volumes/<share>-1 (mountpoint would not match).
    """
    share = share_name_from_dest(dest)
    expected_mountpoint = f"{VOLUMES}/{share}"
    if not os.path.isdir(expected_mountpoint):
        raise MountError(f"{expected_mountpoint} does not exist (share not mounted)")
    info = statfs(expected_mountpoint)
    if info.fstype != "smbfs":
        raise MountError(
            f"{expected_mountpoint} is {info.fstype}, not smbfs — refusing "
            "(a local directory is squatting on the mountpoint)"
        )
    # The mounted source's share must match; the host part is left loose
    # because Finder mounts record it as e.g. NAS._smb._tcp.local, not "nas".
    if not info.source.lower().rstrip("/").endswith(f"/{share.lower()}"):
        raise MountError(f"{expected_mountpoint} is a mount of {info.source}, expected share '{share}'")
    if info.mountpoint != expected_mountpoint:
        raise MountError(f"share '{share}' is mounted at {info.mountpoint}, not {expected_mountpoint}")
    return info


def netfs_mount(smb_url: str) -> list[str]:
    """Mount *smb_url* the way Finder does; credentials come from the Keychain."""
    import Foundation  # deferred: pyobjc only needed when a mount is attempted
    from NetFS import NetFSMountURLSync

    nsurl = Foundation.NSURL.URLWithString_(smb_url)
    if nsurl is None:
        raise MountError(f"invalid SMB URL: {smb_url}")
    status, mountpoints = NetFSMountURLSync(nsurl, None, None, None, None, None, None)
    if status != 0:
        raise MountError(f"NetFS mount of {smb_url} failed (status {status})")
    return list(mountpoints or [])


def check_writable(dest: str | Path) -> None:
    dest = Path(dest)
    if not dest.is_dir():
        raise MountError(f"destination folder missing on the share: {dest}")
    probe = dest / f".osxphotos-runner-write-probe-{uuid.uuid4().hex[:8]}"
    try:
        probe.touch()
        probe.unlink()
    except OSError as e:
        raise MountError(f"destination not writable: {dest}: {e}") from e


def ensure_mounted(dest: str | Path, smb_url: str | None) -> MountInfo:
    """Verify the destination mount, mounting it via NetFS if needed."""
    try:
        info = verify_smb_dest(dest)
    except MountError:
        if smb_url is None:
            raise
        netfs_mount(smb_url)
        # NetFSMountURLSync returns when done, but give the volume a beat to register.
        last: MountError | None = None
        for _ in range(5):
            try:
                info = verify_smb_dest(dest)
                break
            except MountError as e:
                last = e
                time.sleep(1)
        else:
            raise MountError(f"mounted {smb_url} but verification still fails: {last}") from last
    check_writable(dest)
    return info


def preflight(dest: str | Path, smb_url: str | None) -> MountInfo | None:
    """Full destination preflight.

    Destinations under /Volumes get the mount verification (+ auto-mount);
    anywhere else (local test dirs) just needs to exist and be writable.
    """
    if str(dest).startswith(VOLUMES + "/"):
        return ensure_mounted(dest, smb_url)
    check_writable(dest)
    return None
