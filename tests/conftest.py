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

import re
import secrets

import pytest


@pytest.fixture
def tmp_path(request, tmp_path_factory):
    """Keep pytest's lifecycle without scanning all earlier cases for a suffix."""
    original_mktemp = tmp_path_factory.mktemp

    def mktemp(basename, numbered=True):
        if not numbered:
            return original_mktemp(basename, numbered=False)
        # Keep each leaf within 31 ASCII characters, even in large sessions.
        stem = re.sub(r"[^A-Za-z0-9_]", "_", basename)[:14]
        attempts = 0
        while True:
            attempts += 1
            try:
                return original_mktemp(f"{stem}-{secrets.token_hex(8)}", numbered=False)
            except FileExistsError:
                if attempts == 10:
                    raise

    # A dynamic same-name request obtains the overridden builtin fixture. It
    # still owns its generator finalizer, report stash and retention policy.
    # Only this factory instance is adapted, only during allocation — session
    # fixtures and direct factory users retain normal numbered/exact semantics.
    with pytest.MonkeyPatch.context() as patch:
        # Restore attribute ownership too — setattr would leave a bound method
        # on the instance, shadowing the class method after the context exits.
        patch.setitem(vars(tmp_path_factory), "mktemp", mktemp)
        return request.getfixturevalue("tmp_path")


@pytest.fixture(autouse=True)
def _isolate_state_dir(tmp_path, monkeypatch):
    """Point paths.state_dir() at this test's tmp_path.

    Autouse and unreferenced by design: a test that has to remember to
    ask for isolation is a test that will forget.
    """
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "state"))


@pytest.fixture(autouse=True)
def _reset_legacy_state_flag():
    """paths._use_legacy is process-global; a fallback in one test would
    silently redirect every test after it. Reset both sides of the yield so
    an exception mid-test cannot leave it set."""
    from wingman import paths

    paths._use_legacy = False
    yield
    paths._use_legacy = False
