"""Release discovery: strict version parsing and release metadata validation.

Headless and networkless: latest_release() takes an injected urlopen, so
nothing here touches the network. This module is the sole boundary that
decides whether a GitHub release is a legitimate, installable update --
every later update task (download, staging, install, UI) trusts a
ReleaseInfo it received from here rather than re-validating the payload.
"""

import ctypes
import hashlib
import json
import os
import threading
import time
import urllib.request
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from wingman import updates

CURRENT = "4.8.0"


def release_payload(
    *,
    tag="v4.9.0",
    version="4.9.0",
    draft=False,
    prerelease=False,
    assets=None,
    size=77_008_252,
    digest="sha256:" + "ab" * 32,
    content_type="application/x-msdos-program",
):
    """A minimal, valid GitHub "releases/latest" payload.

    Overriding `assets` replaces the asset list wholesale; every other
    keyword tweaks the single default asset so most tests can flip one
    field without hand-building the whole shape.
    """
    asset_name = f"FlyGD-Wingman-Setup-{version}.exe"
    if assets is None:
        assets = [
            {
                "name": asset_name,
                "browser_download_url": (
                    "https://github.com/elboaf/FlyGD-Wingman/releases/"
                    f"download/{tag}/{asset_name}"
                ),
                "size": size,
                "digest": digest,
                "content_type": content_type,
            }
        ]
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "assets": assets,
    }


# ---- parse_version -------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "tagged", "expected"),
    [
        ("4.8.0", False, (4, 8, 0)),
        ("v4.9.0", True, (4, 9, 0)),
        ("0.0.0", False, (0, 0, 0)),
    ],
)
def test_parse_version_accepts_only_three_numeric_segments(value, tagged, expected):
    assert updates.parse_version(value, tagged=tagged) == expected


@pytest.mark.parametrize("value", ["4.8", "4.8.0.1", "v4.8.0", "4.8.0-rc1", "04.8.0"])
def test_untagged_version_rejects_every_other_shape(value):
    with pytest.raises(updates.UpdateFailure, match="version"):
        updates.parse_version(value)


@pytest.mark.parametrize("value", ["4.8.0", "4.8", "4.8.0.1", "V4.8.0", "4.8.0-rc1"])
def test_tagged_version_rejects_every_other_shape(value):
    with pytest.raises(updates.UpdateFailure, match="version"):
        updates.parse_version(value, tagged=True)


def test_update_failure_carries_stage_and_code():
    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.parse_version("bogus")
    assert exc_info.value.stage == "check"
    assert exc_info.value.code == "version"


# ---- release_from_payload: happy path and non-update cases --------------


def test_release_metadata_must_agree_on_tag_filename_size_and_digest():
    payload = release_payload(tag="v4.9.0", version="4.9.0")
    release = updates.release_from_payload(payload, "4.8.0")
    assert release == updates.ReleaseInfo(
        version=(4, 9, 0),
        tag="v4.9.0",
        asset_name="FlyGD-Wingman-Setup-4.9.0.exe",
        url="https://github.com/elboaf/FlyGD-Wingman/releases/download/v4.9.0/FlyGD-Wingman-Setup-4.9.0.exe",
        size=77_008_252,
        sha256="ab" * 32,
        content_type="application/x-msdos-program",
    )


def test_release_metadata_uppercase_digest_is_normalized_to_lowercase():
    payload = release_payload(digest="sha256:" + "AB" * 32)
    release = updates.release_from_payload(payload, CURRENT)
    assert release.sha256 == "ab" * 32


def test_draft_release_is_not_an_update():
    payload = release_payload(draft=True)
    assert updates.release_from_payload(payload, CURRENT) is None


def test_prerelease_release_is_not_an_update():
    payload = release_payload(prerelease=True)
    assert updates.release_from_payload(payload, CURRENT) is None


def test_same_version_release_is_not_an_update():
    payload = release_payload(tag="v4.8.0", version="4.8.0")
    assert updates.release_from_payload(payload, CURRENT) is None


def test_older_version_release_is_not_an_update():
    payload = release_payload(tag="v4.7.0", version="4.7.0")
    assert updates.release_from_payload(payload, CURRENT) is None


# ---- release_from_payload: malformed payload shape -----------------------


@pytest.mark.parametrize(
    "payload",
    [
        "not-a-dict",
        [],
        None,
        {"draft": False, "prerelease": False, "assets": []},  # no tag_name
        {"tag_name": "v4.9.0", "draft": False, "prerelease": False},  # no assets
        {
            "tag_name": "v4.9.0",
            "draft": False,
            "prerelease": False,
            "assets": "not-a-list",
        },
        {"tag_name": 49, "draft": False, "prerelease": False, "assets": []},
    ],
)
def test_malformed_payload_shape_raises_metadata_failure(payload):
    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.release_from_payload(payload, CURRENT)
    assert exc_info.value.code == "metadata"


def test_unparseable_tag_raises_version_failure():
    payload = release_payload(tag="4.9.0")  # missing required "v" prefix
    with pytest.raises(updates.UpdateFailure, match="version"):
        updates.release_from_payload(payload, CURRENT)


# ---- release_from_payload: asset selection --------------------------------


def test_missing_expected_asset_raises_asset_failure():
    payload = release_payload(
        tag="v4.9.0",
        version="4.9.0",
        assets=[
            {
                "name": "FlyGD-Wingman-Setup-4.8.0.exe",  # mismatched filename
                "browser_download_url": "https://github.com/elboaf/FlyGD-Wingman/x",
                "size": 1,
                "digest": "sha256:" + "ab" * 32,
                "content_type": "application/x-msdos-program",
            }
        ],
    )
    with pytest.raises(updates.UpdateFailure, match="asset"):
        updates.release_from_payload(payload, CURRENT)


def test_duplicate_expected_asset_raises_asset_failure():
    good_asset = release_payload(tag="v4.9.0", version="4.9.0")["assets"][0]
    payload = release_payload(
        tag="v4.9.0", version="4.9.0", assets=[good_asset, dict(good_asset)]
    )
    with pytest.raises(updates.UpdateFailure, match="asset"):
        updates.release_from_payload(payload, CURRENT)


# ---- release_from_payload: size ------------------------------------------


@pytest.mark.parametrize("size", [0, -1, 256 * 1024 * 1024 + 1])
def test_invalid_asset_size_raises_size_failure(size):
    payload = release_payload(size=size)
    with pytest.raises(updates.UpdateFailure, match="size"):
        updates.release_from_payload(payload, CURRENT)


def test_asset_size_at_the_defensive_maximum_is_accepted():
    payload = release_payload(size=256 * 1024 * 1024)
    release = updates.release_from_payload(payload, CURRENT)
    assert release.size == 256 * 1024 * 1024


# ---- release_from_payload: digest ----------------------------------------


@pytest.mark.parametrize(
    "digest",
    [
        None,
        "",
        "ab" * 32,  # missing "sha256:" prefix
        "sha256:" + "ab" * 31,  # too short
        "sha256:" + "zz" * 32,  # not hex
        "md5:" + "ab" * 32,
    ],
)
def test_invalid_digest_raises_digest_failure(digest):
    payload = release_payload(digest=digest)
    with pytest.raises(updates.UpdateFailure, match="digest"):
        updates.release_from_payload(payload, CURRENT)


# ---- release_from_payload: url --------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/elboaf/FlyGD-Wingman/releases/download/v4.9.0/x.exe",
        "https://user@github.com/elboaf/FlyGD-Wingman/releases/download/v4.9.0/x.exe",
        "https://github.com:444/elboaf/FlyGD-Wingman/releases/download/v4.9.0/x.exe",
        "https://github.com:notaport/elboaf/FlyGD-Wingman/releases/download/v4.9.0/x.exe",
        "not-a-url",
        "",
    ],
)
def test_invalid_asset_url_raises_url_failure(url):
    asset = release_payload()["assets"][0]
    asset["browser_download_url"] = url
    payload = release_payload(assets=[asset])
    with pytest.raises(updates.UpdateFailure, match="url"):
        updates.release_from_payload(payload, CURRENT)


def test_asset_url_matching_the_validated_tag_and_filename_exactly_is_accepted():
    payload = release_payload(tag="v4.9.0", version="4.9.0")
    release = updates.release_from_payload(payload, CURRENT)
    assert release.url == (
        "https://github.com/elboaf/FlyGD-Wingman/releases/download/"
        "v4.9.0/FlyGD-Wingman-Setup-4.9.0.exe"
    )


@pytest.mark.parametrize(
    "url",
    [
        # wrong host entirely
        "https://gitlab.com/elboaf/FlyGD-Wingman/releases/download/"
        "v4.9.0/FlyGD-Wingman-Setup-4.9.0.exe",
        # misleading suffix: not the exact github.com host
        "https://github.com.evil.example/elboaf/FlyGD-Wingman/releases/"
        "download/v4.9.0/FlyGD-Wingman-Setup-4.9.0.exe",
        # wrong owner
        "https://github.com/attacker/FlyGD-Wingman/releases/download/"
        "v4.9.0/FlyGD-Wingman-Setup-4.9.0.exe",
        # wrong repository
        "https://github.com/elboaf/other-repo/releases/download/"
        "v4.9.0/FlyGD-Wingman-Setup-4.9.0.exe",
        # tag in the path does not match the validated release tag
        "https://github.com/elboaf/FlyGD-Wingman/releases/download/"
        "v9.9.9/FlyGD-Wingman-Setup-4.9.0.exe",
        # asset filename in the path does not match the validated asset name
        "https://github.com/elboaf/FlyGD-Wingman/releases/download/"
        "v4.9.0/FlyGD-Wingman-Setup-9.9.9.exe",
        # otherwise-exact URL with a trailing query string
        "https://github.com/elboaf/FlyGD-Wingman/releases/download/"
        "v4.9.0/FlyGD-Wingman-Setup-4.9.0.exe?x=1",
        # otherwise-exact URL with a trailing fragment
        "https://github.com/elboaf/FlyGD-Wingman/releases/download/"
        "v4.9.0/FlyGD-Wingman-Setup-4.9.0.exe#frag",
    ],
)
def test_asset_url_must_match_the_validated_tag_and_filename_exactly(url):
    """A syntactically valid HTTPS URL is not enough: it must be exactly
    GitHub's release-download URL for *this* repository, the *validated*
    tag, and the *validated* asset filename -- never an arbitrary release
    URL smuggled past validation inside an otherwise-plausible wrapper.
    """
    asset = release_payload(tag="v4.9.0", version="4.9.0")["assets"][0]
    asset["browser_download_url"] = url
    payload = release_payload(tag="v4.9.0", version="4.9.0", assets=[asset])
    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.release_from_payload(payload, CURRENT)
    assert exc_info.value.code == "url"


# ---- release_from_payload: content type ------------------------------------


@pytest.mark.parametrize(
    "content_type", ["application/x-msdos-program", "application/octet-stream"]
)
def test_accepted_content_types_are_accepted(content_type):
    payload = release_payload(content_type=content_type)
    release = updates.release_from_payload(payload, CURRENT)
    assert release.content_type == content_type


@pytest.mark.parametrize("content_type", ["application/zip", "text/plain", None, ""])
def test_unexpected_content_type_raises_content_type_failure(content_type):
    payload = release_payload(content_type=content_type)
    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.release_from_payload(payload, CURRENT)
    assert exc_info.value.code == "content_type"


# ---- latest_release: the network boundary --------------------------------


class _JsonResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


def test_latest_release_sends_the_documented_headers_and_parses_the_body():
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["headers"] = {k.lower(): v for k, v in request.header_items()}
        seen["timeout"] = timeout
        return _JsonResponse(release_payload(tag="v4.9.0", version="4.9.0"))

    release = updates.latest_release(CURRENT, urlopen=fake_urlopen, timeout=5.0)

    assert release.version == (4, 9, 0)
    assert seen["url"] == updates.RELEASES_API
    assert seen["timeout"] == 5.0
    assert seen["headers"]["accept"] == "application/vnd.github+json"
    assert seen["headers"]["user-agent"] == (
        f"FlyGD-Wingman/{CURRENT} (+https://github.com/elboaf/FlyGD-Wingman)"
    )
    assert seen["headers"]["x-github-api-version"] == "2022-11-28"


def test_latest_release_returns_none_when_already_current():
    payload = release_payload(tag="v4.8.0", version="4.8.0")
    release = updates.latest_release(
        CURRENT, urlopen=lambda r, timeout: _JsonResponse(payload)
    )
    assert release is None


def test_latest_release_wraps_a_network_failure():
    import urllib.error

    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("boom")

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.latest_release(CURRENT, urlopen=fake_urlopen)
    assert exc_info.value.stage == "check"
    assert exc_info.value.code == "network"


def test_latest_release_wraps_a_malformed_json_body():
    class _BadResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"not json"

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.latest_release(CURRENT, urlopen=lambda r, timeout: _BadResponse())
    assert exc_info.value.stage == "check"
    assert exc_info.value.code == "metadata"


# ---- download/staging fixtures -------------------------------------------


def release_info(*, payload=b"installer", size=None, sha256=None, url=None):
    """A ReleaseInfo whose size/sha256 agree with *payload* by default.

    Overriding size/sha256 independently of payload lets a test build a
    release that legitimately disagrees with what the fake server sends --
    that mismatch is exactly what download_release must detect.
    """
    return updates.ReleaseInfo(
        version=(4, 9, 0),
        tag="v4.9.0",
        asset_name="FlyGD-Wingman-Setup-4.9.0.exe",
        url=url
        or (
            "https://github.com/elboaf/FlyGD-Wingman/releases/download/"
            "v4.9.0/FlyGD-Wingman-Setup-4.9.0.exe"
        ),
        size=len(payload) if size is None else size,
        sha256=hashlib.sha256(payload).hexdigest() if sha256 is None else sha256,
        content_type="application/x-msdos-program",
    )


class _FakeResponse:
    def __init__(self, payload, *, fail_after=None):
        self._payload = payload
        self._pos = 0
        self._fail_after = fail_after
        self._reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        self._reads += 1
        if self._fail_after is not None and self._reads > self._fail_after:
            raise OSError("connection reset")
        chunk = self._payload[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk


def fake_opener(payload=b"installer", *, fail_after=None, fail_to_open=False):
    """An object with urllib's opener.open(request, timeout=...) shape."""

    class _Opener:
        def open(self, request, timeout=None):
            if fail_to_open:
                raise OSError("connection refused")
            return _FakeResponse(payload, fail_after=fail_after)

    return _Opener()


def _age_file(path: Path, days: float) -> None:
    ts = time.time() - days * 86400
    os.utime(path, (ts, ts))


# ---- validate_download_origin / SafeRedirectHandler -----------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/elboaf/FlyGD-Wingman/releases/download/v4.9.0/setup.exe",
        "https://user@github.com/elboaf/FlyGD-Wingman/releases/download/v4.9.0/setup.exe",
        "https://github.com:444/elboaf/FlyGD-Wingman/releases/download/v4.9.0/setup.exe",
        "https://github.com.evil.example/setup.exe",
    ],
)
def test_download_origin_rejects_unsafe_urls(url):
    with pytest.raises(updates.UpdateFailure, match="origin"):
        updates.validate_download_origin(url)


@pytest.mark.parametrize("host", sorted(updates.DOWNLOAD_HOSTS))
def test_download_origin_accepts_every_allowed_host(host):
    updates.validate_download_origin(
        f"https://{host}/owner/repo/releases/download/v1/setup.exe"
    )


def test_download_origin_does_not_accept_a_githubusercontent_suffix_match():
    # A naive endswith("githubusercontent.com") check would let an attacker
    # register "evil-githubusercontent.com"; only exact members of
    # DOWNLOAD_HOSTS are accepted.
    with pytest.raises(updates.UpdateFailure, match="origin"):
        updates.validate_download_origin("https://evil-githubusercontent.com/x")


def test_redirect_handler_rejects_a_disallowed_intermediate_hop():
    handler = updates.SafeRedirectHandler()
    request = urllib.request.Request(
        "https://github.com/owner/repo/releases/download/v1/setup.exe"
    )
    with pytest.raises(updates.UpdateFailure, match="origin"):
        handler.redirect_request(
            request, None, 302, "Found", {}, "https://evil.example/hop"
        )


def test_redirect_handler_allows_a_hop_to_an_allowed_host():
    handler = updates.SafeRedirectHandler()
    request = urllib.request.Request(
        "https://github.com/owner/repo/releases/download/v1/setup.exe"
    )
    new_request = handler.redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "https://release-assets.githubusercontent.com/owner/repo/asset",
    )
    assert new_request.full_url == (
        "https://release-assets.githubusercontent.com/owner/repo/asset"
    )


# ---- download_release: streaming, progress, verification ------------------


def test_download_streams_and_reports_bytes(tmp_path):
    release = release_info(payload=b"installer")
    progress = []
    path = updates.download_release(
        release,
        tmp_path,
        opener=fake_opener(payload=b"installer"),
        on_progress=lambda done, total: progress.append((done, total)),
    )
    assert path.read_bytes() == b"installer"
    assert path.name.endswith(".ready.exe")
    assert progress[-1] == (len(b"installer"), len(b"installer"))


def test_download_removes_partial_file_on_digest_mismatch(tmp_path):
    release = replace(release_info(payload=b"good"), sha256="00" * 32)
    with pytest.raises(updates.UpdateFailure, match="checksum"):
        updates.download_release(release, tmp_path, opener=fake_opener(payload=b"gorp"))
    assert list(tmp_path.iterdir()) == []


def test_download_wraps_an_interrupted_read_and_removes_the_partial(tmp_path):
    release = release_info(payload=b"installer-bytes")
    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.download_release(
            release,
            tmp_path,
            opener=fake_opener(payload=b"installer-bytes", fail_after=0),
        )
    assert exc_info.value.stage == "download"
    assert exc_info.value.code == "network"
    assert list(tmp_path.iterdir()) == []


def test_download_rejects_a_final_byte_count_below_the_advertised_size(tmp_path):
    release = release_info(payload=b"nine-bytes")
    with pytest.raises(updates.UpdateFailure, match="size"):
        updates.download_release(
            release, tmp_path, opener=fake_opener(payload=b"short")
        )
    assert list(tmp_path.iterdir()) == []


def test_download_stops_a_stream_that_exceeds_the_advertised_size(tmp_path):
    release = replace(release_info(payload=b"1234"), size=4)
    with pytest.raises(updates.UpdateFailure, match="size"):
        updates.download_release(
            release, tmp_path, opener=fake_opener(payload=b"12345678")
        )
    assert list(tmp_path.iterdir()) == []


def test_download_stops_a_stream_that_exceeds_the_defensive_maximum(
    tmp_path, monkeypatch
):
    # Even a release that (incorrectly) advertises a size larger than the
    # defensive maximum must never let a stream actually write past it.
    monkeypatch.setattr(updates, "MAX_INSTALLER_BYTES", 4)
    release = replace(release_info(payload=b"12345678"), size=8)
    with pytest.raises(updates.UpdateFailure, match="size"):
        updates.download_release(
            release, tmp_path, opener=fake_opener(payload=b"12345678")
        )
    assert list(tmp_path.iterdir()) == []


def test_download_uses_unique_exclusive_partial_names(tmp_path):
    release = release_info(payload=b"installer")
    first = updates.download_release(
        release, tmp_path, opener=fake_opener(payload=b"installer")
    )
    second = updates.download_release(
        release, tmp_path, opener=fake_opener(payload=b"installer")
    )
    assert first != second
    assert first.exists()
    assert second.exists()


def test_download_validates_the_release_url_before_opening():
    release = replace(
        release_info(),
        url="https://evil.example/FlyGD-Wingman-Setup-4.9.0.exe",
    )

    def fail_if_opened(*args, **kwargs):
        raise AssertionError("opener.open must not be called for an unsafe origin")

    class _Opener:
        open = staticmethod(fail_if_opened)

    with pytest.raises(updates.UpdateFailure, match="origin"):
        updates.download_release(
            release, Path("/tmp/does-not-matter"), opener=_Opener()
        )


# ---- write_handoff_marker / remove_handoff_marker --------------------------


def test_write_handoff_marker_requires_a_ready_exe_name(tmp_path):
    path = tmp_path / "update.exe"
    path.write_bytes(b"x")
    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.write_handoff_marker(path, release_info())
    assert exc_info.value.code == "unexpected-path"


def test_write_handoff_marker_creates_a_sidecar_without_renaming_the_installer(
    tmp_path,
):
    release = release_info(payload=b"installer")
    path = tmp_path / "update-abc123.ready.exe"
    path.write_bytes(b"installer")

    marker = updates.write_handoff_marker(path, release)

    assert marker == path.with_name(path.name + ".handoff.json")
    assert path.exists()
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload == {
        "file": path.name,
        "sha256": release.sha256,
        "version": "4.9.0",
    }


def test_remove_handoff_marker_deletes_the_sidecar_but_not_the_installer(tmp_path):
    release = release_info()
    path = tmp_path / "update-abc123.ready.exe"
    path.write_bytes(b"installer")
    marker = updates.write_handoff_marker(path, release)

    updates.remove_handoff_marker(marker)

    assert not marker.exists()
    assert path.exists()


def test_remove_handoff_marker_is_a_noop_when_already_gone(tmp_path):
    updates.remove_handoff_marker(tmp_path / "missing.ready.exe.handoff.json")


# ---- cleanup_staging --------------------------------------------------------


def test_cleanup_removes_stale_unmarked_partial_and_ready_files(tmp_path):
    partial = tmp_path / "update-aaa.partial"
    partial.write_bytes(b"x")
    ready = tmp_path / "update-bbb.ready.exe"
    ready.write_bytes(b"x")
    _age_file(partial, 8)
    _age_file(ready, 8)

    updates.cleanup_staging(tmp_path)

    assert not partial.exists()
    assert not ready.exists()


def test_cleanup_keeps_a_fresh_unmarked_ready_file(tmp_path):
    ready = tmp_path / "update-ccc.ready.exe"
    ready.write_bytes(b"x")
    _age_file(ready, 1)

    updates.cleanup_staging(tmp_path)

    assert ready.exists()


def test_cleanup_keeps_a_handed_off_file_younger_than_seven_days(tmp_path):
    release = release_info()
    ready = tmp_path / "update-ddd.ready.exe"
    ready.write_bytes(b"x")
    marker = updates.write_handoff_marker(ready, release)
    _age_file(ready, 1)

    updates.cleanup_staging(tmp_path)

    assert ready.exists()
    assert marker.exists()


def test_cleanup_removes_a_handed_off_file_at_least_seven_days_old(tmp_path):
    release = release_info()
    ready = tmp_path / "update-eee.ready.exe"
    ready.write_bytes(b"x")
    marker = updates.write_handoff_marker(ready, release)
    _age_file(ready, 8)

    updates.cleanup_staging(tmp_path)

    assert not ready.exists()
    assert not marker.exists()


def test_cleanup_swallows_a_sharing_violation_as_safe_retention(tmp_path, monkeypatch):
    ready = tmp_path / "update-fff.ready.exe"
    ready.write_bytes(b"x")
    _age_file(ready, 8)

    real_unlink = Path.unlink

    def locked_unlink(self, *args, **kwargs):
        if self.name == ready.name:
            raise PermissionError("in use")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked_unlink)

    updates.cleanup_staging(tmp_path)  # must not raise

    assert ready.exists()


def test_cleanup_never_touches_files_outside_the_staging_directory(tmp_path):
    outside = tmp_path.parent / "unrelated.ready.exe"
    outside.write_bytes(b"x")
    _age_file(outside, 8)
    unexpected = tmp_path / "notes.txt"
    unexpected.write_bytes(b"x")
    _age_file(unexpected, 8)

    try:
        updates.cleanup_staging(tmp_path)

        assert outside.exists()
        assert unexpected.exists()
    finally:
        outside.unlink()


def test_cleanup_never_follows_or_removes_a_symlink(tmp_path):
    real_target = tmp_path.parent / "real-target.ready.exe"
    real_target.write_bytes(b"x")
    _age_file(real_target, 8)
    link = tmp_path / "update-ggg.ready.exe"
    try:
        link.symlink_to(real_target)
    except OSError:
        pytest.skip("symlinks are not supported in this environment")

    try:
        updates.cleanup_staging(tmp_path)

        assert link.is_symlink()
        assert real_target.exists()
    finally:
        link.unlink(missing_ok=True)
        real_target.unlink(missing_ok=True)


def test_cleanup_is_a_noop_on_a_missing_staging_directory(tmp_path):
    updates.cleanup_staging(tmp_path / "does-not-exist")


# ---- fix round 1: filesystem failures map to UpdateFailure -----------------


def test_download_wraps_a_staging_directory_creation_failure(tmp_path, monkeypatch):
    release = release_info(payload=b"installer")
    staging_root = tmp_path / "updates"

    def raising_mkdir(self, *args, **kwargs):
        raise PermissionError("cannot create directory")

    monkeypatch.setattr(Path, "mkdir", raising_mkdir)

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.download_release(
            release, staging_root, opener=fake_opener(payload=b"installer")
        )

    assert exc_info.value.stage == "download"
    assert exc_info.value.code == "filesystem"
    assert not staging_root.exists()


def test_download_wraps_a_staging_file_creation_failure(tmp_path, monkeypatch):
    release = release_info(payload=b"installer")

    def raising_mkstemp(*args, **kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr(updates.tempfile, "mkstemp", raising_mkstemp)

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.download_release(
            release, tmp_path, opener=fake_opener(payload=b"installer")
        )

    assert exc_info.value.stage == "download"
    assert exc_info.value.code == "filesystem"
    assert list(tmp_path.iterdir()) == []


def test_download_wraps_an_fdopen_failure_without_leaking_the_descriptor(
    tmp_path, monkeypatch
):
    release = release_info(payload=b"installer")
    captured = {}

    def raising_fdopen(handle, mode):
        captured["handle"] = handle
        raise OSError("too many open files")

    monkeypatch.setattr(updates.os, "fdopen", raising_fdopen)

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.download_release(
            release, tmp_path, opener=fake_opener(payload=b"installer")
        )

    assert exc_info.value.stage == "download"
    assert exc_info.value.code == "filesystem"
    assert list(tmp_path.iterdir()) == []

    # download_release must already have closed the raw fd (rather than
    # leaking it) -- closing it again must fail with "bad file descriptor"
    # instead of succeeding a second time.
    with pytest.raises(OSError):
        os.close(captured["handle"])


def test_download_wraps_a_write_failure_and_removes_the_partial(tmp_path, monkeypatch):
    release = release_info(payload=b"installer")
    real_fdopen = updates.os.fdopen

    def failing_fdopen(handle, mode):
        real_stream = real_fdopen(handle, mode)

        class _Wrapper:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return real_stream.__exit__(*exc)

            def write(self, chunk):
                raise OSError("disk full")

            def flush(self):
                real_stream.flush()

            def fileno(self):
                return real_stream.fileno()

        return _Wrapper()

    monkeypatch.setattr(updates.os, "fdopen", failing_fdopen)

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.download_release(
            release, tmp_path, opener=fake_opener(payload=b"installer")
        )

    assert exc_info.value.stage == "download"
    assert exc_info.value.code == "filesystem"
    assert list(tmp_path.iterdir()) == []


def test_download_wraps_a_flush_or_fsync_failure_and_removes_the_partial(
    tmp_path, monkeypatch
):
    release = release_info(payload=b"installer")

    def raising_fsync(fd):
        raise OSError("disk full")

    monkeypatch.setattr(updates.os, "fsync", raising_fsync)

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.download_release(
            release, tmp_path, opener=fake_opener(payload=b"installer")
        )

    assert exc_info.value.stage == "download"
    assert exc_info.value.code == "filesystem"
    assert list(tmp_path.iterdir()) == []


def test_download_wraps_a_publish_replace_failure_and_removes_the_partial(
    tmp_path, monkeypatch
):
    release = release_info(payload=b"installer")

    def raising_replace(src, dst):
        raise OSError("cannot rename across volumes")

    monkeypatch.setattr(updates.os, "replace", raising_replace)

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.download_release(
            release, tmp_path, opener=fake_opener(payload=b"installer")
        )

    assert exc_info.value.stage == "download"
    assert exc_info.value.code == "filesystem"
    assert list(tmp_path.iterdir()) == []


def test_write_handoff_marker_wraps_a_write_failure(tmp_path, monkeypatch):
    release = release_info()
    path = tmp_path / "update-abc123.ready.exe"
    path.write_bytes(b"installer")

    def raising_write_atomic(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(updates.atomicio, "write_atomic", raising_write_atomic)

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.write_handoff_marker(path, release)

    assert exc_info.value.stage == "cleanup"
    assert exc_info.value.code == "filesystem"


def test_remove_handoff_marker_wraps_a_removal_failure(tmp_path, monkeypatch):
    release = release_info()
    path = tmp_path / "update-abc123.ready.exe"
    path.write_bytes(b"installer")
    marker = updates.write_handoff_marker(path, release)

    def raising_unlink(self, *args, **kwargs):
        raise PermissionError("in use")

    monkeypatch.setattr(Path, "unlink", raising_unlink)

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.remove_handoff_marker(marker)

    assert exc_info.value.stage == "cleanup"
    assert exc_info.value.code == "filesystem"


# ---- attachment, protected verification, and shell launch -----------------


def write_installer(tmp_path, payload=b"verified"):
    path = tmp_path / "update-native.ready.exe"
    path.write_bytes(payload)
    return path


def fail_if_called(*args, **kwargs):
    raise AssertionError("this dependency must not be called")


class FakeLockedFile:
    """The high-level protected-file seam used by Linux unit tests."""

    def __init__(self, path, events, *, snapshots=None):
        self.path = Path(path)
        self.events = events
        self.snapshots = iter(snapshots) if snapshots is not None else None
        self.closed = 0

    def __enter__(self):
        self.events.append("open-locked")
        return self

    def __exit__(self, *exc):
        self.closed += 1
        self.events.append("close-locked")
        return False

    def identity_and_size(self):
        if self.snapshots is not None:
            return next(self.snapshots)
        return ((1, 2), self.path.stat().st_size)

    def sha256(self):
        self.events.append("hash")
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def test_launch_orders_attachment_lock_hash_marker_shell_then_close(tmp_path):
    events = []
    path = write_installer(tmp_path, b"verified")
    release = release_info(payload=b"verified")
    handle = FakeLockedFile(path, events)

    process = updates.launch_verified(
        release,
        path,
        attachment=lambda p, u: events.append("attachment"),
        locked_open=lambda p: handle,
        before_launch=lambda: events.append("marker"),
        shell_execute=lambda locked_path: events.append("shell") or 42,
    )

    assert process == 42
    assert events == [
        "attachment",
        "open-locked",
        "hash",
        "marker",
        "shell",
        "close-locked",
    ]
    assert handle.closed == 1


def test_attachment_receives_the_verified_path_and_release_source_url(tmp_path):
    path = write_installer(tmp_path)
    release = release_info(payload=b"verified")
    seen = []

    updates.verify_after_attachment(
        release,
        path,
        attachment=lambda attachment_path, source_url: seen.append(
            (attachment_path, source_url)
        ),
        locked_open=lambda p: FakeLockedFile(p, []),
    )

    assert seen == [(path, release.url)]


def test_attachment_success_that_replaces_file_is_rehashed_and_rejected(tmp_path):
    path = write_installer(tmp_path, b"verified")
    release = release_info(payload=b"verified")

    def replace_after_scan(_path, _url):
        path.write_bytes(b"altered!")

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.launch_verified(
            release,
            path,
            attachment=replace_after_scan,
            shell_execute=fail_if_called,
        )

    assert exc_info.value.stage == "verify"
    assert exc_info.value.code == "checksum"


def test_attachment_success_that_deletes_file_is_rejected_before_shell(tmp_path):
    path = write_installer(tmp_path)
    release = release_info(payload=b"verified")

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.launch_verified(
            release,
            path,
            attachment=lambda p, u: path.unlink(),
            shell_execute=fail_if_called,
        )

    assert exc_info.value.stage == "verify"
    assert exc_info.value.code == "file"


def test_attachment_success_that_truncates_file_is_rejected_before_shell(tmp_path):
    path = write_installer(tmp_path)
    release = release_info(payload=b"verified")

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.launch_verified(
            release,
            path,
            attachment=lambda p, u: path.write_bytes(b""),
            shell_execute=fail_if_called,
        )

    assert exc_info.value.stage == "verify"
    assert exc_info.value.code == "size"


def test_attachment_quarantine_that_moves_file_is_rejected_before_shell(tmp_path):
    path = write_installer(tmp_path)
    quarantine = tmp_path / "quarantined.exe"
    release = release_info(payload=b"verified")

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.launch_verified(
            release,
            path,
            attachment=lambda p, u: path.replace(quarantine),
            shell_execute=fail_if_called,
        )

    assert exc_info.value.stage == "verify"
    assert exc_info.value.code == "file"


def test_identity_change_after_hash_is_rejected_and_locked_handle_closes(tmp_path):
    events = []
    path = write_installer(tmp_path)
    release = release_info(payload=b"verified")
    handle = FakeLockedFile(
        path,
        events,
        snapshots=[((7, 11), len(b"verified")), ((7, 12), len(b"verified"))],
    )

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.launch_verified(
            release,
            path,
            attachment=lambda p, u: events.append("attachment"),
            locked_open=lambda p: handle,
            shell_execute=fail_if_called,
        )

    assert exc_info.value.stage == "verify"
    assert exc_info.value.code == "identity"
    assert events[-1] == "close-locked"
    assert handle.closed == 1


def test_attachment_failure_prevents_protected_open_and_shell(tmp_path):
    events = []
    path = write_installer(tmp_path)
    release = release_info(payload=b"verified")

    def rejected_attachment(_path, _url):
        events.append("attachment")
        raise updates.UpdateFailure("verify", "attachment", "blocked")

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.launch_verified(
            release,
            path,
            attachment=rejected_attachment,
            locked_open=fail_if_called,
            shell_execute=fail_if_called,
        )

    assert exc_info.value.code == "attachment"
    assert events == ["attachment"]


def test_verify_after_attachment_closes_the_protected_handle(tmp_path):
    events = []
    path = write_installer(tmp_path)
    release = release_info(payload=b"verified")
    handle = FakeLockedFile(path, events)

    updates.verify_after_attachment(
        release,
        path,
        attachment=lambda p, u: events.append("attachment"),
        locked_open=lambda p: handle,
    )

    assert events == ["attachment", "open-locked", "hash", "close-locked"]
    assert handle.closed == 1


def test_before_launch_failure_prevents_shell_and_closes_protected_handle(tmp_path):
    events = []
    path = write_installer(tmp_path)
    release = release_info(payload=b"verified")
    handle = FakeLockedFile(path, events)

    def fail_marker():
        events.append("marker")
        raise OSError("marker write failed")

    with pytest.raises(OSError, match="marker write failed"):
        updates.launch_verified(
            release,
            path,
            attachment=lambda p, u: events.append("attachment"),
            locked_open=lambda p: handle,
            before_launch=fail_marker,
            shell_execute=fail_if_called,
        )

    assert events == [
        "attachment",
        "open-locked",
        "hash",
        "marker",
        "close-locked",
    ]
    assert handle.closed == 1


class _BarrierLockedFile:
    """Models Windows' write/delete denial while allowing held-handle reads."""

    def __init__(self, path, hashed):
        self.path = Path(path)
        self.hashed = hashed
        self.active = False
        self.stream = None

    def __enter__(self):
        self.stream = self.path.open("rb")
        self.active = True
        return self

    def __exit__(self, *exc):
        self.active = False
        self.stream.close()
        return False

    def identity_and_size(self):
        stat_result = os.fstat(self.stream.fileno())
        return ((stat_result.st_dev, stat_result.st_ino), stat_result.st_size)

    def sha256(self):
        digest = hashlib.sha256(self.stream.read()).hexdigest()
        self.hashed.set()
        return digest

    def replace(self, payload):
        if self.active:
            raise PermissionError("sharing violation")
        self.path.write_bytes(payload)


def test_replacement_after_hash_is_denied_until_shell_receives_verified_path(tmp_path):
    path = write_installer(tmp_path)
    release = release_info(payload=b"verified")
    hashed = threading.Event()
    replacement_done = threading.Event()
    replacement_errors = []
    shell_paths = []
    handle = _BarrierLockedFile(path, hashed)

    def replace_after_hash():
        assert hashed.wait(2)
        try:
            handle.replace(b"different")
        except PermissionError as exc:
            replacement_errors.append(str(exc))
        finally:
            replacement_done.set()

    replacement = threading.Thread(target=replace_after_hash)
    replacement.start()
    try:
        process = updates.launch_verified(
            release,
            path,
            attachment=lambda p, u: None,
            locked_open=lambda p: handle,
            before_launch=lambda: replacement_done.wait(2),
            shell_execute=lambda shell_path: shell_paths.append(shell_path) or 91,
        )
    finally:
        replacement.join(2)

    assert process == 91
    assert replacement_errors == ["sharing violation"]
    assert shell_paths == [path]
    assert path.read_bytes() == b"verified"


def test_shell_failure_still_closes_the_protected_file_exactly_once(tmp_path):
    events = []
    path = write_installer(tmp_path)
    release = release_info(payload=b"verified")
    handle = FakeLockedFile(path, events)

    def rejected_shell(_path):
        events.append("shell")
        raise updates.UpdateFailure("launch", "shell", "rejected")

    with pytest.raises(updates.UpdateFailure, match="rejected"):
        updates.launch_verified(
            release,
            path,
            attachment=lambda p, u: events.append("attachment"),
            locked_open=lambda p: handle,
            shell_execute=rejected_shell,
        )

    assert events[-2:] == ["shell", "close-locked"]
    assert handle.closed == 1


class FakeLockedKernel32:
    def __init__(self, payload, *, close_success=True):
        self.payload = payload
        self.close_success = close_success
        self.offset = 0
        self.create_calls = []
        self.info_handles = []
        self.read_handles = []
        self.closed_handles = []

    def CreateFileW(self, *args):
        self.create_calls.append(args)
        return 77

    def GetFileInformationByHandle(self, handle, output):
        self.info_handles.append(handle)
        info = ctypes.cast(
            output, ctypes.POINTER(updates._BY_HANDLE_FILE_INFORMATION)
        ).contents
        info.dwVolumeSerialNumber = 9
        info.nFileIndexHigh = 1
        info.nFileIndexLow = 5
        info.nFileSizeHigh = 0
        info.nFileSizeLow = len(self.payload)
        return True

    def ReadFile(self, handle, buffer, size, bytes_read, overlapped):
        self.read_handles.append(handle)
        chunk = self.payload[self.offset : self.offset + size]
        self.offset += len(chunk)
        if chunk:
            ctypes.memmove(buffer, chunk, len(chunk))
        ctypes.cast(bytes_read, ctypes.POINTER(ctypes.c_uint32)).contents.value = len(
            chunk
        )
        return True

    def CloseHandle(self, handle):
        self.closed_handles.append(handle)
        return self.close_success


def test_locked_windows_file_denies_write_delete_and_hashes_held_handle():
    kernel32 = FakeLockedKernel32(b"verified")

    with updates._WindowsLockedFile(
        Path("C:/Temp/update.ready.exe"), kernel32
    ) as locked:
        identity, size = locked.identity_and_size()
        digest = locked.sha256()

    assert kernel32.create_calls == [
        (
            str(Path("C:/Temp/update.ready.exe")),
            0x80000000,
            0x00000001,
            None,
            3,
            0x00000080,
            None,
        )
    ]
    assert identity == (9, (1 << 32) | 5)
    assert size == len(b"verified")
    assert digest == hashlib.sha256(b"verified").hexdigest()
    assert kernel32.info_handles == [77]
    assert set(kernel32.read_handles) == {77}
    assert kernel32.closed_handles == [77]


def test_locked_windows_file_reports_close_failure_after_one_attempt(monkeypatch):
    kernel32 = FakeLockedKernel32(b"verified", close_success=False)
    monkeypatch.setattr(updates, "_get_last_error", lambda: 6)

    with (
        pytest.raises(updates.UpdateFailure) as exc_info,
        updates._WindowsLockedFile(Path("C:/Temp/update.ready.exe"), kernel32),
    ):
        pass

    assert exc_info.value.stage == "verify"
    assert exc_info.value.code == "file-close"
    assert kernel32.closed_handles == [77]


def test_verify_after_attachment_reports_protected_close_failure(tmp_path, monkeypatch):
    path = write_installer(tmp_path)
    release = release_info(payload=b"verified")
    kernel32 = FakeLockedKernel32(b"verified", close_success=False)
    monkeypatch.setattr(updates, "_get_last_error", lambda: 6)

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.verify_after_attachment(
            release,
            path,
            attachment=lambda p, u: None,
            locked_open=lambda p: updates._WindowsLockedFile(p, kernel32),
        )

    assert exc_info.value.stage == "verify"
    assert exc_info.value.code == "file-close"
    assert kernel32.closed_handles == [77]


def test_locked_close_failure_does_not_mask_the_primary_failure(monkeypatch):
    kernel32 = FakeLockedKernel32(b"verified", close_success=False)
    monkeypatch.setattr(updates, "_get_last_error", lambda: 6)

    with (
        pytest.raises(RuntimeError, match="primary") as exc_info,
        updates._WindowsLockedFile(Path("C:/Temp/update.ready.exe"), kernel32),
    ):
        raise RuntimeError("primary")

    assert exc_info.value.__notes__ == ["CloseHandle failed with error 6"]
    assert kernel32.closed_handles == [77]


def test_open_locked_selects_windows_handle_on_win32(monkeypatch):
    path = Path("C:/Temp/update.ready.exe")
    kernel32 = object()
    expected = object()

    monkeypatch.setattr(updates.sys, "platform", "win32")
    monkeypatch.setattr(
        updates, "_load_win32_libs", lambda: SimpleNamespace(kernel32=kernel32)
    )

    def windows_locked(actual_path, actual_kernel32):
        assert actual_path == path
        assert actual_kernel32 is kernel32
        return expected

    monkeypatch.setattr(updates, "_WindowsLockedFile", windows_locked)
    monkeypatch.setattr(updates, "_PortableLockedFile", fail_if_called)

    assert updates._open_locked(path) is expected


def test_open_locked_selects_portable_handle_off_windows(monkeypatch):
    path = Path("/tmp/update.ready.exe")
    expected = object()

    monkeypatch.setattr(updates.sys, "platform", "linux")

    def portable_locked(actual_path):
        assert actual_path == path
        return expected

    monkeypatch.setattr(updates, "_WindowsLockedFile", fail_if_called)
    monkeypatch.setattr(updates, "_PortableLockedFile", portable_locked)
    monkeypatch.setattr(updates, "_load_win32_libs", fail_if_called)

    assert updates._open_locked(path) is expected


class FakeNativeFunction:
    def __init__(self):
        self.argtypes = object()
        self.restype = object()


class FakeNativeLibrary:
    def __init__(self, *function_names):
        for name in function_names:
            setattr(self, name, FakeNativeFunction())


def test_load_win32_libs_binds_every_used_native_signature(monkeypatch):
    ole32 = FakeNativeLibrary(
        "CoInitializeEx", "CoUninitialize", "CLSIDFromString", "CoCreateInstance"
    )
    kernel32 = FakeNativeLibrary(
        "CreateFileW", "GetFileInformationByHandle", "ReadFile", "CloseHandle"
    )
    shell32 = FakeNativeLibrary("ShellExecuteExW")
    libraries = {"ole32": ole32, "kernel32": kernel32, "shell32": shell32}
    loaded = []

    def fake_win_dll(name, *, use_last_error):
        loaded.append((name, use_last_error))
        return libraries[name]

    monkeypatch.setattr(updates.ctypes, "WinDLL", fake_win_dll, raising=False)
    updates._load_win32_libs.cache_clear()
    try:
        libs = updates._load_win32_libs()

        assert libs == updates._Win32Libs(
            ole32=ole32, kernel32=kernel32, shell32=shell32
        )
        assert loaded == [
            ("ole32", True),
            ("kernel32", True),
            ("shell32", True),
        ]
        assert ole32.CoInitializeEx.argtypes == [ctypes.c_void_p, ctypes.c_uint32]
        assert ole32.CoInitializeEx.restype is ctypes.c_int32
        assert ole32.CoUninitialize.argtypes == []
        assert ole32.CoUninitialize.restype is None
        assert ole32.CLSIDFromString.argtypes == [
            ctypes.c_wchar_p,
            ctypes.POINTER(updates._GUID),
        ]
        assert ole32.CLSIDFromString.restype is ctypes.c_int32
        assert ole32.CoCreateInstance.argtypes == [
            ctypes.POINTER(updates._GUID),
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(updates._GUID),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        assert ole32.CoCreateInstance.restype is ctypes.c_int32
        assert kernel32.CreateFileW.argtypes == [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        assert kernel32.CreateFileW.restype is ctypes.c_void_p
        assert kernel32.GetFileInformationByHandle.argtypes == [
            ctypes.c_void_p,
            ctypes.POINTER(updates._BY_HANDLE_FILE_INFORMATION),
        ]
        assert kernel32.GetFileInformationByHandle.restype is ctypes.c_int32
        assert kernel32.ReadFile.argtypes == [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_void_p,
        ]
        assert kernel32.ReadFile.restype is ctypes.c_int32
        assert kernel32.CloseHandle.argtypes == [ctypes.c_void_p]
        assert kernel32.CloseHandle.restype is ctypes.c_int32
        assert shell32.ShellExecuteExW.argtypes == [
            ctypes.POINTER(updates._SHELLEXECUTEINFO)
        ]
        assert shell32.ShellExecuteExW.restype is ctypes.c_int32
    finally:
        updates._load_win32_libs.cache_clear()


_STDCALL = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)


class FakeAttachmentWin32:
    """A real ctypes COM vtable backed by Python callbacks."""

    def __init__(self, *, coinit_hresult=0, create_hresult=0, fail_method=None):
        self.ole32 = self
        self.kernel32 = self
        self.shell32 = self
        self.coinit_hresult = coinit_hresult
        self.create_hresult = create_hresult
        self.fail_method = fail_method
        self.coinit_flags = []
        self.parsed_guids = []
        self.create_calls = []
        self.attachment_calls = []
        self.release_calls = 0
        self.uninitialize_calls = 0
        self._callbacks = []
        self._build_attachment_object()

    def _result(self, method):
        if self.fail_method == method:
            return ctypes.c_int32(0x80004005).value
        return 0

    def _build_attachment_object(self):
        release_type = _STDCALL(ctypes.c_uint32, ctypes.c_void_p)
        guid_type = _STDCALL(
            ctypes.c_int32, ctypes.c_void_p, ctypes.POINTER(updates._GUID)
        )
        string_type = _STDCALL(ctypes.c_int32, ctypes.c_void_p, ctypes.c_wchar_p)
        save_type = _STDCALL(ctypes.c_int32, ctypes.c_void_p)

        @release_type
        def release(_this):
            self.release_calls += 1
            return 0

        @guid_type
        def set_client_guid(_this, guid):
            self.attachment_calls.append(("SetClientGuid", guid.contents.Data1))
            return self._result("SetClientGuid")

        @string_type
        def set_local_path(_this, value):
            self.attachment_calls.append(("SetLocalPath", value))
            return self._result("SetLocalPath")

        @string_type
        def set_source(_this, value):
            self.attachment_calls.append(("SetSource", value))
            return self._result("SetSource")

        @save_type
        def save(_this):
            self.attachment_calls.append(("Save", None))
            return self._result("Save")

        self._callbacks.extend(
            [release, set_client_guid, set_local_path, set_source, save]
        )
        self._vtable = (ctypes.c_void_p * 15)()
        self._vtable[2] = ctypes.cast(release, ctypes.c_void_p).value
        self._vtable[4] = ctypes.cast(set_client_guid, ctypes.c_void_p).value
        self._vtable[5] = ctypes.cast(set_local_path, ctypes.c_void_p).value
        self._vtable[7] = ctypes.cast(set_source, ctypes.c_void_p).value
        self._vtable[11] = ctypes.cast(save, ctypes.c_void_p).value

        class _ComObject(ctypes.Structure):
            _fields_ = [("vtable", ctypes.POINTER(ctypes.c_void_p))]

        self._object = _ComObject(
            ctypes.cast(self._vtable, ctypes.POINTER(ctypes.c_void_p))
        )

    def CoInitializeEx(self, reserved, flags):
        self.coinit_flags.append(flags)
        return self.coinit_hresult

    def CoUninitialize(self):
        self.uninitialize_calls += 1

    def CLSIDFromString(self, text, output):
        self.parsed_guids.append(text)
        guid = ctypes.cast(output, ctypes.POINTER(updates._GUID)).contents
        guid.Data1 = len(self.parsed_guids)
        return 0

    def CoCreateInstance(self, clsid, outer, context, iid, output):
        clsid_value = ctypes.cast(clsid, ctypes.POINTER(updates._GUID)).contents.Data1
        iid_value = ctypes.cast(iid, ctypes.POINTER(updates._GUID)).contents.Data1
        self.create_calls.append((clsid_value, context, iid_value))
        if self.create_hresult < 0:
            return self.create_hresult
        ctypes.cast(
            output, ctypes.POINTER(ctypes.c_void_p)
        ).contents.value = ctypes.addressof(self._object)
        return self.create_hresult


def test_attachment_services_sets_guid_path_source_then_saves(tmp_path, monkeypatch):
    path = write_installer(tmp_path)
    calls = FakeAttachmentWin32()
    monkeypatch.setattr(updates, "_load_win32_libs", lambda: calls)

    updates.save_attachment(path, "https://github.com/source.exe")

    assert calls.parsed_guids == [
        updates.CLSID_ATTACHMENT_SERVICES,
        updates.IID_IATTACHMENT_EXECUTE,
        updates.ATTACHMENT_CLIENT_GUID,
    ]
    assert calls.create_calls == [(1, updates.CLSCTX_INPROC_SERVER, 2)]
    assert calls.attachment_calls == [
        ("SetClientGuid", 3),
        ("SetLocalPath", str(path)),
        ("SetSource", "https://github.com/source.exe"),
        ("Save", None),
    ]
    assert calls.coinit_flags == [
        updates.COINIT_APARTMENTTHREADED | updates.COINIT_DISABLE_OLE1DDE
    ]
    assert calls.release_calls == 1
    assert calls.uninitialize_calls == 1


@pytest.mark.parametrize(
    "method", ["SetClientGuid", "SetLocalPath", "SetSource", "Save"]
)
def test_attachment_hresult_failure_releases_interface_and_uninitializes(
    tmp_path, monkeypatch, method
):
    path = write_installer(tmp_path)
    calls = FakeAttachmentWin32(fail_method=method)
    monkeypatch.setattr(updates, "_load_win32_libs", lambda: calls)

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.save_attachment(path, "https://github.com/source.exe")

    assert exc_info.value.stage == "verify"
    assert exc_info.value.code == "attachment"
    assert exc_info.value.detail == "0x80004005"
    assert calls.release_calls == 1
    assert calls.uninitialize_calls == 1


def test_attachment_com_initialization_failure_does_not_uninitialize(
    tmp_path, monkeypatch
):
    path = write_installer(tmp_path)
    calls = FakeAttachmentWin32(coinit_hresult=ctypes.c_int32(0x80004005).value)
    monkeypatch.setattr(updates, "_load_win32_libs", lambda: calls)

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates.save_attachment(path, "https://github.com/source.exe")

    assert exc_info.value.code == "attachment"
    assert exc_info.value.detail == "0x80004005"
    assert calls.create_calls == []
    assert calls.release_calls == 0
    assert calls.uninitialize_calls == 0


class FakeShellWin32:
    def __init__(self, *, process_handle=123, shell_success=True, coinit_hresult=0):
        self.ole32 = self
        self.kernel32 = self
        self.shell32 = self
        self.process_handle = process_handle
        self.shell_success = shell_success
        self.coinit_hresult = coinit_hresult
        self.coinit_flags = []
        self.uninitialize_calls = 0
        self.shell_calls = 0
        self.shell_info = None
        self.closed_handles = []

    def CoInitializeEx(self, reserved, flags):
        self.coinit_flags.append(flags)
        return self.coinit_hresult

    def CoUninitialize(self):
        self.uninitialize_calls += 1

    def ShellExecuteExW(self, info_pointer):
        self.shell_calls += 1
        info = ctypes.cast(
            info_pointer, ctypes.POINTER(updates._SHELLEXECUTEINFO)
        ).contents
        info.hProcess = self.process_handle
        self.shell_info = SimpleNamespace(
            cbSize=info.cbSize,
            fMask=info.fMask,
            lpVerb=info.lpVerb,
            lpFile=info.lpFile,
            lpParameters=info.lpParameters,
            nShow=info.nShow,
            hProcess=info.hProcess,
        )
        return self.shell_success

    def CloseHandle(self, handle):
        self.closed_handles.append(handle)
        return True


def test_shell_launch_uses_zone_checked_open_and_returns_a_process_handle():
    calls = FakeShellWin32(process_handle=123)

    assert updates._shell_execute(Path("C:/Temp/update.ready.exe"), libs=calls) == 123

    info = calls.shell_info
    assert info.cbSize == ctypes.sizeof(updates._SHELLEXECUTEINFO)
    assert info.lpVerb == "open"
    assert info.lpFile == str(Path("C:/Temp/update.ready.exe"))
    assert info.lpParameters is None
    assert info.nShow == updates.SW_SHOWNORMAL
    assert info.fMask == updates.SEE_MASK_NOASYNC | updates.SEE_MASK_NOCLOSEPROCESS
    assert not info.fMask & updates.SEE_MASK_NOZONECHECKS
    assert calls.coinit_flags == [
        updates.COINIT_APARTMENTTHREADED | updates.COINIT_DISABLE_OLE1DDE
    ]
    assert calls.uninitialize_calls == 1


def test_shell_execute_failure_is_typed_and_uninitializes(monkeypatch):
    calls = FakeShellWin32(shell_success=False)
    monkeypatch.setattr(updates, "_get_last_error", lambda: 5)

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates._shell_execute(Path("C:/Temp/update.ready.exe"), libs=calls)

    assert exc_info.value.stage == "launch"
    assert exc_info.value.code == "shell"
    assert calls.uninitialize_calls == 1


def test_shell_execute_reports_user_cancellation(monkeypatch):
    calls = FakeShellWin32(shell_success=False)
    monkeypatch.setattr(updates, "_get_last_error", lambda: updates.ERROR_CANCELLED)

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates._shell_execute(Path("C:/Temp/update.ready.exe"), libs=calls)

    assert exc_info.value.stage == "launch"
    assert exc_info.value.code == "cancelled"
    assert calls.uninitialize_calls == 1


def test_shell_execute_rejects_a_null_process_handle():
    calls = FakeShellWin32(process_handle=0)

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates._shell_execute(Path("C:/Temp/update.ready.exe"), libs=calls)

    assert exc_info.value.stage == "launch"
    assert exc_info.value.code == "shell"
    assert calls.uninitialize_calls == 1


def test_shell_com_initialization_failure_never_calls_shell_or_uninitialize():
    calls = FakeShellWin32(coinit_hresult=ctypes.c_int32(0x80004005).value)

    with pytest.raises(updates.UpdateFailure) as exc_info:
        updates._shell_execute(Path("C:/Temp/update.ready.exe"), libs=calls)

    assert exc_info.value.stage == "launch"
    assert exc_info.value.code == "com"
    assert exc_info.value.detail == "0x80004005"
    assert calls.shell_calls == 0
    assert calls.uninitialize_calls == 0


def test_shell_returned_process_handle_is_closed_only_by_explicit_owner(
    tmp_path, monkeypatch
):
    path = write_installer(tmp_path)
    release = release_info(payload=b"verified")
    events = []
    locked = FakeLockedFile(path, events)
    calls = FakeShellWin32(process_handle=321)
    monkeypatch.setattr(updates, "_load_win32_libs", lambda: calls)

    process = updates.launch_verified(
        release,
        path,
        attachment=lambda p, u: None,
        locked_open=lambda p: locked,
        shell_execute=lambda p: 321,
    )

    assert process == 321
    assert locked.closed == 1
    assert calls.closed_handles == []
    updates.close_process_handle(process)
    assert calls.closed_handles == [321]


def test_protected_close_failure_after_shell_launch_preserves_process_handle(
    tmp_path, monkeypatch, caplog
):
    path = write_installer(tmp_path)
    release = release_info(payload=b"verified")
    locked_kernel32 = FakeLockedKernel32(b"verified", close_success=False)
    process_owner = FakeShellWin32(process_handle=321)
    monkeypatch.setattr(updates, "_get_last_error", lambda: 6)
    monkeypatch.setattr(updates, "_load_win32_libs", lambda: process_owner)

    with caplog.at_level("WARNING", logger="wingman.updates"):
        process = updates.launch_verified(
            release,
            path,
            attachment=lambda p, u: None,
            locked_open=lambda p: updates._WindowsLockedFile(p, locked_kernel32),
            shell_execute=lambda p: 321,
        )

    assert process == 321
    assert locked_kernel32.closed_handles == [77]
    assert "process handle 321 remains owned by caller" in caplog.text
    assert process_owner.closed_handles == []
    updates.close_process_handle(process)
    assert process_owner.closed_handles == [321]
