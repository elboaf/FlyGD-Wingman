"""dpapi.py is the only Windows-only module in the package. Everything else
runs in CI on Linux, and this test exists to pin the one property that can
be checked off Windows: the module IMPORTS cleanly there.

That is not a formality. ctypes.WinDLL and ctypes.windll do not exist on
Linux, so a library binding built at module scope would raise at import --
and because state.py's neighbour tokens.py imports this module for its
production defaults, that import error would take the entire subsystem's
test suite with it. The bindings are therefore built lazily inside
functions, exactly as preview/win32.py:1-9 describes for the same reason.
"""
import sys

import pytest

from obs_youtube_uploader.eveskills import dpapi


def test_the_module_imports_off_windows():
    assert callable(dpapi.protect)
    assert callable(dpapi.unprotect)


def test_available_is_false_off_windows():
    """The controller reads this to decide whether it can store a token at
    all. A wrong answer here would mean silently discarding one."""
    assert dpapi.available() is (sys.platform == "win32")


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has crypt32")
def test_protect_refuses_off_windows_rather_than_crashing():
    """Called by mistake off Windows this must be a clean, explanatory
    error, not an obscure ctypes AttributeError from three frames down."""
    with pytest.raises(OSError):
        dpapi.protect(b"x")


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has crypt32")
def test_unprotect_refuses_off_windows_rather_than_crashing():
    with pytest.raises(OSError):
        dpapi.unprotect(b"x")


@pytest.mark.skipif(sys.platform != "win32", reason="requires real DPAPI")
def test_round_trips_on_windows():
    """The only place the real crypt32 path is exercised. The smoke
    checklist carries the same check for a release build."""
    assert dpapi.unprotect(dpapi.protect(b"secret")) == b"secret"
