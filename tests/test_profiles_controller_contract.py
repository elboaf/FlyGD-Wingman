import inspect

from wingman.ui.api import Api

PROFILE_METHODS = (
    "eve_settings_state",
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
    "eve_settings_save_formations",
)


def test_profiles_public_methods_exist():
    for method in PROFILE_METHODS:
        assert callable(getattr(Api, method, None)), method


def test_profiles_signatures_are_stable():
    # Exact signature assertions that the extraction must preserve.
    assert list(inspect.signature(Api.eve_settings_copy).parameters) == [
        "self",
        "source",
        "targets",
        "groups",
    ]
    assert inspect.signature(Api.eve_settings_copy).parameters["groups"].default is None
    assert list(inspect.signature(Api.eve_settings_copy_profile).parameters) == [
        "self",
        "expected_source",
        "mode",
        "destination",
    ]
