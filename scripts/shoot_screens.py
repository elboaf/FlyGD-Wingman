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
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Screen:
    key: str
    label: str
    route: str
    section: str | None = None
    gated: bool = False
    at_floor: bool = False


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
    Screen("uploader", "Uploader", "main"),
    Screen("settings-uploading", "Settings - Uploading", "settings", "uploading"),
    Screen(
        "settings-characters", "Settings - Characters", "settings", "characters", True
    ),
    Screen(
        "settings-characters-waiting",
        "Settings - Characters (waiting)",
        "settings",
        "characters",
        True,
    ),
    Screen(
        "settings-characters-narrow",
        "Settings - Characters (narrow 840x625)",
        "settings",
        "characters",
        True,
        True,
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
        "settings-previews-sticky-conflict",
        "Settings - Previews (conflict at sticky edge)",
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
        True,
    ),
    Screen("settings-alerts", "Settings - Alerts", "settings", "alerts", True),
    Screen(
        "settings-alerts-advanced",
        "Settings - Alerts (advanced pulse behavior)",
        "settings",
        "alerts",
        True,
    ),
    Screen("settings-general", "Settings - General", "settings", "general"),
    Screen("profiles", "Profiles", "evesettings", gated=True),
    Screen(
        "profiles-account-identity",
        "Profiles - Identify accounts",
        "accountidentity",
        gated=True,
    ),
    Screen("profiles-backups", "Profiles - Backups", "backups", gated=True),
    Screen("skills", "Skills", "skills", gated=True),
    Screen("fittings", "Fittings", "fittings", gated=True),
    Screen("fittings-unfiled", "Fittings - Unfiled", "fittings", gated=True),
    Screen("fittings-superseded", "Fittings - Superseded", "fittings", gated=True),
    Screen(
        "fittings-alliance",
        "Fittings - Recent alliance import",
        "fittings",
        gated=True,
    ),
    Screen("fittings-detail", "Fittings - Detail", "fittings", gated=True),
    Screen(
        "fittings-narrow",
        "Fittings - Narrow (840x625)",
        "fittings",
        gated=True,
        at_floor=True,
    ),
    Screen(
        "fittings-copy-preflight", "Fittings - Copy preflight", "fittings", gated=True
    ),
    Screen(
        "fittings-copy-limit",
        "Fittings - Copy over the 20-write limit",
        "fittings",
        gated=True,
    ),
    Screen(
        "fittings-copy-progress", "Fittings - Copy progress", "fittings", gated=True
    ),
    Screen("fittings-copy-result", "Fittings - Copy results", "fittings", gated=True),
    Screen("dialog", "Dialog", "main"),
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


def load_dev_characters_scenarios(checkout: str | None = None) -> dict:
    """Load the strict JSON-backed characters scenario table from web/dev.js."""
    if checkout is None:
        checkout = str(pathlib.Path(__file__).resolve().parent.parent)
    path = pathlib.Path(checkout) / "wingman" / "web" / "dev.js"
    source = path.read_text(encoding="utf-8")
    marker = "DEV_CHARACTERS_SCENARIOS"
    if marker not in source:
        raise ValueError(f"{marker} not found in {path}")
    raw = source[source.index(marker) :]
    try:
        start = raw.index("{")
    except ValueError:
        raise ValueError(f"{marker} found in {path} but has no opening brace")
    depth = 0
    end = start
    for index, character in enumerate(raw[start:], start):
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    else:
        raise ValueError(f"{marker} object literal in {path} has unbalanced braces")
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"{marker} body in {path} is not valid JSON: {exc}") from exc


def _fixture_characters_setup(name: str, body: str = "") -> str:
    """Run a Characters capture against one extracted, read-only scenario."""
    scenarios = load_dev_characters_scenarios()
    if name not in scenarios:
        raise ValueError(f"unknown characters screenshot scenario: {name!r}")
    payload_js = json.dumps(scenarios[name])
    return (
        "(function () {\n"
        "  var payload = " + payload_js + ";\n"
        "  if (typeof window.onEveAuthorityScreenshotState !== 'function') {\n"
        "    throw new Error('onEveAuthorityScreenshotState is missing');\n"
        "  }\n"
        "  window.onEveAuthorityScreenshotState(payload);\n"
        "  var roster = document.getElementById('characters-roster');\n"
        "  if (!roster) { throw new Error('Characters roster is missing'); }\n"
        "  var rendered = roster.querySelectorAll('.characters-row');\n"
        "  if (payload.available && payload.characters.length"
        "      && rendered.length !== payload.characters.length) {\n"
        "    throw new Error('Characters screenshot fixture was not accepted');\n"
        "  }\n" + body + "\n}())"
    )


# Every fittings-* stage below shares this route: WM.route('fittings') fires
# unconditionally on every visit (app.js:192), but fittings.js's own
# wm:route listener only tears down selection/overlays/filters when the
# event's detail is NOT 'fittings' -- i.e. only when actually LEAVING the
# route. Since every fittings-* screen stays on this same route, nothing
# resets state between them for free the way it would between two
# different destinations, so each stage's setup script opens with this
# snippet to put the route back into a known, previous-stage-independent
# state before doing anything of its own: no row expanded, neither overlay
# open, and the collection scope back on "All fittings" (which also clears
# whatever this or a prior stage had selected -- selectCollection() in
# fittings.js calls clearSelection() as part of switching collections).
_FIT_RESET_JS = (
    "  var openToggle = document.querySelector(\n"
    "    '.fit-row-toggle[aria-expanded=\"true\"]');\n"
    "  if (openToggle) { openToggle.click(); }\n"
    "  var copyOverlay = document.getElementById('fittings-copy-overlay');\n"
    "  var copyClose = document.getElementById('fittings-copy-close');\n"
    "  if (copyOverlay && !copyOverlay.hidden && copyClose && !copyClose.disabled) {\n"
    "    copyClose.click();\n"
    "  }\n"
    "  var allButton = null;\n"
    "  Array.prototype.forEach.call(\n"
    "    document.querySelectorAll('#fittings-collections .rail-plan'),\n"
    "    function (btn) {\n"
    "      var name = btn.querySelector('.rail-plan-name');\n"
    "      if (name && name.textContent === 'All fittings') { allButton = btn; }\n"
    "    }\n"
    "  );\n"
    "  if (allButton && !allButton.classList.contains('active')) { allButton.click(); }\n"
    # selectCollection() early-returns (and never resets filters.page) when
    # the requested collection is already the active one, so a prior
    # stage's page-2 navigation survives an "All fittings" click that
    # finds "All fittings" already active. Walk pagination back to page 1
    # directly instead -- bounded, because #fittings-page-prev disables
    # itself once page===1 and an unbounded loop over a bug in that would
    # hang the whole capture run rather than fail one screenshot.
    "  var prevPage = document.getElementById('fittings-page-prev');\n"
    "  for (var pageBack = 0; pageBack < 10 && prevPage && !prevPage.disabled; pageBack += 1) {\n"
    "    prevPage.click();\n"
    "  }\n"
)


# Shared by the two copy stages below: find the .fit-copy-target row for a
# named character in the open Copy overlay and check its box. Declared as a
# JS string once rather than duplicated per stage -- the two-part label
# structure (a visual .box span, then the plain name span) is an
# implementation detail of fittings.js's renderCopyTargets() that only one
# place should have to know.
_FIT_CHECK_TARGET_JS = (
    "  function fitCheckTarget(characterName) {\n"
    "    var found = null;\n"
    "    Array.prototype.forEach.call(\n"
    "      document.querySelectorAll('.fit-copy-target'), function (row) {\n"
    "        var label = row.querySelector('label span:last-child');\n"
    "        if (label && label.textContent === characterName) { found = row; }\n"
    "      }\n"
    "    );\n"
    "    if (!found) {\n"
    "      throw new Error(characterName + ' copy target row is missing');\n"
    "    }\n"
    "    var box = found.querySelector('input[type=checkbox]');\n"
    "    if (!box || box.disabled) {\n"
    "      throw new Error(characterName + ' copy target checkbox is unavailable');\n"
    "    }\n"
    "    box.checked = true;\n"
    "    box.dispatchEvent(new Event('change'));\n"
    "  }\n"
)


def _fit_check_row_js(
    var_name: str, predicate_js: str, label: str, *, action: str = "select"
) -> str:
    """Find one summary row, then explicitly select or open it."""
    if action not in {"select", "open"}:
        raise ValueError(f"unsupported fitting row action: {action!r}")
    act = (
        "    target.click();\n"
        if action == "open"
        else (
            "    var row = target.closest('.fit-row');\n"
            "    var box = row.querySelector('.fit-select input[type=checkbox]');\n"
            f"    if (!box) {{ throw new Error({label!r} + ' checkbox is missing'); }}\n"
            "    box.checked = true;\n"
            "    box.dispatchEvent(new Event('change'));\n"
        )
    )
    return (
        f"  (function checkRow_{var_name}() {{\n"
        "    var toggles = document.querySelectorAll(\n"
        "      '#fittings-list .fit-row-toggle');\n"
        "    var target = null;\n"
        "    Array.prototype.forEach.call(toggles, function (btn) {\n"
        "      if (target) { return; }\n"
        f"      if ({predicate_js}) {{ target = btn; }}\n"
        "    });\n"
        f"    if (!target) {{ throw new Error({label!r} + ' row is missing'); }}\n"
        + act
        + "  }());\n"  # Semicolon: two adjacent IIFEs with none between them
        # (as happens when two of these are concatenated back to back) let
        # ASI read the second '(function...' as a call on the first's
        # return value instead of a new statement.
    )


def load_dev_fittings_screenshot_fixture(checkout: str | None = None) -> dict:
    """Load the strict JSON screenshot fixture owned by web/dev.js."""
    if checkout is None:
        checkout = str(pathlib.Path(__file__).resolve().parent.parent)
    path = pathlib.Path(checkout) / "wingman" / "web" / "dev.js"
    source = path.read_text(encoding="utf-8")
    marker = "DEV_FITTINGS_SCREENSHOT_FIXTURE"
    if marker not in source:
        raise ValueError(f"{marker} not found in {path}")
    raw = source[source.index(marker) :]
    try:
        start = raw.index("{")
    except ValueError:
        raise ValueError(f"{marker} found in {path} but has no opening brace")
    depth = 0
    end = start
    for index, character in enumerate(raw[start:], start):
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    else:
        raise ValueError(f"{marker} object literal in {path} has unbalanced braces")
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"{marker} body in {path} is not valid JSON: {exc}") from exc


def fittings_fixture_setup_script() -> str:
    """Inject the bounded dev.js fixture through the screenshot-only handler."""
    payload = json.dumps(load_dev_fittings_screenshot_fixture())
    return (
        "(function () {\n"
        "  var payload = " + payload + ";\n"
        "  if (typeof window.onFittingsScreenshotState !== 'function') {\n"
        "    throw new Error('onFittingsScreenshotState is missing');\n"
        "  }\n"
        "  window.onFittingsScreenshotState(payload);\n"
        "  var rendered = document.querySelectorAll('#fittings-list .fit-row');\n"
        "  var heading = document.getElementById('fittings-collection-name');\n"
        "  if (!heading || heading.textContent !== 'All fittings'\n"
        "      || rendered.length !== payload.entries.length) {\n"
        "    throw new Error('Fittings screenshot fixture was not accepted');\n"
        "  }\n"
        "}())"
    )


def _fittings_setup_script(key: str) -> str:
    """Deterministic staging for every fittings-* screenshot stage.

    Every stage is read-only against the harness's fabricated fixture and
    drives only controls a user could actually press -- selection
    checkboxes, the rail, Copy selected, target checkboxes, Review -- with
    one deliberate exception: the progress/result stages inject the canonical
    dev fixture's production-reachable copy sequence through onFittingsProgress,
    the same read-side pattern the Preview stages use for onPreviewHotkeys. This
    avoids waiting through timer-throttled dev execution while keeping one data
    owner and the same semantic handler the real controller pushes.

    Does NOT include _FIT_RESET_JS or the Alliance scope switch: walk() runs
    each boundary action as its own evaluate call with a settle sleep afterward.
    The injected screenshot state answers collection reads synchronously, but
    retaining the boundary keeps staging equivalent to the ordinary async route.
    """
    body = ""
    if key in {"fittings-unfiled", "fittings-superseded"}:
        label = "Unfiled" if key == "fittings-unfiled" else "Superseded"
        body += (
            "  var wanted = null;\n"
            "  Array.prototype.forEach.call(\n"
            "    document.querySelectorAll('#fittings-collections .rail-plan'),\n"
            "    function (btn) {\n"
            "      var name = btn.querySelector('.rail-plan-name');\n"
            f"      if (name && name.textContent === {label!r}) {{ wanted = btn; }}\n"
            "    }\n"
            "  );\n"
            f"  if (!wanted) {{ throw new Error({label!r} + ' collection row is missing'); }}\n"
            "  wanted.click();\n"
        )
    elif key == "fittings-alliance":
        body += _fit_check_row_js(
            "alliance",
            "btn.querySelector('.fit-name') "
            "&& btn.querySelector('.fit-name').textContent === 'Merlin - Fleet Doctrine'",
            "recent Alliance import",
            action="open",
        )
    elif key == "fittings-detail":
        # Open rather than select: this fixture carries aliases, presences,
        # and three racks specifically for the detail capture.
        body += _fit_check_row_js(
            "detail",
            "btn.querySelector('.fit-name') "
            "&& btn.querySelector('.fit-name').textContent === 'Rifter - Solo PvP'",
            "Rifter - Solo PvP",
            action="open",
        )
    elif key == "fittings-narrow":
        body += (
            "  var rail = document.getElementById('fittings-collections');\n"
            "  var action = document.getElementById('fittings-copy-selected');\n"
            "  var list = document.getElementById('fittings-list');\n"
            "  if (!rail || !action || !list) {\n"
            "    throw new Error('Fittings floor controls are missing');\n"
            "  }\n"
            "  var first = document.querySelector('#fittings-list .fit-row-toggle');\n"
            "  if (!first) { throw new Error('No fitting row rendered at the floor'); }\n"
            "  first.scrollIntoView({block: 'start', behavior: 'instant'});\n"
        )
    elif key == "fittings-copy-preflight":
        # The injected fixture puts the present/conflict pair and its one
        # non-deployable generated fit on the same bounded page. Paging clears
        # page-owned selection, so a mixed preflight must remain one-page data.
        body += (
            _fit_check_row_js(
                "present",
                "btn.querySelector('.fit-name') "
                "&& btn.querySelector('.fit-name').textContent === 'Fleet Doctrine Alpha' "
                "&& btn.querySelector('.fit-meta') "
                "&& btn.querySelector('.fit-meta').textContent.indexOf('1 character') === 0",
                "Fleet Doctrine Alpha (already on Eryn)",
            )
            + _fit_check_row_js(
                "unavailable",
                "btn.querySelector('.fit-name') "
                "&& btn.querySelector('.fit-name').textContent === 'Generated Fit 001'",
                "Generated Fit 001 (non-deployable)",
            )
            + _fit_check_row_js(
                "conflict",
                "btn.querySelector('.fit-name') "
                "&& btn.querySelector('.fit-name').textContent === 'Fleet Doctrine Alpha' "
                "&& btn.querySelector('.fit-meta') "
                "&& btn.querySelector('.fit-meta').textContent.indexOf('0 characters') === 0",
                "Fleet Doctrine Alpha (unfiled source)",
            )
            + "  var copySelected = document.getElementById('fittings-copy-selected');\n"
            "  if (!copySelected || copySelected.disabled) {\n"
            "    throw new Error('Copy selected control is unavailable');\n"
            "  }\n"
            "  copySelected.click();\n"
            "  var overlay = document.getElementById('fittings-copy-overlay');\n"
            "  if (!overlay || overlay.hidden) { throw new Error('Copy overlay did not open'); }\n"
            + _FIT_CHECK_TARGET_JS
            + "  fitCheckTarget('Eryn Voss');\n"
            "  var review = document.getElementById('fittings-copy-review');\n"
            "  if (!review || review.disabled) { throw new Error('Review copy control is unavailable'); }\n"
            # Not asserted here: whether .fit-copy-pair rendered a
            # particular count. requestCopyPreflight()'s render happens
            # inside a Promise chain that this synchronous script cannot
            # reliably await -- CDP.evaluate() does not set awaitPromise --
            # so an assertion immediately after the click risks throwing on
            # a false negative (unsettled, not wrong) and losing the whole
            # screenshot rather than merely a stale one. walk()'s 0.25s
            # post-setup sleep is what the render actually depends on.
            "  review.click();\n"
        )
    elif key == "fittings-copy-limit":
        body += (
            "  var picked = 0;\n"
            "  Array.prototype.some.call(\n"
            "    document.querySelectorAll('#fittings-list .fit-row-toggle'),\n"
            "    function (btn) {\n"
            "      var name = btn.querySelector('.fit-name');\n"
            "      if (!name || name.textContent.indexOf('Generated Fit ') !== 0) {\n"
            "        return false;\n"
            "      }\n"
            "      var meta = btn.querySelector('.fit-meta');\n"
            "      if (meta && meta.textContent.indexOf('Not deployable') !== -1) {\n"
            "        return false;\n"
            # 'Generated Fit 001' is deliberately non-deployable (dev.js).
            "      }\n"
            "      var row = btn.closest('.fit-row');\n"
            "      var box = row.querySelector('.fit-select input[type=checkbox]');\n"
            "      if (!box) { return false; }\n"
            "      box.checked = true;\n"
            "      box.dispatchEvent(new Event('change'));\n"
            "      picked += 1;\n"
            "      return picked >= 21;\n"
            "    }\n"
            "  );\n"
            "  if (picked < 21) {\n"
            "    throw new Error(\n"
            "      'Only found ' + picked + ' Generated Fit rows; need 21 to trip the '\n"
            "      + 'write-count limit');\n"
            "  }\n"
            "  var copySelected = document.getElementById('fittings-copy-selected');\n"
            "  if (!copySelected || copySelected.disabled) {\n"
            "    throw new Error('Copy selected control is unavailable');\n"
            "  }\n"
            "  copySelected.click();\n"
            + _FIT_CHECK_TARGET_JS
            + "  fitCheckTarget('Eryn Voss');\n"
            "  var review = document.getElementById('fittings-copy-review');\n"
            "  if (!review || review.disabled) { throw new Error('Review copy control is unavailable'); }\n"
            # Not asserted here for the same reason as fittings-copy-preflight:
            # the refusal text arrives through requestCopyPreflight()'s
            # Promise chain, which this synchronous script cannot reliably
            # await; walk()'s post-setup sleep is what the screenshot
            # actually depends on.
            "  review.click();\n"
        )
    elif key in {"fittings-copy-progress", "fittings-copy-result"}:
        # One row selected only to make Copy selected clickable and the
        # overlay open (onCopyProgress ignores copy events while it is
        # closed). The result data itself remains owned by dev.js; this
        # tool only serializes that single authoritative fixture.
        fixture = load_dev_fittings_screenshot_fixture()["copy_result"]
        payload = (
            {
                "kind": "copy",
                "phase": "progress",
                "operation_id": fixture["operation_id"],
                "completed": 2,
                "total": len(fixture["results"]),
                "result": fixture["results"][1],
            }
            if key == "fittings-copy-progress"
            else {
                "kind": "copy",
                "phase": "complete",
                "operation_id": fixture["operation_id"],
                "completed": len(fixture["results"]),
                "total": len(fixture["results"]),
                "result": fixture,
            }
        )
        body += (
            _fit_check_row_js(
                "seed",
                "btn.querySelector('.fit-name') "
                "&& btn.querySelector('.fit-name').textContent === 'Generated Fit 002'",
                "Generated Fit 002",
            )
            + "  var copySelected = document.getElementById('fittings-copy-selected');\n"
            "  if (!copySelected || copySelected.disabled) {\n"
            "    throw new Error('Copy selected control is unavailable');\n"
            "  }\n"
            "  copySelected.click();\n"
            "  var payload = " + json.dumps(payload) + ";\n"
            "  if (typeof window.onFittingsProgress !== 'function') {\n"
            "    throw new Error('onFittingsProgress is missing');\n"
            "  }\n"
            "  window.onFittingsProgress(payload);\n"
            "  var copyBody = document.getElementById('fittings-copy-body');\n"
            "  if (!copyBody || !copyBody.textContent) {\n"
            "    throw new Error('Copy state did not render');\n"
            "  }\n"
        )
    else:
        raise ValueError(f"no fittings setup staged for {key!r}")
    return "(function () {\n" + body + "\n}())"


def _fittings_prepare_script(key: str) -> str | None:
    """Optional collection switch run between reset and final staging."""
    if key == "fittings-alliance":
        body = (
            "  var alliance = null;\n"
            "  Array.prototype.forEach.call(\n"
            "    document.querySelectorAll('#fittings-collections .rail-plan'),\n"
            "    function (btn) {\n"
            "      var name = btn.querySelector('.rail-plan-name');\n"
            "      if (name && name.textContent === 'Alliance') { alliance = btn; }\n"
            "    }\n"
            "  );\n"
            "  if (!alliance) {\n"
            "    throw new Error('Alliance collection row is missing');\n"
            "  }\n"
            "  alliance.click();\n"
        )
    else:
        return None
    return "(function () {\n" + body + "}())"


def _fittings_reset_script() -> str:
    """The state-reset half of every fittings-* stage; see
    _fittings_setup_script's docstring for why this runs as its own
    evaluate() call rather than being concatenated onto the stage body.
    """
    return "(function () {\n" + _FIT_RESET_JS + "\n}())"


def screen_setup_script(screen: Screen) -> str | None:
    """Post-navigation staging for screenshots within a long screen."""
    if screen.key == "settings-characters":
        return _fixture_characters_setup(
            "partial",
            "  var count = document.getElementById('characters-count');\n"
            "  var filter = document.getElementById('characters-filter');\n"
            "  if (!count || count.textContent.indexOf('3 character') !== 0) {\n"
            "    throw new Error('Characters summary did not render');\n"
            "  }\n"
            "  if (!filter || filter.disabled) {\n"
            "    throw new Error('Characters filter is unavailable');\n"
            "  }",
        )
    if screen.key == "settings-characters-waiting":
        return _fixture_characters_setup(
            "waiting",
            "  var activity = document.getElementById('characters-activity');\n"
            "  var cancel = document.getElementById('characters-cancel');\n"
            "  if (!activity || activity.textContent.indexOf('Waiting for EVE SSO') !== 0) {\n"
            "    throw new Error('Characters waiting state did not render');\n"
            "  }\n"
            "  if (!cancel || cancel.hidden || cancel.disabled) {\n"
            "    throw new Error('Characters cancel control is unavailable');\n"
            "  }",
        )
    if screen.key == "settings-characters-narrow":
        return _fixture_characters_setup(
            "maximum-50",
            "  var roster = document.getElementById('characters-roster');\n"
            "  var rows = roster.querySelectorAll('.characters-row');\n"
            "  if (rows.length !== 50) {\n"
            "    throw new Error('Characters 50-row fixture did not render');\n"
            "  }\n"
            "  roster.scrollTop = roster.scrollHeight;\n"
            "  var last = rows[rows.length - 1];\n"
            "  if (!last) { throw new Error('Last characters row is missing'); }\n"
            "  var trigger = last.querySelector('.characters-menu-trigger');\n"
            "  if (!trigger) { throw new Error('Characters menu trigger is missing'); }\n"
            "  trigger.click();\n"
            "  var menu = document.getElementById('characters-menu');\n"
            "  if (!menu || menu.hidden || !menu.open) {\n"
            "    throw new Error('Characters overflow menu did not open');\n"
            "  }",
        )
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
    if screen.key == "settings-previews-sticky-conflict":
        # Task 6. Tanuki Solette's row (the FIRST OFFLINE row) used to be
        # the target here, staged behind BOTH the sticky column header and
        # the sticky Offline heading. That left nothing further below her
        # to scroll into: nudging her row behind both stickies clamped the
        # pane at the same maximum scrollTop settings-previews-table
        # already reaches by setting scrollTop = scrollHeight, so the two
        # captures came out pixel-identical.
        #
        # Aiga Otsolen's direct bind (Ctrl+Alt+1) collides with an ACTIVE
        # EVE bookmark keybind instead (bookmark_chords.active in the
        # fixture), and she is the FIRST ONLINE character row -- directly
        # under the sticky column header, with every other online row,
        # the Offline heading and every offline row still beneath her. That
        # gives this capture room to stage her row just behind the header
        # without running out of scrollable content the way Tanuki's did.
        # Only ONE sticky matters for her: the Offline heading opens the
        # offline block, which starts after every online character, so it
        # sits well below her row and never covers it.
        #
        # That headroom is not automatically enough, though: the roster
        # card above #preview-binds (per-character size/lock/never-minimize
        # controls for the fixture's twelve characters) is tall enough at
        # the app's own default window (1040x680, window.py) that Aiga's
        # row sits close to where the pane's OWN maximum scrollTop already
        # is -- measured directly, aligning her row's cell to the pane's
        # top asked for ~54px more scroll than the pane had before opening
        # anything below her. Opening Aleksandrina Shadowbanes Voidstriders'
        # Configure detail -- the same read-only disclosure
        # settings-previews-detail already drives, well below Aiga in the
        # offline block -- adds ~70px of legitimate, real content below her
        # (no fabricated spacing, no bridge write: previews.js's Configure
        # click handler only flips local state and re-renders), which is
        # enough headroom to clear that ~54px gap and let this stage reach
        # its true, non-clamped position instead of the pane's bottom.
        #
        # appendBindRow's owner-key contract (previews.js) is
        # 'character:' + character for a character row; bindConflictId then
        # keys the conflict div's id off encodeURIComponent(ownerKey). The
        # conflict div is the row's very next sibling as long as that
        # character's own Configure detail is not open (appendBindRow only
        # inserts a detail between them when openDetailName matches), so
        # closing every inherited detail first (as the groups/narrow stages
        # already do) keeps that adjacency true here too.
        #
        # The row itself is `display: contents` (style.css), which leaves
        # it with no rendered box of its own -- calling scrollIntoView on
        # it is a silent no-op, not an error, so the earlier Tanuki version
        # of this script relied on the pane's scrollTop already being where
        # it needed to be by coincidence. Its first rendered child carries
        # the box the row would have had, so that child is what gets
        # scrolled and the pane's own scrollTop is what gets read back,
        # rather than trusting the contents element's own (always-zero)
        # geometry.
        #
        # The scroll position is measured live off the rendered sticky
        # header rather than a hardcoded pixel guess, so it holds if its
        # height ever changes: scroll the row's cell toward the pane's top,
        # then nudge only far enough that the conflict text clears the
        # header, leaving the row itself at or behind the sticky-header
        # transition -- the scenario this capture exists to show. Never a
        # blanket `pane.scrollTop = pane.scrollHeight`: that is
        # settings-previews-table's own mechanism, and reusing it here
        # would reproduce the exact pixel-identical capture this rewrite
        # exists to fix. A final bottom-clamp check throws explicitly if
        # the nudge above still lands on that same maximum scrollTop --
        # this stage must FAIL rather than silently ship a duplicate of
        # the table capture again under a different name.
        fixture = load_dev_preview_fixture()
        payload_js = json.dumps(fixture)
        owner_key_js = json.dumps("character:Aiga Otsolen")
        long_name = "Aleksandrina Shadowbanes Voidstriders"
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
            "  var pane = document.querySelector('.settings-pane');\n"
            "  if (!pane) { throw new Error('Settings pane is missing'); }\n"
            "  var extra = document.querySelector(\n"
            "    '[data-preview-configure=\"" + long_name + "\"]');\n"
            "  if (!extra) {\n"
            "    throw new Error(\n"
            "      'Aleksandrina Shadowbanes Voidstriders Configure control '\n"
            "      + 'is missing');\n"
            "  }\n"
            "  extra.click();\n"
            "  var reopened = document.querySelector(\n"
            "    '[data-preview-configure=\"" + long_name + "\"]');\n"
            "  if (!reopened || reopened.getAttribute('aria-expanded') !== 'true') {\n"
            "    throw new Error(\n"
            "      'Aleksandrina Shadowbanes Voidstriders detail did not '\n"
            "      + 'open, so this stage has no extra scroll extent below '\n"
            "      + 'Aiga to work with');\n"
            "  }\n"
            "  var conflict = document.getElementById(\n"
            "    'preview-bind-conflict-' + encodeURIComponent("
            + owner_key_js
            + "));\n"
            "  if (!conflict) {\n"
            "    throw new Error('Aiga Otsolen conflict warning is missing');\n"
            "  }\n"
            "  var row = conflict.previousElementSibling;\n"
            "  if (!row || !row.classList.contains('row')) {\n"
            "    throw new Error(\n"
            "      'Conflict warning is not directly after its owning row');\n"
            "  }\n"
            "  var cell = row.firstElementChild;\n"
            "  if (!cell) {\n"
            "    throw new Error(\n"
            "      'Owning row has no rendered cell to measure');\n"
            "  }\n"
            "  cell.scrollIntoView({block: 'start', behavior: 'instant'});\n"
            "  var headCell = document.querySelector(\n"
            "    '#preview-binds .bind-head > span');\n"
            "  if (!headCell) {\n"
            "    throw new Error('Sticky preview header is missing');\n"
            "  }\n"
            "  var coverBottom = headCell.getBoundingClientRect().bottom;\n"
            "  var conflictTop = conflict.getBoundingClientRect().top;\n"
            "  if (conflictTop < coverBottom) {\n"
            "    pane.scrollTop += (coverBottom - conflictTop);\n"
            "  }\n"
            "  var paneRect = pane.getBoundingClientRect();\n"
            "  var after = conflict.getBoundingClientRect();\n"
            "  if (after.bottom <= paneRect.top || after.top >= paneRect.bottom) {\n"
            "    throw new Error(\n"
            "      'Conflict warning is not within the scrollport');\n"
            "  }\n"
            "  var maxScroll = pane.scrollHeight - pane.clientHeight;\n"
            "  if (pane.scrollTop >= maxScroll - 1) {\n"
            "    throw new Error(\n"
            "      'Staging this row reached the panes bottom clamp, the '\n"
            "      + 'exact pixel-identical capture this stage exists to '\n"
            "      + 'avoid -- settings-previews-table already shows that '\n"
            "      + 'state');\n"
            "  }\n"
            "}())"
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
    if screen.key == "settings-alerts-advanced":
        # Task 5. Every id inside #alert-advanced is unchanged from the
        # primary-table days (0fd49d8), and alerts.js has no listener on
        # the disclosure's own toggle event, so opening it here is purely
        # presentational -- no Api call, no click on any control inside it.
        return (
            "(function () {\n"
            "  var details = document.getElementById('alert-advanced');\n"
            "  if (!details) {\n"
            "    throw new Error('Alerts advanced disclosure is missing');\n"
            "  }\n"
            "  details.open = true;\n"
            "  details.scrollIntoView({block: 'center', behavior: 'instant'});\n"
            "}())"
        )
    if screen.key.startswith("fittings-"):
        return _fittings_setup_script(screen.key)
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
        "been quit yet, or it was and _claim_quit refused because an "
        "upload is in flight.\n"
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
            # Any floor-sized capture must pin 840x625 BEFORE its setup runs.
            # That setup picks scroll positions and visible controls; doing it
            # first would stage the screen against the wrong viewport and then
            # photograph a different layout. The clear is in a finally so one
            # failed floor shot cannot distort every screenshot after it.
            if screen.at_floor:
                cdp.set_device_metrics_override(width=840, height=625)
            try:
                if screen.route == "fittings":
                    # Replace live read state through the bounded page-side
                    # screenshot handler before ANY stage action. This follows
                    # the Preview fixture precedent and cannot call Python, ESI,
                    # or a durable writer. Route leave clears the injected state.
                    cdp.evaluate(fittings_fixture_setup_script())
                    time.sleep(0.25)
                    if screen.key.startswith("fittings-"):
                        cdp.evaluate(_fittings_reset_script())
                        time.sleep(0.25)
                        prepare = _fittings_prepare_script(screen.key)
                        if prepare:
                            cdp.evaluate(prepare)
                            time.sleep(0.25)
                setup = screen_setup_script(screen)
                if setup:
                    cdp.evaluate(setup)
                    time.sleep(0.25)
                (out_dir / name).write_bytes(cdp.screenshot())
            finally:
                if screen.at_floor:
                    cdp.clear_device_metrics_override()
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
