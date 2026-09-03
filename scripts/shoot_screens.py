"""Launch Wingman from a source checkout and screenshot every screen.

Developer tooling for UX review, not part of the shipped app. It runs under
a WINDOWS interpreter (invoked from WSL): WSL2 cannot reliably reach a
Windows-bound 127.0.0.1 port, and running the driver as a Windows process
sidesteps that instead of betting on mirrored networking.

The split here is deliberate and matches bookmarks.py/hotkeys.py: every
decision is a pure function that the Linux test suite covers, and the
Windows shell below them holds none.
"""

import argparse
import base64
import datetime as _dt
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request
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
#
# formations is excluded the same way and for a stronger reason. It is a
# sub-screen of Profiles reached from that screen's tool row, and it draws
# nothing until WM.openFormations has loaded a real account file:
# this tool reaches a screen only through WM.route (see shoot()), and
# Screen carries no setup hook, so a capture would photograph an empty
# editor and put it in the set as if that were the screen. Give Screen a
# setup hook before adding it.
#
EXCLUDED_ROUTES = frozenset({"firstrun", "formations"})

# `gated` mirrors app.js's WM.EVE_ROUTES + WM.EVE_SECTIONS. Not retyped
# from memory: test_shoot_screens.py asserts this column against app.js.
SCREENS = (
    Screen("uploader", "Uploader", "main", None, False),
    Screen(
        "settings-uploading", "Settings - Uploading", "settings", "uploading", False
    ),
    Screen("settings-bookmarks", "Settings - Bookmarks", "settings", "bookmarks", True),
    Screen("settings-previews", "Settings - Previews", "settings", "previews", True),
    Screen(
        "settings-previews-middle",
        "Settings - Previews (middle)",
        "settings",
        "previews",
        True,
    ),
    Screen(
        "settings-previews-table",
        "Settings - Previews (table)",
        "settings",
        "previews",
        True,
    ),
    Screen(
        "settings-previews-detail",
        "Settings - Previews (detail)",
        "settings",
        "previews",
        True,
    ),
    Screen(
        "settings-previews-copy",
        "Settings - Previews (copy picker)",
        "settings",
        "previews",
        True,
    ),
    Screen(
        "settings-previews-groups",
        "Settings - Previews (groups)",
        "settings",
        "previews",
        True,
    ),
    Screen(
        "settings-previews-narrow",
        "Settings - Previews (narrow 840x625)",
        "settings",
        "previews",
        True,
    ),
    Screen("settings-alerts", "Settings - Alerts", "settings", "alerts", True),
    Screen("settings-general", "Settings - General", "settings", "general", False),
    Screen("profiles", "Profiles", "evesettings", None, True),
    Screen(
        "profiles-account-identity",
        "Profiles - Identify accounts",
        "accountidentity",
        None,
        True,
    ),
    Screen("profiles-backups", "Profiles - Backups", "backups", None, True),
    Screen("skills", "Skills", "skills", None, True),
    Screen("fittings", "Fittings", "fittings", None, True),
    Screen("dialog", "Dialog", "main", None, False),
)

# The dialog screen stages a confirm by hand -- an empty recording folder
# has nothing to delete, so the real path cannot be driven -- and what it
# staged did not resemble what the app raises.
#
# Api._delete_worker composes the real body as a heading, one bulleted
# filename per line, and the cost; it passes destructive=True, so panel.js
# renders Confirm as .btn.danger and marks the dialog destructive. The
# harness passed neither the flag nor that shape, so every set ever shot
# showed a one-line body under a brand-purple Confirm -- the exact colour
# inversion the comment at panel.js:370 records as ALREADY FIXED, staged
# by the tool that is supposed to prove it is fixed. Two reviewers filed
# it as a live regression before the cause was found.
#
# Two names, not one: the list is what gives the body its shape, and a
# single line hides that the dialog enumerates what it is about to
# destroy. Keep this in step with _delete_worker if that copy changes.
DIALOG_TITLE = "Confirm Delete"
DIALOG_NAMES = ("2026-08-27 21-14-03.mkv", "2026-08-27 21-31-58.mkv")
DIALOG_BODY = (
    "Permanently delete these files from disk?\n\n"
    + "\n".join(f"  • {name}" for name in DIALOG_NAMES)
    + "\n\nThis cannot be undone."
)


def dialog_payload() -> dict:
    """Mirror the bridge payload raised by Api._delete_worker."""
    count = len(DIALOG_NAMES)
    return {
        "kind": "confirm",
        "title": DIALOG_TITLE,
        "body": DIALOG_BODY,
        "request_id": None,
        "destructive": True,
        "confirm_label": f"Delete {count} {'file' if count == 1 else 'files'}",
    }


def load_dev_preview_fixture(checkout: str | None = None) -> dict:
    """Parse DEV_PREVIEW_HOTKEYS_FIXTURE from wingman/web/dev.js.

    The fixture is a strict JSON-compatible object literal (double-quoted
    keys and strings, no JS-specific syntax inside the literal body), so
    json.loads works directly on the extracted block.

    checkout defaults to the directory containing this script's parent.
    Raises ValueError with a clear message if the marker is absent or
    the braces are unbalanced.
    """
    if checkout is None:
        checkout = str(pathlib.Path(__file__).resolve().parent.parent)
    dev_js_path = pathlib.Path(checkout) / "wingman" / "web" / "dev.js"
    source = dev_js_path.read_text(encoding="utf-8")

    marker = "DEV_PREVIEW_HOTKEYS_FIXTURE"
    if marker not in source:
        raise ValueError(
            f"{marker} not found in {dev_js_path} -- "
            "the fixture declaration may have been renamed or removed"
        )

    raw = source[source.index(marker) :]
    # Locate the opening brace of the object literal
    try:
        brace_start = raw.index("{")
    except ValueError:
        raise ValueError(f"{marker} found in {dev_js_path} but has no opening brace")

    # Walk the source character by character to find the matching closing brace.
    # Bounded by the length of the source -- never infinite.
    depth = 0
    end = brace_start
    found = False
    for i, ch in enumerate(raw[brace_start:], brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                found = True
                break
    if not found:
        raise ValueError(
            f"{marker} object literal in {dev_js_path} has unbalanced braces"
        )

    body = raw[brace_start : end + 1]
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{marker} body in {dev_js_path} is not valid JSON: {exc}"
        ) from exc


def _fixture_preview_setup(body: str) -> str:
    """Run a Preview capture against the one extracted, read-only fixture."""
    payload_js = json.dumps(load_dev_preview_fixture())
    return (
        "(function () {\n"
        "  var payload = " + payload_js + ";\n"
        "  if (typeof window.onPreviewHotkeys !== 'function') {\n"
        "    throw new Error('onPreviewHotkeys is missing');\n"
        "  }\n"
        "  window.onPreviewHotkeys(payload);\n" + body + "\n}())"
    )


def screen_setup_script(screen: Screen) -> str | None:
    """Post-navigation staging for screenshots within a long screen."""
    if screen.key == "settings-previews":
        return _fixture_preview_setup(
            "  var pane = document.querySelector('.settings-pane');\n"
            "  if (!pane) { throw new Error('Settings pane is missing'); }\n"
            "  pane.scrollTop = 0;"
        )
    if screen.key == "settings-previews-middle":
        return _fixture_preview_setup(
            "  var pane = document.querySelector('.settings-pane');\n"
            "  if (!pane) { throw new Error('Settings pane is missing'); }\n"
            "  pane.scrollTop = (pane.scrollHeight - pane.clientHeight) / 2;"
        )
    if screen.key == "settings-previews-table":
        return _fixture_preview_setup(
            "  var pane = document.querySelector('.settings-pane');\n"
            "  if (!pane) { throw new Error('Settings pane is missing'); }\n"
            "  pane.scrollTop = pane.scrollHeight;"
        )
    if screen.key in {"settings-previews-detail", "settings-previews-copy"}:
        # Inject only the authoritative fixture, then drive the same Configure
        # and Copy controls a user reaches. Every required step fails closed:
        # a live-state or half-staged capture is misleading evidence.
        fixture = load_dev_preview_fixture()
        payload_js = json.dumps(fixture)
        long_name = "Aleksandrina Shadowbanes Voidstriders"
        copy_click = ""
        if screen.key == "settings-previews-copy":
            copy_click = (
                "  var copy = document.querySelector(\n"
                "    '[data-preview-detail-control=\"copy\"]');\n"
                "  if (!copy) { throw new Error('Copy control is missing'); }\n"
                "  copy.click();\n"
                "  var overlay = WM.el('overlay');\n"
                "  var dialog = WM.el('dialog');\n"
                "  if (!overlay || overlay.hidden || !dialog\n"
                "      || !dialog.classList.contains('choice')) {\n"
                "    throw new Error('Copy chooser did not open');\n"
                "  }\n"
            )
        return (
            "(function () {\n"
            "  var payload = " + payload_js + ";\n"
            "  if (typeof window.onPreviewHotkeys !== 'function') {\n"
            "    throw new Error('onPreviewHotkeys is missing');\n"
            "  }\n"
            "  window.onPreviewHotkeys(payload);\n"
            "  var expanded = document.querySelectorAll(\n"
            "    '[data-preview-configure][aria-expanded=\"true\"]');\n"
            "  Array.prototype.forEach.call(expanded, function (button) {\n"
            "    button.click();\n"
            "  });\n"
            "  var configure = document.querySelector(\n"
            "    '[data-preview-configure=\"" + long_name + "\"]');\n"
            "  if (!configure) { throw new Error('Configure control is missing'); }\n"
            "  var detailId = configure.getAttribute('aria-controls');\n"
            "  configure.click();\n"
            "  var detail = document.getElementById(detailId);\n"
            "  if (!detail) { throw new Error('Configure detail is missing'); }\n"
            "  detail.scrollIntoView({block: 'center', behavior: 'instant'});\n"
            + copy_click
            + "}())"
        )
    if screen.key == "settings-previews-groups":
        # Load the authoritative fixture through the read-side handler, then
        # frame the real manager. Do not fall back to a live page or its bottom.
        fixture = load_dev_preview_fixture()
        payload_js = json.dumps(fixture)
        return (
            "(function () {\n"
            "  var payload = " + payload_js + ";\n"
            "  if (typeof window.onPreviewHotkeys !== 'function') {\n"
            "    throw new Error('onPreviewHotkeys is missing');\n"
            "  }\n"
            "  window.onPreviewHotkeys(payload);\n"
            "  var expanded = document.querySelectorAll(\n"
            "    '[data-preview-configure][aria-expanded=\"true\"]');\n"
            "  Array.prototype.forEach.call(expanded, function (configure) {\n"
            "    configure.click();\n"
            "  });\n"
            "  if (document.querySelector(\n"
            "      '[data-preview-configure][aria-expanded=\"true\"]')) {\n"
            "    throw new Error('No preview detail was closed');\n"
            "  }\n"
            "  var mgr = document.querySelector('.preview-group-manager');\n"
            "  if (!mgr) { throw new Error('Preview group manager is missing'); }\n"
            "  mgr.scrollIntoView({block: 'start', behavior: 'instant'});\n"
            "}())"
        )
    if screen.key == "settings-previews-narrow":
        # CDP pins 840x625 before this fixture-backed setup. Close inherited
        # details, then frame the generated roster heading; every missing
        # prerequisite fails the shot instead of photographing live state.
        fixture = load_dev_preview_fixture()
        payload_js = json.dumps(fixture)
        return (
            "(function () {\n"
            "  var payload = " + payload_js + ";\n"
            "  if (typeof window.onPreviewHotkeys !== 'function') {\n"
            "    throw new Error('onPreviewHotkeys is missing');\n"
            "  }\n"
            "  window.onPreviewHotkeys(payload);\n"
            "  var expanded = document.querySelectorAll(\n"
            "    '[data-preview-configure][aria-expanded=\"true\"]');\n"
            "  Array.prototype.forEach.call(expanded, function (configure) {\n"
            "    configure.click();\n"
            "  });\n"
            "  var heading = document.querySelector('#preview-roster-heading');\n"
            "  if (!heading) { throw new Error('Preview roster heading is missing'); }\n"
            "  heading.scrollIntoView({block: 'start', behavior: 'instant'});\n"
            "}())"
        )
    return None


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


def launch_command(python: str, checkout: str, port: int) -> str:
    """Build the cmd.exe invocation that starts the app with a debug port.

    The `set` statements MUST run inside cmd.exe. WSL environment variables
    do not cross into a Windows process at all, so the usual `FOO=x cmd`
    form silently arrives as unset.

    LOCALAPPDATA is deliberately NOT set: this tool shoots live state.
    """
    args = f"--remote-debugging-port={port} --remote-allow-origins=*"
    return (
        "cmd.exe /c "
        f'"set WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS={args}'
        f" && cd /d {checkout}"
        f' && {python} -m wingman"'
    )


def build_manifest(
    *,
    branch: str,
    sha: str,
    dirty: bool,
    python: str,
    viewport: dict,
    eve_shown: bool,
    engine_present: bool,
    shots: list[dict],
    skipped: list[Screen],
) -> dict:
    """Describe the run precisely enough that the set cannot mislead.

    A run that shot four screens because the EVE gate was off is correct; a
    run that shot four and looks truncated is not. The difference is only
    visible if the gate state and the skip list are recorded.

    `engine_present` is the same kind of claim about a screen rather than
    the set: false means Settings > Bookmarks shot its engine-missing
    error, which is a property of this tool (see ensure_engine) and not of
    the app. Required, not defaulted -- a provenance field that can be
    silently omitted is the bug this field exists to prevent.
    """
    return {
        "branch": branch,
        "sha": sha,
        "dirty": dirty,
        "python": python,
        "viewport": viewport,
        "eve_shown": eve_shown,
        "engine_present": engine_present,
        "screens_total": len(SCREENS),
        "shot_count": sum(1 for s in shots if not s.get("error")),
        "failed": [s["key"] for s in shots if s.get("error")],
        "skipped": [s.key for s in skipped],
        "shots": shots,
    }


APP_EXE = "Wingman.exe"

# NOT a `CommandLine -like '*wingman*'` match. The checkout directory is
# named flygd-wingman, so that pattern matches every process whose command
# line contains the repo path -- this script included, and an editor with
# the repo open -- and find_incumbent would treat them as the app. Match on
# process IDENTITY instead: the installed exe by name, or a python
# running `-m wingman` as its module.
_MATCH = (
    f"$_.Name -eq '{APP_EXE}'"
    " -or ($_.Name -like 'python*.exe'"
    " -and $_.CommandLine -match '-m\\s+wingman(\\s|$)')"
)


class BusyError(Exception):
    """The incumbent did not exit within the timeout."""


def _powershell(script: str) -> str:
    out = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip()


def find_incumbent() -> str | None:
    """Return the running app's full command line, or None.

    Read rather than assumed: the incumbent may be the installed exe or a
    source checkout, and restoring the wrong one is worse than not
    restoring at all.
    """
    script = (
        "Get-CimInstance Win32_Process"
        f" | Where-Object {{ {_MATCH} }}"
        " | Select-Object -First 1 -ExpandProperty CommandLine"
    )
    return _powershell(script) or None


def await_incumbent_exit(timeout_s: float = 120.0) -> None:
    """Wait for the user to quit Wingman from its own tray menu.

    There is no programmatic way to end this process, and that is not a gap
    to work around -- it is the app working as designed. WM_CLOSE (which is
    all `taskkill` without /F can deliver) routes to `api.close()`, and
    ui/api.py:450 says verbatim: "HIDE, never destroy... Only the tray's
    Quit destroys." So a taskkill against the user's instance can never make
    it exit; it can only hide their window, an unwanted side effect on the
    way to a guaranteed timeout. `taskkill /F` is not the answer either:
    atomicio does not cover settings.json, seen.json or token.json
    (settings.py:560 and watcher.py:47 are plain write_text; uploader.py:340
    opens with O_TRUNC), so a forced kill can truncate live state.
    __main__.py:145 rules out IPC for the same reason a second instance
    exits quietly instead of raising the first: proper cross-process
    signalling needs a named pipe or WM_COPYDATA, which is disproportionate
    here. Asking and waiting is therefore the only correct move.
    """
    print("Wingman is running, and only its tray menu can quit it.")
    print("Right-click the Wingman tray icon and choose Quit, then this")
    print(f"will continue. Waiting up to {timeout_s:.0f}s...")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if find_incumbent() is None:
            return
        time.sleep(1.0)
    raise BusyError(
        f"Wingman did not exit within {timeout_s:.0f}s. Either it has not "
        "been quit yet, or it was and _confirm_quit_if_busy "
        "(__main__.py:669) refused because an upload is in flight.\n"
        "Nothing was killed and nothing needs restoring. Quit it from the "
        "tray menu -- once any upload finishes if that is what is blocking "
        "it -- then re-run."
    )


def restore_incumbent(command_line: str) -> None:
    """Relaunch exactly what was running before.

    `command_line` is Win32_Process.CommandLine, which comes back already
    quoted -- for the installed build, verbatim
    '"C:\\...\\Programs\\FlyGD Wingman\\Wingman.exe"'. That install path
    contains a space, so tokenizing it with `.split()` (the previous
    implementation) shredded it into two nonexistent paths and cmd launched
    neither -- the user's own Wingman never came back. Hand the string to
    cmd as ONE piece and let it parse quoting the same way it was produced,
    instead of re-tokenizing something that is already a complete, correctly
    quoted command line. This also has to survive the source-build form,
    which legitimately carries trailing arguments, e.g.
    '"C:\\...\\python.exe" -m wingman'.
    """
    # shell=True runs this through cmd.exe /c. The empty "" is start's own
    # title argument and must stay -- without it, start treats a quoted
    # first token as the window title and opens a bare console instead of
    # the app.
    subprocess.Popen(f'start "" {command_line}', shell=True)


class TargetError(Exception):
    """No target could be confirmed as the real app page."""


# Without this the socket blocks forever, and a hang (unlike an exception)
# never reaches main()'s finally -- so restore_incumbent() never runs and
# the user's own Wingman stays closed.
CDP_TIMEOUT_S = 30.0


class CDP:
    """A minimal Chrome DevTools Protocol client over one websocket."""

    def __init__(self, ws):
        self._ws = ws
        self._next_id = 0

    def _call(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        self._ws.send(
            json.dumps({"id": self._next_id, "method": method, "params": params or {}})
        )
        while True:
            message = json.loads(self._ws.recv())
            # CDP interleaves unsolicited events with replies; anything
            # without our id is an event and is not the answer.
            if message.get("id") == self._next_id:
                if "error" in message:
                    raise TargetError(message["error"])
                return message.get("result", {})

    def evaluate(self, expression: str):
        result = self._call(
            "Runtime.evaluate", {"expression": expression, "returnByValue": True}
        )
        if "exceptionDetails" in result:
            raise TargetError(result["exceptionDetails"])
        return result.get("result", {}).get("value")

    def screenshot(self) -> bytes:
        return base64.b64decode(self._call("Page.captureScreenshot")["data"])

    def set_device_metrics_override(self, *, width: int, height: int) -> None:
        """Pin the page viewport to the given logical pixel size.

        deviceScaleFactor=1 keeps CSS pixels equal to physical pixels (no
        DPI scaling artefacts).  mobile=False avoids viewport-meta
        side-effects that could widen the layout beyond the requested width.
        """
        self._call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )

    def clear_device_metrics_override(self) -> None:
        """Restore the real viewport after a pinned-viewport capture."""
        self._call("Emulation.clearDeviceMetricsOverride")

    def close(self) -> None:
        self._ws.close()


def attach(port: int, timeout_s: float = 30.0) -> CDP:
    """Connect to the real app page, proven by capability rather than URL.

    suppress_origin is required, not optional: WebView2 and Chromium reject
    the websocket with 403 Forbidden when an Origin header is present, and
    --remote-allow-origins=* alone does not fix it.
    """
    import websocket

    deadline = time.monotonic() + timeout_s
    seen: list[str] = []
    while time.monotonic() < deadline:
        try:
            raw = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/list", timeout=2
            ).read()
        except OSError:
            # The app has not opened the debug port yet, which is the normal
            # state for the first second or two of startup. Retrying IS the
            # handling. Note there is deliberately no S112 suppression here:
            # that rule fires only on a bare try-except-continue, and this
            # handler sleeps first, so a suppression would itself be flagged
            # by RUF100. Do not write the directive token out in this comment
            # either -- ruff parses it wherever it appears and reports an
            # invalid-directive warning, which is only visible under
            # `ruff check --no-cache` and so survived three reviews.
            time.sleep(0.5)
            continue
        targets = json.loads(raw)
        seen = [t.get("url", "") for t in targets]
        for target in page_candidates(targets):
            cdp = None
            try:
                ws = websocket.create_connection(
                    target["webSocketDebuggerUrl"],
                    suppress_origin=True,
                    timeout=CDP_TIMEOUT_S,
                )
                cdp = CDP(ws)
                # The decisive check. dev.js activates ONLY when
                # window.pywebview is absent, so a page that HAS it cannot
                # be the fabricating harness. This is proof, where the URL
                # filter was only a cheap pre-filter.
                is_real = cdp.evaluate("typeof window.pywebview !== 'undefined'")
            except Exception:  # noqa: BLE001 -- a candidate that cannot be
                # interrogated (connect refused, target vanished between
                # /json/list and connect, a mid-handshake CDP error) is
                # simply not our page; close what was opened and let the
                # next candidate have its own try.
                if cdp is not None:
                    cdp.close()
                continue
            if is_real is True:
                return cdp
            cdp.close()
        time.sleep(0.5)
    raise TargetError(
        f"No real app page found on port {port} within {timeout_s:.0f}s.\n"
        f"Targets seen: {seen}"
    )


def walk(
    cdp: CDP, out_dir: pathlib.Path, settle_ms: int = 2500
) -> tuple[list[dict], list["Screen"], bool]:
    """Visit each reachable screen and capture it.

    The settle wait is load-bearing. The page populates asynchronously, and
    reading too early once produced an -886px "delta" that was really a
    populated page compared against a half-built one.
    """
    eve_shown = cdp.evaluate("WM.eve_shown !== false") is True
    to_shoot, skipped = screens_for_gate(eve_shown)
    out_dir.mkdir(parents=True, exist_ok=True)

    shots = []
    for index, screen in enumerate(to_shoot, start=1):
        name = f"{index:02d}-{screen.key}.png"
        try:
            if screen.key == "dialog":
                cdp.evaluate("WM.route('main')")
                # Drive the same handler and payload shape used by Python.
                # WM.confirm is a separate page-owned path and silently lost
                # production-only fields such as the specific action label.
                cdp.evaluate("window.onDialog(" + json.dumps(dialog_payload()) + ")")
            else:
                cdp.evaluate(f"WM.route({screen.route!r})")
                if screen.section:
                    cdp.evaluate(f"WM.section({screen.section!r})")
            time.sleep(settle_ms / 1000)
            if screen.key == "settings-previews-narrow":
                # CDP viewport override MUST be applied before the setup
                # script runs (finding 1, round 2): the setup script injects
                # the fixture via onPreviewHotkeys and scrolls to the roster
                # heading -- both must execute at 840x625 so the layout
                # is already constrained before the scroll position is chosen.
                # window.resizeTo is a no-op in WebView2; CDP emulation is
                # the only mechanism that works.
                # The clear is in a finally so the real viewport is restored
                # even when setup or capture fails, preventing distorted
                # captures of all later screens.
                cdp.set_device_metrics_override(width=840, height=625)
                try:
                    setup = screen_setup_script(screen)
                    if setup:
                        cdp.evaluate(setup)
                        time.sleep(0.25)
                    (out_dir / name).write_bytes(cdp.screenshot())
                finally:
                    cdp.clear_device_metrics_override()
            else:
                setup = screen_setup_script(screen)
                if setup:
                    cdp.evaluate(setup)
                    time.sleep(0.25)
                (out_dir / name).write_bytes(cdp.screenshot())
            if screen.key in {"dialog", "settings-previews-copy"}:
                # Dismiss every staged overlay before the next screen. Cancel
                # is side-effect free for both the Python-shaped confirm and
                # the page-owned choice promise, neither of which has a
                # consumer in this tool.
                cdp.evaluate("WM.el('dlg-cancel').click()")
        except Exception as exc:  # noqa: BLE001 -- one dead screen must not
            # abandon the other eight; the failure is recorded instead.
            shots.append({"key": screen.key, "file": None, "error": str(exc)})
        else:
            shots.append({"key": screen.key, "file": name, "error": None})
    return shots, skipped, eve_shown


def _git(checkout: str, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", checkout, *args], capture_output=True, text=True, check=False
    )
    return out.stdout.strip()


def _probe_interpreter(path: str) -> bool:
    out = subprocess.run(
        [path, "-c", "import webview, pystray"], capture_output=True, check=False
    )
    return out.returncode == 0


def ensure_engine(checkout: str, python: str) -> bool:
    """Fetch the AutoHotkey engine into the checkout. Returns whether it is
    there afterwards.

    Without this the Bookmarks shot is not merely incomplete, it is WRONG.
    AutoHotkeyU64.exe is downloaded at build time by
    packaging/fetch_autohotkey.py and never committed, so a source checkout
    -- which is exactly what this tool launches -- always reports "The
    bookmark engine is missing from this installation. Reinstall FlyGD
    Wingman to restore it.", and the status strip always reads
    SIG - ROOT - NEXT with no values (bookmarks.js gates them on
    state === 'running', deliberately: a stale root gets acted on).

    So every set ever shot showed a primary feature reporting itself
    broken, in a way indistinguishable from a real regression, and the
    screen behind the error -- the actual bind list -- has never been
    reviewed by anyone.

    paths.engine_exe() already falls back to packaging/bin in a non-frozen
    run, which is where the fetcher writes, so this needs no cooperation
    from the app. The fetcher is idempotent and self-skips when the pinned
    sha256 already matches.

    Non-fatal on purpose, and called BEFORE the incumbent is asked to quit
    for the same reason the interpreter is resolved there: a network
    failure must not leave the user with no app and no screenshots.
    Offline, the old behaviour is still eight good screens, and the
    manifest records which kind of set this was.
    """
    exe = pathlib.Path(checkout) / "packaging" / "bin" / "AutoHotkeyU64.exe"
    if exe.exists():
        return True
    script = pathlib.Path(checkout) / "packaging" / "fetch_autohotkey.py"
    if not script.exists():
        print(f"No {script}; Bookmarks will shoot its engine-missing state.")
        return False
    print("Fetching the AutoHotkey engine so Bookmarks shoots its real state...")
    out = subprocess.run(
        [python, str(script)], capture_output=True, text=True, check=False
    )
    if out.returncode != 0 or not exe.exists():
        detail = (out.stderr or out.stdout).strip().splitlines()
        print(
            "Could not fetch the engine, so Settings > Bookmarks will show "
            '"the bookmark engine is missing" -- that error is this tool, '
            "not the app."
        )
        if detail:
            print(f"  {detail[-1]}")
        return False
    return True


def _search_interpreters() -> list[str]:
    """Look where Python actually installs, not where PATH claims.

    where.exe surfaces only the Microsoft Store stub, which prints "Python
    was not found" -- concluding from it that there is no Windows Python is
    a mistake that has already cost this project a verification pass.
    """
    roots = [
        pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
        pathlib.Path("C:/"),
    ]
    found = []
    for root in roots:
        if not root.exists():
            continue
        for child in sorted(root.glob("Python3*")):
            candidate = child / "python.exe"
            if candidate.exists():
                found.append(str(candidate))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", default=str(pathlib.Path.cwd()))
    parser.add_argument("--python", default=None)
    parser.add_argument("--port", type=int, default=9700)
    parser.add_argument("--settle-ms", type=int, default=2500)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    # Resolve the interpreter BEFORE closing anything: a failure here after
    # the incumbent is down leaves the user with no app and no screenshots.
    python = resolve_interpreter(
        args.python,
        os.environ.get("WINGMAN_PY"),
        search=_search_interpreters,
        probe=_probe_interpreter,
    )

    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    default_out = pathlib.Path(args.checkout) / "tmp" / "screens" / stamp
    out_dir = pathlib.Path(args.out) if args.out else default_out

    # Before the incumbent goes down, for the reason stated above it.
    engine_present = ensure_engine(args.checkout, python)

    incumbent = find_incumbent()
    if incumbent:
        print(f"Found running: {incumbent}")
        try:
            await_incumbent_exit()
        except BusyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    else:
        print(
            "No running Wingman found, so nothing will be relaunched when "
            "this run finishes -- start it yourself afterward if you want it."
        )

    app = None
    try:
        app = subprocess.Popen(
            launch_command(python, args.checkout, args.port), shell=True
        )
        cdp = attach(args.port)
        viewport = {
            "width": cdp.evaluate("window.innerWidth"),
            "height": cdp.evaluate("window.innerHeight"),
        }
        shots, skipped, eve_shown = walk(cdp, out_dir, args.settle_ms)
        cdp.close()

        manifest = build_manifest(
            branch=_git(args.checkout, "branch", "--show-current"),
            sha=_git(args.checkout, "rev-parse", "--short", "HEAD"),
            dirty=bool(_git(args.checkout, "status", "--short")),
            python=python,
            viewport=viewport,
            eve_shown=eve_shown,
            engine_present=engine_present,
            shots=shots,
            skipped=skipped,
        )
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    finally:
        # Asymmetric on purpose: we ASK for the user's instance above
        # (nothing else can end it -- see await_incumbent_exit) and FORCE
        # our own here. That is not a double standard; it is the same
        # rule applied to different owners. This tool launched `app`
        # itself, so nothing of the user's is at stake in killing it, and
        # unlike the user's window it never held anything worth asking
        # about. `app` is the cmd.exe wrapper Popen(shell=True) gave us;
        # terminating it also ends the python child cmd.exe spawned.
        #
        # Exceptions here are swallowed on purpose. Raised out of a
        # finally they would skip the restore below, so a launched
        # instance that refuses to die would cost the user their own
        # Wingman too. Restoring theirs outranks a clean shutdown of ours.
        if app is not None:
            try:
                app.terminate()
                try:
                    app.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    app.kill()
                    app.wait(timeout=5)
            except Exception as exc:  # noqa: BLE001 -- see comment above:
                # any failure here must not prevent the restore below.
                print(
                    "warning: could not terminate the instance this run "
                    f"launched: {exc}. It may still hold the mutex, so the "
                    "restore below may fail. Close it by hand.",
                    file=sys.stderr,
                )
        if incumbent:
            print(f"Restoring: {incumbent}")
            restore_incumbent(incumbent)

    print(f"{manifest['shot_count']}/{manifest['screens_total']} screens -> {out_dir}")
    if manifest["skipped"]:
        print(f"EVE gate off, skipped: {', '.join(manifest['skipped'])}")
    if manifest["failed"]:
        print(f"FAILED: {', '.join(manifest['failed'])}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
