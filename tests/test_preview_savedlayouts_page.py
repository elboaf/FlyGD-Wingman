"""Production controller payloads and production page ordering, not rendered UI."""

import json
import subprocess
from pathlib import Path

import pytest

from tests.html_tree import PageTree, TextPageTree
from tests.test_api import Api, FakeWindow, make_state, pushes
from wingman import settings


@pytest.mark.parametrize(
    "scenario",
    [
        "reversed",
        "bulk",
        "keybind",
        "retry",
        "draft",
        "early",
        "named",
        "staging",
        "geometry-ack",
        "geometry-getter",
        "geometry-keybind",
        "geometry-staging",
        "geometry-dialog-navigation",
        "geometry-dialog-capture",
        "controls-empty",
        "controls-select",
        "controls-save",
        "controls-apply",
        "controls-update",
        "controls-rename",
        "controls-remove",
        "controls-cancel",
        "controls-errors",
        "controls-pending",
        "controls-staging",
        "controls-capture",
        "controls-busy",
        "row-feedback",
        "row-rejected",
        "controls-unhydrated",
        "controls-unavailable",
        "controls-failed-save",
        "controls-incomplete",
        "controls-reopen",
        "controls-staged-receipt",
    ],
)
def test_saved_layout_page_ordering(tmp_path, scenario, monkeypatch):
    state = make_state(tmp_path)
    with settings.update(state.settings) as doc:
        doc.setdefault("preview", {}).update(seen=["Alice", "Bob"])
    api = Api(state)
    api._window = FakeWindow()
    from wingman.preview.geometry import Rect
    from wingman.preview.layout import Entry

    api._preview_layout_store.replace("Alice", Entry(Rect(1, 2, 500, 300)))
    initial = api.get_preview_hotkey_state()
    hidden = api.set_preview_excluded("Alice", True)
    both = api.set_preview_excluded("Bob", True)
    created = api.create_preview_layout("Hidden")
    record = created["state"]["layouts"][0]
    api.set_preview_excluded("Bob", False)
    visible = api.set_preview_excluded("Alice", False)
    # A blocked native boundary lets the real shared presentation owner sample
    # pending state deterministically; coalescing need not replay every transition.
    pending_states = []
    original = api._apply_preview_layout
    from dataclasses import replace

    def apply_pending(*args):
        api._fleet_worker.iterate_once()
        pending_states.extend(
            payload
            for handler, payload in pushes(api._window)
            if handler == "onPreviewLayouts" and payload["operation"]["pending"]
        )
        return original(*args)

    api._preview_layouts._ports = replace(
        api._preview_layouts._ports, apply=apply_pending
    )
    bulk = api.apply_preview_layout(record["id"], record["revision"])
    pending = pending_states[-1]
    lease = api._preview_layout_admission.try_begin(exclusive=True)
    refused = api.set_preview_excluded("Alice", False)
    api._preview_layout_admission.finish(lease)
    retry = api.set_preview_excluded("Alice", False)
    size_ack = api.set_preview_size("Alice", 600, 400)
    geometry_apply = api.apply_preview_layout(record["id"], record["revision"])
    api.set_preview_size("Alice", 700, 450)
    newer_geometry = api._sample_preview_geometry()
    api._preview_layout_store.replace("Bob", Entry(Rect(5, 6, 640, 480)))
    api.copy_preview_layout("Alice", "Bob")
    newer_copy = api._sample_preview_geometry()
    api.reset_preview_layouts()
    newer_reset = api._sample_preview_geometry()
    duplicate = api.create_preview_layout("HIDDEN")
    stale = api.apply_preview_layout(record["id"], "stale")
    updated = api.update_preview_layout(record["id"], record["revision"])
    updated_record = updated["state"]["layouts"][0]
    renamed = api.rename_preview_layout(
        updated_record["id"], updated_record["revision"], "__proto__"
    )
    renamed_record = renamed["state"]["layouts"][0]
    removed = api.remove_preview_layout(
        renamed_record["id"], renamed_record["revision"]
    )
    with monkeypatch.context() as patch:

        def fail_save(*args, **kwargs):
            raise OSError("Disk unavailable")

        patch.setattr(settings, "_save_locked", fail_save)
        failed_save = api.create_preview_layout("Refused")
    from wingman.preview.savedlayouts import PrimaryLayoutLiveResult

    api._preview_layouts._ports = replace(
        api._preview_layouts._ports,
        refresh_visibility=lambda lease: api._settled_preview_layout(
            PrimaryLayoutLiveResult(
                "incomplete", "Saved, but one preview could not be shown."
            )
        ),
    )
    incomplete = api.set_preview_excluded("Alice", False)
    empty_api = Api(make_state(tmp_path))
    unavailable = empty_api.get_preview_hotkey_state()
    web = Path(__file__).parents[1] / "wingman/web"
    data = tmp_path / "page.json"
    tree = TextPageTree()
    tree.feed((web / "index.html").read_text(encoding="utf-8"))
    data.write_text(
        json.dumps(
            {
                "scenario": scenario,
                "page": tree.root,
                "initial": initial,
                "hidden": hidden,
                "both": both,
                "visible": visible,
                "bulk": bulk,
                "pending": pending,
                "refused": refused,
                "retry": retry,
                "created": created,
                "duplicate": duplicate,
                "stale": stale,
                "updated": updated,
                "renamed": renamed,
                "removed": removed,
                "size_ack": size_ack,
                "geometry_apply": geometry_apply,
                "newer_geometry": newer_geometry,
                "newer_copy": newer_copy,
                "newer_reset": newer_reset,
                "failed_save": failed_save,
                "incomplete": incomplete,
                "unavailable": unavailable,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "node",
            str(Path(__file__).parent / "fixtures/preview_savedlayouts.cjs"),
            str(data),
            str(web),
        ],
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS " + scenario in result.stdout


@pytest.mark.parametrize("scenario", ["reversed", "local", "boundary"])
def test_capture_session_page_ordering(tmp_path, scenario):
    state = make_state(tmp_path)
    with settings.update(state.settings) as doc:
        doc.setdefault("preview", {}).update(seen=["Alice", "Bob"])
    api = Api(state)
    web = Path(__file__).parents[1] / "wingman/web"
    tree = PageTree()
    tree.feed((web / "index.html").read_text(encoding="utf-8"))
    data = tmp_path / "capture.json"
    data.write_text(
        json.dumps(
            {
                "scenario": scenario,
                "page": tree.root,
                "initial": api.get_preview_hotkey_state(),
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "node",
            str(Path(__file__).parent / "fixtures/preview_capture_sessions.cjs"),
            str(data),
            str(web),
        ],
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS " + scenario in result.stdout
