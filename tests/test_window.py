"""ui/window.py -- construction flags, placement, and the js_api guard.

No real pywebview here. window.py imports it lazily inside create()/run()
(see that module's docstring), which is what lets these tests inject a stub
module and run on a headless box with no WebView2 anywhere.
"""

import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from obs_youtube_uploader.ui import window as window_mod
from obs_youtube_uploader.ui.api import Api


class _FakeEvent:
    """pywebview's Event, reduced to the one operator create() uses.

    Real Events run their subscribers on the pywebview thread; this only
    records them, so the tests can assert that the border is wired up
    without any of it reaching Win32.
    """

    def __init__(self, sink):
        self._sink = sink

    def __iadd__(self, handler):
        self._sink.append(handler)
        return self


@pytest.fixture
def fake_webview(monkeypatch):
    """Stand in for the `webview` module and record what it was asked for."""
    calls = {}

    def create_window(title, url, **kwargs):
        calls["title"] = title
        calls["url"] = url
        calls["kwargs"] = kwargs
        # `events` is not decoration: create() subscribes to `shown` to
        # attach the resize border, so a window without it raises in every
        # test here. `shown` records its subscribers rather than firing
        # them, because firing would reach the real Win32 code.
        calls["shown_handlers"] = []
        calls["window"] = SimpleNamespace(
            label="the-window",
            events=SimpleNamespace(shown=_FakeEvent(calls["shown_handlers"])),
        )
        return calls["window"]

    def start(**kwargs):
        calls["start_kwargs"] = kwargs

    monkeypatch.setitem(
        sys.modules,
        "webview",
        SimpleNamespace(create_window=create_window, start=start),
    )
    return calls


def _bare_api():
    """An Api instance built without running __init__.

    Deliberate: this file tests the PUBLIC SURFACE that pywebview walks,
    which is a property of the class. Coupling it to whatever arguments the
    constructor happens to take would make the RecursionError guard below
    fail for an unrelated reason the day Api gains a parameter.
    """
    return Api.__new__(Api)


def test_the_window_is_frameless_with_drag_left_to_the_page(fake_webview):
    """easy_drag moves the whole window on any mousedown in the body, which
    would make every button, row, and text field drag the window instead of
    doing its job. The page marks its own title bar with
    `pywebview-drag-region` -- that is the entire drag surface."""
    window_mod.create(_bare_api())
    kwargs = fake_webview["kwargs"]
    assert kwargs["frameless"] is True
    assert kwargs["easy_drag"] is False


def test_the_window_has_a_resize_border_attached_once_it_is_shown(fake_webview):
    """The border is attached on `shown`, not at create time.

    window.native does not exist until the form is created
    (winforms.py:195), and enable_resize needs its handle. Subscribing is
    all this can check on Linux -- what the handler then does is Win32 and
    only testable by hand.
    """
    window_mod.create(_bare_api())
    assert len(fake_webview["shown_handlers"]) == 1


def test_the_window_declares_the_size_its_layout_can_survive(fake_webview):
    """Asserts the exact tuple, not merely that the kwarg was passed.

    A presence-only check passes on a wrong number, and both provisional
    estimates WERE wrong -- the height by 65px, in the direction that lets
    a user drag part of the layout out of view. These numbers were measured
    against the real page; changing them should require saying why.
    """
    window_mod.create(_bare_api())
    assert fake_webview["kwargs"]["min_size"] == (840, 625)


def test_the_window_is_given_an_explicit_position(fake_webview):
    """Frameless windows get no sensible default placement -- the spike's
    window opened somewhere not visible on the primary screen. x and y are
    not optional here."""
    window_mod.create(_bare_api())
    kwargs = fake_webview["kwargs"]
    assert isinstance(kwargs["x"], int)
    assert isinstance(kwargs["y"], int)


def test_the_native_background_matches_the_ground_token(fake_webview):
    """The native surface is painted before the first frame of HTML. If it
    does not match --bg, launch flashes white on a near-black design."""
    window_mod.create(_bare_api())
    assert fake_webview["kwargs"]["background_color"] == "#0c0d10"
    assert window_mod.BACKGROUND == "#0c0d10"


def test_the_window_loads_a_page_that_actually_exists(fake_webview):
    """PyInstaller exits 0 when a `datas` entry resolves to nothing, so a
    misresolved web/ shows up as a blank window rather than a build error.
    Asserting the file is really there is the cheap half of that guard."""
    window_mod.create(_bare_api())
    url = Path(fake_webview["url"])
    assert url.name == "index.html"
    assert url.exists()


def test_the_api_gets_the_window_after_construction(fake_webview):
    """create_window() needs js_api, and the window does not exist until it
    returns -- so the wiring is necessarily a second step."""
    api = _bare_api()
    window = window_mod.create(api)
    assert window is fake_webview["window"]
    assert api._window is window


def test_no_public_attribute_of_the_api_holds_the_window(fake_webview):
    """THE RecursionError guard, and the reason this test exists at all.

    pywebview builds its JS proxy by walking the js_api object's public
    attributes. A public attribute holding a webview.Window sends that walk
    into the WinForms native object, where Rectangle.Empty returns itself;
    it recurses until RecursionError terminates the process about eight
    seconds after launch, with no traceback a user would ever see.

    Every non-method attribute must be underscore-prefixed. Forever.
    """
    api = _bare_api()
    window_mod.create(api)

    assert all(name.startswith("_") for name in vars(api)), (
        f"public instance attribute on Api: {sorted(vars(api))}"
    )
    for name in dir(api):
        if name.startswith("_"):
            continue
        assert callable(getattr(api, name)), (
            f"Api.{name} is public and is not a method; pywebview will walk it"
        )


def test_run_pins_the_backend(fake_webview):
    """Autodetection silently falling back to another backend would make a
    passing run meaningless -- the whole design targets WebView2."""
    window_mod.run()
    assert fake_webview["start_kwargs"] == {"func": None, "gui": "edgechromium"}


def test_run_hands_startup_work_to_pywebview_rather_than_doing_it_first(fake_webview):
    """Anything that pushes at startup must go through this parameter.

    pywebview wraps every evaluate_js in `event.wait(20)` on
    `_pywebviewready`, which cannot be set before start() has run. Work
    done on the main thread ahead of run() therefore blocks the launch for
    the full twenty seconds and then loses its message to Api._push's bare
    except. start() runs `func` on its own thread instead.
    """

    def work():
        pass

    window_mod.run(work)
    assert fake_webview["start_kwargs"]["func"] is work


def test_run_silences_pywebviews_property_walk():
    """pywebview logs an unbounded property walk of native objects at DEBUG.
    Harmless in a windowed build; it would swamp the rotating log file."""
    log = logging.getLogger("pywebview")
    log.setLevel(logging.DEBUG)
    log.addHandler(logging.StreamHandler())
    try:
        window_mod._silence_pywebview_logging()
        assert log.level == logging.WARNING
        assert log.handlers == []
        # propagate stays on: warnings and errors must still reach the
        # rotating file handler configure_logging() puts on the root logger.
        assert log.propagate is True
    finally:
        log.handlers = []
        log.setLevel(logging.NOTSET)


def test_placement_centres_the_window_on_the_screen():
    assert window_mod._placement(1000, 600, metrics=lambda: (1920, 1080)) == (460, 240)


def test_placement_never_goes_negative_on_a_small_screen():
    """A negative x on Windows is legal and puts the title bar off the left
    edge -- on a frameless window that means no way to drag it back."""
    assert window_mod._placement(1600, 1200, metrics=lambda: (1280, 720)) == (0, 0)


def test_placement_is_in_logical_units_on_a_scaled_primary():
    """pywebview takes x/y in the SAME logical units as width/height and
    applies the DPI scale itself (winforms.py), but GetSystemMetrics
    reports PHYSICAL pixels under PROCESS_SYSTEM_DPI_AWARE. Centring
    against the physical number hands pywebview a coordinate it then
    doubles.

    Observed on a 3840x2160 primary at 200%: the window was placed at
    x=2800 on a screen 3840 wide and hung 1014px off the right edge, half
    of it on the next monitor. Invisible at 100%, where the two units are
    the same number."""
    x, y = window_mod._placement(
        1040, 680, metrics=lambda: (3840, 2160), scale=lambda: 2.0
    )
    assert (x, y) == (440, 200)
    # What pywebview will actually use, once it applies the scale back.
    assert (x * 2, y * 2) == (880, 400)


def test_placement_at_100_percent_is_unchanged():
    """The scaled path must not move the window for the majority of users
    who run at 100%."""
    assert window_mod._placement(
        1000, 600, metrics=lambda: (1920, 1080), scale=lambda: 1.0
    ) == (460, 240)


def test_placement_survives_a_scale_of_zero():
    """GetDpiForSystem returning 0 is a documented failure mode, and
    dividing by it would take the window down at startup."""
    assert window_mod._placement(
        1000, 600, metrics=lambda: (1920, 1080), scale=lambda: 0.0
    ) == (460, 240)


# --- the login launch (M3) --------------------------------------------------


def test_the_window_is_shown_by_default(fake_webview):
    """Every launch except the login one raises its window. A default of
    hidden would make the Start menu shortcut look like it did nothing."""
    window_mod.create(_bare_api())
    assert fake_webview["kwargs"]["hidden"] is False


def test_the_login_launch_builds_the_window_without_showing_it(fake_webview):
    """M3: the app is tray-resident, and a start-on-login that raises a
    window at every boot is worse than no setting at all.

    Built, not skipped -- only its visibility differs, which is what lets
    the tray's Open item call show() with no special case for this path.
    """
    window_mod.create(_bare_api(), hidden=True)
    kwargs = fake_webview["kwargs"]
    assert kwargs["hidden"] is True
    # Everything else about the window is unchanged by starting hidden.
    assert kwargs["min_size"] == (840, 625)
    assert kwargs["frameless"] is True
