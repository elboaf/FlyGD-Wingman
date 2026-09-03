"""Wiring for the EVE skills subsystem, mirroring test_preview_wiring.py.

What must hold: the builder runs on every platform, a broken subsystem does
not stop Wingman launching, the callbacks it passes are resolved eagerly,
and main() both constructs it and tears it down.
"""

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

from wingman import __main__ as main_mod
from wingman.eveauth.migration import MigrationResult
from wingman.eveauth.state import AuthorityState


def build_for_test(monkeypatch, tmp_path):
    monkeypatch.setattr(main_mod.paths, "state_dir", lambda: tmp_path)
    from tests.test_api import make_api

    api = make_api(tmp_path)
    migration = main_mod.migrate_eve_authority()
    authority = main_mod.build_authority_controller(api, migration)
    return api, authority, main_mod.build_skills_controller(api, authority)


def test_build_skills_controller_is_not_windows_gated(monkeypatch, tmp_path):
    """Unlike build_preview_host, this one runs everywhere. Twelve of the
    thirteen modules are pure or filesystem-only; the Windows-only piece
    (dpapi) is reached through an injected seam, so gating the whole
    subsystem on sys.platform would take the entire Linux test surface with
    it -- and would make the route dead in development."""
    monkeypatch.setattr(main_mod.sys, "platform", "linux")
    _api, _authority, controller = build_for_test(monkeypatch, tmp_path)

    assert controller is not None


def test_build_skills_controller_survives_a_broken_subsystem(monkeypatch):
    """Skills are secondary to the upload workflow. A failure to construct
    them must not stop Wingman launching -- the same posture
    build_preview_host takes, and the reason its whole body is wrapped."""
    assert main_mod.build_skills_controller(object(), object()) is None


def test_the_builder_passes_bound_methods_not_lambdas(monkeypatch, tmp_path):
    """A name resolved lazily inside a lambda is not checked when the
    builder runs, so a wrong module alias ships green and fails on a user's
    machine the first time a push happens.
    tests/test_preview_wiring.py:96-108 records exactly what that cost --
    `save_settings=lambda data: settings.save(data)` with the wrong alias.
    """
    api, authority, controller = build_for_test(monkeypatch, tmp_path)

    # _push_skills, not _push. It is still a bound method -- which is what
    # this test is about -- and it is the one that adds `fetched_label` to
    # every onSkills payload. Handing the controller the raw _push was D3's
    # bug: the label reached the page on the first render and never again.
    assert controller._push_cb == api._push_skills
    assert controller._alert == api._alert
    assert authority._changed == api._eve_authority_changed


def test_every_pushed_skills_payload_carries_the_fetch_labels(monkeypatch, tmp_path):
    """The gap D3 found, pinned from the wiring end.

    `_with_fetch_labels` was applied by the skills_state METHOD alone, and
    skills.js asks for state on FIRST ENTRY only -- after that every
    mutation pushes. So the labelled payload was the one the user saw
    least, and the page's fallback invented "Never fetched" for every
    character on every render after it. Nothing caught it:
    test_bridge_contract.py checks handler NAMES, not payload shape, and
    nothing in this suite renders the page.

    Checked through the callback the builder actually hands over, not by
    calling _push_skills directly -- the bug was in which function was
    passed, so a test that picks the function itself cannot see it.
    """
    api, _authority, controller = build_for_test(monkeypatch, tmp_path)
    monkey = []
    api._push = lambda handler, payload: monkey.append((handler, payload))
    controller._push_cb(
        "onSkills", {"characters": [{"character_id": 1, "fetched_utc": ""}]}
    )
    controller._push_cb("onSkillsProgress", {"completed": 1, "total": 2})

    assert monkey[0][1]["characters"][0]["fetched_label"] == "Never fetched"
    # Everything else goes through untouched.
    assert monkey[1] == ("onSkillsProgress", {"completed": 1, "total": 2})


def test_production_wiring_migrates_credentials_and_surfaces_recovery_warning(
    monkeypatch, tmp_path
):
    """The startup composition must consume the lossless migration result."""
    monkeypatch.setattr(main_mod.paths, "state_dir", lambda: tmp_path)
    fixture = Path(__file__).parent / "fixtures" / "eveauth" / "legacy-valid.json"
    (tmp_path / "eve_skills.json.bak").write_bytes(fixture.read_bytes())
    from tests.test_api import make_api

    api = make_api(tmp_path)
    authority, skills = main_mod.wire_eve_controllers(api)

    assert authority is not None and skills is not None
    assert authority._state.characters[0].refresh_token_blob == "QUJD"
    saved_skills = json.loads(
        (tmp_path / "eve_skills.json").read_text(encoding="utf-8")
    )
    assert "refresh_token_blob" not in saved_skills["characters"][0]
    assert any(
        "using eve_skills.json.bak" in warning
        for warning in api.skills_state()["warnings"]
    )


def test_wiring_orders_migration_authority_and_feature_registration(monkeypatch):
    """No feature may load credentials before the ordered split completes."""
    order = []
    migration = MigrationResult(AuthorityState(), SimpleNamespace(), True)
    authority = SimpleNamespace(
        register_participant=lambda participant: order.append(("register", participant))
    )
    skills = object()
    fittings = object()
    api = SimpleNamespace(
        _authority=None,
        _skills=None,
        _fittings=None,
        _authority_warnings=[],
    )

    monkeypatch.setattr(
        main_mod,
        "migrate_eve_authority",
        lambda: order.append("migration") or migration,
    )
    monkeypatch.setattr(
        main_mod,
        "build_authority_controller",
        lambda actual_api, actual_migration: (
            order.append(("authority", actual_api, actual_migration)) or authority
        ),
    )
    monkeypatch.setattr(
        main_mod,
        "build_skills_controller",
        lambda actual_api, actual_authority, **kwargs: (
            order.append(("skills", actual_api, actual_authority, kwargs)) or skills
        ),
    )
    monkeypatch.setattr(
        main_mod,
        "build_fittings_controller",
        lambda actual_api, actual_authority: (
            order.append(("fittings", actual_api, actual_authority)) or fittings
        ),
    )

    assert main_mod.wire_eve_controllers(api) == (authority, skills)
    assert order[0] == "migration"
    assert order[1][0] == "authority"
    assert order[2][0] == "skills"
    assert order[3] == ("register", skills)
    assert order[4][0] == "fittings"
    assert order[5] == ("register", fittings)
    assert api._authority is authority and api._skills is skills
    assert api._fittings is fittings


def test_failed_migration_builds_no_empty_authority_and_surfaces_error(monkeypatch):
    """A failed split must leave both EVE consumers unavailable and retryable."""
    migration = MigrationResult(
        None,
        None,
        False,
        ("Recovered evidence was retained.",),
        "Restore eve_skills.json, then restart Wingman.",
    )
    api = SimpleNamespace(
        _authority=None,
        _skills=None,
        _authority_warnings=[],
    )
    monkeypatch.setattr(main_mod, "migrate_eve_authority", lambda: migration)
    monkeypatch.setattr(
        main_mod,
        "build_authority_controller",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("failed migration must not build authority")
        ),
    )

    assert main_mod.wire_eve_controllers(api) == (None, None)
    assert api._authority is None and api._skills is None
    assert api._authority_warnings == [
        "Recovered evidence was retained.",
        "Restore eve_skills.json, then restart Wingman.",
    ]


def test_main_calls_shared_eve_wiring_and_teardown_unconditionally():
    src = inspect.getsource(main_mod.main)

    assert "wire_eve_controllers(api)" in src
    assert "shutdown_eve_controllers(api)" in src


def test_feature_workers_stop_before_shared_authority():
    order = []
    fittings = SimpleNamespace(shutdown=lambda: order.append("fittings"))
    api = SimpleNamespace(
        _fittings=fittings,
        shutdown_skills=lambda: order.append("skills"),
        shutdown_authority=lambda: order.append("authority"),
    )

    main_mod.shutdown_eve_controllers(api)

    assert order == ["fittings", "skills", "authority"]
