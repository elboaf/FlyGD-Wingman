"""The EVE visibility gate.

One switch hides the EVE destinations and sections. The tests that matter
are about what it is NOT allowed to do: it governs visibility only, and it
must never be able to hide a feature that is still running, because that
would conceal the only control that stops it.
"""

from tests.test_api_settings import settings_api
from wingman import settings as settings_mod


def test_it_defaults_to_shown(tmp_path, monkeypatch):
    """An upgrading user's settings.json predates this key. Defaulting it
    off would silently remove four things they already use."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    assert settings_mod.DEFAULTS["show_eve_tools"] is True
    assert api.get_settings()["settings"]["show_eve_tools"] is True


def test_a_missing_key_normalises_to_shown(tmp_path):
    """The same guarantee at the file level, since that is where an
    upgrading user's document actually arrives from."""
    doc = settings_mod._normalize({"privacy": "unlisted"})
    assert doc["show_eve_tools"] is True


def test_a_junk_value_is_coerced_not_defaulted(tmp_path):
    """A hand-edited string would otherwise make every non-empty value mean
    "shown" and "" mean "hidden", which nobody intended."""
    assert settings_mod._normalize({"show_eve_tools": 0})["show_eve_tools"] is False
    assert settings_mod._normalize({"show_eve_tools": "no"})["show_eve_tools"] is True


def test_hiding_is_refused_while_bookmarks_are_running(tmp_path, monkeypatch):
    """THE guard. Hiding a running feature conceals its off switch:
    eighteen global keybinds would keep firing in EVE with no reachable
    control to stop them."""
    api, _window, saved = settings_api(
        tmp_path, monkeypatch, settings={"eve_bookmarks": {"enabled": True}}
    )

    result = api.set_show_eve_tools(False)

    assert result["applied"] is False
    assert "Bookmarks" in result["error"]
    assert saved == {}
    assert api._state.settings["show_eve_tools"] is True


def test_hiding_is_refused_while_previews_are_running(tmp_path, monkeypatch):
    api, _window, saved = settings_api(
        tmp_path, monkeypatch, settings={"preview": {"enabled": True}}
    )

    result = api.set_show_eve_tools(False)

    assert result["applied"] is False
    assert "Previews" in result["error"]
    assert saved == {}


def test_hiding_is_refused_while_fleet_bar_is_running(tmp_path, monkeypatch):
    """Fleet Bar is a third EVE-only feature with its own runtime switch.
    Hiding it while it is enabled would conceal the only control that stops
    it -- the same shape as the Bookmarks and Previews guards."""
    api, _window, saved = settings_api(
        tmp_path, monkeypatch, settings={"fleet_bar": {"enabled": True}}
    )

    result = api.set_show_eve_tools(False)

    assert result["applied"] is False
    assert "Fleet Bar" in result["error"]
    assert saved == {}
    assert api._state.settings["show_eve_tools"] is True


def test_the_refusal_names_both_when_both_are_running(tmp_path, monkeypatch):
    """ "Turn something off first" is useless if it does not say what."""
    api, _window, _saved = settings_api(
        tmp_path,
        monkeypatch,
        settings={"eve_bookmarks": {"enabled": True}, "preview": {"enabled": True}},
    )

    error = api.set_show_eve_tools(False)["error"]

    assert "Bookmarks" in error and "Previews" in error


def test_hiding_succeeds_once_both_are_off(tmp_path, monkeypatch):
    api, _window, saved = settings_api(
        tmp_path,
        monkeypatch,
        settings={"eve_bookmarks": {"enabled": False}, "preview": {"enabled": False}},
    )

    assert api.set_show_eve_tools(False)["applied"] is True
    assert saved["show_eve_tools"] is False


def test_showing_is_never_refused(tmp_path, monkeypatch):
    """The guard is asymmetric on purpose. Turning the tools back ON can
    never strand anything, so a running feature must not block it -- and a
    user whose file somehow has both would otherwise be stuck hidden."""
    api, _window, _saved = settings_api(
        tmp_path,
        monkeypatch,
        settings={"show_eve_tools": False, "eve_bookmarks": {"enabled": True}},
    )

    assert api.set_show_eve_tools(True)["applied"] is True


def test_the_gate_never_touches_the_runtime_switches(tmp_path, monkeypatch):
    """Visibility only. The rejected alternative was a kill switch, which
    would silently stop global keybinds from what reads as a display
    preference -- and could not know which of the two to restore on
    re-enable without a third persisted value."""
    api, _window, _saved = settings_api(
        tmp_path,
        monkeypatch,
        settings={"eve_bookmarks": {"enabled": False}, "preview": {"enabled": False}},
    )

    api.set_show_eve_tools(False)

    assert api._state.settings["eve_bookmarks"]["enabled"] is False
    assert api._state.settings["preview"]["enabled"] is False

    api.set_show_eve_tools(True)

    # Unchanged in both directions: the gate has no opinion about them.
    assert api._state.settings["eve_bookmarks"]["enabled"] is False
    assert api._state.settings["preview"]["enabled"] is False


def test_startup_still_reads_only_the_feature_flags():
    """The gate must not become a second input to whether the engine runs.
    start_engine_if_enabled and start_previews_if_enabled read the feature
    flags at every launch; if the gate ever reached them, a hidden-but-
    enabled install would stop starting its own engine."""
    import inspect

    from wingman import __main__ as main_mod

    src = inspect.getsource(main_mod.start_engine_if_enabled)
    assert "show_eve_tools" not in src
    assert "enabled" in src


def test_the_page_gates_both_destinations_and_every_eve_section():
    """Nothing executes web/*.js, so this asserts on its source the way the
    bridge-contract test does. A destination left out of the list stays
    visible with the tools hidden; a section left out shows a rail entry
    for a feature the user asked not to see.

    Round 5's E1 is what this now pins. The rail is five entries, and the
    claim the merge rests on is that the split runs along PRODUCT.md's own
    independence axis -- "It must not require the EVE tools to upload a
    video, or a Google account to use the EVE tools." The observable form
    of that claim is what the rail becomes with the gate off: **exactly
    Uploading and General**, the two halves that owe EVE nothing. So the
    survivors are derived by subtracting EVE_SECTIONS from the real rail
    rather than retyped -- add a sixth entry and forget to gate it and this
    fails, which is the mistake worth catching.
    """
    import pathlib
    import re

    web = pathlib.Path(__file__).resolve().parents[1] / "wingman" / "web"
    app = (web / "app.js").read_text(encoding="utf-8")
    html = (web / "index.html").read_text(encoding="utf-8")

    # Derived rather than a literal list, and this is the second half of
    # the same rule the sections below already follow. It used to read
    # `"WM.EVE_ROUTES = ['evesettings', 'skills']" in app`, which pinned
    # the whole list -- so the probe formation editor, a sub-screen of
    # Profiles with a route id and deliberately NO navbtn, could not join
    # the list without failing a test whose subject is the title bar.
    #
    # What has to hold is: every EVE-only destination the bar offers is
    # gated. An entry with no button of its own is gated for the other
    # half of apply_eve_gate -- a user standing on a hidden route is moved
    # off it -- and it is checked here only for existing.
    routes = re.search(r"WM\.EVE_ROUTES = \[([^\]]*)\]", app)
    assert routes, "app.js no longer declares WM.EVE_ROUTES"
    gated_routes = set(re.findall(r"'([\w-]+)'", routes.group(1)))
    nav_routes = set(re.findall(r'class="navbtn[^"]*"[^>]*data-route="([\w-]+)"', html))
    # The mirror of the sections half's `assert rail`. Without it an
    # attribute order this regex does not expect (data-route before class)
    # empties the set, and the subset check below then passes over nothing
    # -- which is how a derived assertion rots silently.
    assert nav_routes, "index.html no longer carries any title-bar nav buttons"
    assert nav_routes - {"main"} <= gated_routes, (
        "a destination in the title bar is not gated, so it stays visible "
        f"with the EVE tools hidden: {sorted(nav_routes - {'main'} - gated_routes)}"
    )
    # OVER-gating, which the literal this replaced also caught. Uploader is
    # the half of the product that owes EVE nothing (PRODUCT.md), so gating
    # it would hide the one destination left and strand the user on an
    # empty nav -- the same shape as the last_destination bug app.js's own
    # comment records.
    assert "main" not in gated_routes, (
        "the Uploader is in WM.EVE_ROUTES, so turning the EVE tools off "
        "would hide the one destination that does not need EVE"
    )
    page_routes = set(re.findall(r'id="route-([\w-]+)"', html))
    assert gated_routes <= page_routes, (
        "WM.EVE_ROUTES names routes the page does not have: "
        f"{sorted(gated_routes - page_routes)}"
    )

    declared = re.search(r"WM\.EVE_SECTIONS = \[([^\]]*)\]", app)
    assert declared, "app.js no longer declares WM.EVE_SECTIONS"
    gated = re.findall(r"'([\w-]+)'", declared.group(1))

    rail = re.findall(r'<button class="rail-item[^"]*" data-section="([\w-]+)">', html)
    assert rail, "index.html no longer carries a Settings rail"

    missing = [name for name in gated if name not in rail]
    assert not missing, f"EVE_SECTIONS names sections the rail does not have: {missing}"

    survivors = [name for name in rail if name not in gated]
    assert survivors == ["uploading", "general"], (
        "with the EVE gate off the rail should be exactly Uploading and "
        f"General -- the two halves that need no EVE install -- but it is "
        f"{survivors}. Either a new entry was added without gating it, or "
        "the merge axis E1 chose has been broken."
    )

    # Hiding the screen you are ON would leave a dead pane with no way back.
    block = app.split("WM.apply_eve_gate")[1]
    assert "WM.route('main')" in block
    assert "WM.section('general')" in block


def test_the_toggle_repaints_the_chrome_itself():
    """Found by smoke test: the value persisted and the tabs stayed put
    until the next launch.

    Applying the gate hung off the `wm:settings` push -- but the per-field
    endpoints deliberately do NOT push, because re-sending the whole
    payload is what used to rewrite the field still being edited. So
    nothing told the page to repaint.

    This is the general hazard of immediate save: an endpoint whose effect
    reaches outside its own control has to apply that effect locally,
    because there is no longer a whole-document push to ride on. The gate
    is currently the only such control.
    """
    import pathlib

    web = pathlib.Path(__file__).resolve().parents[1] / "wingman" / "web"
    js = (web / "settings.js").read_text(encoding="utf-8")

    handler = js.split("set_show_eve_tools")[1].split("});")[0]
    assert "apply_eve_gate" in handler, (
        "the toggle writes the setting but never repaints the nav or rail"
    )


def test_hiding_cuts_every_route_into_a_hidden_screen():
    """Found by smoke test: untick the tools while standing on Skills, then
    leave Settings -- and the gear puts you back on Skills, with the nav
    hidden and no way out.

    The toggle lives in Settings, so current_route is 'settings' when it
    fires and the current-route check never matches. `last_destination` is
    what the gear returns to, and it still pointed at Skills.

    The rule this encodes: hiding a screen means cutting EVERY route into
    it, not just the one the user is standing on.
    """
    import pathlib

    web = pathlib.Path(__file__).resolve().parents[1] / "wingman" / "web"
    app = (web / "app.js").read_text(encoding="utf-8")

    block = app.split("WM.apply_eve_gate")[1].split("document.addEventListener")[0]
    assert "WM.last_destination" in block, (
        "the gear can still return to a hidden destination"
    )
