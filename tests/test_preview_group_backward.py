"""Named back binds share forward ownership, history and persistence."""

import copy
import inspect
import json
import subprocess
import threading
from pathlib import Path

import pytest

from tests.test_api import make_api
from tests.test_preview_host import _batch_hotkey_host, _FakeLibs, _FakeUser32
from tests.test_preview_wiring import FakeHost
from wingman import settings
from wingman.preview import gestures, host


@pytest.mark.parametrize(
    "fields,forward,back",
    [
        ({"cycle": "Ctrl+F2"}, "Ctrl+F2", ""),
        ({"cycle_prev": "alt+ctrl+f3"}, "", "Ctrl+Alt+F3"),
        ({"cycle": "broken", "cycle_prev": "Ctrl+F3"}, "", "Ctrl+F3"),
        ({"cycle": "Ctrl+F2", "cycle_prev": None}, "Ctrl+F2", ""),
        ({"cycle": "Ctrl+F2", "cycle_prev": 42}, "Ctrl+F2", ""),
        ({"cycle": "Ctrl+F2", "cycle_prev": "broken"}, "Ctrl+F2", ""),
    ],
)
def test_group_directions_normalize_independently(fields, forward, back):
    result = settings.validated_preview(
        {"hotkeys": {"groups": [{"id": "g:prev", "name": " All back ", **fields}]}}
    )
    assert result["hotkeys"]["groups"] == [
        {"id": "g:prev", "name": "All back", "cycle": forward, "cycle_prev": back}
    ]


@pytest.mark.parametrize("with_host", [False, True])
def test_group_back_api_set_clear_rename_delete_and_forward_signature(
    tmp_path, with_host
):
    native = FakeHost() if with_host else None
    api = make_api(tmp_path, preview_host=native, id_factory=lambda: "g:prev")
    assert list(inspect.signature(api.set_preview_cycle_group_bind).parameters) == [
        "group_id",
        "gesture",
    ]
    assert api.create_preview_cycle_group("All back")["applied"]
    assert api.set_preview_cycle_group_bind("g:prev", "Ctrl+F2")["applied"]
    setter = getattr(api, "set_preview_cycle_group_prev_bind", None)
    assert callable(setter), "Separate public back endpoint"
    result = setter("g:prev", "alt+ctrl+f3")
    expected = [
        {
            "id": "g:prev",
            "name": "All back",
            "cycle": "Ctrl+F2",
            "cycle_prev": "Ctrl+Alt+F3",
        }
    ]
    assert result == {
        "applied": True,
        "persisted": True,
        "error": None,
        "hotkeys": api._preview_hotkeys(),
    }
    assert result["hotkeys"]["groups"] == expected
    assert settings.load()["preview"]["hotkeys"]["groups"] == expected
    if native:
        assert native.hotkeys["groups"] == expected
    # Save-and-report duplicates, not a new duplicate-refusal policy.
    assert setter("g:prev", "Ctrl+F2")["applied"]
    assert api.rename_preview_cycle_group("g:prev", "Alice")["hotkeys"]["groups"] == [
        {"id": "g:prev", "name": "Alice", "cycle": "Ctrl+F2", "cycle_prev": "Ctrl+F2"}
    ]
    assert api.set_preview_binds({"characters": {}, "cycle_next": "", "cycle_prev": ""})
    assert api._preview_hotkeys()["groups"][0]["cycle_prev"] == "Ctrl+F2"
    assert setter("g:prev", "  ")["hotkeys"]["groups"][0]["cycle_prev"] == ""
    assert api._preview_hotkeys()["groups"][0]["cycle"] == "Ctrl+F2"
    assert api.delete_preview_cycle_group("g:prev")["hotkeys"]["groups"] == []
    assert not setter("g:prev", "Ctrl+F3")["applied"]


@pytest.mark.parametrize(
    "gid,gesture",
    [
        (None, "Ctrl+F3"),
        (42, "Ctrl+F3"),
        ("", "Ctrl+F3"),
        ("stale", "Ctrl+F3"),
        ("g", None),
        ("g", 42),
        ("g", "broken"),
    ],
)
def test_group_back_api_refuses_invalid_boundary_without_delivery(
    tmp_path, gid, gesture
):
    native = FakeHost()
    api = make_api(tmp_path, preview_host=native, id_factory=lambda: "g")
    api.create_preview_cycle_group("DPS")
    before = copy.deepcopy(api._state.settings)
    delivered = native.hotkeys
    setter = getattr(api, "set_preview_cycle_group_prev_bind", None)
    assert callable(setter), "Separate public back endpoint"
    result = setter(gid, gesture)
    assert not result["applied"] and not result["persisted"] and result["error"]
    assert api._state.settings == before
    assert native.hotkeys is delivered


def test_group_back_api_save_failure_rolls_back_and_never_delivers(
    tmp_path, monkeypatch
):
    native = FakeHost()
    api = make_api(tmp_path, preview_host=native, id_factory=lambda: "g")
    api.create_preview_cycle_group("DPS")
    before = copy.deepcopy(api._state.settings)
    delivered = native.hotkeys
    setter = getattr(api, "set_preview_cycle_group_prev_bind", None)
    assert callable(setter), "Separate public back endpoint"

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(settings, "_save_locked", fail)
    result = setter("g", "Ctrl+F3")
    assert not result["applied"] and not result["persisted"] and result["error"]
    assert api._state.settings == before
    assert native.hotkeys is delivered
    assert result["hotkeys"]["groups"][0]["cycle_prev"] == ""


def test_group_direction_writes_serialize_without_lost_fields(tmp_path):
    native = FakeHost()
    api = make_api(tmp_path, preview_host=native, id_factory=lambda: "g")
    api.create_preview_cycle_group("DPS")
    setter = getattr(api, "set_preview_cycle_group_prev_bind", None)
    assert callable(setter), "Separate public back endpoint"
    entered, release, started = threading.Event(), threading.Event(), threading.Event()
    deliveries, results = [], []

    def deliver(table):
        deliveries.append(table)
        if len(deliveries) == 1:
            entered.set()
            assert release.wait(2)

    native.set_hotkeys = deliver
    first = threading.Thread(
        target=lambda: results.append(api.set_preview_cycle_group_bind("g", "Ctrl+F2"))
    )

    def back():
        started.set()
        results.append(setter("g", "Ctrl+F3"))

    second = threading.Thread(target=back)
    try:
        first.start()
        assert entered.wait(2)
        second.start()
        assert started.wait(2)
        assert not api._preview_hotkey_lock.acquire(blocking=False)
    finally:
        release.set()
        first.join(2)
        second.join(2)
    assert not first.is_alive() and not second.is_alive()
    assert len(results) == 2 and all(r["applied"] for r in results)
    assert [t["groups"][0] for t in deliveries] == [
        {"id": "g", "name": "DPS", "cycle": "Ctrl+F2", "cycle_prev": ""},
        {"id": "g", "name": "DPS", "cycle": "Ctrl+F2", "cycle_prev": "Ctrl+F3"},
    ]
    assert settings.load()["preview"]["hotkeys"]["groups"] == deliveries[-1]["groups"]


def test_named_back_plans_append_after_all_established_forward_actions():
    plan = host.plan_registrations(
        {
            "characters": {"Alice": "Ctrl+F1"},
            "cycle_next": "Ctrl+F2",
            "cycle_prev": "Ctrl+F3",
            "groups": [
                {"id": "early", "cycle": "Ctrl+F4", "cycle_prev": "Ctrl+F6"},
                {"id": "late", "cycle": "Ctrl+F5", "cycle_prev": "Ctrl+F7"},
                {"id": "back-only", "cycle_prev": "alt+ctrl+f8"},
            ],
        }
    )
    assert [(text, action) for _, text, action in plan] == [
        ("Ctrl+F1", ("focus", ("Alice",))),
        ("Ctrl+F2", ("cycle", 1)),
        ("Ctrl+F3", ("cycle", -1)),
        ("Ctrl+F4", ("cycle_group", "early")),
        ("Ctrl+F5", ("cycle_group", "late")),
        ("Ctrl+F6", ("cycle_group_prev", "early")),
        ("Ctrl+F7", ("cycle_group_prev", "late")),
        ("Ctrl+Alt+F8", ("cycle_group_prev", "back-only")),
    ]


@pytest.mark.parametrize(
    "winner", ["character", "all-forward", "all-back", "later-forward", "earlier-back"]
)
def test_named_back_canonical_duplicates_keep_registration_priority(winner):
    table = {"characters": {}, "groups": [{"id": "early", "cycle_prev": "alt+ctrl+f3"}]}
    if winner == "character":
        table["characters"] = {"Alice": "Ctrl+Alt+F3"}
        expected = ("focus", ("Alice",))
    elif winner.startswith("all"):
        table["cycle_next" if winner == "all-forward" else "cycle_prev"] = "Ctrl+Alt+F3"
        expected = ("cycle", 1 if winner == "all-forward" else -1)
    else:
        table["groups"].append(
            {
                "id": "later",
                "cycle" if winner == "later-forward" else "cycle_prev": "Ctrl+Alt+F3",
            }
        )
        expected = (
            ("cycle_group", "later")
            if winner == "later-forward"
            else ("cycle_group_prev", "early")
        )
    assert [(t, a) for _, t, a in host.plan_registrations(table)] == [
        ("Ctrl+Alt+F3", expected)
    ]


@pytest.mark.parametrize(
    "foreground,history,pending,members,excluded,actions,target,last",
    [
        ("Carol", None, None, ["Alice", "Bravo", "Carol"], [], [2], "Bravo", "Bravo"),
        ("Alice", None, None, ["Alice", "Bravo", "Carol"], [], [2], "Carol", "Carol"),
        (
            "Delta",
            "Carol",
            None,
            ["Alice", "Bravo", "Carol"],
            [],
            [2],
            "Alice",
            "Alice",
        ),
        (None, "Carol", None, ["Alice", "Bravo", "Carol"], [], [2], "Bravo", "Bravo"),
        (None, "Delta", None, ["Alice", "Bravo", "Carol"], [], [2], "Alice", "Alice"),
        (
            None,
            "Alice",
            "Carol",
            ["Alice", "Bravo", "Carol"],
            [],
            [2],
            "Bravo",
            "Bravo",
        ),
        (
            "Carol",
            None,
            "Alice",
            ["Alice", "Bravo", "Carol"],
            [],
            [2],
            "Bravo",
            "Bravo",
        ),
        ("Alice", None, None, ["Alice", "Bravo", "Carol"], [], [1, 2], None, "Alice"),
        (
            "Alice",
            None,
            None,
            ["Alice", "Bravo", "Carol"],
            [],
            [2, 1, 2],
            "Carol",
            "Carol",
        ),
        (
            "Alice",
            None,
            None,
            ["Alice", "Bravo", "Carol"],
            [],
            [3, 2, 4],
            None,
            "Bravo",
        ),
        ("Alice", None, None, ["Alice"], [], [2], None, "Alice"),
        ("Alice", None, None, ["Offline"], [], [2], None, None),
        ("Alice", None, None, ["Bravo"], ["Bravo"], [2], None, None),
        ("Alice", None, None, ["Offline"], [], [3, 2], "Carol", None),
        (
            "Alice",
            None,
            None,
            ["Alice", "Bravo", "Carol", "Offline"],
            ["Carol"],
            [2],
            "Bravo",
            "Bravo",
        ),
    ],
)
def test_named_back_uses_existing_sequential_cursor_and_shared_history(
    monkeypatch, foreground, history, pending, members, excluded, actions, target, last
):
    from types import SimpleNamespace

    h, libs = _batch_hotkey_host()
    libs.user32.GetForegroundWindow = lambda: (
        h._clients[foreground].hwnd if foreground else 0
    )
    h._is_excluded = lambda name: name in excluded
    h._active_hotkeys = {"group_by_character": {name: "g" for name in members}}
    if history:
        h._last_group_cycled["g"] = history
    if pending:
        h._pending_switch = SimpleNamespace(stable_key=pending)
    h._registered = {
        1: ("cycle_group", "g"),
        2: ("cycle_group_prev", "g"),
        3: ("focus", ("Carol",)),
        4: ("cycle", -1),
    }
    activated = []
    monkeypatch.setattr(
        h, "_activate_client", lambda libs, c: activated.append(c.stable_key)
    )
    h._on_hotkeys(libs, actions)
    assert activated == ([target] if target else [])
    assert h._last_group_cycled == ({"g": last} if last else {})


def test_named_back_revocation_keeps_os_cleanup_debt_but_rejects_queued_action(
    monkeypatch,
):
    h, libs = _batch_hotkey_host()
    h._hwnd = 0x99
    monkeypatch.setattr(h, "_post", lambda *args: None)  # drive pump calls below
    table = {
        "groups": [{"id": "g", "cycle_prev": "Ctrl+F3"}],
        "group_by_character": {"Alice": "g", "Bravo": "g", "Carol": "g"},
    }
    h.set_hotkeys(table)
    h._apply_hotkeys(libs, table)
    assert h._registered == {1: ("cycle_group_prev", "g")}
    activated = []
    monkeypatch.setattr(
        h, "_activate_client", lambda libs, c: activated.append(c.stable_key)
    )
    # A committed membership change takes effect even ahead of native REBIND.
    table["group_by_character"] = {"Alice": "g", "Bravo": "g"}
    h.set_hotkeys(table)
    h._on_hotkeys(libs, [1])
    assert activated == ["Bravo"]
    activated.clear()
    h.set_hotkeys({"groups": []})
    monkeypatch.setattr(libs.user32, "UnregisterHotKey", lambda *args: False)
    h._on_hotkeys(libs, [1])
    h._apply_hotkeys(libs, {})
    assert activated == [] and h._registered == {} and h.hotkey_status() == {}
    assert h._registered_text == {1: "Ctrl+F3"}
    monkeypatch.setattr(libs.user32, "UnregisterHotKey", lambda *args: True)
    h._apply_hotkeys(libs, {})
    assert h._registered_text == {}


def test_named_back_os_refusal_is_reported_without_dispatch():
    refused = gestures.parse("Ctrl+F3")
    libs = _FakeLibs(_FakeUser32(refuse={(refused.mods, refused.vk)}))
    h = host.PreviewHost(on_layout_changed=lambda *args: None)
    h._hwnd = 0x99
    h._apply_hotkeys(
        libs, {"groups": [{"id": "g", "cycle": "Ctrl+F2", "cycle_prev": "Ctrl+F3"}]}
    )
    assert h.hotkey_status() == {"Ctrl+F2": True, "Ctrl+F3": False}
    assert h._registered == {1: ("cycle_group", "g")}


@pytest.mark.parametrize(
    "scenario",
    [
        "dev",
        "rows",
        "conflicts",
        "writes",
        "stale",
        "cancel",
        "marker",
        "focus-draft",
        "focus-lifecycle",
        "focus-ownership",
        "focus-stable",
    ],
)
def test_group_backward_page(tmp_path, scenario):
    from tests.html_tree import PageTree
    from wingman.preview.labelmarkers import marker_choices

    root = Path(__file__).resolve().parents[1]
    tree = PageTree()
    tree.feed((root / "wingman/web/index.html").read_text(encoding="utf-8"))
    data = tmp_path / "group-backward.json"
    data.write_text(
        json.dumps(
            {"page": tree.root, "choices": marker_choices(), "scenario": scenario}
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "node",
            str(root / "tests/fixtures/preview_group_backward.cjs"),
            str(data),
            str(root / "wingman/web"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS group backward {scenario}" in result.stdout


def test_group_back_survives_unrelated_transaction_and_reload():
    cfg = settings.load()
    with settings.update(cfg) as doc:
        doc["preview"]["hotkeys"]["groups"] = [
            {"id": "g", "name": "DPS", "cycle": "Ctrl+F2", "cycle_prev": "Ctrl+F3"}
        ]
    with settings.update(cfg) as doc:
        doc["preview"]["show_labels"] = False
    assert settings.load()["preview"]["hotkeys"]["groups"] == [
        {"id": "g", "name": "DPS", "cycle": "Ctrl+F2", "cycle_prev": "Ctrl+F3"}
    ]
