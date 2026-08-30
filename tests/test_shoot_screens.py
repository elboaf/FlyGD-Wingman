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
    assert len(to_shoot) == 10
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
    assert len(skipped) == 6


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
        "settings-alerts",
        "settings-bookmarks",
        "settings-previews",
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
