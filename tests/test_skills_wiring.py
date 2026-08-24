"""Wiring for the EVE skills subsystem, mirroring test_preview_wiring.py.

What must hold: the builder runs on every platform, a broken subsystem does
not stop Wingman launching, the callbacks it passes are resolved eagerly,
and main() both constructs it and tears it down.
"""
import inspect

from obs_youtube_uploader import __main__ as main_mod


def test_build_skills_controller_is_not_windows_gated(monkeypatch, tmp_path):
    """Unlike build_preview_host, this one runs everywhere. Twelve of the
    thirteen modules are pure or filesystem-only; the Windows-only piece
    (dpapi) is reached through an injected seam, so gating the whole
    subsystem on sys.platform would take the entire Linux test surface with
    it -- and would make the route dead in development."""
    monkeypatch.setattr(main_mod.sys, "platform", "linux")
    monkeypatch.setattr(main_mod.paths, "state_dir", lambda: tmp_path)

    from tests.test_api import make_api
    controller = main_mod.build_skills_controller(make_api(tmp_path))

    assert controller is not None


def test_build_skills_controller_survives_a_broken_subsystem(monkeypatch):
    """Skills are secondary to the upload workflow. A failure to construct
    them must not stop Wingman launching -- the same posture
    build_preview_host takes, and the reason its whole body is wrapped."""
    assert main_mod.build_skills_controller(object()) is None


def test_the_builder_passes_bound_methods_not_lambdas(monkeypatch, tmp_path):
    """A name resolved lazily inside a lambda is not checked when the
    builder runs, so a wrong module alias ships green and fails on a user's
    machine the first time a push happens.
    tests/test_preview_wiring.py:96-108 records exactly what that cost --
    `save_settings=lambda data: settings.save(data)` with the wrong alias.
    """
    monkeypatch.setattr(main_mod.paths, "state_dir", lambda: tmp_path)

    from tests.test_api import make_api
    api = make_api(tmp_path)
    controller = main_mod.build_skills_controller(api)

    assert controller._push_cb == api._push
    assert controller._alert == api._alert


def test_main_builds_the_controller_and_hands_it_to_the_api():
    """The method existed, was tested directly, and nothing called it -- the
    exact failure test_preview_wiring.py records for previews. A unit test
    on the builder cannot catch that; only reading main() can."""
    src = inspect.getsource(main_mod.main)

    assert "build_skills_controller(api)" in src
    assert "api._skills =" in src


def test_main_tears_the_subsystem_down_last_and_unconditionally():
    """A live loopback socket on the fixed redirect port would make the next
    launch's sign-in fail to bind, and there is no fallback port.

    Unconditionality is checked by INDENTATION against a known sibling
    statement, not by asserting the exact previous line is
    `api.shutdown_previews()`. That neighbour check proved "not inside an
    `if`" only by proxy, and it came with two costs: it forbade a comment
    between the two teardown calls -- which is what forced the Step 8
    deviation the very first time this landed -- and it coupled this test
    to the previews subsystem sitting immediately above, so a future task
    inserting a third subsystem's teardown between them, or reordering the
    two, would break this test even though unconditionality still held.
    Checking indentation instead survives both.
    """
    raw = inspect.getsource(main_mod.main).splitlines()
    stripped = [line.strip() for line in raw if line.strip()]

    assert "api.shutdown_skills()" in stripped
    at = stripped.index("api.shutdown_skills()")
    assert stripped[at + 1] == "return 0", "nothing may run after the teardown"

    # Base indent of main()'s body, taken from a known sibling statement
    # rather than a hardcoded column count.
    base_indent = next(len(line) - len(line.lstrip())
                        for line in raw if line.strip() == "shutdown_engine(engine)")
    skills_line = next(line for line in raw if line.strip() == "api.shutdown_skills()")
    skills_indent = len(skills_line) - len(skills_line.lstrip())
    assert skills_indent == base_indent, "must not be nested inside an `if`"
