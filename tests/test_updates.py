"""Release discovery: strict version parsing and release metadata validation.

Headless and networkless: latest_release() takes an injected urlopen, so
nothing here touches the network. This module is the sole boundary that
decides whether a GitHub release is a legitimate, installable update --
every later update task (download, staging, install, UI) trusts a
ReleaseInfo it received from here rather than re-validating the payload.
"""

import hashlib
import json
import os
import time
import urllib.request
from dataclasses import replace
from pathlib import Path

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
