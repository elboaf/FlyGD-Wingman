"""Suite-wide isolation of the application's state directory.

Two files used to land in the developer's real state directory on every
run. Not through save_bookmarks -- test_api_bookmarks.py already
redirects settings_file() in its api fixture -- but through three other
paths nobody had stubbed: the upload worker persisting the channel title
(api.py:783-796, 15 tests in test_api_upload.py), the probe cache
writing durations.json, and set_preview_enabled (api.py:1285, 3 tests in
test_preview_wiring.py). Per-test stubs closed the instances someone
noticed; this closes the class.

LOCALAPPDATA rather than paths.settings_file(): state_dir() reads that
one variable (paths.py:14-20) and every other path derives from it, so
redirecting it moves settings, durations, token, seen, logs and tmp
together. Patching settings_file() would also break test_paths.py:16-19,
which sets this same variable and then asserts on the real function.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolate_state_dir(tmp_path, monkeypatch):
    """Point paths.state_dir() at this test's tmp_path.

    Autouse and unreferenced by design: a test that has to remember to
    ask for isolation is a test that will forget.
    """
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "state"))
