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
    shots: list[dict],
    skipped: list[Screen],
) -> dict:
    """Describe the run precisely enough that the set cannot mislead.

    A run that shot four screens because the EVE gate was off is correct; a
    run that shot four and looks truncated is not. The difference is only
    visible if the gate state and the skip list are recorded.
    """
    return {
        "branch": branch,
        "sha": sha,
        "dirty": dirty,
        "python": python,
        "viewport": viewport,
        "eve_shown": eve_shown,
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
# the repo open -- and close_incumbent would taskkill them. Match on
# process IDENTITY instead: the installed exe by name, or a python
# running `-m wingman` as its module.
_MATCH = (
    f"$_.Name -eq '{APP_EXE}'"
    " -or ($_.Name -like 'python*.exe'"
    " -and $_.CommandLine -match '-m\\s+wingman(\\s|$)')"
)


class BusyError(Exception):
    """The app would not close, most likely because it is uploading."""


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


def close_incumbent(timeout_s: float = 20.0) -> None:
    """Ask the app to close, and accept no for an answer.

    taskkill WITHOUT /F posts WM_CLOSE and lets the app take its own path.
    There is deliberately no /F escalation:

      - atomicio does NOT cover settings.json, seen.json or token.json
        (settings.py:559 and watcher.py:47 are plain write_text;
        uploader.py:340 opens with O_TRUNC), so a forced kill can truncate
        live state; and
      - _confirm_quit_if_busy (__main__.py:621) exists precisely so that
        quitting cannot discard an upload in flight.

    A refusal to exit is very often that guard doing its job. A screenshot
    is never worth overriding it, so a timeout aborts the run.
    """
    script = (
        "Get-CimInstance Win32_Process"
        f" | Where-Object {{ {_MATCH} }}"
        " | ForEach-Object { taskkill /PID $_.ProcessId }"
    )
    _powershell(script)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if find_incumbent() is None:
            return
        time.sleep(0.5)
    raise BusyError(
        "Wingman did not close within "
        f"{timeout_s:.0f}s. It may be uploading -- _confirm_quit_if_busy "
        "refuses to quit mid-upload on purpose.\n"
        "Nothing was killed and nothing needs restoring. Quit it from the "
        "tray menu when the upload finishes, then re-run."
    )


def restore_incumbent(command_line: str) -> None:
    """Relaunch exactly what was running before."""
    subprocess.Popen(["cmd.exe", "/c", "start", "", *command_line.split()])


class TargetError(Exception):
    """No target could be confirmed as the real app page."""


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
        return result.get("result", {}).get("value")

    def screenshot(self) -> bytes:
        return base64.b64decode(self._call("Page.captureScreenshot")["data"])

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
            # handling. Note there is no `# noqa: S112` here: that rule fires
            # only on a bare try-except-continue, and this handler sleeps
            # first, so a suppression would itself be flagged by RUF100.
            time.sleep(0.5)
            continue
        targets = json.loads(raw)
        seen = [t.get("url", "") for t in targets]
        for target in page_candidates(targets):
            ws = websocket.create_connection(
                target["webSocketDebuggerUrl"], suppress_origin=True
            )
            cdp = CDP(ws)
            # The decisive check. dev.js activates ONLY when
            # window.pywebview is absent, so a page that HAS it cannot be
            # the fabricating harness. This is proof, where the URL filter
            # was only a cheap pre-filter.
            if cdp.evaluate("typeof window.pywebview !== 'undefined'") is True:
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
                cdp.evaluate(
                    "WM.confirm('Delete recording?',"
                    " 'This removes the local file. It cannot be undone.')"
                )
            else:
                cdp.evaluate(f"WM.route({screen.route!r})")
                if screen.section:
                    cdp.evaluate(f"WM.section({screen.section!r})")
            time.sleep(settle_ms / 1000)
            (out_dir / name).write_bytes(cdp.screenshot())
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

    incumbent = find_incumbent()
    if incumbent:
        print(f"Closing: {incumbent}")
        try:
            close_incumbent()
        except BusyError as exc:
            print(str(exc), file=sys.stderr)
            return 2

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
            shots=shots,
            skipped=skipped,
        )
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    finally:
        # Close the instance WE launched through the same graceful path, not
        # app.terminate(): Popen(shell=True) holds the cmd.exe wrapper, and
        # killing that need not take the python child with it, which would
        # leave the mutex held and the restore below silently failing.
        #
        # The BusyError is swallowed on purpose. Raised out of a finally it
        # would skip the restore below, so a shot instance that would not
        # close would cost the user their own Wingman. Restoring theirs
        # outranks a clean shutdown of ours.
        if app is not None:
            try:
                close_incumbent()
            except BusyError:
                print(
                    "warning: the instance this run launched did not close;"
                    " it still holds the mutex, so the restore below may fail."
                    " Close it by hand.",
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
