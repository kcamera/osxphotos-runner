"""Publisher tests — local rsync targets plus remote/local classification."""

import json

import pytest

from osxphotos_runner import publish


def test_is_remote_classification():
    assert publish.is_remote("kcamera@nas:/srv/dashboard/data")
    assert publish.is_remote("nas:/srv/data")
    assert not publish.is_remote("/srv/local/dir")
    assert not publish.is_remote("relative/dir")
    assert not publish.is_remote("./dir:with:colons")  # '/' before ':' means path


def test_publish_local_target(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    status_file = src / "status.json"
    history_file = src / "history.jsonl"
    status_file.write_text(json.dumps({"schema_version": 1}))
    history_file.write_text('{"outcome": "succeeded"}\n')

    target = tmp_path / "data"  # does not exist yet: publish must create local dirs
    publish.publish(str(target), files=[status_file, history_file])

    assert json.loads((target / "status.json").read_text()) == {"schema_version": 1}
    assert (target / "history.jsonl").read_text() == '{"outcome": "succeeded"}\n'


def test_publish_overwrites_stale_copy(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    status_file = src / "status.json"
    status_file.write_text('{"v": 2}')
    target = tmp_path / "data"
    target.mkdir()
    (target / "status.json").write_text('{"v": 1}')

    publish.publish(str(target), files=[status_file])
    assert (target / "status.json").read_text() == '{"v": 2}'


def test_publish_missing_files_raises(tmp_path):
    with pytest.raises(publish.PublishError, match="missing"):
        publish.publish(str(tmp_path / "data"), files=[tmp_path / "nope.json"])


def test_publish_rsync_failure_raises(tmp_path):
    src = tmp_path / "status.json"
    src.write_text("{}")
    # A file squatting where the target dir should be makes rsync fail.
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")
    with pytest.raises(publish.PublishError):
        publish.publish(str(blocked), files=[src])
