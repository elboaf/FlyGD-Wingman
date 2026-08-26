"""Launch Wingman from a source checkout and screenshot every screen.

Developer tooling for UX review, not part of the shipped app. It runs under
a WINDOWS interpreter (invoked from WSL): WSL2 cannot reliably reach a
Windows-bound 127.0.0.1 port, and running the driver as a Windows process
sidesteps that instead of betting on mirrored networking.

The split here is deliberate and matches bookmarks.py/hotkeys.py: every
decision is a pure function that the Linux test suite covers, and the
Windows shell below them holds none.
"""

from collections.abc import Callable
from typing import NamedTuple
from urllib.parse import urlparse


class Screen(NamedTuple):
    key: str
    label: str
    route: str
    section: str | None
    gated: bool


# firstrun is a real route (app.js) that this tool deliberately never
# shoots. It is named here rather than silently absent so the test can
# assert it still EXISTS -- an exclusion nobody checks rots the day the
# route is renamed.
EXCLUDED_ROUTES = frozenset({"firstrun"})

# `gated` mirrors app.js's WM.EVE_ROUTES + WM.EVE_SECTIONS. Not retyped
# from memory: test_shoot_screens.py asserts this column against app.js.
SCREENS = (
    Screen("uploader", "Uploader", "main", None, False),
    Screen(
        "settings-uploading", "Settings - Uploading", "settings", "uploading", False
    ),
    Screen("settings-bookmarks", "Settings - Bookmarks", "settings", "bookmarks", True),
    Screen("settings-previews", "Settings - Previews", "settings", "previews", True),
    Screen("settings-alerts", "Settings - Alerts", "settings", "alerts", True),
    Screen("settings-general", "Settings - General", "settings", "general", False),
    Screen("profiles", "Profiles", "evesettings", None, True),
    Screen("skills", "Skills", "skills", None, True),
    Screen("dialog", "Dialog", "main", None, False),
)


def screens_for_gate(eve_shown: bool) -> tuple[list[Screen], list[Screen]]:
    """Split SCREENS into what to shoot and what the EVE gate hides.

    WM.route and WM.section do NOT enforce visibility -- they will render a
    gated screen perfectly happily -- so the gate has to be honoured here or
    the set silently includes screens the user cannot reach.
    """
    if eve_shown:
        return list(SCREENS), []
    to_shoot = [s for s in SCREENS if not s.gated]
    skipped = [s for s in SCREENS if s.gated]
    return to_shoot, skipped


def page_candidates(targets: list[dict]) -> list[dict]:
    """Narrow a /json/list payload to plausible Wingman page targets.

    Deliberately NOT a URL-port match: pywebview serves index.html from its
    own random port (ui/window.py:202-205), unrelated to the debug port, so
    matching the debug port rejects every real target.

    Any query string disqualifies a target, which is what excludes the
    ?dev=1 harness. That is a cheap pre-filter, not the proof -- the caller
    still confirms window.pywebview exists on whichever candidate it picks.
    """
    keep = []
    for target in targets:
        if target.get("type") != "page":
            continue
        parsed = urlparse(target.get("url", ""))
        if parsed.query:
            continue
        if not parsed.path.endswith("/index.html"):
            continue
        keep.append(target)
    return keep


class InterpreterError(Exception):
    """No Windows interpreter that can actually run the app was found."""


def resolve_interpreter(
    explicit: str | None,
    env: str | None,
    search: Callable[[], list[str]],
    probe: Callable[[str], bool],
) -> str:
    """Pick the Windows interpreter that will launch the app.

    Verified by IMPORT, never by path. `where.exe python` surfaces only the
    Microsoft Store stub, and concluding "no Windows Python" from it is
    wrong -- that mistake once cost a lane its real-window verification.
    A path that exists proves nothing; one that imports webview does.

    Ordered explicit > env > search so a machine that has moved its Python
    can be fixed without editing the script.
    """
    tried = []
    for candidate in [explicit, env, *search()]:
        if not candidate:
            continue
        tried.append(candidate)
        if probe(candidate):
            return candidate
    raise InterpreterError(
        "No Windows interpreter able to import webview and pystray was found.\n"
        f"Tried: {tried or 'nothing -- no candidates at all'}\n"
        "Pass one with --python, or set WINGMAN_PY."
    )
