"""Unit tests for the UX screenshot shooter's decision logic.

The shooter's Windows shell (process control, CDP socket, capture) has no
tests, exactly as hotkeys.py has none: it is unreachable off-platform. So
every DECISION it makes lives in a pure function here instead, which is
the same split bookmarks.py/hotkeys.py already uses.
"""

import importlib.util
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / "wingman" / "web"


def _load():
    """Import scripts/shoot_screens.py by path.

    scripts/ is deliberately not a package -- making it one would put it in
    reach of setuptools auto-discovery for no benefit -- so the module is
    loaded from its path rather than imported by name.
    """
    path = ROOT / "scripts" / "shoot_screens.py"
    spec = importlib.util.spec_from_file_location("shoot_screens", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


shoot = _load()


def test_gate_on_shoots_every_screen():
    to_shoot, skipped = shoot.screens_for_gate(True)
    assert len(to_shoot) == 9
    assert skipped == []


def test_gate_off_shoots_only_the_four_reachable_screens():
    """With EVE undetected the app hides two routes AND three sections.

    Photographing them anyway would produce a set showing screens the user
    cannot reach -- the same kind of lie as a ?dev=1 capture, which is the
    thing this tool exists to avoid.
    """
    to_shoot, skipped = shoot.screens_for_gate(False)
    assert [s.key for s in to_shoot] == [
        "uploader",
        "settings-uploading",
        "settings-general",
        "dialog",
    ]
    assert len(skipped) == 5


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


def test_screen_list_matches_the_page():
    """The routes and sections shot are the ones the page actually has.

    Retyped copies of derived lists have drifted into user-visible text in
    this repo before, which is why the rule exists.
    """
    raw = (WEB / "index.html").read_text(encoding="utf-8")
    html = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL)

    routes = set(re.findall(r'id="route-([\w-]+)"', html))
    shot_routes = {s.route for s in shoot.SCREENS}
    assert routes - shoot.EXCLUDED_ROUTES == shot_routes

    # The other half of the exclusion: assert it still names a real route.
    # Without this the exclusion silently covers nothing after a rename.
    # (Written this way round deliberately: `EXCLUDED_ROUTES <= routes` is
    # the same assertion but trips ruff's SIM300 yoda-condition rule.)
    assert routes >= shoot.EXCLUDED_ROUTES

    sections = set(re.findall(r'data-section="([\w-]+)"', html))
    assert {s.section for s in shoot.SCREENS if s.section} == sections


def test_gated_column_matches_the_apps_own_gate():
    """Derived from app.js, following test_settings_eve_gate.py's pattern."""
    app = _strip_js_comments((WEB / "app.js").read_text(encoding="utf-8"))

    declared_routes = re.search(r"WM\.EVE_ROUTES = \[([^\]]*)\]", app)
    declared_sections = re.search(r"WM\.EVE_SECTIONS = \[([^\]]*)\]", app)
    assert declared_routes, "app.js no longer declares WM.EVE_ROUTES"
    assert declared_sections, "app.js no longer declares WM.EVE_SECTIONS"
    eve_routes = set(re.findall(r"'([\w-]+)'", declared_routes.group(1)))
    eve_sections = set(re.findall(r"'([\w-]+)'", declared_sections.group(1)))

    for screen in shoot.SCREENS:
        expected = screen.route in eve_routes or screen.section in eve_sections
        assert screen.gated == expected, (
            f"{screen.key} gated flag disagrees with app.js"
        )


def test_page_candidates_keeps_the_real_app_page():
    targets = [
        {"type": "page", "url": "http://127.0.0.1:52913/index.html"},
    ]
    assert shoot.page_candidates(targets) == targets


def test_page_candidates_rejects_the_dev_harness():
    """dev.js fabricates bridge replies and photographs convincingly.

    A stray ?dev=1 page holding the debug port once returned
    {applied: true} for a call that never reached Python, which invented a
    bug that did not exist. Any query string is refused.
    """
    targets = [{"type": "page", "url": "file:///C:/dev/web/index.html?dev=1"}]
    assert shoot.page_candidates(targets) == []


def test_page_candidates_rejects_non_page_targets():
    """targets[0] is routinely a Chrome extension background page.

    Attaching to one succeeds and evaluates fine, then reports
    "WM is not defined" -- which reads exactly like the page failing to
    load, and has cost a previous session an entire debugging session.
    """
    targets = [
        {"type": "background_page", "url": "chrome-extension://abc/index.html"},
        {"type": "service_worker", "url": "http://127.0.0.1:1/index.html"},
    ]
    assert shoot.page_candidates(targets) == []


def test_page_candidates_ignores_the_debug_port():
    """pywebview serves the page from its OWN random port.

    ui/window.py hands pywebview a local file and 6.2.1 serves it through a
    separate HTTP server, so requiring the URL to carry the debug port
    rejects every legitimate target.
    """
    targets = [{"type": "page", "url": "http://127.0.0.1:1/index.html"}]
    assert shoot.page_candidates(targets) == targets


def test_page_candidates_rejects_a_page_that_is_not_index_html():
    """A same-server page other than index.html is not the app.

    Without pinning the path, /json/list or some other page served by the
    same pywebview HTTP server would be accepted as a candidate just
    because it shares a debug session with the real page.
    """
    targets = [
        {"type": "page", "url": "http://127.0.0.1:52913/json/list"},
        {"type": "page", "url": "http://127.0.0.1:52913/other.html"},
    ]
    assert shoot.page_candidates(targets) == []


def test_page_candidates_rejects_any_non_dev_query_string_too():
    """The docstring promises ANY query string is refused, not just ?dev=1.

    A narrower check that only special-cases the literal dev=1 harness
    would still let a target like ?foo=1 through -- this uses an http://
    URL so the query string is the only thing that could disqualify it.
    """
    targets = [{"type": "page", "url": "http://127.0.0.1:52913/index.html?foo=1"}]
    assert shoot.page_candidates(targets) == []
