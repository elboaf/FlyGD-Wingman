"""The Python/JavaScript bridge contract, checked lexically.

This repo has no JavaScript test harness (webview-replatform-design.md:545),
so nothing executes web/*.js and nothing would notice a push whose name the
page refuses to register. `WM.handle` is deliberately strict -- it throws on
a name absent from `WM.HANDLERS` (web/app.js) so a typo is caught at
registration rather than becoming a silent no-op.

That strictness has a sharp edge, which is why this file exists. Handlers
are registered at the top level of each route's IIFE, so one unknown name
does not merely fail to register: it throws mid-module, and every
registration and `wire()` call BELOW it never runs. The route then loads as
an inert, empty version of itself -- no data, no buttons, no error the user
can see. Python is complicit in the silence, because `_push` renders as
`window.<handler> && window.<handler>(...)`, so the push is a no-op rather
than an error, and `_push` swallows evaluate_js failures at debug level.

A real instance: `onEveSettingsRunning` was pushed from ui/api.py and added
to web/evesettings.js without being added to `WM.HANDLERS`, which broke the
whole EVE Settings route while every test still passed.

Purely lexical, and only as good as the spellings it watches:

- Only `self._push("literal", ...)` calls are found. A pushed name built at
  runtime is invisible here.
- Only the `WM.HANDLERS = [...]` array literal is parsed. A name appended
  elsewhere at runtime is invisible here.
- A handler in the allowlist that nothing registers is not an error: it may
  be pushed from somewhere other than ui/api.py.
"""
import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "obs_youtube_uploader" / "web"
API = (Path(__file__).resolve().parent.parent / "obs_youtube_uploader"
       / "ui" / "api.py")


def allowlist() -> list:
    """The names in web/app.js's WM.HANDLERS array literal."""
    source = (WEB / "app.js").read_text(encoding="utf-8")
    match = re.search(r"WM\.HANDLERS\s*=\s*\[(.*?)\]", source, re.S)
    assert match, "WM.HANDLERS array literal not found in web/app.js"
    return re.findall(r"'([^']+)'", match.group(1))


def pushed_names() -> list:
    """Every handler name ui/api.py pushes as a string literal."""
    source = API.read_text(encoding="utf-8")
    return sorted(set(re.findall(r"_push\(\s*\"([A-Za-z0-9_]+)\"", source)))


def registered_names() -> dict:
    """Every WM.handle('name', ...) registration, by file."""
    found = {}
    for path in sorted(WEB.glob("*.js")):
        source = path.read_text(encoding="utf-8")
        for name in re.findall(r"WM\.handle\(\s*'([^']+)'", source):
            found.setdefault(name, []).append(path.name)
    return found


def test_the_allowlist_is_parseable_and_not_empty():
    """A regex that silently matched nothing would make every other test in
    this file vacuously pass."""
    names = allowlist()
    assert len(names) > 5
    assert "onStatus" in names


def test_api_pushes_are_all_parseable():
    """Same guard from the Python side."""
    names = pushed_names()
    assert len(names) > 5
    assert "onStatus" in names


@pytest.mark.parametrize("name", pushed_names())
def test_every_pushed_name_is_in_the_allowlist(name):
    """A push whose name is not in WM.HANDLERS can never be received, and
    any page that tries to register it throws and takes the rest of its
    module down with it."""
    assert name in allowlist(), (
        f"ui/api.py pushes {name!r}, which is absent from WM.HANDLERS in "
        "web/app.js. WM.handle() throws on an unknown name, so the route "
        "registering it would fail to load entirely.")


@pytest.mark.parametrize("name", sorted(registered_names()))
def test_every_registered_handler_is_in_the_allowlist(name):
    """The failure mode that broke the EVE Settings route: a page calling
    WM.handle() for a name app.js does not know."""
    where = ", ".join(registered_names()[name])
    assert name in allowlist(), (
        f"{where} registers {name!r} via WM.handle(), which is absent from "
        "WM.HANDLERS in web/app.js. That throws at registration and every "
        "handler declared below it in the same file is never registered.")


def test_the_eve_settings_route_registers_all_three_of_its_pushes():
    """Named explicitly rather than left to the sweep above, because this
    is the route the sweep was written for and a regression here is
    invisible to every other test."""
    registered = registered_names()
    for name in ("onEveSettingsNames", "onEveSettingsRunning",
                 "onEveSettingsDone"):
        assert name in allowlist(), name
        assert "evesettings.js" in registered.get(name, []), name
