"""The nine EVE skills façade methods. The controller is faked whole.

These are pure delegation, so what is worth testing is exactly the two
things delegation gets wrong: what a mutation returns, and what happens when
there is no controller at all.
"""
from tests.fakes import FakeWindow
from tests.test_api import make_api


class FakeSkills:
    """Records calls. The real controller has its own suite."""

    def __init__(self):
        self.calls = []
        self.forget_result = True

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

    def select_plan(self, plan_name):
        self.calls.append(("select_plan", plan_name))
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


def test_forget_reports_the_controllers_answer(tmp_path):
    """The one mutation with a real False: a payload that is not an id."""
    api, skills = make(tmp_path, FakeSkills())
    skills.forget_result = False

    assert api.skills_forget_character(None) is False


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
    api.shutdown_skills()


def test_the_empty_state_has_the_same_shape_as_a_real_one(tmp_path):
    """One renderer, one shape. A payload missing keys when the subsystem is
    absent means every access in skills.js needs a guard, and the one that
    gets forgotten throws inside a click handler."""
    api, _ = make(tmp_path, None)

    payload = api.skills_state()

    for key in ("auth_configured", "auth_in_progress", "refresh_in_flight",
                "selected_plan_name", "plans", "characters", "plan_issues",
                "warnings", "plans_updated_utc"):
        assert key in payload
    assert payload["auth_configured"] is False


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
