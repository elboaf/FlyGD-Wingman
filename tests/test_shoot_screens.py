"""Unit tests for the UX screenshot shooter's decision logic.

The shooter's Windows shell (process control, CDP socket, capture) has no
tests, exactly as hotkeys.py has none: it is unreachable off-platform. So
every DECISION it makes lives in a pure function here instead, which is
the same split bookmarks.py/hotkeys.py already uses.
"""

import importlib.util
import pathlib
import re

import pytest

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
    assert len(to_shoot) == 17
    assert skipped == []


def test_gate_off_shoots_only_the_four_reachable_screens():
    """With EVE undetected the app hides three shot routes and three sections.

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
    assert len(skipped) == 13


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


def _query_selector_arguments(expression: str) -> list[str]:
    """Parse literal arguments passed directly to document.querySelector."""
    return [
        match.group(2)
        for match in re.finditer(
            r"document\.querySelector\(\s*(['\"])(.*?)\1\s*\)",
            expression,
            re.DOTALL,
        )
    ]


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


def test_preview_capture_variants_cover_the_scroller_and_picker():
    variants = {
        screen.key: shoot.screen_setup_script(screen)
        for screen in shoot.SCREENS
        if screen.key.startswith("settings-previews")
    }
    assert set(variants) == {
        "settings-previews",
        "settings-previews-middle",
        "settings-previews-table",
        "settings-previews-detail",
        "settings-previews-copy",
        "settings-previews-groups",
        "settings-previews-narrow",
    }
    assert "scrollTop = 0" in variants["settings-previews"]
    assert "scrollHeight - pane.clientHeight" in variants["settings-previews-middle"]
    assert "pane.scrollHeight" in variants["settings-previews-table"]
    detail = variants["settings-previews-detail"]
    copy = variants["settings-previews-copy"]
    assert '[data-preview-configure="Aleksandrina Shadowbanes Voidstriders"]' in detail
    assert "WM.choose(" not in copy
    assert '[data-preview-configure="Aleksandrina Shadowbanes Voidstriders"]' in copy
    assert '[data-preview-detail-control="copy"]' in copy
    assert copy.index("configure.click()") < copy.index("copy.click()")


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


def test_resolve_interpreter_prefers_explicit_over_env():
    got = shoot.resolve_interpreter(
        "C:/explicit/python.exe",
        "C:/env/python.exe",
        search=lambda: ["C:/found/python.exe"],
        probe=lambda path: True,
    )
    assert got == "C:/explicit/python.exe"


def test_resolve_interpreter_falls_back_to_search():
    got = shoot.resolve_interpreter(
        None, None, search=lambda: ["C:/found/python.exe"], probe=lambda path: True
    )
    assert got == "C:/found/python.exe"


def test_resolve_interpreter_rejects_a_python_without_the_app_deps():
    """A found Python that cannot import webview is worse than none.

    It launches, fails, and by then the user's Wingman is already closed.
    So the probe runs BEFORE anything is closed, and a failure is fatal.
    """
    with pytest.raises(shoot.InterpreterError) as excinfo:
        shoot.resolve_interpreter(
            "C:/store/stub/python.exe",
            None,
            search=list,
            probe=lambda path: False,
        )
    assert "webview" in str(excinfo.value)


def test_resolve_interpreter_skips_unusable_candidates_and_keeps_looking():
    got = shoot.resolve_interpreter(
        None,
        None,
        search=lambda: ["C:/stub/python.exe", "C:/real/python.exe"],
        probe=lambda path: path == "C:/real/python.exe",
    )
    assert got == "C:/real/python.exe"


def test_resolve_interpreter_reports_every_place_it_looked():
    with pytest.raises(shoot.InterpreterError) as excinfo:
        shoot.resolve_interpreter(None, None, search=list, probe=lambda path: True)
    assert "--python" in str(excinfo.value)


def test_launch_command_sets_the_env_inside_cmd():
    """WSL environment variables do NOT cross into a Windows process.

    Passing FOO=x before the exe arrives as NOT PASSED. When PYTHONPATH was
    lost this way the package resolved from cwd instead, so a run silently
    exercised the MAIN checkout while the worktree fix sat unused -- and the
    fix was declared broken against code that never contained it.
    """
    cmd = shoot.launch_command("C:/py/python.exe", "C:/dev/wingman", 9600)
    assert cmd.startswith("cmd.exe /c ")
    assert "set WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=" in cmd
    assert "--remote-debugging-port=9600" in cmd
    assert "--remote-allow-origins=*" in cmd
    assert "cd /d C:/dev/wingman" in cmd
    assert "-m wingman" in cmd


def test_launch_command_does_not_redirect_localappdata():
    """The agreed design shoots LIVE state. Redirecting it is a real
    behaviour change, so assert it is absent rather than assume."""
    cmd = shoot.launch_command("C:/py/python.exe", "C:/dev/wingman", 9600)
    assert "LOCALAPPDATA" not in cmd


def test_manifest_records_what_the_gate_skipped():
    _, skipped = shoot.screens_for_gate(False)
    manifest = shoot.build_manifest(
        branch="main",
        sha="abc1234",
        dirty=False,
        python="C:/py/python.exe",
        viewport={"width": 1015, "height": 700},
        eve_shown=False,
        engine_present=True,
        shots=[{"key": "uploader", "file": "01-uploader.png", "error": None}],
        skipped=skipped,
    )
    assert manifest["eve_shown"] is False
    assert sorted(manifest["skipped"]) == [
        "profiles",
        "profiles-account-identity",
        "profiles-backups",
        "settings-alerts",
        "settings-bookmarks",
        "settings-previews",
        "settings-previews-copy",
        "settings-previews-detail",
        "settings-previews-groups",
        "settings-previews-middle",
        "settings-previews-narrow",
        "settings-previews-table",
        "skills",
    ]
    assert manifest["shot_count"] == 1
    assert manifest["python"] == "C:/py/python.exe"


def test_manifest_counts_a_failed_shot_as_not_shot():
    """A set that looks complete but is not is the failure mode here."""
    manifest = shoot.build_manifest(
        branch="main",
        sha="abc1234",
        dirty=True,
        python="C:/py/python.exe",
        viewport={"width": 1015, "height": 700},
        eve_shown=True,
        engine_present=True,
        shots=[
            {"key": "uploader", "file": "01-uploader.png", "error": None},
            {"key": "skills", "file": None, "error": "TypeError: x is undefined"},
        ],
        skipped=[],
    )
    assert manifest["shot_count"] == 1
    assert manifest["failed"] == ["skills"]


def test_restore_incumbent_keeps_a_spaced_install_path_intact(monkeypatch):
    """Prevents the drift that broke every real restore: the old
    `.split()` implementation tokenized the installed exe's own quoted
    command line on its embedded space, producing two nonexistent paths
    that cmd could not launch."""
    calls = []
    monkeypatch.setattr(
        shoot.subprocess, "Popen", lambda *a, **kw: calls.append((a, kw))
    )
    command_line = (
        '"C:\\Users\\tng\\AppData\\Local\\Programs\\FlyGD Wingman\\Wingman.exe"'
    )
    shoot.restore_incumbent(command_line)
    (args, kwargs) = calls[0]
    called_with = args[0]
    assert "FlyGD Wingman\\Wingman.exe" in called_with
    assert kwargs.get("shell") is True


def test_restore_incumbent_keeps_source_build_arguments_intact(monkeypatch):
    """Prevents the drift where a source-build command line's trailing
    `-m wingman` argument gets separated from its quoted interpreter path."""
    calls = []
    monkeypatch.setattr(
        shoot.subprocess, "Popen", lambda *a, **kw: calls.append((a, kw))
    )
    command_line = '"C:\\Python312\\python.exe" -m wingman'
    shoot.restore_incumbent(command_line)
    (args, _kwargs) = calls[0]
    called_with = args[0]
    assert "-m wingman" in called_with


def test_staged_dialog_matches_the_production_delete_payload():
    """The capture must exercise the same bridge payload production sends.

    Dropping the specific affirming label made a successful product change look
    broken in the screenshot that was supposed to verify it.
    """
    assert shoot.dialog_payload() == {
        "kind": "confirm",
        "title": "Confirm Delete",
        "body": shoot.DIALOG_BODY,
        "request_id": None,
        "destructive": True,
        "confirm_label": "Delete 2 files",
    }


def test_dialog_body_matches_the_shape_the_app_actually_raises():
    """The staged confirm stands in for Api._delete_worker's dialog, and a
    screenshot of a dialog the app cannot produce is worse than no shot.

    Asserts the SHAPE, not the wording: the heading, one bulleted line per
    file, and the cost sentence. A one-line body hides that the real dialog
    enumerates what it is about to destroy, which is the whole reason that
    dialog is worth a screenshot."""
    body = shoot.DIALOG_BODY
    assert body.startswith("Permanently delete these files from disk?")
    assert body.endswith("This cannot be undone.")
    bullets = [ln for ln in body.splitlines() if ln.startswith("  \u2022 ")]
    assert len(bullets) == len(shoot.DIALOG_NAMES) >= 2
    for name in shoot.DIALOG_NAMES:
        assert f"  \u2022 {name}" in body


def test_manifest_records_a_set_shot_without_the_engine():
    """False here means Settings > Bookmarks shot its engine-missing error,
    which is a property of this tool and not of the app. Every set shot
    before ensure_engine existed carried that error with nothing in the
    manifest to say so, and two reviewers filed it as a live regression."""
    manifest = shoot.build_manifest(
        branch="main",
        sha="abc1234",
        dirty=False,
        python="C:/py/python.exe",
        viewport={"width": 1015, "height": 700},
        eve_shown=True,
        engine_present=False,
        shots=[{"key": "uploader", "file": "01-uploader.png", "error": None}],
        skipped=[],
    )
    assert manifest["engine_present"] is False


def test_ensure_engine_is_a_noop_when_the_binary_is_already_there(tmp_path):
    """The fetcher self-skips on a matching pin, but this must not even
    spawn it -- the shoot runs before the user's app is restarted and has
    no business making a network call it does not need."""
    exe = tmp_path / "packaging" / "bin" / "AutoHotkeyU64.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    calls = []
    original = shoot.subprocess.run
    try:
        shoot.subprocess.run = lambda *a, **kw: calls.append(a)
        assert shoot.ensure_engine(str(tmp_path), "python") is True
    finally:
        shoot.subprocess.run = original
    assert calls == []


def test_ensure_engine_reports_false_without_raising_when_it_cannot_fetch(tmp_path):
    """Non-fatal on purpose: offline, the old behaviour is still eight good
    screens. Aborting the run here would strand a user who has already been
    asked to quit their app."""
    (tmp_path / "packaging").mkdir()
    (tmp_path / "packaging" / "fetch_autohotkey.py").write_text("")

    class _Failed:
        returncode = 1
        stdout = ""
        stderr = "ERROR: download failed"

    original = shoot.subprocess.run
    try:
        shoot.subprocess.run = lambda *a, **kw: _Failed()
        assert shoot.ensure_engine(str(tmp_path), "python") is False
    finally:
        shoot.subprocess.run = original


def test_ensure_engine_reports_false_when_the_fetcher_is_absent(tmp_path):
    """A checkout without packaging/ is not an error, just a set that will
    carry the artifact."""
    assert shoot.ensure_engine(str(tmp_path), "python") is False


def test_preview_group_stages_are_present():
    """Task 5: the shoot list must include a group-populated stage and an
    840x625 narrow-viewport stage for the previews section.

    The group-keybinds stage shows the Global keybinds card fully populated
    with group rows.  The narrow stage captures 840x625 character rows with
    long character/group names.  Both must be in SCREENS and gated (require
    EVE) like the other previews screens.
    """
    keys = {s.key for s in shoot.SCREENS}
    assert "settings-previews-groups" in keys, (
        "settings-previews-groups stage missing from SCREENS"
    )
    assert "settings-previews-narrow" in keys, (
        "settings-previews-narrow stage missing from SCREENS"
    )
    groups_screen = next(
        s for s in shoot.SCREENS if s.key == "settings-previews-groups"
    )
    narrow_screen = next(
        s for s in shoot.SCREENS if s.key == "settings-previews-narrow"
    )
    assert groups_screen.gated, "settings-previews-groups must be gated (EVE required)"
    assert narrow_screen.gated, "settings-previews-narrow must be gated (EVE required)"
    assert groups_screen.section == "previews"
    assert narrow_screen.section == "previews"


def test_preview_group_stage_setup_scripts():
    """The group and floor stages scroll without resizing the page.

    CDP owns the 840x625 override; the floor setup merely closes inherited
    details and frames the roster heading in the Settings scrollport.
    """
    scripts = {
        s.key: shoot.screen_setup_script(s)
        for s in shoot.SCREENS
        if s.key in {"settings-previews-groups", "settings-previews-narrow"}
    }
    assert "settings-previews-groups" in scripts
    assert "settings-previews-narrow" in scripts
    groups_script = scripts["settings-previews-groups"]
    narrow_script = scripts["settings-previews-narrow"]
    # The groups stage must scroll to reveal the Manage groups disclosure.
    assert groups_script is not None, "settings-previews-groups needs a setup script"
    assert "preview-group-manager" in groups_script
    assert "scrollIntoView" in groups_script, (
        "groups stage setup must scroll the real group manager into view"
    )
    # The narrow stage must scroll (not resize via window.resizeTo --
    # that is a no-op in WebView2; the viewport is set through CDP instead).
    assert narrow_script is not None, "settings-previews-narrow needs a setup script"
    assert "resizeTo" not in narrow_script, (
        "narrow stage must NOT use window.resizeTo (it is a no-op in WebView2); "
        "use Emulation.setDeviceMetricsOverride via CDP instead"
    )
    assert "#preview-roster-heading" in narrow_script
    assert "scrollIntoView" in narrow_script, (
        "narrow stage must frame the roster heading in the scrollport"
    )


def test_gate_on_shoots_every_screen_including_new_group_stages():
    """The representative detail stage brings the gated capture set to 17."""
    to_shoot, skipped = shoot.screens_for_gate(True)
    assert len(to_shoot) == 17
    assert skipped == []


# ---------------------------------------------------------------------------
# CDP viewport-override tests
# ---------------------------------------------------------------------------


class _FakeWS:
    """Minimal websocket stand-in that speaks just enough CDP to satisfy CDP."""

    def __init__(self):
        self._sent = []
        self._id = 0
        self._queue = []

    def send(self, text):
        import json as _json

        msg = _json.loads(text)
        self._sent.append(msg)
        # Prepare a matching reply so _call() sees its id immediately.
        self._queue.append({"id": msg["id"], "result": {"data": ""}})

    def recv(self):
        import json as _json

        return _json.dumps(self._queue.pop(0))


def test_cdp_set_device_metrics_override_sends_correct_params():
    """Emulation.setDeviceMetricsOverride must be sent with width=840,
    height=625, deviceScaleFactor=1, mobile=False.

    These are the only parameters that meet the brief: width/height match
    the documented minimum viewport, scale factor 1 keeps CSS pixels equal
    to physical pixels (no DPI scaling artefacts), and mobile=False avoids
    viewport-meta side-effects that could widen the layout.
    """
    ws = _FakeWS()
    cdp = shoot.CDP(ws)
    cdp.set_device_metrics_override(width=840, height=625)
    methods = [m["method"] for m in ws._sent]
    assert "Emulation.setDeviceMetricsOverride" in methods, (
        "CDP must send Emulation.setDeviceMetricsOverride for the narrow viewport"
    )
    call = next(
        m for m in ws._sent if m["method"] == "Emulation.setDeviceMetricsOverride"
    )
    params = call["params"]
    assert params["width"] == 840
    assert params["height"] == 625
    assert params["deviceScaleFactor"] == 1
    assert params["mobile"] is False


def test_cdp_clear_device_metrics_override_sends_correct_method():
    """Emulation.clearDeviceMetricsOverride must be sent with no params
    (or empty params) to restore the real viewport after the narrow shot.
    """
    ws = _FakeWS()
    cdp = shoot.CDP(ws)
    cdp.clear_device_metrics_override()
    methods = [m["method"] for m in ws._sent]
    assert "Emulation.clearDeviceMetricsOverride" in methods, (
        "CDP must send Emulation.clearDeviceMetricsOverride after the narrow shot"
    )


class _ExceptionWS:
    """Websocket stub that returns a Runtime.evaluate response with
    exceptionDetails set, simulating a JavaScript exception."""

    def __init__(self, exception_details):
        self._exception_details = exception_details
        self._id = 0
        self._queue = []

    def send(self, text):
        import json as _json

        msg = _json.loads(text)
        # For Runtime.evaluate, return exceptionDetails; for others, normal empty result.
        if msg.get("method") == "Runtime.evaluate":
            self._queue.append(
                {
                    "id": msg["id"],
                    "result": {
                        "result": {"type": "undefined"},
                        "exceptionDetails": self._exception_details,
                    },
                }
            )
        else:
            self._queue.append({"id": msg["id"], "result": {}})

    def recv(self):
        import json as _json

        return _json.dumps(self._queue.pop(0))


def test_cdp_evaluate_raises_target_error_on_exception_details():
    """CDP.evaluate must detect exceptionDetails in the Runtime.evaluate
    response and raise TargetError, so a failed JavaScript setup script
    is recorded as a failed shot rather than returning None silently.

    Without this guard, a setup script failure (e.g. missing DOM element,
    undefined handler) produces a valid-looking None return, and the
    subsequent screenshot documents the wrong page state.
    """
    exc_details = {
        "exceptionId": 1,
        "text": "Uncaught",
        "lineNumber": 0,
        "columnNumber": 0,
        "exception": {
            "type": "error",
            "description": "ReferenceError: x is not defined",
        },
    }
    ws = _ExceptionWS(exc_details)
    cdp = shoot.CDP(ws)
    with pytest.raises(shoot.TargetError):
        cdp.evaluate("x.notDefined()")


def test_cdp_evaluate_returns_value_when_no_exception():
    """CDP.evaluate must return the JS result value when no exceptionDetails
    is present -- i.e., normal execution is unaffected by the guard."""
    import json as _json

    class _ValueWS:
        def __init__(self):
            self._id = 0
            self._queue = []

        def send(self, text):
            msg = _json.loads(text)
            self._queue.append(
                {
                    "id": msg["id"],
                    "result": {"result": {"type": "string", "value": "hello"}},
                }
            )

        def recv(self):
            return _json.dumps(self._queue.pop(0))

    cdp = shoot.CDP(_ValueWS())
    assert cdp.evaluate("'hello'") == "hello"


def test_walk_records_setup_failure_as_failed_shot(tmp_path, monkeypatch):
    """When a setup script raises TargetError (e.g. JS exception in the
    setup expression), walk() must record that shot as failed rather than
    continuing as if the setup succeeded.

    This tests the end-to-end path: CDP.evaluate(setup) raises TargetError
    → walk() catches it and records error='...' for that shot key.
    """
    monkeypatch.setattr(shoot.time, "sleep", lambda _: None)

    class _SetupFailCDP:
        """CDP that raises TargetError on any evaluate() call containing 'setup'."""

        def __init__(self):
            self._ops = []

        def evaluate(self, expression: str):
            # Fail the setup script evaluations (fixture injection calls).
            # The eve_shown check must still return True.
            if "WM.eve_shown" in expression:
                return True
            if (
                "window.onPreviewHotkeys" in expression
                or "scrollIntoView" in expression
            ):
                raise shoot.TargetError("JS exception: setup failed")
            return None

        def screenshot(self) -> bytes:
            import base64 as _b64

            return _b64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
                "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
            )

        def set_device_metrics_override(self, *, width: int, height: int) -> None:
            pass

        def clear_device_metrics_override(self) -> None:
            pass

    cdp = _SetupFailCDP()
    shots, _skipped, _eve_shown = shoot.walk(cdp, tmp_path, settle_ms=0)

    # The group and narrow stages both use setup scripts; they must fail.
    group_shot = next(
        (s for s in shots if s["key"] == "settings-previews-groups"), None
    )
    narrow_shot = next(
        (s for s in shots if s["key"] == "settings-previews-narrow"), None
    )
    assert group_shot is not None, "settings-previews-groups stage must be attempted"
    assert narrow_shot is not None, "settings-previews-narrow stage must be attempted"
    assert group_shot["error"] is not None, (
        "settings-previews-groups must be recorded as failed when setup raises TargetError"
    )
    assert narrow_shot["error"] is not None, (
        "settings-previews-narrow must be recorded as failed when setup raises TargetError"
    )


class _TrackedCDP:
    """A traceable fake CDP that records protocol operations in order.

    Used to verify that walk() applies device metrics before capturing
    the narrow screenshot and clears them afterward in a finally-safe
    manner, including when the screenshot itself raises an exception.
    """

    def __init__(self, *, fail_narrow_screenshot: bool = False):
        self._ops: list[str] = []  # ordered record of operations
        self._fail_narrow = fail_narrow_screenshot
        self._override_active = False

    def evaluate(self, expression: str):
        if "WM.eve_shown" in expression:
            return True
        return None

    def screenshot(self) -> bytes:
        if self._fail_narrow and self._override_active:
            # Simulate a CDP capture failure while the narrow override is set.
            raise RuntimeError("screenshot failed during narrow override")
        # Minimal valid PNG header so write_bytes() succeeds.
        import base64 as _b64

        return _b64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
            "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        )

    def set_device_metrics_override(self, *, width: int, height: int) -> None:
        self._ops.append(f"set:{width}x{height}")
        self._override_active = True

    def clear_device_metrics_override(self) -> None:
        self._ops.append("clear")
        self._override_active = False

    def close(self) -> None:
        pass


def test_walk_applies_and_clears_device_metrics_for_narrow_screen(
    tmp_path, monkeypatch
):
    """walk() must call set_device_metrics_override before capturing the
    narrow screen and clear_device_metrics_override after it -- in that
    order -- so the screenshot is taken at 840x625 and the real viewport
    is restored for every subsequent capture.
    """
    monkeypatch.setattr(shoot.time, "sleep", lambda _: None)
    cdp = _TrackedCDP()
    shots, skipped, eve_shown = shoot.walk(cdp, tmp_path, settle_ms=0)

    assert eve_shown is True
    assert not skipped

    # The narrow screen must have been shot successfully.
    narrow = next((s for s in shots if s["key"] == "settings-previews-narrow"), None)
    assert narrow is not None, "narrow screen not found in shots"
    assert narrow["error"] is None, f"narrow screen failed: {narrow['error']}"

    # Verify exact operation ordering: set -> screenshot -> clear.
    # The ops list records set:WxH and clear; screenshots do not write to ops
    # so we verify set comes before clear and that both are present.
    assert "set:840x625" in cdp._ops, (
        "walk() must call set_device_metrics_override(width=840, height=625) "
        "before the narrow screenshot"
    )
    assert "clear" in cdp._ops, (
        "walk() must call clear_device_metrics_override() after the narrow screenshot"
    )
    set_idx = cdp._ops.index("set:840x625")
    clear_idx = cdp._ops.index("clear")
    assert set_idx < clear_idx, (
        "set_device_metrics_override must be called before clear_device_metrics_override"
    )
    # No stray set/clear for non-narrow screens.
    assert cdp._ops.count("clear") == 1, "clear must only be called once (for narrow)"
    assert cdp._ops.count("set:840x625") == 1, (
        "set must only be called once (for narrow)"
    )


def test_walk_clears_device_metrics_even_when_narrow_screenshot_fails(
    tmp_path, monkeypatch
):
    """clear_device_metrics_override() must be called even if the narrow
    screenshot raises an exception (finally-safe ordering).

    A viewport stuck at 840x625 would distort every subsequent capture
    in the same session, which is silently wrong and harder to diagnose
    than a single recorded failure.
    """
    monkeypatch.setattr(shoot.time, "sleep", lambda _: None)
    cdp = _TrackedCDP(fail_narrow_screenshot=True)
    shots, _skipped, _eve_shown = shoot.walk(cdp, tmp_path, settle_ms=0)

    # The narrow screen should be recorded as failed, not silently absent.
    narrow = next((s for s in shots if s["key"] == "settings-previews-narrow"), None)
    assert narrow is not None, "narrow screen must appear in shots even on failure"
    assert narrow["error"] is not None, (
        "narrow screen must record the error, not succeed silently"
    )

    # Clearing must still have happened despite the screenshot failure.
    assert "clear" in cdp._ops, (
        "clear_device_metrics_override() must run in a finally block "
        "even when the narrow screenshot raises an exception"
    )
    # The override must not still be active after walk() returns.
    assert not cdp._override_active, (
        "device metrics override must be inactive after walk() returns"
    )


# ---------------------------------------------------------------------------
# Round 1 fix: fixture extractor, semantic selectors, no-write guarantees
# ---------------------------------------------------------------------------


def test_dev_preview_fixture_extractor_exists_and_is_callable():
    """shoot_screens.py must expose a load_dev_preview_fixture() function
    that reads and parses DEV_PREVIEW_HOTKEYS_FIXTURE from dev.js source.
    """
    assert hasattr(shoot, "load_dev_preview_fixture"), (
        "shoot_screens.py must define load_dev_preview_fixture() -- "
        "it is needed by both the group-stage setup scripts and the tests "
        "that verify the screenshot payload matches the fixture"
    )
    assert callable(shoot.load_dev_preview_fixture)


def test_dev_preview_fixture_extractor_returns_a_dict_with_hotkeys():
    """load_dev_preview_fixture() must return a dict parsed from the named
    literal in dev.js, containing at least the 'hotkeys' key with 'groups'.
    """
    fixture = shoot.load_dev_preview_fixture(str(ROOT))
    assert isinstance(fixture, dict), "load_dev_preview_fixture must return a dict"
    assert "hotkeys" in fixture, (
        "fixture must have a 'hotkeys' key matching the get_preview_hotkey_state shape"
    )
    assert "groups" in fixture["hotkeys"], "fixture.hotkeys must have a 'groups' list"
    assert len(fixture["hotkeys"]["groups"]) >= 1, (
        "fixture must have at least one group"
    )
    assert len(fixture["roster"]) >= 10
    assert any(len(name) >= 30 for name in fixture["roster"])
    assert set(fixture["roster"]) - set(fixture["characters"])


def test_groups_stage_injects_fixture_via_onPreviewHotkeys():
    """The settings-previews-groups setup script must inject the fixture
    by calling window.onPreviewHotkeys(payload), not by calling a write
    API like create_preview_cycle_group or set_preview_character_group.

    Calling write APIs in a screenshot script would mutate user data; the
    correct approach is the read path onPreviewHotkeys.
    """
    groups_screen = next(
        s for s in shoot.SCREENS if s.key == "settings-previews-groups"
    )
    script = shoot.screen_setup_script(groups_screen)
    assert script is not None
    assert "onPreviewHotkeys" in script, (
        "groups stage setup must inject fixture via window.onPreviewHotkeys, "
        "not by calling write APIs"
    )


def test_narrow_stage_injects_fixture_via_onPreviewHotkeys():
    """The settings-previews-narrow setup script must also inject the fixture
    via window.onPreviewHotkeys so the page has deterministic group state
    regardless of what the real user's settings contain.
    """
    narrow_screen = next(
        s for s in shoot.SCREENS if s.key == "settings-previews-narrow"
    )
    script = shoot.screen_setup_script(narrow_screen)
    assert script is not None
    assert "onPreviewHotkeys" in script, (
        "narrow stage setup must inject fixture via window.onPreviewHotkeys"
    )


def test_groups_stage_scrolls_to_preview_group_manager():
    """The groups stage must scroll to .preview-group-manager (the Manage
    groups disclosure), NOT scroll to pane.scrollHeight (absolute bottom).

    Scrolling to absolute bottom shows the last group row, but the manager
    element is rendered between the group keybind rows and the character rows,
    so it may not be at the bottom. The semantic selector guarantees the
    disclosure is in frame.
    """
    groups_screen = next(
        s for s in shoot.SCREENS if s.key == "settings-previews-groups"
    )
    script = shoot.screen_setup_script(groups_screen)
    assert script is not None
    assert "preview-group-manager" in script, (
        "groups stage must scroll to .preview-group-manager to frame the "
        "Manage groups disclosure -- scrolling to pane.scrollHeight shows "
        "the bottom of the page, which may not include the manager"
    )
    # Must NOT just scroll to pane.scrollHeight (arbitrary bottom position)
    # without also targeting the manager element
    if "scrollHeight" in script and "preview-group-manager" not in script:
        raise AssertionError(
            "groups stage scrolls to scrollHeight without targeting "
            ".preview-group-manager -- this is the bug being fixed"
        )


def test_narrow_stage_frames_roster_heading_at_scrollport_start():
    """The viewport-floor stage starts at the collapsed roster heading."""
    narrow_screen = next(
        s for s in shoot.SCREENS if s.key == "settings-previews-narrow"
    )
    script = shoot.screen_setup_script(narrow_screen)
    assert script is not None
    selectors = _query_selector_arguments(script)
    assert selectors.count("#preview-roster-heading") == 1, selectors
    assert "heading.scrollIntoView({block: 'start', behavior: 'instant'})" in script


def test_detail_stage_scrolls_opened_character_detail_into_view():
    """Opening after the bottom stage must deterministically reframe detail."""
    detail_screen = next(
        s for s in shoot.SCREENS if s.key == "settings-previews-detail"
    )
    script = shoot.screen_setup_script(detail_screen)
    assert script is not None
    assert "configure.getAttribute('aria-controls')" in script
    assert "document.getElementById(detailId)" in script
    assert "detail.scrollIntoView({block: 'center', behavior: 'instant'})" in script
    assert script.index("configure.click()") < script.index("detail.scrollIntoView")


def test_fixture_backed_preview_staging_does_not_invoke_write_methods():
    """Fixture-backed setup must remain page-only and read-only.

    Detail and Copy now join groups and floor captures. Configure is local and
    Copy only opens the page-owned chooser; none of those stages may call a
    bridge writer against the user's settings.
    """
    write_methods = {
        "create_preview_cycle_group",
        "rename_preview_cycle_group",
        "delete_preview_cycle_group",
        "set_preview_cycle_group_bind",
        "set_preview_character_group",
        "set_preview_binds",
        "set_preview_size",
        "copy_preview_layout",
        "set_preview_excluded",
        "set_preview_locked",
        "set_never_minimize",
    }
    for key in (
        "settings-previews-detail",
        "settings-previews-copy",
        "settings-previews-groups",
        "settings-previews-narrow",
    ):
        screen = next(s for s in shoot.SCREENS if s.key == key)
        script = shoot.screen_setup_script(screen)
        assert script is not None
        for method in write_methods:
            assert method not in script, (
                f"{key} setup script must not call {method!r} -- "
                "screenshot scripts are read-only and must not mutate user settings"
            )


def test_fixture_extractor_raises_clearly_on_missing_marker():
    """load_dev_preview_fixture must raise a clear ValueError (not a cryptic
    index error) when DEV_PREVIEW_HOTKEYS_FIXTURE is absent from the source.
    """
    import inspect

    src = inspect.getsource(shoot.load_dev_preview_fixture)
    # The function must have bounded error handling, not a bare index() that
    # raises a cryptic ValueError: substring not found.
    assert "ValueError" in src or "raise" in src, (
        "load_dev_preview_fixture must raise a clear error when the marker "
        "is not found, rather than letting a bare index() raise a cryptic message"
    )


# ---------------------------------------------------------------------------
# Round 2: ordering proof and deterministic selector tests
# ---------------------------------------------------------------------------


class _OrderedCDP(_TrackedCDP):
    """Extended TrackedCDP that also records evaluate calls and screenshot
    invocations, enabling ordering proofs over the full CDP call sequence.

    evaluate() records:
      - "eval:setup"  when the expression contains "onPreviewHotkeys"
        (the fixture-injection + scroll setup script for stages)
      - "eval:screenshot_wait" for the settle-time evaluates (route/section)

    screenshot() records "screenshot" unconditionally so the ordering test
    can verify: set:840x625 -> eval:setup -> screenshot -> clear.
    """

    def evaluate(self, expression: str):
        if "onPreviewHotkeys" in expression:
            self._ops.append("eval:setup")
        return super().evaluate(expression)

    def screenshot(self) -> bytes:
        self._ops.append("screenshot")
        return super().screenshot()


def test_walk_applies_device_metrics_before_narrow_setup_script(tmp_path, monkeypatch):
    """walk() MUST apply set_device_metrics_override before evaluating the
    narrow stage's setup script (which injects the fixture and scrolls).

    The required order is:
      set:840x625 -> eval:setup (onPreviewHotkeys + scroll) -> screenshot -> clear

    The current bug: walk() evaluates the setup script first, THEN sets
    device metrics -- so the fixture injection and scroll happen at the
    previous viewport size, not at 840x625.

    This test records the exact CDP call sequence and asserts the ordering
    constraint is satisfied.
    """
    monkeypatch.setattr(shoot.time, "sleep", lambda _: None)
    cdp = _OrderedCDP()
    shots, _skipped, _eve_shown = shoot.walk(cdp, tmp_path, settle_ms=0)

    narrow = next((s for s in shots if s["key"] == "settings-previews-narrow"), None)
    assert narrow is not None and narrow["error"] is None, (
        f"narrow screen must succeed: {narrow}"
    )

    # Locate the index of each required operation for the narrow stage.
    # Because groups stage also has eval:setup before narrow, we want the
    # LAST set:840x625 (the narrow override) and the eval:setup that follows it.
    try:
        set_idx = max(i for i, op in enumerate(cdp._ops) if op == "set:840x625")
    except ValueError:
        raise AssertionError(
            "set:840x625 not found in ops -- walk() never called set_device_metrics_override"
        )

    # The eval:setup for the narrow stage must come AFTER the set:840x625.
    post_set_ops = cdp._ops[set_idx + 1 :]
    assert "eval:setup" in post_set_ops, (
        f"walk() runs the narrow setup script BEFORE applying set_device_metrics_override.\n"
        f"Full ops: {cdp._ops}\n"
        "Required order: set:840x625 -> eval:setup -> screenshot -> clear"
    )

    # screenshot must come after eval:setup (post-set)
    post_set_setup_idx = next(
        i for i, op in enumerate(post_set_ops) if op == "eval:setup"
    )
    post_setup_ops = post_set_ops[post_set_setup_idx + 1 :]
    assert "screenshot" in post_setup_ops, (
        "screenshot must occur after eval:setup (narrow setup script)"
    )

    # clear must come after screenshot
    screenshot_idx = next(
        i for i, op in enumerate(post_setup_ops) if op == "screenshot"
    )
    post_screenshot_ops = post_setup_ops[screenshot_idx + 1 :]
    assert "clear" in post_screenshot_ops, (
        "clear must come after screenshot in the narrow stage"
    )


def test_walk_narrow_setup_runs_inside_device_metrics_override_on_failure(
    tmp_path, monkeypatch
):
    """Even when the narrow screenshot fails the ordering must hold:
    set:840x625 -> eval:setup -> (screenshot raises) -> clear.

    A fail-then-clear order that skips the setup would mean the page
    never received the fixture injection, making the cleared viewport the
    only visible effect.
    """
    monkeypatch.setattr(shoot.time, "sleep", lambda _: None)
    cdp = _OrderedCDP(fail_narrow_screenshot=True)
    shots, _skipped, _eve_shown = shoot.walk(cdp, tmp_path, settle_ms=0)

    narrow = next((s for s in shots if s["key"] == "settings-previews-narrow"), None)
    assert narrow is not None and narrow["error"] is not None, (
        "narrow screen must be recorded as failed"
    )

    try:
        set_idx = max(i for i, op in enumerate(cdp._ops) if op == "set:840x625")
    except ValueError:
        raise AssertionError("set:840x625 not found in ops")

    post_set_ops = cdp._ops[set_idx + 1 :]
    assert "eval:setup" in post_set_ops, (
        f"eval:setup must still occur after set:840x625 even on failure.\n"
        f"Full ops: {cdp._ops}"
    )
    assert "clear" in post_set_ops, (
        "clear must run even when the narrow screenshot fails (finally-safe)"
    )


def test_narrow_stage_closes_details_and_returns_the_roster_heading_to_top():
    """The floor shot must not inherit the preceding detail's expanded state.

    It deliberately frames the roster heading at the Settings scrollport top,
    so the 840x625 capture shows the collapsed table geometry rather than a
    stale disclosure or an arbitrary offset.
    """
    narrow_screen = next(
        s for s in shoot.SCREENS if s.key == "settings-previews-narrow"
    )
    script = shoot.screen_setup_script(narrow_screen)
    assert script is not None
    assert '[data-preview-configure][aria-expanded="true"]' in script
    assert "#preview-roster-heading" in script
    assert script.index("aria-expanded") < script.index("#preview-roster-heading")


def test_narrow_stage_targets_roster_heading_deterministically():
    """The floor capture must use the actual roster-heading id, not a row.

    A detail can be left open by a preceding shot; framing a character after
    closing it makes the capture depend on roster order. The heading names the
    stable collapsed-table starting point instead.
    """
    narrow_screen = next(
        s for s in shoot.SCREENS if s.key == "settings-previews-narrow"
    )
    script = shoot.screen_setup_script(narrow_screen)
    assert script is not None
    selectors = _query_selector_arguments(script)
    assert selectors.count("#preview-roster-heading") == 1, selectors


def test_fixture_backed_preview_setup_scripts_embed_exact_fixture_payload():
    """Every fixture-backed preview setup script embeds the exact JSON serialization of
    load_dev_preview_fixture() -- no extra fields, no missing fields.

    The assertion is: json.loads(embedded_payload) == load_dev_preview_fixture().

    If the embedded payload diverges from what load_dev_preview_fixture()
    returns (e.g. the fixture changed after the script was generated), the
    page receives stale data and the screenshots no longer match the tests.
    """
    import json as _json

    fixture = shoot.load_dev_preview_fixture()

    for key in (
        "settings-previews-detail",
        "settings-previews-copy",
        "settings-previews-groups",
        "settings-previews-narrow",
    ):
        screen = next(s for s in shoot.SCREENS if s.key == key)
        script = shoot.screen_setup_script(screen)
        assert script is not None

        # Extract the embedded JSON by finding var payload = <JSON>;
        match = re.search(r"var payload = (\{.*?\});", script, re.DOTALL)
        assert match, (
            f"{key} setup script must embed the fixture as "
            "'var payload = <JSON>;' -- pattern not found in script"
        )
        embedded_json = match.group(1)
        try:
            embedded = _json.loads(embedded_json)
        except _json.JSONDecodeError as exc:
            raise AssertionError(
                f"{key} setup script embeds invalid JSON: {exc}\n"
                f"Embedded text: {embedded_json[:200]}"
            ) from exc

        assert embedded == fixture, (
            f"{key} setup script embeds a different payload than load_dev_preview_fixture().\n"
            f"Expected keys: {sorted(fixture.keys())}\n"
            f"Got keys:      {sorted(embedded.keys())}"
        )


# ---------------------------------------------------------------------------
# Round 3 fix: exact selector contracts, exact CDP ordering proof
# ---------------------------------------------------------------------------


def test_groups_stage_uses_preview_group_manager_selector():
    """The settings-previews-groups setup script must scroll to
    '.preview-group-manager'  — the exact class selector for the Manage
    Groups disclosure element — not to a generic pane or a first-match.

    A generic fallback (e.g. scrollTop = pane.scrollHeight) may overshoot
    or miss entirely depending on how much content precedes the manager
    at render time, defeating the purpose of the stage.

    The script may fall back to pane.scrollHeight but the FIRST choice must
    be document.querySelector('.preview-group-manager').
    """
    groups_screen = next(
        s for s in shoot.SCREENS if s.key == "settings-previews-groups"
    )
    script = shoot.screen_setup_script(groups_screen)
    assert script is not None
    # Must explicitly reference the exact semantic selector
    assert ".preview-group-manager" in script, (
        "settings-previews-groups setup script must use "
        "document.querySelector('.preview-group-manager') as the primary scroll target -- "
        "a generic scroll-to-bottom may miss or overshoot the manager element"
    )
    # Parse direct calls so a selector elsewhere in the expression cannot pass.
    selectors = _query_selector_arguments(script)
    assert selectors.count(".preview-group-manager") == 1, (
        "settings-previews-groups must pass '.preview-group-manager' exactly once "
        f"to document.querySelector; got {selectors!r}"
    )


def test_narrow_stage_uses_the_exact_roster_heading_selector():
    """The floor script must use the real heading selector as its scroll target."""
    narrow_screen = next(
        s for s in shoot.SCREENS if s.key == "settings-previews-narrow"
    )
    script = shoot.screen_setup_script(narrow_screen)
    assert script is not None
    selectors = _query_selector_arguments(script)
    assert selectors.count("#preview-roster-heading") == 1, selectors


def test_narrow_stage_does_not_target_a_character_control():
    """The floor stage frames the roster heading, never a first character control."""
    narrow_screen = next(
        s for s in shoot.SCREENS if s.key == "settings-previews-narrow"
    )
    script = shoot.screen_setup_script(narrow_screen)
    assert script is not None
    # A bare first-match character selector would capture an arbitrary row
    # rather than the stable roster heading.
    bare_first_match = re.search(
        r"querySelector\s*\(\s*['\"]\s*\.preview-group-select\s*['\"]\s*\)",
        script,
    )
    assert bare_first_match is None, (
        "narrow stage setup script must not target a character control; "
        "it must frame #preview-roster-heading."
    )


def test_fixture_stages_fail_closed_when_required_controls_are_missing():
    """Fixture stages must never capture live state or an incomplete target."""
    scripts = {
        key: shoot.screen_setup_script(next(s for s in shoot.SCREENS if s.key == key))
        for key in (
            "settings-previews-detail",
            "settings-previews-copy",
            "settings-previews-groups",
            "settings-previews-narrow",
        )
    }
    for key, script in scripts.items():
        assert script is not None
        assert "typeof window.onPreviewHotkeys !== 'function'" in script, key
        assert "throw new Error" in script, key
    for key in ("settings-previews-detail", "settings-previews-copy"):
        assert "Configure control" in scripts[key]
        assert "detail" in scripts[key]
    assert "Copy control" in scripts["settings-previews-copy"]
    assert "group manager" in scripts["settings-previews-groups"]
    assert "roster heading" in scripts["settings-previews-narrow"]


def test_copy_stage_fails_closed_unless_the_copy_chooser_opens():
    """Clicking Copy is setup, not proof that the picker was staged."""
    copy = shoot.screen_setup_script(
        next(s for s in shoot.SCREENS if s.key == "settings-previews-copy")
    )
    assert copy is not None
    assert copy.index("copy.click()") < copy.index("overlay.hidden")
    assert "Copy chooser did not open" in copy
    assert "dialog.classList.contains('choice')" in copy
    assert "throw new Error" in copy


class _FailOnceCDP(_OrderedCDP):
    """Record setup evaluation and every screenshot attempt before failure."""

    def screenshot(self) -> bytes:
        self._ops.append("screenshot_attempt")
        return _TrackedCDP.screenshot(self)


def test_walk_failure_path_records_set_eval_attempt_clear_in_order(
    tmp_path, monkeypatch
):
    """When the narrow screenshot raises the CDP call sequence must prove:
        set:840x625  →  eval:setup  →  screenshot_attempt  →  clear

    Recording the attempt before raising is the only way to verify the
    attempt happened (once it raises there is no return value to inspect).
    The test uses _FailOnceCDP which appends 'screenshot_attempt' before
    raising so we can inspect the ordered ops list.

    This test is stronger than test_walk_clears_device_metrics_even_when_narrow_screenshot_fails
    because it asserts the entire ordered sequence, not just that set and clear
    both appeared somewhere.
    """
    monkeypatch.setattr(shoot.time, "sleep", lambda _: None)
    cdp = _FailOnceCDP(fail_narrow_screenshot=True)
    shots, _skipped, _eve_shown = shoot.walk(cdp, tmp_path, settle_ms=0)

    narrow = next((s for s in shots if s["key"] == "settings-previews-narrow"), None)
    assert narrow is not None and narrow["error"] is not None, (
        "narrow screen must be recorded as failed"
    )

    ops = cdp._ops
    set_idx = max(i for i, op in enumerate(ops) if op == "set:840x625")
    assert ops[set_idx : set_idx + 4] == [
        "set:840x625",
        "eval:setup",
        "screenshot_attempt",
        "clear",
    ], f"narrow failure sequence was incomplete or out of order: {ops!r}"
    assert ops[set_idx + 3] == "clear"


def test_walk_failure_path_records_attempt_before_clear_not_only_clear(
    tmp_path, monkeypatch
):
    """A version of the failure-path test that specifically catches an
    implementation that skips the screenshot attempt and goes straight to clear.

    If walk() catches the error before attempting the screenshot (e.g. by
    checking a flag) and jumps to the finally block, clear would appear in
    the ops but screenshot_attempt would not.  This test catches that case.
    """
    monkeypatch.setattr(shoot.time, "sleep", lambda _: None)
    cdp = _FailOnceCDP(fail_narrow_screenshot=True)
    shoot.walk(cdp, tmp_path, settle_ms=0)

    ops = cdp._ops
    assert "screenshot_attempt" in ops, (
        "screenshot_attempt must appear in ops -- walk() must ATTEMPT the screenshot "
        "before reaching the finally/except block that clears the override.\n"
        f"ops: {ops!r}"
    )
    assert "clear" in ops, "clear must appear in ops"
    # Find the narrow override (last set:840x625) and verify the attempt/clear ordering
    # within that segment.  _FailOnceCDP records ALL screenshots so we anchor to
    # the narrow override's set op.
    try:
        narrow_set_idx = max(i for i, op in enumerate(ops) if op == "set:840x625")
    except ValueError:
        raise AssertionError(f"set:840x625 not found in ops: {ops!r}")
    post_set = ops[narrow_set_idx + 1 :]
    assert "screenshot_attempt" in post_set, (
        f"screenshot_attempt must appear after the narrow set:840x625, got ops: {ops!r}\n"
        "walk() must attempt the screenshot inside the device-metrics override block."
    )
    attempt_idx = next(i for i, op in enumerate(post_set) if op == "screenshot_attempt")
    post_attempt_ops = post_set[attempt_idx + 1 :]
    assert "clear" in post_attempt_ops, (
        f"clear must appear AFTER the screenshot_attempt in the narrow block, "
        f"post-set ops: {post_set!r}\n"
        "Ensure the screenshot call is inside the try block, not after the finally."
    )
