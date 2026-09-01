"""FightRecorder: OBS discovery, release checks, staged updates.

Headless and networkless: discovery gets injected registry/default-path
fakes, latest_release gets a fake urlopen, and apply_update exercises
real temp files. The elevation helper is Windows-only by nature and is
covered by the smoke checklist, not here.
"""

import hashlib
import os

import pytest

from wingman import fightrecorder as fr

# ---- OBS discovery ------------------------------------------------------
#
# Expected paths are built with os.path.join, never typed with
# separators: the code joins with os.path.join, and a typed "\" answer
# passes on Windows and fails on Linux CI (observed both ways).


def test_obs_plugins_directory_is_required(monkeypatch):
    location = os.path.join("R:", "obs-studio")
    monkeypatch.setattr(fr, "_registry_install_location", lambda: location)
    monkeypatch.setattr(fr.os.path, "isdir", lambda p: p.endswith("obs-plugins"))
    made = []
    monkeypatch.setattr(fr.os, "mkdir", lambda p: made.append(p))

    expected = os.path.join(location, "obs-plugins", "64bit")
    assert fr.find_obs_plugin_dir() == expected
    assert made == [expected]


def test_an_existing_64bit_directory_is_returned_as_is(monkeypatch):
    location = os.path.join("R:", "obs-studio")
    monkeypatch.setattr(fr, "_registry_install_location", lambda: location)
    monkeypatch.setattr(fr.os.path, "isdir", lambda p: True)
    made = []
    monkeypatch.setattr(fr.os, "mkdir", lambda p: made.append(p))

    assert fr.find_obs_plugin_dir() == os.path.join(location, "obs-plugins", "64bit")
    assert made == []  # already there; nothing created


def test_a_failed_mkdir_reports_no_obs(monkeypatch):
    monkeypatch.setattr(fr, "_registry_install_location", lambda: "R:\\obs-studio")
    monkeypatch.setattr(fr.os.path, "isdir", lambda p: p.endswith("obs-plugins"))

    def refuse(p):
        raise PermissionError(p)

    monkeypatch.setattr(fr.os, "mkdir", refuse)
    assert fr.find_obs_plugin_dir() is None


def test_dll_path_is_none_without_the_file(monkeypatch):
    plugin_dir = os.path.join("D:", "64bit")
    monkeypatch.setattr(fr, "find_obs_plugin_dir", lambda: plugin_dir)
    monkeypatch.setattr(fr.os.path, "isfile", lambda p: False)
    assert fr.dll_path() is None

    monkeypatch.setattr(fr.os.path, "isfile", lambda p: True)
    assert fr.dll_path() == os.path.join(plugin_dir, fr.DLL_NAME)


# ---- the release lookup -------------------------------------------------


class _JsonResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        import json

        return json.dumps(self._payload).encode()


class _BinaryResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._payload


def _release(digest="a" * 64):
    return {
        "tag_name": "v1.1.2",
        "assets": [
            {
                "name": fr.DLL_NAME,
                "browser_download_url": "https://example/download",
                "digest": "sha256:" + digest,
            }
        ],
    }


def test_latest_release_parses_tag_url_and_digest(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["agent"] = request.headers.get("User-agent")
        return _JsonResponse(_release())

    monkeypatch.setattr(fr.urllib.request, "urlopen", fake_urlopen)
    release = fr.latest_release()
    assert release == {
        "tag": "v1.1.2",
        "url": "https://example/download",
        "digest": "a" * 64,
    }
    assert "releases/latest" in seen["url"]
    # GitHub rejects a bare urllib user agent outright, so the header is
    # load-bearing, not cosmetic.
    assert seen["agent"]


def test_latest_release_without_the_asset_raises(monkeypatch):
    payload = _release()
    payload["assets"] = [{"name": "something-else.zip", "digest": "sha256:bb"}]
    monkeypatch.setattr(
        fr.urllib.request, "urlopen", lambda r, **k: _JsonResponse(payload)
    )
    with pytest.raises(LookupError):
        fr.latest_release()


# ---- download, verify, apply --------------------------------------------


def test_download_latest_refuses_a_checksum_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(
        fr.urllib.request,
        "urlopen",
        lambda r, **k: _BinaryResponse(b"not the dll"),
    )
    staged = tmp_path / "staged.dll"
    assert fr.download_latest("https://x", "b" * 64, str(staged)) != ""
    assert not staged.exists()  # the mismatched download is not left behind


def test_download_accepts_a_matching_file(tmp_path, monkeypatch):
    payload = b"the real dll"
    monkeypatch.setattr(
        fr.urllib.request,
        "urlopen",
        lambda r, **k: _BinaryResponse(payload),
    )
    staged = tmp_path / "staged.dll"
    digest = hashlib.sha256(payload).hexdigest()
    assert fr.download_latest("https://x", digest, str(staged)) == ""
    assert staged.read_bytes() == payload


def test_download_without_a_digest_fails_closed(tmp_path, monkeypatch):
    """A missing digest is disqualifying, not permissive: with no second
    integrity gate, an unverifiable binary must not reach the plugin
    directory."""

    monkeypatch.setattr(
        fr.urllib.request, "urlopen", lambda r, **k: _BinaryResponse(b"whatever")
    )
    staged = tmp_path / "staged.dll"
    assert fr.download_latest("https://x", "", str(staged)) != ""
    assert not staged.exists()


def test_apply_update_copies_into_the_target_directory(tmp_path):
    staged = tmp_path / "staged.dll"
    staged.write_bytes(b"new dll")
    target_dir = tmp_path / "64bit"
    target_dir.mkdir()

    assert fr.apply_update(str(target_dir), str(staged)) == ""
    assert (target_dir / fr.DLL_NAME).read_bytes() == b"new dll"


def test_apply_update_reports_a_locked_target(tmp_path):
    """A PermissionError on the write is the OBS-is-running case; the
    message says that rather than surfacing 'access denied'."""
    staged = tmp_path / "staged.dll"
    staged.write_bytes(b"new dll")
    target_dir = tmp_path / "64bit"
    target_dir.mkdir()
    locked = target_dir / fr.DLL_NAME
    locked.write_bytes(b"locked")
    locked.chmod(0o444)
    try:
        message = fr.apply_update(str(target_dir), str(staged))
    finally:
        locked.chmod(0o644)
    assert message != ""
