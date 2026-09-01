"""The FightRecorder bridge methods, with the module faked out.

The bridge must own none of the mechanics -- discovery, hashing, the
network and the copy all live in wingman/fightrecorder.py and have
their own tests. What is pinned here is the shape the page consumes:
local-unless-asked status, and an update that reports each failure mode
instead of a boolean.
"""

import pytest

from tests.test_api import make_api


@pytest.fixture
def fake_fr(monkeypatch):
    """A wingman.fightrecorder whose functions record what the bridge
    called and answer from a dict the tests can rewrite."""
    from wingman.ui import api as api_mod

    state = {"calls": []}

    def install(**overrides):
        defaults = {
            "dll_path": lambda: r"C:\obs\obs-fightrecorder.dll",
            "find_obs_plugin_dir": lambda: r"C:\obs",
            "sha256_file": lambda p: "a" * 64,
            "latest_release": lambda: {
                "tag": "v1.1.2",
                "url": "https://x",
                "digest": "a" * 64,
            },
            "download_latest": lambda url, digest, staged: (
                state["calls"].append(("download", url, digest)) or ""
            ),
            "apply_update": lambda d, staged: (
                state["calls"].append(("apply", d, staged)) or ""
            ),
            "elevated_copy": lambda d, staged: (
                state["calls"].append(("elevated", d, staged)) or ""
            ),
        }
        defaults.update(overrides)
        for name, fn in defaults.items():
            monkeypatch.setattr(api_mod.fightrecorder, name, fn)
        return state

    return install


def test_status_is_local_until_asked(tmp_path, fake_fr):
    """Opening Settings must not touch the network: no check, no
    latest_release call, and up_to_date stays None (an absence, which
    the page renders as no verdict, not as a lie)."""
    api = make_api(tmp_path)
    fake_fr()
    res = api.fightrecorder_status()
    assert res["installed"] is True
    assert res["up_to_date"] is None
    assert res["latest_tag"] == ""


def test_status_check_compares_digests(tmp_path, fake_fr):
    api = make_api(tmp_path)
    state = fake_fr()
    res = api.fightrecorder_status(check=True)
    assert res["up_to_date"] is True
    assert res["latest_tag"] == "v1.1.2"

    state["calls"] = []
    fake_fr(sha256_file=lambda p: "b" * 64)
    res = api.fightrecorder_status(check=True)
    assert res["up_to_date"] is False


def test_status_reports_an_offline_check_without_losing_the_local_half(
    tmp_path, fake_fr
):
    api = make_api(tmp_path)

    def offline():
        raise OSError("no network")

    fake_fr(latest_release=offline)
    res = api.fightrecorder_status(check=True)
    assert res["installed"] is True  # the local half survives
    assert "GitHub" in res["error"]


def test_status_without_obs_reports_not_detected(tmp_path, fake_fr):
    api = make_api(tmp_path)
    fake_fr(dll_path=lambda: None, find_obs_plugin_dir=lambda: None)
    res = api.fightrecorder_status(check=True)
    assert res["installed"] is False
    assert res["detected"] is False
    assert res["up_to_date"] is None  # nothing installed: no verdict


def test_update_happy_path_downloads_applies_and_verifies(tmp_path, fake_fr):
    api = make_api(tmp_path)
    state = fake_fr()
    res = api.update_fightrecorder()
    assert res == {"ok": True, "error": "", "tag": "v1.1.2"}
    kinds = [c[0] for c in state["calls"]]
    assert kinds == ["download", "apply"]  # no elevation needed


def test_update_falls_back_to_elevation_when_the_direct_copy_refuses(tmp_path, fake_fr):
    api = make_api(tmp_path)
    state = fake_fr()

    def refusing(d, staged):
        state["calls"].append(("apply", d, staged))
        return "OBS may be running, or the folder needs admin rights."

    fake_fr(apply_update=refusing)
    res = api.update_fightrecorder()
    assert res["ok"] is True
    kinds = [c[0] for c in state["calls"]]
    assert kinds == ["download", "apply", "elevated"]


def test_update_reports_each_failure_verbatim(tmp_path, fake_fr):
    api = make_api(tmp_path)

    fake_fr(find_obs_plugin_dir=lambda: None, dll_path=lambda: None)
    res = api.update_fightrecorder()
    assert res == {"ok": False, "error": "OBS Studio was not detected on this machine."}

    def offline():
        raise OSError("no network")

    fake_fr(latest_release=offline)
    res = api.update_fightrecorder()
    assert "GitHub" in res["error"]

    fake_fr(
        download_latest=lambda u, d, s: (
            "The download did not match the release checksum -- not installed."
        )
    )
    res = api.update_fightrecorder()
    assert res["ok"] is False and "checksum" in res["error"]

    def refusing(d, staged):
        state["calls"].append(("apply", d, staged))
        return "OBS may be running, or the folder needs admin rights."

    # One install call: a second fake_fr() would reset the first call's
    # overrides along with the defaults.
    state = fake_fr(
        apply_update=refusing,
        elevated_copy=lambda d, s: (
            state["calls"].append(("elevated", d, s)) or "declined"
        ),
    )
    res = api.update_fightrecorder()
    assert res["ok"] is False and res["error"] == "declined"
    assert [c[0] for c in state["calls"]] == ["download", "apply", "elevated"]
