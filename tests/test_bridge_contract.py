"""The Python/JavaScript bridge contract, checked lexically.

This repo has no JavaScript test harness
(docs/history/webview-replatform-design.md:545), so nothing executes web/*.js and nothing would notice a push whose name the
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

- Only `self._push("literal", ...)` calls in ui/api.py and
  `self._push_cb("literal", ...)` calls in eveskills/controller.py are
  found. A pushed name built at runtime is invisible here.
- The call sweep sees `WM.send('literal'`, the bars' bare `send('literal'`,
  and the two wrappers that take a method name as an argument
  (`writeFlag(box, 'literal'` in alerts.js, `chooseRoot('literal'` in
  evesettings.js). A method name reaching WM.send through any OTHER
  variable is invisible here.
- Only the `WM.HANDLERS = [...]` array literal is parsed. A name appended
  elsewhere at runtime is invisible here.
- A handler in the allowlist that nothing registers is not an error: it may
  be pushed from somewhere other than ui/api.py.
"""

import ast
import inspect
import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "wingman" / "web"
API = Path(__file__).resolve().parent.parent / "wingman" / "ui" / "api.py"


def allowlist() -> list:
    """The names in web/app.js's WM.HANDLERS array literal."""
    source = (WEB / "app.js").read_text(encoding="utf-8")
    match = re.search(r"WM\.HANDLERS\s*=\s*\[(.*?)\]", source, re.DOTALL)
    assert match, "WM.HANDLERS array literal not found in web/app.js"
    return re.findall(r"'([^']+)'", match.group(1))


SKILLS_CONTROLLER = (
    Path(__file__).resolve().parent.parent / "wingman" / "eveskills" / "controller.py"
)


def pushed_names() -> list:
    """Every handler name pushed as a string literal, from ui/api.py's
    `_push("name", ...)` and eveskills/controller.py's `_push_cb("name", ...)`.

    The controller is the one module outside api.py that names a handler:
    it is handed `_push_skills` as a callback and pushes `onSkills` and
    `onSkillsProgress` through it, so api.py never spells those two.
    Before this sweep read the controller, renaming either there would
    have been a silent no-op on the page -- `window.<name> && ...` -- with
    the allowlist and skills.js still agreeing with each other.
    """
    names = set()
    for path in (API, SKILLS_CONTROLLER):
        source = path.read_text(encoding="utf-8")
        names.update(re.findall(r"_push(?:_cb)?\(\s*\"([A-Za-z0-9_]+)\"", source))
    return sorted(names)


def api_method_body(name: str) -> str:
    source = API.read_text(encoding="utf-8")
    parts = source.split(f"def {name}(", 1)
    if len(parts) != 2:
        return ""
    return parts[1].split("\n    def ", 1)[0]


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
        "registering it would fail to load entirely."
    )


@pytest.mark.parametrize("name", sorted(registered_names()))
def test_every_registered_handler_is_in_the_allowlist(name):
    """The failure mode that broke the EVE Settings route: a page calling
    WM.handle() for a name app.js does not know."""
    where = ", ".join(registered_names()[name])
    assert name in allowlist(), (
        f"{where} registers {name!r} via WM.handle(), which is absent from "
        "WM.HANDLERS in web/app.js. That throws at registration and every "
        "handler declared below it in the same file is never registered."
    )


def test_crop_state_publisher_has_a_literal_allowlisted_handler():
    assert "onPreviewCrops" in pushed_names()
    assert "onPreviewCrops" in allowlist()


@pytest.mark.parametrize(
    "method, parameters",
    [
        ("select_preview_crop", ["self", "name"]),
        ("set_preview_crop_enabled", ["self", "name", "enabled"]),
        ("remove_preview_crop", ["self", "name"]),
        ("get_preview_crop_state", ["self"]),
    ],
)
def test_crop_bridge_accepts_only_semantic_arguments(method, parameters):
    from wingman.ui.api import Api

    assert list(inspect.signature(getattr(Api, method)).parameters) == parameters


def test_the_eve_settings_route_registers_all_three_of_its_pushes():
    """Named explicitly rather than left to the sweep above, because this
    is the route the sweep was written for and a regression here is
    invisible to every other test."""
    registered = registered_names()
    for name in ("onEveSettingsNames", "onEveSettingsRunning", "onEveSettingsDone"):
        assert name in allowlist(), name
        assert "evesettings.js" in registered.get(name, []), name


def test_selective_copy_reuses_the_existing_bridge_contract():
    """Task 4 adds an argument, not an endpoint, push, or handler owner."""
    from wingman.ui.api import Api

    assert callable(getattr(Api, "eve_settings_copy", None))
    parameters = inspect.signature(Api.eve_settings_copy).parameters
    # Exact parameter list asserted as the façade contract for the copy API.
    assert list(inspect.signature(Api.eve_settings_copy).parameters) == [
        "self",
        "source",
        "targets",
        "groups",
    ]
    assert "groups" in parameters
    assert parameters["groups"].default is None
    registered = registered_names()
    assert set(registered) & {
        "onEveSettingsNames",
        "onEveSettingsRunning",
        "onEveSettingsDone",
    } == {"onEveSettingsNames", "onEveSettingsRunning", "onEveSettingsDone"}
    assert all(
        set(registered[name]) == {"evesettings.js"}
        for name in ("onEveSettingsNames", "onEveSettingsRunning", "onEveSettingsDone")
    )


def test_profile_copy_bridge_shape():
    """The page sends intent -- an expected source token, a mode, and one
    destination -- never filesystem authority."""
    from wingman.ui.api import Api

    params = inspect.signature(Api.eve_settings_copy_profile).parameters
    assert list(params) == ["self", "expected_source", "mode", "destination"]


def test_profile_copy_reuses_the_single_profiles_completion_push():
    """Whole-profile copy extends the onEveSettingsDone payload rather than
    adding a second completion channel: two competing handlers would let a
    page close its disclosure on one event and refresh on the other."""
    assert [name for name in pushed_names() if name.startswith("onEveSettings")] == [
        "onEveSettingsDone",
        "onEveSettingsNames",
        "onEveSettingsRunning",
    ]
    assert set(registered_names().get("onEveSettingsDone", [])) == {"evesettings.js"}


def test_profiles_controller_factory_binds_named_semantic_ports():
    source = API.read_text(encoding="utf-8")

    assert "def _build_profiles_controller(self)" in source
    assert "ProfilesController(" in source
    assert "ProfilesPorts(" in source
    assert "publish_running=self._publish_eve_settings_running" in source
    assert "publish_names=self._publish_eve_settings_names" in source
    assert "publish_done=self._publish_eve_settings_done" in source
    assert "alert=self._profiles_alert" in source
    assert "status=self._profiles_status" in source
    assert "confirm=self._profiles_confirm" in source
    assert "choose_root=self._choose_eve_settings_root" in source
    assert "choose_setup_input=self._choose_setup_input" in source
    assert "choose_setup_output=self._choose_setup_output" in source
    assert "spawn=self._spawn_profiles_worker" in source
    assert "advisory_client_running=self._profiles_advisory_client_running" in source
    assert "strict_client_running=self._profiles_strict_client_running" in source
    assert "profile_copy_refusal=self._profiles_copy_refusal" in source
    assert "backup_root=paths.eve_settings_backup_dir" in source
    assert "update_settings=self._update_profiles_settings" in source
    assert "format_copy_confirm=copy_mod.format_eve_copy_confirm" in source
    assert "format_copy_done=copy_mod.format_eve_copy_done" in source
    assert "self._profiles = self._build_profiles_controller()" in source


def test_profiles_semantic_push_adapters_stay_literal_and_private_to_api():
    assert 'self._push("onEveSettingsRunning", payload)' in api_method_body(
        "_publish_eve_settings_running"
    )
    assert 'self._push("onEveSettingsNames", payload)' in api_method_body(
        "_publish_eve_settings_names"
    )
    assert 'self._push("onEveSettingsDone", payload)' in api_method_body(
        "_publish_eve_settings_done"
    )


def test_profiles_facade_methods_delegate_lexically_to_private_controller_methods():
    source = API.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert "getattr(self._profiles" not in source
    assert "__getattr__(self" not in source
    expected = {
        "eve_settings_state": ("state", []),
        "eve_settings_setup_limits": ("setup_limits", []),
        "eve_settings_setup_catalog": ("setup_catalog", []),
        "eve_settings_setup_catalog_entry": (
            "setup_catalog_entry",
            ["preset_id", "revision", "sha256"],
        ),
        "eve_settings_setup_context": ("setup_context", ["profile"]),
        "eve_settings_setup_export": (
            "setup_export",
            ["expected_profile", "account_path", "character_path"],
        ),
        "eve_settings_setup_read_file": ("setup_read_file", []),
        "eve_settings_setup_save_file": ("setup_save_file", ["text"]),
        "eve_settings_setup_review": (
            "setup_review",
            [
                "text",
                "expected_profile",
                "account_path",
                "character_path",
                "destination_name",
                "keep_ship_labels",
            ],
        ),
        "eve_settings_setup_discard": ("setup_discard", ["review_id"]),
        "eve_settings_setup_create": ("setup_create", ["review_id", "request_id"]),
        "eve_settings_pick_root": ("pick_root", []),
        "eve_settings_detect_root": ("detect_root", []),
        "eve_settings_select": ("select", ["server", "profile"]),
        "eve_settings_set_account_name": (
            "set_account_name",
            ["account_id", "name"],
        ),
        "eve_settings_set_account_characters": (
            "set_account_characters",
            ["account_id", "character_ids"],
        ),
        "eve_settings_identification_start": ("identification_start", []),
        "eve_settings_identification_check": ("identification_check", []),
        "eve_settings_identification_confirm": (
            "identification_confirm",
            ["account_id", "character_id", "account_name"],
        ),
        "eve_settings_identification_cancel": ("identification_cancel", []),
        "eve_settings_resolve_names": ("resolve_names", []),
        "eve_settings_set_auto_keep": ("set_auto_keep", ["value"]),
        "eve_settings_copy": ("copy", ["source", "targets", "groups"]),
        "eve_settings_copy_profile": (
            "copy_profile",
            ["expected_source", "mode", "destination"],
        ),
        "eve_settings_backup": ("backup", ["path", "kind"]),
        "eve_settings_restore": ("restore", ["archive"]),
        "eve_settings_delete_backup": ("delete_backup", ["archive"]),
        "eve_settings_formations": ("formations", ["path"]),
        "eve_settings_export_formations": ("export_formations", ["items"]),
        "eve_settings_parse_formations": (
            "parse_formations",
            ["text", "existing_names"],
        ),
        "eve_settings_validate_formation_import": (
            "validate_formation_import",
            ["items", "existing_names"],
        ),
        "eve_settings_save_formations": (
            "save_formations",
            ["path", "formations", "expected_content_revision", "request_id"],
        ),
    }
    methods = {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    for method_name, (delegate_name, arg_names) in expected.items():
        method = methods[method_name]
        returns = [node for node in method.body if isinstance(node, ast.Return)]
        assert returns, method_name
        call = returns[-1].value
        assert isinstance(call, ast.Call), method_name
        assert isinstance(call.func, ast.Attribute), method_name
        assert call.func.attr == delegate_name, method_name
        owner = call.func.value
        assert isinstance(owner, ast.Attribute), method_name
        assert owner.attr == "_profiles", method_name
        assert isinstance(owner.value, ast.Name) and owner.value.id == "self", (
            method_name
        )
        assert [ast.unparse(arg) for arg in call.args] == arg_names, method_name
        assert call.keywords == [], method_name


@pytest.mark.parametrize(
    "facade,delegate,args",
    [
        ("get_custom_alert_state", "state", []),
        ("add_custom_alert", "add", []),
        ("edit_custom_alert", "edit", ["rule_id", "draft"]),
        ("set_custom_alert_enabled", "set_enabled", ["rule_id", "enabled"]),
        ("remove_custom_alert", "remove", ["rule_id"]),
        ("test_custom_alert", "test", ["rule_id", "draft"]),
    ],
)
def test_custom_alert_facades_are_exact_single_line_delegates(facade, delegate, args):
    from wingman.ui.api import Api

    assert list(inspect.signature(getattr(Api, facade)).parameters) == ["self", *args]
    tree = ast.parse(API.read_text(encoding="utf-8"))
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == facade
    )
    assert len(method.body) == 1
    assert isinstance(method.body[0], ast.Return)
    assert (
        ast.unparse(method.body[0])
        == f"return self._alerts_controller.{delegate}({', '.join(args)})"
    )


@pytest.mark.parametrize(
    "facade,delegate,args",
    [
        ("wanderer_state", "state", []),
        ("set_wanderer_enabled", "set_enabled", ["enabled"]),
        ("set_wanderer_url", "set_url", ["base"]),
        ("set_wanderer_map", "set_map", ["map"]),
        ("replace_wanderer_token", "replace_token", ["token", "base", "map"]),
        ("test_wanderer_connection", "test_connection", []),
        ("remove_wanderer_connection", "remove_connection", []),
    ],
)
def test_wanderer_facades_are_exact_single_line_delegates(facade, delegate, args):
    from wingman.ui.api import Api

    assert list(inspect.signature(getattr(Api, facade)).parameters) == ["self", *args]
    tree = ast.parse(API.read_text(encoding="utf-8"))
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == facade
    )
    assert len(method.body) == 1
    assert (
        ast.unparse(method.body[0])
        == f"return self._wanderer.{delegate}({', '.join(args)})"
    )


def test_wanderer_literal_push_and_controller_boundary():
    assert 'self._push("onWandererState", payload)' in api_method_body(
        "_publish_wanderer_state"
    )
    assert "onWandererState" in allowlist()
    tree = ast.parse(
        (API.parent.parent / "wanderer/controller.py").read_text(encoding="utf-8")
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert "ui" not in (node.module or "").split(".")
        elif isinstance(node, ast.Import):
            assert not any("ui" in alias.name.split(".") for alias in node.names)
        elif isinstance(node, ast.Attribute):
            assert node.attr not in {"_push", "evaluate_js", "_window"}


def test_custom_alerts_have_no_push_channel_or_ui_import():
    assert not any("alert" in name.lower() for name in allowlist() + pushed_names())
    source = (API.parent.parent / "alerts" / "controller.py").read_text(
        encoding="utf-8"
    )
    assert "WM.handle(" not in (WEB / "alerts.js").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert "ui" not in (node.module or "").split(".")
        elif isinstance(node, ast.Import):
            assert not any("ui" in alias.name.split(".") for alias in node.names)
        elif isinstance(node, ast.Attribute):
            assert node.attr not in {"_push", "evaluate_js", "_window"}


UPLOAD_CONTROLLER = API.parent.parent / "upload" / "controller.py"


def uploader_publish_ports() -> list:
    """Every `publish_*` field of UploaderPorts, derived from the dataclass."""
    import dataclasses

    from wingman.upload.controller import UploaderPorts

    names = [
        field.name
        for field in dataclasses.fields(UploaderPorts)
        if field.name.startswith("publish_")
    ]
    assert len(names) >= 9, names
    return names


def test_uploader_controller_factory_binds_named_semantic_ports():
    source = API.read_text(encoding="utf-8")
    factory = api_method_body("_build_uploader_controller")

    assert "def _build_uploader_controller(" in source
    assert "UploaderController(" in factory
    assert "UploaderPorts(" in factory
    # The gate is injected, never constructed here or in the controller:
    # the updater and Quit claim against the same object from api.py.
    assert "gate=self._work_gate" in factory
    for port in uploader_publish_ports():
        assert re.search(rf"\b{port}=self\._\w+", factory), port
    for port, adapter in (
        ("status", "_uploader_status"),
        ("progress", "_uploader_progress"),
        ("alert", "_uploader_alert"),
        ("confirm", "_uploader_confirm"),
        ("spawn", "_spawn_uploader_worker"),
        ("watcher", "_uploader_watcher"),
        ("update_preparing", "_uploader_update_preparing"),
    ):
        assert f"{port}=self.{adapter}" in factory, port
    assert "self._uploader = self._build_uploader_controller(" in source


def test_uploader_publish_ports_stay_literal_pushes_private_to_api():
    """pushed_names() reads ui/api.py only. Every publish_* port must
    therefore bind to an Api method whose body is one literal `_push("name")`
    (or the existing `_push_auth`), so no handler name the uploader reaches
    can sit outside that sweep. Derived from the ports dataclass so a port
    added later is checked without anyone retyping the list here."""
    factory = api_method_body("_build_uploader_controller")
    allowed = set(allowlist())
    for port in uploader_publish_ports():
        bound = re.search(rf"\b{port}=self\.(_\w+)", factory)
        assert bound, port
        body = api_method_body(bound.group(1))
        assert body, (port, bound.group(1))
        pushes = re.findall(r'self\._push\(\s*"([A-Za-z0-9_]+)"', body)
        if pushes:
            assert len(pushes) == 1, (port, pushes)
            assert pushes[0] in allowed, (port, pushes)
        else:
            assert "self._push_auth(" in body, port


def test_uploader_controller_never_pushes_or_imports_the_bridge():
    """The controller reaches the page only through its ports.

    A `_push("...")` literal in wingman/upload would be a handler name
    outside pushed_names()'s sweep -- the silent no-op CLAUDE.md warns
    about, with no guard left to catch it -- and an import from `ui` would
    put the window one attribute away from an upload worker.
    """
    # Walked with ast, not matched as substrings: the controller's own
    # docstrings NAME `_push` and `evaluate_js` to explain the lost-push
    # defence they implement, and a comment that must stay is not a call.
    for path in (UPLOAD_CONTROLLER, UPLOAD_CONTROLLER.parent / "gate.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        reached = sorted(
            {
                node.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
                and node.attr in ("_push", "evaluate_js", "_window")
            }
        )
        assert reached == [], (path.name, reached)
        imported = sorted(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and (
                (node.level == 2 and (node.module or "").split(".")[0] == "ui")
                or (node.module or "").startswith("wingman.ui")
            )
        )
        assert imported == [], (path.name, imported)
        assert not any(
            alias.name.startswith("wingman.ui")
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ), path.name


def test_uploader_facade_methods_delegate_lexically_to_private_controller_methods():
    source = API.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert "getattr(self._uploader" not in source
    expected = {
        "list_rows": ("list_rows", ["preselect"]),
        "panel_text": ("panel_text", ["ids", "stitch"]),
        "delete_selected": ("delete_selected", ["ids"]),
        "copy_path": ("copy_path", ["row_id"]),
        "open_path": ("open_path", ["row_id"]),
        "play_recording": ("play_recording", ["row_id"]),
        "rename_recording": ("rename_recording", ["row_id", "stem"]),
        "open_recording_dir": ("open_recording_dir", []),
        "start_upload": ("start_upload", ["title", "description", "stitch", "ids"]),
        "cancel_upload": ("cancel_upload", []),
        "retry": ("retry", []),
        "post_recent_logs": ("post_recent_logs", []),
        # Private, but __main__.poll_tick and _status/_progress read it, so
        # it is a facade in every sense that matters here.
        "_busy": ("busy", []),
    }
    methods = {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    for method_name, (delegate_name, arg_names) in expected.items():
        method = methods[method_name]
        returns = [node for node in method.body if isinstance(node, ast.Return)]
        assert returns, method_name
        call = returns[-1].value
        assert isinstance(call, ast.Call), method_name
        assert isinstance(call.func, ast.Attribute), method_name
        assert call.func.attr == delegate_name, method_name
        owner = call.func.value
        assert isinstance(owner, ast.Attribute), method_name
        assert owner.attr == "_uploader", method_name
        assert isinstance(owner.value, ast.Name) and owner.value.id == "self", (
            method_name
        )
        assert [ast.unparse(arg) for arg in call.args] == arg_names, method_name
        assert call.keywords == [], method_name


def test_update_status_handler_is_allowlisted_and_registered_literally():
    source = (WEB / "app.js").read_text(encoding="utf-8")

    assert "onUpdateStatus" in allowlist()
    assert registered_names().get("onUpdateStatus") == ["app.js"]
    assert "WM.handle('onUpdateStatus', renderUpdateBadge);" in source


def test_eve_authority_change_handler_is_allowlisted_and_fanned_out_literally():
    app_js = (WEB / "app.js").read_text(encoding="utf-8")
    api_source = API.read_text(encoding="utf-8")

    assert 'self._push("onEveAuthorityChanged", {})' in api_source
    assert "onEveAuthorityChanged" in allowlist()
    assert registered_names().get("onEveAuthorityChanged") == ["app.js"]
    assert "new CustomEvent('wm:eve-authority'" in app_js
    assert "_skills._push_state(force=True)" not in api_source


def test_setup_completion_cannot_settle_an_ordinary_profiles_mutation():
    source = (WEB / "evesettings.js").read_text(encoding="utf-8")
    done = source.split("WM.handle('onEveSettingsDone', function (payload) {", 1)[1]
    handoff, ordinary = done.split("var completedMutation = pendingMutation;", 1)
    assert "if (payload.operation === 'ui_setup_create')" in handoff
    # Runtime coverage also executes both modules with the shell's real routes.
    assert "if (WM.uiSetupDone && WM.uiSetupDone(payload)) refresh();" in handoff
    assert "return;" in handoff
    assert "pendingMutation =" not in handoff
    assert "setBusy(" not in handoff
    assert "WM.formationsDone(payload)" in ordinary


def test_obsolete_character_auth_bridge_methods_are_gone():
    from wingman.ui.api import Api

    for name in (
        "skills_add_character",
        "skills_cancel_auth",
        "skills_forget_character",
        "fittings_enable_character",
        "fittings_cancel_auth",
        "fittings_forget_character",
    ):
        assert getattr(Api, name, None) is None


def test_startup_update_read_cannot_overwrite_a_newer_push():
    """A startup read is only authoritative until the first badge render.

    The automatic check may push checking/current while the cached read is
    still in flight. Every accepted render advances one generation, and the
    read may render only when the generation it captured before sending is
    still current. Keeping the read (rather than relying on a push) is what
    lets the browser dev harness paint its fixture.
    """
    source = (WEB / "app.js").read_text(encoding="utf-8")
    renderer = source.split("function renderUpdateBadge(payload) {", 1)[1].split(
        "\n  }", 1
    )[0]
    startup = source.split("// ---- startup", 1)[1]

    assert "var updateBadgeGeneration = 0;" in source
    assert "updateBadgeGeneration += 1;" in renderer
    capture = "var badgeGenerationAtRead = updateBadgeGeneration;"
    send = "WM.send('update_status')"
    assert startup.index(capture) < startup.index(send)
    assert re.search(
        r"if \(payload\s*&&\s*updateBadgeGeneration\s*===\s*"
        r"badgeGenerationAtRead\)\s*\{\s*window\.onUpdateStatus\(payload\);\s*\}",
        startup,
    )


def test_get_settings_remains_a_network_free_read():
    source = API.read_text(encoding="utf-8")
    body = source.split("def get_settings(self) -> dict:", 1)[1].split(
        "\n    def update_status", 1
    )[0]

    assert "return self._settings_payload()" in body
    assert "latest_release" not in body
    assert "_start_update_check" not in body


def test_the_watch_url_is_written_exactly_once():
    """One place decides what a YouTube watch URL looks like, and it is
    uploader.watch_url.

    Round 5 found the string written THREE times: `ui/api.py` held a
    `YOUTUBE_WATCH` constant, `ui/rows.py`'s `set_link` rebuilt the same
    thing with an f-string, and `web/list.js` concatenated a third copy.
    The JS copy was not an oversight -- the `onLink` push carried a bare
    `video_id`, so the page had nothing else to render and no way to stop
    knowing. Removing it is what made the push carry the finished URL.

    That is why this guard spans BOTH sides of the bridge rather than
    living with the Python: a payload that hands the page a fragment
    recreates the duplicate no matter how tidy the Python is. Same
    grep-shaped answer as test_page_conventions.py's
    test_no_colour_is_decided_outside_the_root_token_block, and for the
    same reason -- the assertion is a count, so a fourth copy fails here
    rather than drifting a number in a docstring.

    Comments are stripped first: the note in uploader.py explains the rule
    by naming the sites it replaced, and a guard that fails on its own
    explanation is a guard people delete.
    """
    package = Path(__file__).resolve().parent.parent / "wingman"
    sources = sorted(package.rglob("*.py")) + sorted(WEB.glob("*.js"))
    assert len(sources) > 20, "the sweep found almost nothing -- check the globs"

    found = {}
    for path in sources:
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        text = re.sub(r"(?m)^\s*(#|//).*$", "", text)
        hits = len(re.findall(r"youtube\.com/watch", text))
        if hits:
            # as_posix(), because the message names a file and the suite runs
            # on windows-latest as well as ubuntu-latest. The first draft
            # compared against a typed "a/b.py" and failed on Windows alone
            # -- over the separator, with the finding itself correct.
            found[path.relative_to(package.parent).as_posix()] = hits

    assert found == {"wingman/uploader.py": 1}, (
        f"the watch URL must be written once, in uploader.watch_url. Found: {found}"
    )


# The two floating bars do not load app.js (their header comments say
# why), so they have a local `send(method)` with the same contract as
# WM.send and no WM prefix. bookmarks.js and previews.js ALSO define a
# local `send(next)`, whose argument is a section or a pending value,
# never a method name -- so the bare form is read only from the files
# listed here, and a bar added later has to be added by hand.
STANDALONE_PAGES = ("fleetbar.js", "sigbar.js")

# Wrappers that take a bridge method name as an argument and hand it to
# WM.send inside their body. The sweep's `WM.send('literal'` regex saw
# none of these: `WM.send(method, wanted)` is a variable, and the literal
# sits at the wrapper's call site instead. Each entry is (file, regex with
# one group for the name). A new wrapper of this shape joins the list or
# its methods go unchecked, which is the failure this list prevents.
CALL_WRAPPERS = (
    ("alerts.js", r"writeFlag\(\s*\w+\s*,\s*'([a-z_]\w*)'"),
    ("evesettings.js", r"chooseRoot\(\s*'([a-z_]\w*)'"),
)


def bridge_calls() -> dict:
    """Every bridge method name the pages call, as {method: {files}}.

    Three spellings, each for a stated reason: `WM.send('x'` everywhere
    (dev.js excluded -- it fabricates the API rather than calling it), the
    bars' bare `send('x'`, and the wrappers in CALL_WRAPPERS.
    """
    called = {}
    for path_js in sorted(WEB.glob("*.js")):
        if path_js.name == "dev.js":
            continue
        source = path_js.read_text(encoding="utf-8")
        patterns = [r"WM\.send\(\s*'([a-z_]\w*)'"]
        if path_js.name in STANDALONE_PAGES:
            patterns.append(r"(?<![\w.])send\(\s*'([a-z_]\w*)'")
        patterns.extend(rx for name, rx in CALL_WRAPPERS if name == path_js.name)
        for pattern in patterns:
            for method in set(re.findall(pattern, source)):
                called.setdefault(method, set()).add(path_js.name)
    return called


def test_the_call_sweep_sees_the_bars_and_the_wrappers():
    """The regex extensions above must be seen to match, or the sweep below
    passes on the old WM.send-only set while claiming more. Each name here
    is one that ONLY its extension can find: the bars have no WM, and the
    wrapper call sites hold the only literal spelling of their methods."""
    called = bridge_calls()
    assert "fleetbar.js" in called.get("fleet_bar_snapshot", set())
    assert "fleetbar.js" in called.get("fit_fleet_bar_height", set())
    assert "fleetbar.js" in called.get("activate_fleet_bar", set())
    assert "sigbar.js" in called.get("fit_sig_bar", set())
    assert "sigbar.js" in called.get("save_sig_bar_pos", set())
    assert "alerts.js" in called.get("set_alert_enabled", set())
    assert "alerts.js" in called.get("set_alert_pve_filter", set())
    assert "evesettings.js" in called.get("eve_settings_pick_root", set())
    assert "evesettings.js" in called.get("eve_settings_detect_root", set())


def test_fleet_page_interfaces_are_token_first_and_standalone_only():
    from inspect import signature

    from wingman.ui.api import Api

    calls = bridge_calls()
    expected = {
        "fleet_bar_snapshot": ("page_id",),
        "fit_fleet_bar_height": ("page_id", "height"),
        "settle_fleet_bar_resize": ("page_id", "content_width", "x"),
        "reset_fleet_bar_page_width": ("page_id",),
        "save_fleet_bar_pos": ("page_id", "x", "y", "phase", "drag_id"),
        "fleet_bar_ready": ("page_id",),
        "activate_fleet_bar": ("page_id",),
        "deactivate_fleet_bar": ("page_id",),
        "hide_fleet_bar": ("page_id",),
    }
    for method, parameters in expected.items():
        params = signature(getattr(Api, method)).parameters
        assert tuple(params) == ("self", *parameters)
        assert all(params[name].default is None for name in parameters)
        assert calls[method] == {"fleetbar.js"}
    for method in (
        "fleet_bar_settings",
        "toggle_fleet_bar",
        "set_fleet_bar_character_visible",
    ):
        assert "page_id" not in signature(getattr(Api, method)).parameters


def test_the_skills_controller_pushes_are_swept_and_allowlisted():
    """Proves pushed_names() reads eveskills/controller.py: `onSkills` and
    `onSkillsProgress` are spelled there and nowhere in api.py, so a sweep
    that stopped at api.py would never see them and a rename in the
    controller would be a silent no-op on the Skills page."""
    api_source = API.read_text(encoding="utf-8")
    assert '"onSkillsProgress"' not in api_source, (
        "the controller push is now spelled in api.py too; this test's "
        "premise moved, re-read it before changing it"
    )
    for name in ("onSkills", "onSkillsProgress"):
        assert name in pushed_names(), name
        assert name in allowlist(), name


def test_the_sig_bar_registers_the_status_handler_it_is_pushed():
    """sigbar.html loads sigbar.js alone -- no app.js, no WM.HANDLERS -- so
    the allowlist tests above say nothing about it. `_push` broadcasts to
    the sig bar window as well as the main one, and the bar renders only
    if it assigned `window.onEveStatus` itself. Renaming either side
    leaves a bar of em-dash placeholders that never updates, which is
    indistinguishable from an engine that has not started."""
    sigbar = (WEB / "sigbar.js").read_text(encoding="utf-8")
    assert re.search(r"window\.onEveStatus\s*=\s*function", sigbar), (
        "sigbar.js must assign window.onEveStatus as a plain global"
    )
    assert "onEveStatus" in pushed_names(), "api.py no longer pushes onEveStatus"


def test_the_fleet_bar_handler_name_agrees_across_the_bridge():
    """fleetbar.js is pushed to by `_push_fleet_snapshot`, which writes its
    own `window.<name> && window.<name>(...)` script rather than going
    through `_push` -- so neither the allowlist sweep nor pushed_names()
    covers it, and the two spellings are held together only here. A rename
    on one side makes the fleet bar sit on 'Waiting for EVE clients...'
    forever, with the snapshot push landing as a silent no-op."""
    body = api_method_body("_push_fleet_snapshot")
    assert body, "_push_fleet_snapshot is gone from ui/api.py"
    pushed = re.search(r"window\.(\w+) && window\.\1\(", body)
    assert pushed, (
        "the fleet snapshot script no longer has the window.x && window.x( shape"
    )
    fleetbar = (WEB / "fleetbar.js").read_text(encoding="utf-8")
    assigned = re.findall(r"window\.(on\w+)\s*=", fleetbar)
    assert assigned == [pushed.group(1)], (pushed.group(1), assigned)


def test_every_bridge_method_the_page_calls_exists_on_the_api():
    """The other direction of the same silence.

    The push half above is guarded because a bad handler name makes a route
    inert. The CALL half fails differently and just as quietly: `WM.send`
    reaches `pywebview.api.<method>` and, for a name Api does not carry,
    rejects to the console -- which nobody reads while looking at a screen.
    The control simply does nothing when clicked, in a codebase where
    nothing renders the page in a test.

    Checked against the real class rather than a lexical `def` scan, so a
    method that exists only as a name in a comment or a docstring does not
    count, and one inherited or assigned at class level does.

    Not a subset check with a known-gaps list, unlike the ?dev=1 double
    guard in test_dev_harness.py: a missing DOUBLE degrades the harness,
    while a missing METHOD is a control that is dead in the shipped app.
    There is no acceptable gap.
    """
    from wingman.ui.api import Api

    called = bridge_calls()

    # A regex that matched nothing would make the assertion below pass while
    # checking air -- the trap this suite records falling into elsewhere.
    assert len(called) >= 40, f"the WM.send scan found only {sorted(called)}"

    missing = {
        method: sorted(files)
        for method, files in called.items()
        if not callable(getattr(Api, method, None))
    }
    assert not missing, (
        "the page calls bridge methods that do not exist on Api, so those "
        "controls are dead in the shipped app and say nothing when "
        f"clicked: {missing}"
    )
