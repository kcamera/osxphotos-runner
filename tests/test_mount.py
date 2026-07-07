"""Mount preflight tests — pure derivation logic plus statfs against local paths."""

import pytest

from osxphotos_runner import mount


def test_share_name_from_dest():
    assert mount.share_name_from_dest("/Volumes/camera/Photo Library Backup/") == "camera"
    assert mount.share_name_from_dest("/Volumes/camera") == "camera"


def test_share_name_rejects_non_volumes_paths():
    for bad in ("/tmp/dest", "/Volumes", "relative/path"):
        with pytest.raises(mount.MountError):
            mount.share_name_from_dest(bad)


def test_host_from_publish_target():
    assert mount.host_from_publish_target("kcamera@nas:/srv/dashboard/data") == "nas"
    assert mount.host_from_publish_target("nas:/srv/data") == "nas"


def test_host_rejects_local_publish_targets():
    for bad in ("/srv/local/path", "relative/dir"):
        with pytest.raises(mount.MountError):
            mount.host_from_publish_target(bad)


def test_derive_smb_url():
    url = mount.derive_smb_url("/Volumes/camera/Photo Library Backup/", "kcamera@nas:/srv/data")
    assert url == "smb://nas/camera"


def test_statfs_on_root():
    info = mount.statfs("/")
    assert info.mountpoint == "/"
    assert info.fstype  # apfs on any modern Mac, but at minimum non-empty


def test_verify_rejects_local_fs_squatting(tmp_path, monkeypatch):
    # A destination whose "mount" is actually the local disk must be refused.
    monkeypatch.setattr(mount, "VOLUMES", str(tmp_path))
    dest = tmp_path / "camera" / "backup"
    dest.mkdir(parents=True)
    with pytest.raises(mount.MountError, match="not smbfs"):
        mount.verify_smb_dest(dest)


def test_verify_rejects_missing_mountpoint(monkeypatch, tmp_path):
    monkeypatch.setattr(mount, "VOLUMES", str(tmp_path))
    with pytest.raises(mount.MountError, match="not mounted"):
        mount.verify_smb_dest(tmp_path / "camera" / "backup")


def test_preflight_local_dir_checks_writability(tmp_path):
    assert mount.preflight(tmp_path, None) is None  # writable local dir passes
    with pytest.raises(mount.MountError, match="missing"):
        mount.preflight(tmp_path / "nope", None)
