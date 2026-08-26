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
