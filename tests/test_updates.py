"""Release discovery: strict version parsing and release metadata validation.

Headless and networkless: latest_release() takes an injected urlopen, so
nothing here touches the network. This module is the sole boundary that
decides whether a GitHub release is a legitimate, installable update --
every later update task (download, staging, install, UI) trusts a
ReleaseInfo it received from here rather than re-validating the payload.
"""

import json

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
