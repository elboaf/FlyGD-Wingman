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


@pytest.fixture
def fake_webview(monkeypatch):
    """Stand in for the `webview` module and record what it was asked for."""
    calls = {}

    def create_window(title, url, **kwargs):
        calls["title"] = title
        calls["url"] = url
        calls["kwargs"] = kwargs
        calls["window"] = SimpleNamespace(label="the-window")
        return calls["window"]

    def start(**kwargs):
        calls["start_kwargs"] = kwargs

    monkeypatch.setitem(
        sys.modules, "webview",
        SimpleNamespace(create_window=create_window, start=start))
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
        f"public instance attribute on Api: {sorted(vars(api))}")
    for name in dir(api):
        if name.startswith("_"):
            continue
        assert callable(getattr(api, name)), (
            f"Api.{name} is public and is not a method; pywebview will walk it")


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
