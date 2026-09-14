"""Production controller payloads and production page ordering, not rendered UI."""

import json
import subprocess
from pathlib import Path

import pytest

from tests.html_tree import PageTree
from tests.test_api import Api, FakeWindow, make_state, pushes
from wingman import settings


@pytest.mark.parametrize(
    "scenario",
    ["reversed", "bulk", "keybind", "retry", "draft", "early", "named", "staging"],
)
def test_saved_layout_page_ordering(tmp_path, scenario):
    state = make_state(tmp_path)
    with settings.update(state.settings) as doc:
        doc.setdefault("preview", {}).update(seen=["Alice", "Bob"])
    api = Api(state)
    api._window = FakeWindow()
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
    web = Path(__file__).parents[1] / "wingman/web"
    data = tmp_path / "page.json"
    tree = PageTree()
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
