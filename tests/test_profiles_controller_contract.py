import dataclasses
import importlib
import importlib.util
import inspect

import pytest

from tests import fakes
from tests.test_api import decode_payload
from wingman import paths
from wingman import settings as settings_mod
from wingman.ui import api as api_mod
from wingman.ui import copy as copy_mod
from wingman.ui.api import Api

PROFILE_METHODS = (
    "eve_settings_state",
    "eve_settings_setup_limits",
    "eve_settings_setup_catalog",
    "eve_settings_setup_catalog_entry",
    "eve_settings_setup_context",
    "eve_settings_setup_export",
    "eve_settings_setup_read_file",
    "eve_settings_setup_save_file",
    "eve_settings_setup_review",
    "eve_settings_setup_discard",
    "eve_settings_setup_create",
    "eve_settings_pick_root",
    "eve_settings_detect_root",
    "eve_settings_select",
    "eve_settings_set_account_name",
    "eve_settings_set_account_characters",
    "eve_settings_identification_start",
    "eve_settings_identification_check",
    "eve_settings_identification_confirm",
    "eve_settings_identification_cancel",
    "eve_settings_resolve_names",
    "eve_settings_set_auto_keep",
    "eve_settings_copy",
    "eve_settings_copy_profile",
    "eve_settings_backup",
    "eve_settings_restore",
    "eve_settings_delete_backup",
    "eve_settings_formations",
    "eve_settings_export_formations",
    "eve_settings_parse_formations",
    "eve_settings_validate_formation_import",
    "eve_settings_save_formations",
)

PROFILE_SIGNATURES = {
    "eve_settings_state": "(self) -> dict",
    "eve_settings_setup_limits": "(self) -> dict",
    "eve_settings_setup_catalog": "(self) -> dict",
    "eve_settings_setup_catalog_entry": "(self, preset_id: str, revision: int, sha256: str) -> dict",
    "eve_settings_setup_context": "(self, profile: str) -> dict",
    "eve_settings_setup_export": "(self, expected_profile: str, account_path: str, character_path: str) -> dict",
    "eve_settings_setup_read_file": "(self) -> dict",
    "eve_settings_setup_save_file": "(self, text: str) -> dict",
    "eve_settings_setup_review": "(self, text: str, expected_profile: str, account_path: str, character_path: str, destination_name: str, keep_ship_labels: bool = False) -> dict",
    "eve_settings_setup_discard": "(self, review_id: str) -> bool",
    "eve_settings_setup_create": "(self, review_id: str, request_id: str) -> dict",
    "eve_settings_pick_root": "(self) -> str",
    "eve_settings_detect_root": "(self) -> str",
    "eve_settings_select": "(self, server: str, profile: str) -> bool",
    "eve_settings_set_account_name": "(self, account_id: str, name: str) -> dict",
    "eve_settings_set_account_characters": (
        "(self, account_id: str, character_ids: list) -> dict"
    ),
    "eve_settings_identification_start": "(self) -> dict",
    "eve_settings_identification_check": "(self) -> dict",
    "eve_settings_identification_confirm": (
        "(self, account_id: str, character_id: str, account_name: str) -> dict"
    ),
    "eve_settings_identification_cancel": "(self) -> dict",
    "eve_settings_resolve_names": "(self) -> None",
    "eve_settings_set_auto_keep": "(self, value) -> dict",
    "eve_settings_copy": "(self, source: str, targets: list, groups: list | None = None) -> bool",
    "eve_settings_copy_profile": (
        "(self, expected_source: str, mode: str, destination: str) -> dict"
    ),
    "eve_settings_backup": "(self, path: str, kind: str) -> bool",
    "eve_settings_restore": "(self, archive: str) -> bool",
    "eve_settings_delete_backup": "(self, archive: str) -> bool",
    "eve_settings_formations": "(self, path: str) -> dict",
    "eve_settings_export_formations": "(self, items: list) -> dict",
    "eve_settings_parse_formations": "(self, text: str, existing_names: list) -> dict",
    "eve_settings_validate_formation_import": (
        "(self, items: list, existing_names: list) -> dict"
    ),
    "eve_settings_save_formations": (
        "(self, path: str, formations: list, expected_content_revision: str = '', "
        "request_id: str = '') -> bool"
    ),
}

PROFILE_DELEGATES = {
    "eve_settings_state": "state",
    "eve_settings_setup_limits": "setup_limits",
    "eve_settings_setup_catalog": "setup_catalog",
    "eve_settings_setup_catalog_entry": "setup_catalog_entry",
    "eve_settings_setup_context": "setup_context",
    "eve_settings_setup_export": "setup_export",
    "eve_settings_setup_read_file": "setup_read_file",
    "eve_settings_setup_save_file": "setup_save_file",
    "eve_settings_setup_review": "setup_review",
    "eve_settings_setup_discard": "setup_discard",
    "eve_settings_setup_create": "setup_create",
    "eve_settings_pick_root": "pick_root",
    "eve_settings_detect_root": "detect_root",
    "eve_settings_select": "select",
    "eve_settings_set_account_name": "set_account_name",
    "eve_settings_set_account_characters": "set_account_characters",
    "eve_settings_identification_start": "identification_start",
    "eve_settings_identification_check": "identification_check",
    "eve_settings_identification_confirm": "identification_confirm",
    "eve_settings_identification_cancel": "identification_cancel",
    "eve_settings_resolve_names": "resolve_names",
    "eve_settings_set_auto_keep": "set_auto_keep",
    "eve_settings_copy": "copy",
    "eve_settings_copy_profile": "copy_profile",
    "eve_settings_backup": "backup",
    "eve_settings_restore": "restore",
    "eve_settings_delete_backup": "delete_backup",
    "eve_settings_formations": "formations",
    "eve_settings_export_formations": "export_formations",
    "eve_settings_parse_formations": "parse_formations",
    "eve_settings_validate_formation_import": "validate_formation_import",
    "eve_settings_save_formations": "save_formations",
}

PROFILE_PORTS = (
    "publish_running",
    "publish_names",
    "publish_done",
    "alert",
    "status",
    "confirm",
    "choose_root",
    "choose_setup_input",
    "choose_setup_output",
    "spawn",
    "advisory_client_running",
    "strict_client_running",
    "profile_copy_refusal",
    "backup_root",
    "update_settings",
    "format_copy_confirm",
    "format_copy_done",
)

PROFILE_RUNTIME_FIELDS = (
    "_setup_review",
    "_eve_mutation",
    "_eve_identification_lock",
    "_eve_identification_generation",
    "_eve_identification",
    "_eve_identification_candidate",
    "_eve_names",
    "_eve_deleted",
    "_eve_applied",
    "_eve_resolve_lock",
    "_eve_resolve_running",
    "_eve_resolve_pending",
    "_eve_running",
    "_eve_probe",
)

PROFILE_FORBIDDEN_CONTROLLER_FIELDS = (
    "api",
    "_api",
    "window",
    "_window",
    "_sigbar_window",
    "_fleetbar_window",
    "_push",
    "_alert",
    "_status",
    "_confirm",
    "_spawn",
)


class _RefusingWorkerHandle:
    def start(self):
        raise RuntimeError("worker start should stay behind the controller boundary")


def _build_state(tmp_path):
    return api_mod.AppState(
        recording_dir=tmp_path,
        settings=settings_mod.load(tmp_path / "settings.json"),
    )


def _build_api(tmp_path):
    api, window = fakes.build_api(tmp_path)
    api._confirm = lambda *args, **kwargs: False
    api._eve_confirm = lambda *args, **kwargs: False
    api._spawn = lambda **kwargs: _RefusingWorkerHandle()
    return api, window


class _ProfilesSpy:
    def __init__(self):
        self.calls = []
        self.returns = {
            controller: object() for controller in PROFILE_DELEGATES.values()
        }
        self.returns["resolve_names"] = None

    def _record(self, name, *args):
        self.calls.append((name, args))
        return self.returns[name]

    def state(self):
        return self._record("state")

    def setup_limits(self):
        return self._record("setup_limits")

    def setup_catalog(self):
        return self._record("setup_catalog")

    def setup_catalog_entry(self, preset_id, revision, sha256):
        return self._record("setup_catalog_entry", preset_id, revision, sha256)

    def setup_context(self, profile):
        return self._record("setup_context", profile)

    def setup_export(self, expected_profile, account_path, character_path):
        return self._record(
            "setup_export", expected_profile, account_path, character_path
        )

    def setup_read_file(self):
        return self._record("setup_read_file")

    def setup_save_file(self, text):
        return self._record("setup_save_file", text)

    def setup_review(
        self,
        text,
        expected_profile,
        account_path,
        character_path,
        destination_name,
        keep_ship_labels=False,
    ):
        return self._record(
            "setup_review",
            text,
            expected_profile,
            account_path,
            character_path,
            destination_name,
            keep_ship_labels,
        )

    def setup_discard(self, review_id):
        return self._record("setup_discard", review_id)

    def setup_create(self, review_id, request_id):
        return self._record("setup_create", review_id, request_id)

    def pick_root(self):
        return self._record("pick_root")

    def detect_root(self):
        return self._record("detect_root")

    def select(self, server, profile):
        return self._record("select", server, profile)

    def set_account_name(self, account_id, name):
        return self._record("set_account_name", account_id, name)

    def set_account_characters(self, account_id, character_ids):
        return self._record("set_account_characters", account_id, character_ids)

    def identification_start(self):
        return self._record("identification_start")

    def identification_check(self):
        return self._record("identification_check")

    def identification_confirm(self, account_id, character_id, account_name):
        return self._record(
            "identification_confirm", account_id, character_id, account_name
        )

    def identification_cancel(self):
        return self._record("identification_cancel")

    def resolve_names(self):
        return self._record("resolve_names")

    def set_auto_keep(self, value):
        return self._record("set_auto_keep", value)

    def copy(self, source, targets, groups=None):
        return self._record("copy", source, targets, groups)

    def copy_profile(self, expected_source, mode, destination):
        return self._record("copy_profile", expected_source, mode, destination)

    def backup(self, path, kind):
        return self._record("backup", path, kind)

    def restore(self, archive):
        return self._record("restore", archive)

    def delete_backup(self, archive):
        return self._record("delete_backup", archive)

    def formations(self, path):
        return self._record("formations", path)

    def export_formations(self, items):
        return self._record("export_formations", items)

    def parse_formations(self, text, existing_names):
        return self._record("parse_formations", text, existing_names)

    def validate_formation_import(self, items, existing_names):
        return self._record("validate_formation_import", items, existing_names)

    def save_formations(
        self, path, formations, expected_content_revision="", request_id=""
    ):
        return self._record(
            "save_formations", path, formations, expected_content_revision, request_id
        )


def _pushes(window) -> list[tuple[str, object]]:
    out = []
    for script in window.calls:
        handler = script.split("window.", 1)[1].split(" ", 1)[0]
        payload = decode_payload(
            script[script.index("(", script.rindex(handler)) + 1 : script.rindex(")")]
        )
        out.append((handler, payload))
    return out


def test_profiles_public_methods_exist():
    assert set(PROFILE_METHODS) == set(PROFILE_SIGNATURES) == set(PROFILE_DELEGATES)
    assert {name for name in vars(Api) if name.startswith("eve_settings_")} == set(
        PROFILE_METHODS
    )
    for method in PROFILE_METHODS:
        assert callable(getattr(Api, method, None)), method


def test_profiles_signatures_are_stable():
    assert {
        method: str(inspect.signature(getattr(Api, method)))
        for method in PROFILE_METHODS
    } == PROFILE_SIGNATURES


def test_profiles_controller_module_exports_named_boundary_types():
    spec = importlib.util.find_spec("wingman.evesettings.controller")
    assert spec is not None

    module = importlib.import_module("wingman.evesettings.controller")
    assert hasattr(module, "ProfilesController")
    assert hasattr(module, "ProfilesPorts")
    assert dataclasses.is_dataclass(module.ProfilesPorts)
    assert module.ProfilesPorts.__dataclass_params__.frozen is True
    assert (
        tuple(field.name for field in dataclasses.fields(module.ProfilesPorts))
        == PROFILE_PORTS
    )


def test_profiles_controller_is_private_and_owns_the_boundary(tmp_path):
    api, _window = _build_api(tmp_path)

    assert callable(getattr(api, "_build_profiles_controller", None))
    assert hasattr(api, "_profiles")
    controller = api._profiles
    assert controller is not api
    assert controller._settings is api._state.settings
    assert api.eve_settings_state() == controller.state()
    assert set(PROFILE_RUNTIME_FIELDS) <= set(controller.__dict__)
    assert set(PROFILE_RUNTIME_FIELDS).isdisjoint(api.__dict__)
    assert not (set(PROFILE_FORBIDDEN_CONTROLLER_FIELDS) & set(controller.__dict__))


def test_profiles_controller_construction_has_no_effects_and_factory_runs_last(
    tmp_path, monkeypatch
):
    seen = []
    checkpoint = {}
    real_build = api_mod.Api._build_profiles_controller

    def trap(name):
        def fail(*args, **kwargs):
            seen.append((name, args, kwargs))
            raise AssertionError(f"{name} ran during Api construction")

        return fail

    def wrapped_build(self):
        checkpoint.update(
            {
                "has_state": "_state" in self.__dict__,
                "window": self._window,
                "has_dialog_lock": "_dialog_lock" in self.__dict__,
                "has_dialogs": "_dialogs" in self.__dict__,
                "has_work_gate": "_work_gate" in self.__dict__,
                "spawn": self._spawn,
                "has_profiles": "_profiles" in self.__dict__,
            }
        )
        return real_build(self)

    monkeypatch.setattr(api_mod.Api, "_build_profiles_controller", wrapped_build)
    monkeypatch.setattr(api_mod.Api, "_push", trap("_push"))
    monkeypatch.setattr(
        api_mod.Api,
        "_publish_eve_settings_running",
        trap("_publish_eve_settings_running"),
    )
    monkeypatch.setattr(
        api_mod.Api,
        "_publish_eve_settings_names",
        trap("_publish_eve_settings_names"),
    )
    monkeypatch.setattr(
        api_mod.Api,
        "_publish_eve_settings_done",
        trap("_publish_eve_settings_done"),
    )
    monkeypatch.setattr(api_mod.Api, "_profiles_alert", trap("_profiles_alert"))
    monkeypatch.setattr(api_mod.Api, "_profiles_status", trap("_profiles_status"))
    monkeypatch.setattr(api_mod.Api, "_profiles_confirm", trap("_profiles_confirm"))
    monkeypatch.setattr(
        api_mod.Api,
        "_choose_eve_settings_root",
        trap("_choose_eve_settings_root"),
    )
    monkeypatch.setattr(api_mod.Api, "_choose_setup_input", trap("choose_setup_input"))
    monkeypatch.setattr(
        api_mod.Api, "_choose_setup_output", trap("choose_setup_output")
    )
    monkeypatch.setattr(
        api_mod.Api,
        "_spawn_profiles_worker",
        trap("_spawn_profiles_worker"),
    )
    monkeypatch.setattr(
        api_mod.Api,
        "_profiles_advisory_client_running",
        trap("_profiles_advisory_client_running"),
    )
    monkeypatch.setattr(
        api_mod.Api,
        "_profiles_strict_client_running",
        trap("_profiles_strict_client_running"),
    )
    monkeypatch.setattr(
        api_mod.Api,
        "_profiles_copy_refusal",
        trap("_profiles_copy_refusal"),
    )
    monkeypatch.setattr(
        api_mod.Api,
        "_update_profiles_settings",
        trap("_update_profiles_settings"),
    )
    monkeypatch.setattr(api_mod.settings_mod, "update_section", trap("update_section"))
    monkeypatch.setattr(
        api_mod.paths,
        "eve_settings_backup_dir",
        trap("paths.eve_settings_backup_dir"),
    )
    monkeypatch.setattr(
        api_mod.copy_mod,
        "format_eve_copy_confirm",
        trap("copy_mod.format_eve_copy_confirm"),
    )
    monkeypatch.setattr(
        api_mod.copy_mod,
        "format_eve_copy_done",
        trap("copy_mod.format_eve_copy_done"),
    )

    api = api_mod.Api(_build_state(tmp_path), spawn=_RefusingWorkerHandle)

    assert hasattr(api, "_profiles")
    assert checkpoint == {
        "has_state": True,
        "window": None,
        "has_dialog_lock": True,
        "has_dialogs": True,
        "has_work_gate": True,
        "spawn": _RefusingWorkerHandle,
        "has_profiles": False,
    }
    assert seen == []


@pytest.mark.parametrize(
    ("api_name", "controller_name", "args"),
    [
        ("eve_settings_state", "state", ()),
        ("eve_settings_setup_limits", "setup_limits", ()),
        ("eve_settings_setup_catalog", "setup_catalog", ()),
        (
            "eve_settings_setup_catalog_entry",
            "setup_catalog_entry",
            ("synthetic-fleet", 3, "a" * 64),
        ),
        ("eve_settings_setup_context", "setup_context", ("sibling",)),
        ("eve_settings_setup_export", "setup_export", ("base", "account", "character")),
        ("eve_settings_setup_read_file", "setup_read_file", ()),
        ("eve_settings_setup_save_file", "setup_save_file", ("text",)),
        (
            "eve_settings_setup_review",
            "setup_review",
            ("text", "base", "account", "character", "New", True),
        ),
        ("eve_settings_setup_discard", "setup_discard", ("review-id",)),
        ("eve_settings_setup_create", "setup_create", ("review-id", "request-id")),
        ("eve_settings_pick_root", "pick_root", ()),
        ("eve_settings_detect_root", "detect_root", ()),
        ("eve_settings_select", "select", ("tranquility", "settings_Default")),
        ("eve_settings_set_account_name", "set_account_name", ("9001", "Main")),
        (
            "eve_settings_set_account_characters",
            "set_account_characters",
            ("9001", ["100", "101"]),
        ),
        ("eve_settings_identification_start", "identification_start", ()),
        ("eve_settings_identification_check", "identification_check", ()),
        (
            "eve_settings_identification_confirm",
            "identification_confirm",
            ("9001", "100", "Main"),
        ),
        ("eve_settings_identification_cancel", "identification_cancel", ()),
        ("eve_settings_resolve_names", "resolve_names", ()),
        ("eve_settings_set_auto_keep", "set_auto_keep", (9,)),
        (
            "eve_settings_copy_profile",
            "copy_profile",
            ("settings_Default", "replace", "settings_Fleet"),
        ),
        ("eve_settings_backup", "backup", ("/tmp/account.dat", "account")),
        ("eve_settings_restore", "restore", ("/tmp/archive.zip",)),
        ("eve_settings_delete_backup", "delete_backup", ("/tmp/archive.zip",)),
        ("eve_settings_formations", "formations", ("/tmp/account.dat",)),
        ("eve_settings_export_formations", "export_formations", ([{"id": 7}],)),
        ("eve_settings_parse_formations", "parse_formations", ("draft text", ["Name"])),
        (
            "eve_settings_validate_formation_import",
            "validate_formation_import",
            ([{"id": None}], ["Name"]),
        ),
    ],
)
def test_profiles_facade_methods_delegate_directly_to_the_private_controller(
    tmp_path, api_name, controller_name, args
):
    api, _window = _build_api(tmp_path)
    spy = _ProfilesSpy()
    api._profiles = spy

    result = getattr(api, api_name)(*args)

    assert spy.calls == [(controller_name, args)]
    assert all(actual is original for actual, original in zip(spy.calls[0][1], args))
    assert result is spy.returns[controller_name]


def test_profiles_setup_review_delegate_preserves_keep_labels_default(tmp_path):
    api, _window = _build_api(tmp_path)
    spy = _ProfilesSpy()
    api._profiles = spy
    args = ("text", "base", "account", "character", "New")
    assert api.eve_settings_setup_review(*args) is spy.returns["setup_review"]
    assert spy.calls == [("setup_review", (*args, False))]


def test_profiles_copy_delegate_preserves_the_omitted_groups_default(tmp_path):
    api, _window = _build_api(tmp_path)
    spy = _ProfilesSpy()
    api._profiles = spy
    targets = ["/tmp/one.dat", "/tmp/two.dat"]

    result = api.eve_settings_copy("/tmp/source.dat", targets)

    assert spy.calls == [("copy", ("/tmp/source.dat", targets, None))]
    assert result is spy.returns["copy"]


@pytest.mark.parametrize("groups", [None, [], ["windows", "chat"]])
def test_profiles_copy_delegate_preserves_groups_and_list_identity(tmp_path, groups):
    api, _window = _build_api(tmp_path)
    spy = _ProfilesSpy()
    api._profiles = spy
    targets = ["/tmp/one.dat", "/tmp/two.dat"]

    result = api.eve_settings_copy("/tmp/source.dat", targets, groups)

    assert spy.calls == [("copy", ("/tmp/source.dat", targets, groups))]
    _name, (_source, forwarded_targets, forwarded_groups) = spy.calls[0]
    assert forwarded_targets is targets
    assert forwarded_groups is groups
    assert result is spy.returns["copy"]


def test_profiles_set_account_characters_delegate_preserves_the_original_list_object(
    tmp_path,
):
    api, _window = _build_api(tmp_path)
    spy = _ProfilesSpy()
    api._profiles = spy
    character_ids = ["101", "102"]

    result = api.eve_settings_set_account_characters("9001", character_ids)

    assert spy.calls == [("set_account_characters", ("9001", character_ids))]
    _name, (_account_id, forwarded_character_ids) = spy.calls[0]
    assert forwarded_character_ids is character_ids
    assert result is spy.returns["set_account_characters"]


@pytest.mark.parametrize("correlation", [(), ("a" * 64,), ("a" * 64, "save:1")])
def test_profiles_save_formations_delegate_preserves_the_original_list_object(
    tmp_path, correlation
):
    api, _window = _build_api(tmp_path)
    spy = _ProfilesSpy()
    api._profiles = spy
    formations = [{"name": "center", "x_m": 1.0, "y_m": 2.0, "z_m": 3.0}]
    path = "/tmp/account.dat"
    revision, request_id = (*correlation, "", "")[:2]

    result = api.eve_settings_save_formations(path, formations, *correlation)

    assert spy.calls == [("save_formations", (path, formations, revision, request_id))]
    _name, forwarded = spy.calls[0]
    assert forwarded[0] is path
    assert forwarded[1] is formations
    assert forwarded[2] is revision
    assert forwarded[3] is request_id
    assert result is spy.returns["save_formations"]


def test_profiles_factory_publish_ports_push_the_existing_semantic_handlers(tmp_path):
    api, window = _build_api(tmp_path)

    assert hasattr(api, "_profiles")
    api._profiles._ports.publish_running({"running": True})
    api._profiles._ports.publish_names(
        {
            "identification_generation": 7,
            "deleted_candidate_ids": ["202"],
        }
    )
    api._profiles._ports.publish_done({"ok": True, "operation": "profile_copy"})

    assert _pushes(window)[-3:] == [
        ("onEveSettingsRunning", {"running": True}),
        (
            "onEveSettingsNames",
            {
                "identification_generation": 7,
                "deleted_candidate_ids": ["202"],
            },
        ),
        ("onEveSettingsDone", {"ok": True, "operation": "profile_copy"}),
    ]


def test_profiles_publish_ports_resolve_the_current_push_collaborator(tmp_path):
    api, _window = _build_api(tmp_path)

    assert hasattr(api, "_profiles")
    sent = []
    api._push = lambda handler, payload: sent.append((handler, payload))

    api._profiles._ports.publish_running({"running": False})
    api._profiles._ports.publish_names(
        {
            "identification_generation": 11,
            "deleted_candidate_ids": ["404"],
        }
    )
    api._profiles._ports.publish_done({"ok": False, "operation": "profile_copy"})

    assert sent == [
        ("onEveSettingsRunning", {"running": False}),
        (
            "onEveSettingsNames",
            {
                "identification_generation": 11,
                "deleted_candidate_ids": ["404"],
            },
        ),
        ("onEveSettingsDone", {"ok": False, "operation": "profile_copy"}),
    ]


def test_profiles_update_settings_port_targets_the_live_document_by_identity(
    tmp_path, monkeypatch
):
    api, _window = _build_api(tmp_path)

    assert hasattr(api, "_profiles")
    seen = []

    def update_section(settings, section, values):
        seen.append((settings, section, values))

    monkeypatch.setattr(api_mod.settings_mod, "update_section", update_section)

    api._profiles._ports.update_settings({"server": "tranquility"})

    assert len(seen) == 1
    settings_doc, section, values = seen[0]
    assert settings_doc is api._state.settings
    assert section == "eve_settings"
    assert values == {"server": "tranquility"}


def test_profiles_update_settings_port_propagates_exceptions(tmp_path, monkeypatch):
    api, _window = _build_api(tmp_path)

    assert hasattr(api, "_profiles")

    def boom(settings, section, values):
        assert settings is api._state.settings
        assert section == "eve_settings"
        assert values == {"profile": "settings_Fleet"}
        raise OSError("disk full")

    monkeypatch.setattr(api_mod.settings_mod, "update_section", boom)

    with pytest.raises(OSError, match="disk full"):
        api._profiles._ports.update_settings({"profile": "settings_Fleet"})


def test_profiles_choose_root_port_uses_the_current_window_and_dialog_kind(
    tmp_path, monkeypatch
):
    api, _window = _build_api(tmp_path)

    assert hasattr(api, "_profiles")
    replacement = fakes.FakeWindow()
    replacement.dialog_result = ["/picked/EVE"]
    api._window = replacement
    from wingman.ui import api as api_mod

    monkeypatch.setattr(api_mod, "_folder_dialog_kind", lambda: "folder-kind")

    chosen = api._profiles._ports.choose_root("/start/here")

    assert chosen == "/picked/EVE"
    assert replacement.dialogs == [("folder-kind", "/start/here")]


def test_profiles_confirm_port_uses_the_current_bounded_confirmation_collaborator(
    tmp_path,
):
    api, _window = _build_api(tmp_path)

    assert hasattr(api, "_profiles")
    asked = []
    api._eve_confirm = lambda title, body, **kwargs: (
        asked.append((title, body, kwargs)) or True
    )

    ok = api._profiles._ports.confirm(
        "Confirm Copy", "This cannot be undone.", destructive=True
    )

    assert ok is True
    assert asked == [
        (
            "Confirm Copy",
            "This cannot be undone.",
            {"destructive": True},
        )
    ]


def test_profiles_spawn_port_uses_the_current_worker_factory_without_starting(tmp_path):
    api, _window = _build_api(tmp_path)

    assert hasattr(api, "_profiles")
    seen = []

    class Handle:
        def __init__(self):
            self.started = False

        def start(self):
            self.started = True

    handle = Handle()

    def replacement_spawn(*, target, args=(), daemon=True):
        seen.append((target, args, daemon))
        return handle

    api._spawn = replacement_spawn
    worker = api._profiles._ports.spawn(target=str.upper, args=("x",), daemon=False)

    assert worker is handle
    assert handle.started is False
    assert seen == [(str.upper, ("x",), False)]


@pytest.mark.parametrize(
    ("port_name", "replacement", "expected"),
    [
        ("advisory_client_running", lambda: True, True),
        ("strict_client_running", lambda: False, False),
        (
            "profile_copy_refusal",
            lambda: "EVE is running. Close EVE and retry.",
            "EVE is running. Close EVE and retry.",
        ),
    ],
)
def test_profiles_probe_ports_resolve_replaced_runtime_collaborators(
    tmp_path, port_name, replacement, expected
):
    api, _window = _build_api(tmp_path)

    assert hasattr(api, "_profiles")
    setattr(
        api,
        {
            "advisory_client_running": "_eve_client_running",
            "strict_client_running": "_eve_client_running_strict",
            "profile_copy_refusal": "_eve_profile_copy_refusal",
        }[port_name],
        replacement,
    )

    assert getattr(api._profiles._ports, port_name)() == expected


def test_profiles_alert_and_status_ports_resolve_replaced_collaborators(tmp_path):
    api, _window = _build_api(tmp_path)

    assert hasattr(api, "_profiles")
    alerts = []
    statuses = []
    api._alert = lambda kind, title, body: alerts.append((kind, title, body))
    api._status = lambda text: statuses.append(text)

    api._profiles._ports.alert("warning", "Busy", "Close EVE and retry.")
    api._profiles._ports.status("Keeping 10 automatic backups per item.")

    assert alerts == [("warning", "Busy", "Close EVE and retry.")]
    assert statuses == ["Keeping 10 automatic backups per item."]


def test_profiles_backup_root_and_copy_format_ports_use_the_bound_callables(tmp_path):
    api, _window = _build_api(tmp_path)

    assert hasattr(api, "_profiles")
    targets = ["Alpha", "Beta"]
    preserved = ["Search history & suggestions"]

    assert api._profiles._ports.backup_root() == paths.eve_settings_backup_dir()
    assert api._profiles._ports.format_copy_done(2, "character") == (
        copy_mod.format_eve_copy_done(2, "character")
    )
    assert api._profiles._ports.format_copy_confirm(
        targets,
        "character",
        True,
        source_name="Source",
        preserved_groups=preserved,
    ) == copy_mod.format_eve_copy_confirm(
        targets,
        "character",
        True,
        source_name="Source",
        preserved_groups=preserved,
    )
