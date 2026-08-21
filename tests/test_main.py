import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from obs_youtube_uploader import paths, settings
from obs_youtube_uploader.app import dpi_scale
from obs_youtube_uploader.__main__ import (
    configure_logging, get_system_dpi, resolve_recording_dir, set_dpi_awareness,
)


def _unreachable_ask(**kwargs):
    """Fails the test if reached -- proves a branch didn't fall through to
    asking the user."""
    raise AssertionError("filedialog.askdirectory should not have been called")


def test_stored_value_wins_over_detection(tmp_path):
    """A valid stored dir must win even when detection disagrees -- this is
    the precedence bug: prove it's actually exercised, not trivially true
    because detection would return the same thing."""
    stored_dir = tmp_path / "stored"
    stored_dir.mkdir()
    detected_dir = tmp_path / "detected"
    detected_dir.mkdir()
    cfg = {"recording_dir": str(stored_dir)}

    with patch("obs_youtube_uploader.__main__.obsconfig.find_recording_dir",
               return_value=detected_dir) as mock_detect:
        result = resolve_recording_dir(cfg, ask=_unreachable_ask)

    assert result == stored_dir
    mock_detect.assert_not_called()


def test_stale_stored_value_falls_through_to_detection(tmp_path):
    """A stored dir that no longer exists (e.g. a drive unplugged, or -- as
    happened for real -- a wrong folder saved before a detection bug was
    fixed) must not be trusted; detection must run instead."""
    detected_dir = tmp_path / "detected"
    detected_dir.mkdir()
    cfg = {"recording_dir": str(tmp_path / "does-not-exist")}

    with patch("obs_youtube_uploader.__main__.obsconfig.find_recording_dir",
               return_value=detected_dir):
        result = resolve_recording_dir(cfg, ask=_unreachable_ask)

    assert result == detected_dir


def test_no_stored_value_falls_through_to_detection(tmp_path):
    detected_dir = tmp_path / "detected"
    detected_dir.mkdir()
    cfg = {}

    with patch("obs_youtube_uploader.__main__.obsconfig.find_recording_dir",
               return_value=detected_dir):
        result = resolve_recording_dir(cfg, ask=_unreachable_ask)

    assert result == detected_dir


def test_no_stored_value_and_no_detection_asks_user(tmp_path):
    chosen_dir = tmp_path / "chosen"
    chosen_dir.mkdir()
    cfg = {}

    with patch("obs_youtube_uploader.__main__.obsconfig.find_recording_dir",
               return_value=None):
        result = resolve_recording_dir(cfg, ask=lambda **kwargs: str(chosen_dir))

    assert result == chosen_dir


def test_configure_logging_redacts_webhook_token_from_foreign_logger(tmp_path, monkeypatch):
    """The redaction filter must be attached to the HANDLER, not a logger, so
    it also catches records from libraries we never touch directly (e.g. an
    HTTP transport logging a request URL at DEBUG). A filter on our own
    logger would never see those records -- this proves the control is
    actually live, not just unit-tested in isolation."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    paths.ensure_dirs()

    token = "supersecrettoken1234567890abcdef1234567890abcdef1234567890abcd"
    webhook_url = f"https://discord.com/api/webhooks/123456789012345678/{token}"
    settings.save({**settings.DEFAULTS, "discord_webhook": webhook_url})

    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    try:
        configure_logging()
        handler = root_logger.handlers[-1]

        foreign_logger = logging.getLogger("some.third.party.transport")
        foreign_logger.warning("GET %s", webhook_url)
        handler.flush()

        log_path = paths.log_dir() / "uploader_debug.log"
        contents = log_path.read_text(encoding="utf-8")
    finally:
        for h in list(root_logger.handlers):
            if h not in original_handlers:
                root_logger.removeHandler(h)
                h.close()

    assert token not in contents
    assert "GET" in contents


class _FakeUser32:
    """Stands in for `ctypes.windll.user32` so the Windows-only DPI path can
    be exercised on the Linux test host."""

    def __init__(self, dpi=None, exc=None):
        self._dpi = dpi
        self._exc = exc

    def GetDpiForSystem(self):
        if self._exc is not None:
            raise self._exc
        return self._dpi


class _FakeShcore:
    def __init__(self, exc=None):
        self._exc = exc
        self.calls = []

    def SetProcessDpiAwareness(self, value):
        if self._exc is not None:
            raise self._exc
        self.calls.append(value)


def _fake_windll(monkeypatch, **modules):
    import ctypes
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(**modules), raising=False)


def test_get_system_dpi_falls_back_to_96_off_windows():
    """96 is 100% scaling. The suite runs on Linux, where the Win32 call does
    not exist at all -- the platform guard, not an exception handler, is what
    must produce the fallback."""
    with patch("sys.platform", "linux"):
        assert get_system_dpi() == 96


def test_set_dpi_awareness_is_a_silent_no_op_off_windows():
    """Must not raise: it is the very first statement in main(), so anything
    it throws off-Windows blocks startup entirely during development."""
    with patch("sys.platform", "linux"):
        assert set_dpi_awareness() is None


def test_get_system_dpi_floors_a_zero_return_at_96(monkeypatch):
    """GetDpiForSystem returns 0 on failure rather than raising, so the
    except clause structurally cannot catch it. Without the floor this would
    feed `tk scaling 0.0` and silently collapse every point-sized font in the
    app -- a total failure that is nearly undiagnosable from a user report."""
    with patch("sys.platform", "win32"):
        _fake_windll(monkeypatch, user32=_FakeUser32(dpi=0))
        assert get_system_dpi() == 96


def test_get_system_dpi_floors_any_sub_96_return(monkeypatch):
    """Nothing below 100% scaling is meaningful here; the constants this
    feeds were all chosen at 96 DPI, so shrinking below it is never right."""
    with patch("sys.platform", "win32"):
        _fake_windll(monkeypatch, user32=_FakeUser32(dpi=48))
        assert get_system_dpi() == 96


def test_get_system_dpi_passes_through_a_real_high_dpi_value(monkeypatch):
    """The floor must not clamp legitimate values -- 144 is 150% scaling."""
    with patch("sys.platform", "win32"):
        _fake_windll(monkeypatch, user32=_FakeUser32(dpi=144))
        assert get_system_dpi() == 144


def test_get_system_dpi_survives_a_missing_user32_export(monkeypatch):
    """GetDpiForSystem is Windows 10+; older hosts raise AttributeError."""
    with patch("sys.platform", "win32"):
        _fake_windll(monkeypatch, user32=_FakeUser32(exc=AttributeError()))
        assert get_system_dpi() == 96


def test_set_dpi_awareness_requests_system_dpi_aware_not_per_monitor(monkeypatch):
    """1 == PROCESS_SYSTEM_DPI_AWARE. Per-Monitor (2) is deliberately NOT
    used: it would require handling WM_DPICHANGED when the window moves
    between monitors of different scale."""
    shcore = _FakeShcore()
    with patch("sys.platform", "win32"):
        _fake_windll(monkeypatch, shcore=shcore)
        set_dpi_awareness()
    assert shcore.calls == [1]


def test_set_dpi_awareness_degrades_when_shcore_is_missing(monkeypatch):
    """shcore.dll predates Windows 8.1. A missing DLL must leave the process
    DPI-unaware, never prevent it from starting."""
    with patch("sys.platform", "win32"):
        _fake_windll(monkeypatch, shcore=_FakeShcore(exc=OSError("no shcore.dll")))
        assert set_dpi_awareness() is None


def test_dpi_scale_normalises_tk_scaling_to_a_100_percent_multiplier():
    """`tk scaling` is points-per-pixel (dpi/72), so 96 DPI is 1.333..., not
    1.0. dpi_scale divides that by the 96-DPI baseline to get the plain
    "1.0 at 100%, 1.5 at 150%" multiplier the pixel constants are scaled by.
    Reading it as points-per-pixel directly would over-size everything by a
    third."""
    for dpi, expected in ((96, 1.0), (120, 1.25), (144, 1.5)):
        widget = SimpleNamespace(tk=SimpleNamespace(
            call=lambda *args, _v=dpi / 72.0: _v))
        assert dpi_scale(widget) == pytest.approx(expected)
