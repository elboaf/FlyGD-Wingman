"""Real controller/native-family transaction seam, with only OS resources doubled."""

import queue
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from tests.test_companion_controller import Harness
from tests.test_companion_family import BINDING, Catalog, Window
from wingman.preview.companionfamily import CompanionFamily
from wingman.preview.companions import (
    CompanionDefinition,
    SourceDescriptor,
    region_from_pixels,
    serialize_definitions,
)
from wingman.preview.layout import Rect


class Integrated:
    def __init__(self, tmp_path, initial=None):
        self.h = Harness(tmp_path, initial)
        self.queue = queue.SimpleQueue()
        self.windows = []
        self.commands = []
        self.catalog = Catalog()
        self.picker_callbacks = None
        self.h.controller._ports = replace(
            self.h.controller._ports, submit_native=self.submit
        )
        self.native = CompanionFamily(
            SimpleNamespace(),
            self.h.controller,
            pump_epoch=1,
            authorized=self.authorized,
            temporary=lambda: True,
            monitors=lambda: [Rect(0, 0, 1920, 1080)],
            catalog=self.catalog,
            create_window=self.window,
            create_picker=self.picker,
        )

    def submit(self, command):
        self.queue.put(command)
        return True

    def authorized(self, token, *, promotion=False):
        live = bool(self.h.runtime.demands and self.h.runtime.demands[-1][0])
        return token.pump_epoch == 1 and (
            live and token.family_epoch == 1
            if promotion or token.selection_lease is None
            else self.h.controller.selection_valid(token)
        )

    def window(self, libs, binding, rect, source, **callbacks):
        window = Window(binding, rect, source, callbacks)
        self.windows.append(window)
        return window

    def picker(self, *args, **callbacks):
        self.picker_callbacks = callbacks
        return SimpleNamespace(
            cancel=lambda reason: callbacks["on_cancel"](reason),
            process_dialog_message=lambda message: False,
        )

    def wait(self, predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            while not self.queue.empty():
                command = self.queue.get_nowait()
                self.commands.append(command)
                self.native.command(command)
            if predicate():
                return
            time.sleep(0.005)
        raise AssertionError("Integrated controller/family did not settle")

    def receipt(self, pending):
        def result():
            return next(
                (
                    r
                    for r in self.h.controller.state()["operations"]
                    if r["operation_id"] == pending["operation_id"] and not r["pending"]
                ),
                None,
            )

        self.wait(result)
        return result()

    def add(self, mode="whole"):
        self.receipt(self.h.controller.set_master(True))
        listing = self.receipt(self.h.controller.sources())
        token = listing["sources"][0]["candidate_token"]
        pending = self.h.controller.select(
            None, token, mode, "Mapper", "exact", "Mapper", None
        )
        if mode == "region":
            self.wait(lambda: self.picker_callbacks is not None)
            self.picker_callbacks["on_confirm"](
                BINDING, Rect(100, 100, 400, 300), BINDING.client_size
            )
        result = self.receipt(pending)
        self.wait(lambda: self.h.runtime.lease is None)
        self.wait(lambda: pending["id"] in self.native.live)
        return pending["id"], result

    def close(self):
        self.h.controller.close_admission()
        self.h.controller.close_publication()
        self.wait(
            lambda: (
                not any(r["pending"] for r in self.h.controller.state()["operations"])
            )
        )
        assert self.h.controller.shutdown()
        assert self.native.close_native()


@pytest.mark.parametrize("mode", ["whole", "region"])
def test_real_family_promotes_saved_definition_and_reset_moves_owned_window(
    tmp_path, mode
):
    i = Integrated(tmp_path)
    try:
        identity, receipt = i.add(mode)
        assert receipt["persisted"]
        live = i.native.live[identity]
        assert not live.window.hidden
        generation = i.h.controller.state()["rows"][0]["generation"]
        live.window.move(Rect(700, 500, 320, 210))
        reset = i.h.controller.reset_geometry(identity, generation)
        assert i.receipt(reset)["persisted"]
        i.wait(lambda: live.window.rect.x == 100)
        assert live.spec.generation == generation + 1
    finally:
        i.close()


def test_saved_region_enable_maps_original_authority_to_new_client_size(tmp_path):
    identity = "11111111111141118111111111111111"
    region = region_from_pixels(Rect(100, 100, 400, 300), (1280, 720))
    definition = CompanionDefinition(
        1,
        identity,
        "Map",
        False,
        "region",
        SourceDescriptor(
            BINDING.executable_path,
            "browser.exe",
            "Browser",
            "Mapper",
            "exact",
            "Mapper",
        ),
        Rect(50, 60, 320, 210),
        region,
    )
    i = Integrated(
        tmp_path, {"enabled": True, "definitions": serialize_definitions((definition,))}
    )
    i.catalog.rows = (replace(BINDING, client_size=(1600, 900)),)
    try:
        pending = i.h.controller.set_enabled(identity, True, 1)
        receipt = i.receipt(pending)
        assert receipt["persisted"] and receipt["applied"]
        i.wait(lambda: identity in i.native.live)
        assert i.native.live[identity].window.source_rect == Rect(125, 125, 500, 375)
    finally:
        i.close()
