"""The EVE skills façade methods. The controller is faked whole.

These are pure delegation, so what is worth testing is exactly the two
things delegation gets wrong: what a mutation returns, and what happens when
there is no controller at all.
"""

from tests.fakes import FakeWindow
from tests.test_api import make_api
from wingman.eveauth.controller import MutationResult


class FakeSkills:
    """Records calls. The real controller has its own suite."""

    def __init__(self):
        self.calls = []
        self.forget_result = True
        self.plan_text_result = "Navigation IV\n"
        self.group_result = True

    def state_payload(self):
        self.calls.append(("state_payload",))
        return {"characters": [], "plans": []}

    def character_detail(self, character_id, plan_name):
        self.calls.append(("character_detail", character_id, plan_name))
        return {"ok": True, "requirements": []}

    def authenticate(self):
        self.calls.append(("authenticate",))

    def cancel_auth(self):
        self.calls.append(("cancel_auth",))

    def forget(self, character_id):
        self.calls.append(("forget", character_id))
        return self.forget_result

    def refresh_characters(self):
        self.calls.append(("refresh_characters",))

    def reload_plans(self):
        self.calls.append(("reload_plans",))

    def open_plans_folder(self):
        self.calls.append(("open_plans_folder",))

    def plan_text(self, plan_name):
        self.calls.append(("plan_text", plan_name))
        return self.plan_text_result

    def select_plan(self, plan_name):
        self.calls.append(("select_plan", plan_name))
        return True

    def set_character_group(self, character_id, group_name):
        self.calls.append(("set_character_group", character_id, group_name))
        return self.group_result

    def select_group(self, group_name):
        self.calls.append(("select_group", group_name))
        return True

    def rename_group(self, old_name, new_name):
        self.calls.append(("rename_group", old_name, new_name))
        return True

    def delete_group(self, name):
        self.calls.append(("delete_group", name))
        return True

    def shutdown(self):
        self.calls.append(("shutdown",))


def make(tmp_path, skills=None):
    api = make_api(tmp_path, window=FakeWindow(), skills=skills)
    return api, skills


def test_reads_return_the_controllers_payload(tmp_path):
    api, skills = make(tmp_path, FakeSkills())

    assert api.skills_state() == {"characters": [], "plans": []}
    assert api.skills_character_detail(95, "Interceptor")["ok"] is True
    assert skills.calls[1] == ("character_detail", 95, "Interceptor")


def test_every_mutation_returns_truthy(tmp_path):
    """WM.send resolves to null on a bridge failure, so the page cannot tell
    a method that returned None from a call that never landed. ui/api.py
    records that returning None from a no-op WAS the bug -- the redundant
    preview toggle read as a broken call and reverted the checkbox.

    Every mutation here therefore returns True, INCLUDING the paths that
    did nothing."""
    api, _ = make(tmp_path, FakeSkills())

    assert api.skills_add_character() is True
    assert api.skills_cancel_auth() is True
    assert api.skills_refresh() is True
    assert api.skills_reload_plans() is True
    assert api.skills_open_plans_folder() is True
    assert api.skills_select_plan("Interceptor") is True
    assert api.skills_set_character_group(95, "Wolfpack") is True
    assert api.skills_select_group("Wolfpack") is True
    assert api.skills_rename_group("Wolfpack", "Nightcrew") is True
    assert api.skills_delete_group("Wolfpack") is True


def test_the_group_methods_delegate_to_the_controller(tmp_path):
    api, skills = make(tmp_path, FakeSkills())

    api.skills_set_character_group(7, "Wolfpack")
    api.skills_select_group("Wolfpack")
    api.skills_rename_group("Wolfpack", "Nightcrew")
    api.skills_delete_group("Wolfpack")

    assert skills.calls == [
        ("set_character_group", 7, "Wolfpack"),
        ("select_group", "Wolfpack"),
        ("rename_group", "Wolfpack", "Nightcrew"),
        ("delete_group", "Wolfpack"),
    ]


def test_a_refused_assignment_reports_the_controllers_answer(tmp_path):
    """A façade that swallowed False would tell the page a refused change
    succeeded -- an over-long name would look like it had been applied."""
    api, skills = make(tmp_path, FakeSkills())
    skills.group_result = False

    assert api.skills_set_character_group(7, "W" * 200) is False


class FakeAuthority:
    def __init__(self, forget_result=None):
        self.calls = []
        self.forget_result = forget_result or MutationResult(True, True, "")

    def authenticate_skills(self):
        self.calls.append(("authenticate_skills",))
        return MutationResult(True, True, "")

    def cancel_auth(self):
        self.calls.append(("cancel_auth",))

    def forget(self, character_id):
        self.calls.append(("forget", character_id))
        return self.forget_result

    def shutdown(self):
        self.calls.append(("shutdown",))


def test_authorization_and_forget_delegate_to_shared_authority(tmp_path):
    authority = FakeAuthority()
    api = make_api(
        tmp_path, window=FakeWindow(), skills=FakeSkills(), authority=authority
    )

    assert api.skills_add_character() is True
    assert api.skills_cancel_auth() is True
    assert api.skills_forget_character("42") is True

    assert authority.calls == [
        ("authenticate_skills",),
        ("cancel_auth",),
        ("forget", 42),
    ]


def test_forget_rejects_an_invalid_id_before_shared_authority(tmp_path):
    authority = FakeAuthority()
    api = make_api(
        tmp_path, window=FakeWindow(), skills=FakeSkills(), authority=authority
    )

    assert api.skills_forget_character(None) is False
    assert api.skills_forget_character(True) is False
    assert authority.calls == []


def test_forget_reports_shared_authority_refusal(tmp_path):
    authority = FakeAuthority(MutationResult(False, False, "Reconcile first."))
    api = make_api(
        tmp_path, window=FakeWindow(), skills=FakeSkills(), authority=authority
    )

    assert api.skills_forget_character(42) is False
    assert authority.calls == [("forget", 42)]


def test_every_method_tolerates_no_controller(tmp_path):
    """The controller is None when it failed to build. Every call site
    returns a safe value rather than platform-checking or raising -- the
    same posture build_preview_host()'s None takes, and the reason the page
    needs no capability probe."""
    api, _ = make(tmp_path, None)

    assert api.skills_state()["characters"] == []
    assert api.skills_character_detail(95, "x")["ok"] is False
    assert api.skills_add_character() is True
    assert api.skills_cancel_auth() is True
    assert api.skills_forget_character(95) is False
    assert api.skills_refresh() is True
    assert api.skills_reload_plans() is True
    assert api.skills_open_plans_folder() is True
    assert api.skills_select_plan("x") is True
    assert api.skills_set_character_group(95, "Wolfpack") is True
    assert api.skills_select_group("Wolfpack") is True
    assert api.skills_rename_group("Wolfpack", "Nightcrew") is True
    assert api.skills_delete_group("Wolfpack") is True
    assert api.skills_plan_text("x") == ""
    api.shutdown_skills()


def test_the_empty_state_has_the_same_shape_as_a_real_one(tmp_path):
    """One renderer, one shape. A payload missing keys when the subsystem is
    absent means every access in skills.js needs a guard, and the one that
    gets forgotten throws inside a click handler."""
    api, _ = make(tmp_path, None)

    payload = api.skills_state()

    for key in (
        "auth_configured",
        "auth_in_progress",
        "refresh_in_flight",
        "selected_plan_name",
        "selected_group",
        "groups",
        "plans",
        "characters",
        "plan_issues",
        "warnings",
        "plans_updated_utc",
    ):
        assert key in payload
    assert payload["auth_configured"] is False


def test_migration_failure_is_visible_in_the_unavailable_payload(tmp_path):
    api = make_api(
        tmp_path,
        window=FakeWindow(),
        authority_warnings=["Restore eve_skills.json, then restart Wingman."],
    )

    assert api.skills_state()["warnings"] == [
        "Restore eve_skills.json, then restart Wingman."
    ]


def test_shutdown_skills_never_raises(tmp_path):
    """Called last on every exit path, after the window has gone."""

    class Exploding(FakeSkills):
        def shutdown(self):
            raise RuntimeError("teardown")

    api, _ = make(tmp_path, Exploding())

    api.shutdown_skills()


def test_the_api_still_exposes_no_public_non_method_attributes(tmp_path):
    """test_api.py:114 asserts this globally; repeated here because adding a
    public `skills` attribute holding a controller is exactly the shape that
    sent pywebview's proxy walk into WinForms and killed the process eight
    seconds after launch."""
    api, _ = make(tmp_path, FakeSkills())

    for name in dir(api):
        if name.startswith("_"):
            continue
        assert callable(getattr(api, name)), f"{name} is not a method"


# --- Skills 8: one time vocabulary ------------------------------------------


class SkillsWithFetchTimes(FakeSkills):
    """A controller whose payload carries the fetch stamps the real one does."""

    def __init__(self, characters):
        super().__init__()
        self._characters = characters

    def state_payload(self):
        self.calls.append(("state_payload",))
        return {"characters": list(self._characters), "plans": []}


def test_each_character_carries_a_rendered_fetch_label(tmp_path):
    """Skills rendered "8/25/2026, 12:12:28 AM" with the page's own
    toLocaleString while the Uploader said "5h ago". The page should not be
    inventing a time format nothing else in the app agrees with."""
    import datetime

    stamped = (
        datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=5)
    ).isoformat()
    api, _ = make(
        tmp_path,
        SkillsWithFetchTimes(
            [
                {"character_id": 1, "fetched_utc": stamped},
                {"character_id": 2, "fetched_utc": ""},
            ]
        ),
    )

    characters = api.skills_state()["characters"]

    assert characters[0]["fetched_label"] == "Last fetched 5h ago"
    assert characters[1]["fetched_label"] == "Never fetched"


def test_the_raw_fetch_stamp_survives_beside_the_label(tmp_path):
    """skills.js reads fetched_utc for its own staleness logic. The label is
    an addition, not a replacement -- dropping the raw value would break the
    freshness badge."""
    api, _ = make(
        tmp_path,
        SkillsWithFetchTimes(
            [{"character_id": 1, "fetched_utc": "2026-08-25T04:00:00"}]
        ),
    )

    (character,) = api.skills_state()["characters"]

    assert character["fetched_utc"] == "2026-08-25T04:00:00"
    assert character["character_id"] == 1


def test_labelling_does_not_mutate_the_controllers_own_dicts(tmp_path):
    """controller.py is the only writer of the skills state document, and
    state_payload may hand back structures the document still references. A
    presentation key written into those would be one save away from being
    persisted -- and a stored relative time is wrong within the hour."""
    original = {"character_id": 1, "fetched_utc": ""}
    api, _ = make(tmp_path, SkillsWithFetchTimes([original]))

    api.skills_state()

    assert "fetched_label" not in original


def test_a_payload_without_characters_is_passed_through_untouched(tmp_path):
    """The empty-state payload and any future shape must not throw here."""
    api, _ = make(tmp_path, FakeSkills())

    assert api.skills_state() == {"characters": [], "plans": []}


def _status_lines(window):
    """Every onStatus text the api pushed at the fake window, in order."""
    import json
    import re

    out = []
    for script in window.calls:
        match = re.search(r"window\.onStatus\((.*)\)$", script)
        if match:
            out.append(json.loads(match.group(1)))
    return out


def test_copying_a_plan_returns_its_text_without_claiming_clipboard_success(tmp_path):
    """The browser owns the clipboard write, so only it can report success.

    Python still reports a vanished plan, which it alone can diagnose before
    returning to the page.
    """
    api = make_api(tmp_path, window=FakeWindow(), skills=FakeSkills())

    assert api.skills_plan_text("Ishtar") == "Navigation IV\n"
    assert api._skills.calls[-1] == ("plan_text", "Ishtar")
    assert _status_lines(api._window) == []


def test_a_plan_that_no_longer_exists_is_reported_not_silent(tmp_path):
    """ "" is a plan the last reload invalidated, never an empty plan:
    plans.parse rejects a file with no requirements, so a listed plan always
    has at least one. The page copies nothing; the strip says why."""
    skills = FakeSkills()
    skills.plan_text_result = ""
    api = make_api(tmp_path, window=FakeWindow(), skills=skills)

    assert api.skills_plan_text("Ishtar") == ""
    line = _status_lines(api._window)[-1]
    assert line["kind"] == "WARNING" and "Reload plans" in line["text"]
