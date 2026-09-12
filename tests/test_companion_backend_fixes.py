"""Review regressions through the real host/runtime/controller/family pipeline."""

from contextlib import contextmanager
from dataclasses import replace

import pytest

from tests.test_companion_controller import until
from tests.test_companion_family import BINDING
from tests.test_companion_host import add
from tests.test_companion_host import integrated as integrated
from tests.test_preview_host import crop_pump as crop_pump
from wingman.preview.layout import Rect


def replacement(r, identity, binding):
    r.catalog.rows = (BINDING, binding)
    listing = r.receipt(r.controller.sources())
    row = r.controller.state()["rows"][0]
    return r.controller.select(
        identity,
        listing["sources"][1]["candidate_token"],
        "whole",
        "Replacement",
        "exact",
        binding.title,
        row["generation"],
    )


def settled(r):
    until(lambda: not r.runtime.snapshot().selection_pending)
    r.call(lambda: r.host._companion_family.scan())
    assert r.controller.drain().result(3)
    return r.controller.state()["rows"][0]


@pytest.mark.parametrize("mode", ["whole", "region"])
def test_first_add_preserves_explicit_choice_among_identical_sources(integrated, mode):
    r = integrated
    selected = replace(BINDING, hwnd=11, pid=21)
    r.catalog.rows = (BINDING, selected)
    commands = []
    submit = r.controller._ports.submit_native

    def record(command):
        commands.append(command)
        return submit(command)

    r.controller._ports = replace(r.controller._ports, submit_native=record)
    r.receipt(r.controller.set_master(True))
    listing = r.receipt(r.controller.sources())
    pending = r.controller.select(
        None,
        listing["sources"][1]["candidate_token"],
        mode,
        "Selected map",
        "exact",
        "Mapper",
        None,
    )
    if mode == "region":
        until(lambda: r.picks)
        r.call(
            lambda: r.picks[-1]["on_confirm"](
                selected, Rect(100, 100, 400, 300), selected.client_size
            )
        )
    assert r.receipt(pending)["persisted"]
    row = settled(r)
    assert row["status"] == "live"
    live = r.host._companion_family.live[pending["id"]]
    assert live.binding.hwnd == 11 and not live.window.hidden
    prepare = next(c for c in commands if c.kind == "prepare")
    promote = next(c for c in commands if c.kind == "promote")
    assert prepare.token == promote.token
    assert prepare.token.family_epoch != r.runtime.snapshot().companion_epoch
    assert r.windows[0].closed and r.windows[0] is not live.window
    persisted = r.document["companion_previews"]["definitions"][0]
    assert "selection" not in persisted and "hwnd" not in persisted["source"]
    assert "selection" not in row and "binding" not in row


def test_metadata_edit_keeps_explicit_binding_after_title_change(integrated):
    r = integrated
    identity = add(r)
    live = r.host._companion_family.live[identity]
    r.catalog.rows = (
        replace(BINDING, title="Changed title"),
        replace(BINDING, hwnd=11),
    )
    r.call(lambda: r.host._companion_family.scan())
    assert r.controller.drain().result(3)
    row = r.controller.state()["rows"][0]
    pending = r.controller.edit(
        identity, "Renamed", "exact", "Mapper", row["generation"]
    )
    assert r.receipt(pending)["persisted"]
    settled(r)
    assert r.host._companion_family.live[identity] is live
    assert live.binding.hwnd == 10 and live.binding.title == "Changed title"
    assert not live.window.closed


def test_committed_replacement_source_loss_cannot_relabel_old_live_binding(integrated):
    r = integrated
    identity = add(r)
    old = r.host._companion_family.live[identity].window
    selected = replace(BINDING, hwnd=11, pid=21, title="Notes B")
    submit = r.controller._ports.submit_native

    def lose_source_after_commit(command):
        if command.kind == "promote":
            assert (
                r.document["companion_previews"]["definitions"][0]["source"][
                    "title_hint"
                ]
                == "Notes B"
            )
            r.call(lambda: setattr(r.catalog, "rows", (BINDING,)))
        return submit(command)

    r.controller._ports = replace(
        r.controller._ports, submit_native=lose_source_after_commit
    )
    assert r.receipt(replacement(r, identity, selected))["persisted"]
    row = settled(r)
    assert identity not in r.host._companion_family.live
    assert old.closed
    assert row["status"] != "live"
    assert row["source"]["title_hint"] == "Notes B"


def test_failed_replacement_save_keeps_old_live_binding(integrated):
    r = integrated
    identity = add(r)
    old = r.host._companion_family.live[identity]
    update = r.controller._ports.update_settings

    @contextmanager
    def fail_save():
        with update() as data:
            yield data
            assert r.host._companion_family.live[identity] is old
            assert not old.window.closed and not old.window.hidden
            raise OSError("disk full")

    r.controller._ports = replace(r.controller._ports, update_settings=fail_save)
    pending = replacement(r, identity, replace(BINDING, hwnd=11, title="Notes B"))
    assert not r.receipt(pending)["persisted"]
    row = settled(r)
    assert r.host._companion_family.live[identity] is old
    assert row["status"] == "live" and row["source"]["title_hint"] == "Mapper"
    assert (
        r.document["companion_previews"]["definitions"][0]["source"]["title_hint"]
        == "Mapper"
    )


def test_motion_after_prepare_before_event_keeps_promoted_and_saved_rect_equal(
    integrated,
):
    r = integrated
    identity = add(r)
    old = r.host._companion_family.live[identity].window
    moved = Rect(700, 500, 320, 180)
    event = r.controller.native_event
    prepared_rects = []

    def move_before_delivery(value):
        if value.kind == "prepared":
            prepared_rects.append(value.payload.window)
            old.move(moved)
            getattr(old, "_on_geometry", old.callbacks["on_geometry"])(moved)
        event(value)

    r.controller.native_event = move_before_delivery
    pending = replacement(r, identity, replace(BINDING, hwnd=11, title="Notes B"))
    assert r.receipt(pending)["persisted"]
    settled(r)
    assert prepared_rects and prepared_rects[0] != moved
    assert (
        r.document["companion_previews"]["definitions"][0]["window"] == moved._asdict()
    )
    assert r.host._companion_family.live[identity].window.rect == moved


def test_successful_replacement_retires_old_cleanup_fault(integrated):
    r = integrated
    identity = add(r)
    old = r.host._companion_family.live[identity].window
    old.close_ok = False
    pending = replacement(r, identity, replace(BINDING, hwnd=11, title="Notes B"))
    assert r.receipt(pending)["persisted"]
    until(
        lambda: (
            r.host._companion_family._candidate is not None
            and r.host._companion_family._candidate.terminal == ("promote", None)
        )
    )
    old.close_ok = True
    r.call(lambda: r.host._companion_family.scan())
    row = settled(r)
    assert row["status"] == "live" and row["error"] is None
    assert r.host._companion_family.live[identity].binding.hwnd == 11
    assert r.controller._rows[identity]["binding"].hwnd == 11
