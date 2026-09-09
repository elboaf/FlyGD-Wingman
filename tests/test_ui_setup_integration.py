"""Facade-to-publication contracts on independent synthetic recipient data.

Only the OS process probe, worker scheduling and page are external doubles.
The lossless variant substitutes codec transport; native uses the bundled-path
resolver and real release subprocess, including encode/read-back verification.
Detailed authority/race permutations remain in test_ui_setup_controller.py.
"""

import copy
import json
from pathlib import Path

import pytest
import yaml

from tests import fakes
from tests.setup_fixtures import (
    install_lossless_codec,
    native_with_tabs,
    seed_profile,
    source_with_tabs,
    wire_with_tabs,
)
from tests.test_evesettings_codec import CODEC
from tests.test_evesettings_controller import QueuedThreads
from tests.test_setup_catalog import ADMITTED_SETUPS
from tests.test_ui_setup_controller import files_under
from tests.test_ui_setup_documents import value
from wingman import atomicio, paths, settings
from wingman.evesettings import codec


@pytest.fixture
def pipeline(request, tmp_path, monkeypatch):
    if request.param == "lossless":
        install_lossless_codec(monkeypatch)
    else:
        # No availability skip or external/debug executable fallback: this is
        # also a regression guard for CI's before-pytest installation step.
        assert CODEC.is_file() and codec.codec_available(), (
            "Build the locked release settings codec and copy it to packaging/bin "
            "before running native setup integration tests."
        )
        assert Path(paths.codec_exe()).resolve() == CODEC.resolve()
    source = seed_profile(tmp_path, case="source", name="Source")
    base = seed_profile(tmp_path)
    (base.profile / "core_char_31.dat").write_bytes(b"unselected recipient character")
    (base.profile / "core_user_99.dat").write_bytes(b"unselected recipient account")
    (base.profile / "cache.txt").write_bytes(b"not profile settings")
    api, _window = fakes.build_api(
        tmp_path,
        settings={
            "eve_settings": {
                "root": str(source.root),
                "server": str(source.server),
                "profile": str(source.profile),
                "account_names": {
                    "10": "Synthetic source",
                    "20": "Synthetic recipient",
                },
                "account_characters": {"10": ["11"], "20": ["30", "31"]},
            }
        },
    )
    queued = QueuedThreads()
    api._spawn = queued.spawn
    api._eve_profile_copy_refusal = lambda: None
    sent = fakes.record_pushes(api)
    return api, source, base, queued, sent


def exported_text(api, source):
    result = api.eve_settings_setup_export(
        str(source.profile), str(source.account_path), str(source.character_path)
    )
    assert result["ok"], result
    # Assert independently of the adapter's summary/projection: the effective
    # source override, not its saved [25, 26] body, must cross this boundary.
    body = json.loads(result["text"])
    assert body["overview"]["presets"][0] == {
        "name": "Synthetic Fleet",
        "groups": [25, 27],
        "filteredStates": [9],
        "alwaysShownStates": [12],
    }
    for private in (
        str(source.profile),
        "syntheticPrivate",
        "had_crc",
        "content_revision",
    ):
        assert private not in result["text"]
    return result["text"]


def review(api, base, text, *, keep=False):
    return api.eve_settings_setup_review(
        text,
        str(base.profile),
        str(base.account_path),
        str(base.character_path),
        "Imported",
        keep_ship_labels=keep,
    )


def create(api, base, queued, sent, reviewed):
    assert reviewed["ok"], reviewed
    destination = base.server / "settings_Imported"
    assert not destination.exists()
    assert api.eve_settings_setup_create(reviewed["review_id"], "integration-1") == {
        "accepted": True,
        "error": None,
    }
    assert not destination.exists()
    assert fakes.payloads(sent, "onEveSettingsDone") == []
    queued.run_next()
    [done] = fakes.payloads(sent, "onEveSettingsDone")
    assert done["request_id"] == "integration-1"
    assert done["review_id"] == reviewed["review_id"]
    assert done["operation"] == "ui_setup_create"
    assert not list(base.server.glob(".wingman-profile-copy-*"))
    assert not api.eve_settings_setup_create(reviewed["review_id"], "replay")[
        "accepted"
    ]
    return destination, done


def assert_recipient_preserved(base, destination, before):
    assert {path: path.read_bytes() for path in before} == before
    assert {p.name for p in destination.iterdir()} == {
        "core_user_20.dat",
        "core_char_30.dat",
        "core_user_99.dat",
        "core_char_31.dat",
        "core_public__.yaml",
        "prefs.ini",
    }
    for name, expected in {
        "core_public__.yaml": b"# synthetic recipient local preferences\r\nuiScale: 1.25\r\n",
        "prefs.ini": b"; synthetic recipient local preferences\r\nmonitor=2\r\n",
        "core_char_31.dat": b"unselected recipient character",
        "core_user_99.dat": b"unselected recipient account",
    }.items():
        assert (destination / name).read_bytes() == expected
    account = codec.read_document(destination / base.account_path.name)
    character = codec.read_document(destination / base.character_path.name)
    assert account.had_crc is character.had_crc is False
    assert account.doc["bytes:syntheticPrivate"] == {
        "bytes:accountID": 20,
        "bytes:marker": "utf8:Synthetic private recipient account",
    }
    assert character.doc["bytes:syntheticPrivate"] == {
        "bytes:characterID": 30,
        "bytes:marker": "utf8:Synthetic private recipient character",
    }
    # Whole non-owned sections, including original local timestamps, survive.
    original_a = codec.read_document(base.account_path)
    original_c = codec.read_document(base.character_path)
    for section in ("audio", "defaultoverview"):
        assert account.doc[f"bytes:{section}"] == original_a.doc[f"bytes:{section}"]
    for key in ("presetHistoryKeys", "restoreData", "activeOverviewPreset"):
        assert (
            account.doc["bytes:overview"][f"bytes:{key}"]
            == original_a.doc["bytes:overview"][f"bytes:{key}"]
        )
    for key in ("overviewProfileName", "editHistory"):
        assert (
            account.doc["bytes:ui"][f"bytes:{key}"]
            == original_a.doc["bytes:ui"][f"bytes:{key}"]
        )
    assert character.doc["bytes:ui"] == original_c.doc["bytes:ui"]
    assert value(character, "windows", "preferredIdxInStack3") == {
        "bytes:SyntheticRecipientStack": {"utf8:SyntheticPrivateChat": 1}
    }
    assert settings.load()["eve_settings"]["profile"] == str(destination)
    return account, character


@pytest.mark.parametrize("pipeline", ["lossless", "native"], indirect=True)
def test_facade_export_review_create_publishes_exact_recipient_setup(pipeline):
    api, source, base, queued, sent = pipeline
    before = files_under(base.root)
    text = exported_text(api, source)
    context = api.eve_settings_setup_context(str(base.profile))
    assert context["ok"] and context["profile"] == str(base.profile)
    assert {row["id"] for row in context["accounts"]} == {"20", "99"}
    reviewed = review(api, base, text)
    assert files_under(base.root) == before  # Review did not write or publish.
    destination, done = create(api, base, queued, sent, reviewed)
    assert done == {
        "ok": True,
        "operation": "ui_setup_create",
        "request_id": "integration-1",
        "review_id": reviewed["review_id"],
        "published": True,
        "path": str(destination),
        "selection_persisted": True,
        "error_code": "",
        "error": "",
        "warning": "",
    }
    account, character = assert_recipient_preserved(base, destination, before)
    assert value(account, "overview", "tabsByWindowInstanceID") == [
        [0, 1, 2],
        [3, 4, 5],
        [6, 7],
    ]
    assert [
        row["bytes:name"]
        for row in value(account, "overview", "tabsettings_new").values()
    ] == [
        "utf8:Synthetic near",
        "utf8:Synthetic far",
        "utf8:Synthetic travel",
        "utf8:Synthetic fleet",
        "utf8:Synthetic routes",
        "utf8:Synthetic brackets",
        "utf8:Synthetic reserve",
        "utf8:Synthetic retreat",
    ]
    assert value(account, "overview", "overviewProfilePresets") == {
        "utf8:Synthetic Fleet": {
            "bytes:groups": [25, 27],
            "bytes:filteredStates": [9],
            "bytes:alwaysShownStates": [12],
        },
        "utf8:Synthetic Brackets": {
            "bytes:groups": [6, 7],
            "bytes:filteredStates": [],
            "bytes:alwaysShownStates": [],
        },
        "utf8:Synthetic Travel": {
            "bytes:groups": [8],
            "bytes:filteredStates": [9],
            "bytes:alwaysShownStates": [],
        },
        "utf8:Synthetic Local": {
            "bytes:groups": [89],
            "bytes:filteredStates": [],
            "bytes:alwaysShownStates": [10],
        },
        "bytes:DefaultPreset_SyntheticBuiltin": {
            "bytes:groups": [90],
            "bytes:filteredStates": [],
            "bytes:alwaysShownStates": [],
        },
    }
    assert value(account, "overview", "overviewProfilePresets_notSaved") == {
        "utf8:Synthetic Local": {
            "bytes:groups": [86],
            "bytes:filteredStates": [],
            "bytes:alwaysShownStates": [10],
        },
    }
    labels = value(account, "overview", "shipLabels")
    assert [
        (r["bytes:type"], r["bytes:pre"], r["bytes:post"], r["bytes:state"])
        for r in labels
    ] == [
        (None, "utf8:<b>Synthetic flight</b>", "utf8:", 1),
        ("utf8:pilot name", "utf8:Pilot: ", "utf8: | ", 1),
        (None, "utf8:[", "utf8:", 1),
        ("utf8:corporation", "utf8:", "utf8:]", 1),
        (None, "utf8:<br>", "utf8:", 1),
        ("utf8:alliance", "utf8:(", "utf8:)", 1),
        ("utf8:ship type", "utf8: — ", "utf8:", 1),
        (None, "utf8: / ", "utf8:", 1),
        ("utf8:ship name", "utf8:'", "utf8:'", 0),
    ]
    for index, label in enumerate(labels):
        assert type(label["bytes:state"]) is int
        formatting = {
            key: val
            for key, val in label.items()
            if key not in ("bytes:type", "bytes:pre", "bytes:post", "bytes:state")
        }
        assert formatting == (
            {
                "bytes:bold": False,
                "bytes:italic": False,
                "bytes:underline": False,
                "bytes:fontsize": None,
                "bytes:color": None,
            }
            if index in (1, 8)
            else {}
        )
    assert value(character, "windows", "windowSizesAndPositions_1") == {
        "bytes:overview": {"tuple": [100, 120, 340, 500, 1920, 1080]},
        "bytes:overview_1": {"tuple": [-20, 200, 320, 420, 1600, 900]},
        "bytes:overview_2": {"tuple": [900, 100, 300, 400, 1920, 1080]},
        "bytes:overview_3": {"tuple": [630, 330, 280, 360, 1280, 720]},
        "bytes:selecteditemview": {"tuple": [100, 10, 300, 100, 1920, 1080]},
        "bytes:probeScannerWindow": {"tuple": [20, 600, 400, 250, 1600, 900]},
        "bytes:directionalScannerWindow": {"tuple": [430, 600, 350, 250, 1600, 900]},
        "bytes:droneview": {"tuple": [1400, 500, 240, 300, 1920, 1080]},
        "bytes:fleetwindow": {"tuple": [10, 10, 280, 400, 1920, 1080]},
        "bytes:watchlistpanel": {"tuple": [10, 420, 280, 200, 1920, 1080]},
        "bytes:standaloneBookmarkWnd": {"tuple": [10, 630, 280, 200, 1920, 1080]},
        "utf8:SyntheticPrivateChat": {"tuple": [50, 60, 200, 300, 1280, 720]},
    }
    assert value(character, "windows", "openWindows")["bytes:overview_3"] is False
    assert value(account, "ui", "targetOrigin") == {"tuple": [0.25, 0.75]}
    assert value(character, "windows", "shipuialignleftoffset") == -160
    assert value(account, "overview", "flagStates2") == [12, 9]
    # The evidenced legacy integer zero exports as semantic False, unlike
    # label state and target-lock fields, whose physical representation is int.
    assert value(account, "overview", "useSmallText") is False


@pytest.mark.parametrize("pipeline", ["native"], indirect=True)
def test_facade_dat_compat_normalizes_only_projected_values_through_native_codec(
    pipeline,
):
    api, source, base, queued, sent = pipeline
    source_a = codec.read_document(source.account_path)
    value(source_a, "overview", "overviewProfilePresets")[
        "utf8:Synthetic Brackets"
    ].pop("bytes:alwaysShownStates")
    value(source_a, "overview", "overviewProfilePresets_notSaved")[
        "utf8:Synthetic Fleet"
    ].pop("bytes:alwaysShownStates")
    source_labels = value(source_a, "overview", "shipLabels")
    source_labels[0].update({"bytes:bold": 0, "bytes:italic": 0, "bytes:underline": 0})
    source_labels[1].update({"bytes:bold": 1, "bytes:italic": 1, "bytes:underline": 1})
    codec.write_document(source.account_path, source_a, backup=lambda path: None)
    base_a = codec.read_document(base.account_path)
    saved = value(base_a, "overview", "overviewProfilePresets")
    saved["utf8:Synthetic Fleet"].pop("bytes:alwaysShownStates")
    saved["bytes:DefaultPreset_SyntheticBuiltin"].pop("bytes:alwaysShownStates")
    base_labels = value(base_a, "overview", "shipLabels")
    base_labels[0].update({"bytes:bold": 0, "bytes:italic": 0, "bytes:underline": 0})
    base_labels[1]["bytes:underline"] = 1
    codec.write_document(base.account_path, base_a, backup=lambda path: None)
    before = files_under(base.root)

    result = api.eve_settings_setup_export(
        str(source.profile), str(source.account_path), str(source.character_path)
    )
    assert result["ok"], result
    artifact = json.loads(result["text"])
    definitions = {row["name"]: row for row in artifact["overview"]["presets"]}
    assert definitions["Synthetic Fleet"] == {
        "name": "Synthetic Fleet",
        "groups": [25, 27],
        "filteredStates": [9],
        "alwaysShownStates": [],
    }
    assert definitions["Synthetic Brackets"]["alwaysShownStates"] == []
    for field in ("bold", "italic", "underline"):
        assert artifact["overview"]["shipLabels"][0][field] is False
    assert artifact["overview"]["shipLabels"][1]["underline"] is True
    reviewed = review(api, base, result["text"])
    assert files_under(base.root) == before
    destination, done = create(api, base, queued, sent, reviewed)
    assert done["ok"] and done["published"] and done["selection_persisted"]
    account, _character = assert_recipient_preserved(base, destination, before)
    output_saved = value(account, "overview", "overviewProfilePresets")
    assert output_saved["utf8:Synthetic Fleet"] == {
        "bytes:groups": [25, 27],
        "bytes:filteredStates": [9],
        "bytes:alwaysShownStates": [],
    }
    assert output_saved["bytes:DefaultPreset_SyntheticBuiltin"] == {
        "bytes:groups": [90],
        "bytes:filteredStates": [],
    }
    labels = value(account, "overview", "shipLabels")
    for field in ("bold", "italic", "underline"):
        assert labels[0][f"bytes:{field}"] is False
    assert labels[1]["bytes:underline"] is True
    for field in ("bold", "italic"):
        assert type(labels[1][f"bytes:{field}"]) is int
        assert labels[1][f"bytes:{field}"] == 1
    # Explicitly distinguish source integers from encoded output booleans.
    original = codec.read_document(source.account_path)
    assert type(value(original, "overview", "shipLabels")[0]["bytes:bold"]) is int
    assert original == source_a
    result = api.eve_settings_setup_export(
        str(destination),
        str(destination / base.account_path.name),
        str(destination / base.character_path.name),
    )
    assert result["ok"], result
    reexported = json.loads(result["text"])
    assert reexported["overview"]["shipLabels"] == artifact["overview"]["shipLabels"]
    assert reexported["layout"] == artifact["layout"]


@pytest.mark.parametrize("pipeline", ["native"], indirect=True)
@pytest.mark.parametrize("count", [9, 20])
def test_facade_twenty_tab_budget_exports_creates_and_reexports_real_codec(
    pipeline, count
):
    api, source, base, queued, sent = pipeline
    for path, document in zip(
        (source.account_path, source.character_path),
        source_with_tabs(count),
        strict=True,
    ):
        codec.write_document(path, document, backup=lambda path: None)
    before = files_under(base.root)
    text = exported_text(api, source)
    exported = json.loads(text)
    assert exported["version"] == 1
    assert len(exported["overview"]["tabs"]) == count
    assert exported["overview"]["tabs"][-1]["name"] == f"Synthetic tab {count - 1}"
    assert exported["overview"]["windowGroups"] == [list(range(count))]
    reviewed = review(api, base, text)
    assert reviewed["ok"], reviewed
    assert reviewed["summary"]["counts"]["tabs"] == count
    assert files_under(base.root) == before
    destination, done = create(api, base, queued, sent, reviewed)
    assert done["ok"] and done["published"] and done["selection_persisted"]
    account, character = assert_recipient_preserved(base, destination, before)
    assert len(value(account, "overview", "tabsettings_new")) == count
    assert value(character, "windows", "windowSizesAndPositions_1")[
        "bytes:overview"
    ] == {"tuple": [100, 120, 340, 500, 1920, 1080]}
    result = api.eve_settings_setup_export(
        str(destination),
        str(destination / base.account_path.name),
        str(destination / base.character_path.name),
    )
    assert result["ok"], result
    reexported = json.loads(result["text"])
    for field in ("tabs", "windowGroups", "shipLabels", "settings"):
        assert reexported["overview"][field] == exported["overview"][field]
    assert reexported["layout"] == exported["layout"]
    assert result["summary"]["counts"]["tabs"] == count


@pytest.mark.parametrize("pipeline", ["native"], indirect=True)
def test_facade_twenty_one_tabs_cannot_offer_or_create_a_profile(pipeline):
    api, _source, base, queued, sent = pipeline
    before = files_under(base.root)
    refused = review(api, base, json.dumps(wire_with_tabs(21)))
    assert not refused["ok"] and refused["error_code"] == "collection_limit"
    assert not refused["review_id"]
    assert not api.eve_settings_setup_create(refused["review_id"], "oversized")[
        "accepted"
    ]
    assert not queued.queued and not fakes.payloads(sent, "onEveSettingsDone")
    assert files_under(base.root) == before


@pytest.mark.parametrize("pipeline", ["lossless", "native"], indirect=True)
@pytest.mark.parametrize("count", [8, 9, 20])
def test_facade_native_yaml_keeps_distinct_ordered_recipient_labels(pipeline, count):
    api, _source, base, queued, sent = pipeline
    # The recipient fixture's two-record sequence is deliberately NOT the
    # sender's nine records or the YAML's ambiguous nine-record ordering.
    original_a = codec.read_document(base.account_path)
    original_c = codec.read_document(base.character_path)
    before = files_under(base.root)
    text = yaml.safe_dump(native_with_tabs(count), allow_unicode=True)
    refused = review(api, base, text)
    assert not refused["ok"] and refused["needs_label_choice"]
    assert refused["error_code"] == "label_choice_required" and not refused["review_id"]
    assert not api.eve_settings_setup_create(refused["review_id"], "unreviewed")[
        "accepted"
    ]
    reviewed = review(api, base, text, keep=True)
    destination, done = create(api, base, queued, sent, reviewed)
    assert done["published"] and done["selection_persisted"] and not done["error"]
    account, character = assert_recipient_preserved(base, destination, before)
    assert value(account, "overview", "shipLabels") == [
        {
            "bytes:type": None,
            "bytes:pre": "bytes:Synthetic recipient: ",
            "bytes:post": "bytes:",
            "bytes:state": 1,
        },
        {
            "bytes:type": "bytes:pilot name",
            "bytes:pre": "bytes:",
            "bytes:post": "bytes:!",
            "bytes:state": 1,
        },
    ]
    assert (
        account.doc["bytes:overview"]["bytes:shipLabels"]
        == original_a.doc["bytes:overview"]["bytes:shipLabels"]
    )
    assert value(account, "overview", "tabsByWindowInstanceID") == [list(range(count))]
    assert len(value(account, "overview", "tabsettings_new")) == count
    assert reviewed["summary"]["counts"]["tabs"] == count
    assert (
        value(account, "overview", "tabsettings_new")["int:0"]["bytes:overview"]
        == "utf8:Synthetic Filter 00"
    )
    assert value(account, "overview", "overviewProfilePresets")[
        "utf8:Synthetic Filter 00"
    ] == {
        "bytes:groups": [25, 27],
        "bytes:filteredStates": [9],
        "bytes:alwaysShownStates": [12],
    }
    for key in ("windowSizesAndPositions_1", "shipuialignleftoffset"):
        assert (
            character.doc["bytes:windows"][f"bytes:{key}"]
            == original_c.doc["bytes:windows"][f"bytes:{key}"]
        )
    assert value(character, "windows", "openWindows") == {
        "bytes:overview": True,
        "bytes:overview_1": False,
        "bytes:overview_2": False,
        "bytes:overview_3": False,
        "bytes:selecteditemview": False,
        "bytes:droneview": True,
        "bytes:primary_map_panel": True,
        "utf8:SyntheticPrivateChat": False,
    }
    assert value(account, "ui", "targetOrigin") == {"tuple": [0.6, 0.4]}
    assert value(account, "overview", "flagStates2") == [
        0,
        9,
    ]  # Supplied aggregate replaced.
    assert (
        value(account, "overview", "useSmallText") is True
    )  # Omitted option retained.


@pytest.mark.parametrize(
    ("pipeline", "fault"),
    [
        ("lossless", "stale-manifest"),
        ("lossless", "copy"),
        ("lossless", "encode"),
        ("lossless", "publish"),
        ("native", "stale-manifest"),
        ("native", "copy"),
        ("native", "publish"),
    ],
    indirect=["pipeline"],
)
def test_facade_failures_leave_no_partial_profile_and_allow_fresh_review(
    pipeline, monkeypatch, fault
):
    api, source, base, queued, sent = pipeline
    text = exported_text(api, source)
    reviewed = review(api, base, text)
    assert reviewed["ok"], reviewed
    selection = copy.deepcopy(api._profiles._settings)
    before = files_under(base.root)
    with monkeypatch.context() as patch:
        if fault == "stale-manifest":
            # Same-size unselected DAT edit: not just the selected pair's hashes.
            changed = base.profile / "core_char_31.dat"
            changed.write_bytes(b"unselected RECIPIENT character")
            assert len(changed.read_bytes()) == len(before[changed])
            before = files_under(base.root)
        elif fault == "copy":
            original = atomicio.shutil.copyfileobj

            def copyfileobj(src, dst, *args):
                if Path(src.name).name == "prefs.ini":
                    raise OSError("synthetic copy failure")
                return original(src, dst, *args)

            patch.setattr(atomicio.shutil, "copyfileobj", copyfileobj)
        elif fault == "encode":
            original = codec._run
            encodes = 0

            def transport(mode, payload, **kwargs):
                nonlocal encodes
                if mode == "encode":
                    encodes += 1
                    if encodes == 2:
                        raise codec.CodecError("synthetic encode failure")
                return original(mode, payload, **kwargs)

            patch.setattr(codec, "_run", transport)
        else:
            original = Path.rename

            def rename(path, target):
                if Path(target).name == "settings_Imported":
                    raise OSError("synthetic publish failure")
                return original(path, target)

            patch.setattr(Path, "rename", rename)
        if fault == "stale-manifest":
            result = api.eve_settings_setup_create(
                reviewed["review_id"], "integration-1"
            )
            assert not result["accepted"] and "changed" in result["error"]
            assert not queued.queued and fakes.payloads(sent, "onEveSettingsDone") == []
        else:
            destination, done = create(api, base, queued, sent, reviewed)
            assert not destination.exists()
            assert (
                not done["ok"]
                and not done["published"]
                and not done["selection_persisted"]
            )
            assert done["error_code"] == "create_failed"
            assert f"synthetic {fault} failure" in done["error"]
    assert files_under(base.root) == before
    assert api._profiles._settings == selection
    assert not list(base.server.glob(".wingman-profile-copy-*"))
    # Recover through the facade, not by manually unlocking private state.
    retried = review(api, base, text)
    assert retried["ok"] and retried["review_id"] != reviewed["review_id"]
    assert api.eve_settings_setup_discard(retried["review_id"])


def selected_catalog_text(api, preset_id):
    listed = api.eve_settings_setup_catalog()
    assert listed["ok"], listed
    entry = next(row for row in listed["entries"] if row["id"] == preset_id)
    assert entry["sha256"] == ADMITTED_SETUPS[preset_id]["sha256"]
    selected = api.eve_settings_setup_catalog_entry(
        entry["id"], entry["revision"], entry["sha256"]
    )
    assert selected["ok"], selected
    return entry, selected["text"]


@pytest.mark.parametrize("pipeline", ["native"], indirect=True)
@pytest.mark.parametrize("preset_id", ADMITTED_SETUPS)
def test_shipped_catalog_facades_publish_exact_setup_on_independent_recipient(
    pipeline, preset_id
):
    api, _source, base, queued, sent = pipeline
    before = files_under(base.root)
    entry, text = selected_catalog_text(api, preset_id)
    artifact = json.loads(text)
    overview = artifact["overview"]
    facts = ADMITTED_SETUPS[preset_id]
    original = codec.read_document(base.account_path)
    reviewed = review(api, base, text)
    assert files_under(base.root) == before
    destination, done = create(api, base, queued, sent, reviewed)
    assert done["ok"] and done["published"] and done["selection_persisted"]
    account, character = assert_recipient_preserved(base, destination, before)
    assert value(account, "overview", "tabsByWindowInstanceID") == facts["groups"]
    assert overview["windowGroups"] == facts["groups"]

    # All imported filter bodies, not just the ones referenced by current tabs.
    saved = value(account, "overview", "overviewProfilePresets")
    original_saved = value(original, "overview", "overviewProfilePresets")
    assert len(saved) == len(original_saved) + facts["counts"][0]
    for name, record in original_saved.items():
        assert saved[name] == record
    for row in overview["presets"]:
        name = row["name"]
        physical = f"utf8:{name}"
        assert physical in saved, f"Imported preset missing its UTF-8 key: {name}"
        assert saved[physical] == {
            f"bytes:{key}": row[key]
            for key in ("groups", "filteredStates", "alwaysShownStates")
        }
    assert (
        account.doc["bytes:overview"]["bytes:overviewProfilePresets_notSaved"]
        == original.doc["bytes:overview"]["bytes:overviewProfilePresets_notSaved"]
    )
    # Hand-inspected memberships independent of the selected-artifact oracle.
    filter_name, groups, filtered = (
        (
            "<color=0xFFFF9900>❖ Ships: Enemy Utility (red+neutral)</color>",
            [540, 541, 894, 1534],
            [11, 12, 14, 15, 16, 21],
        )
        if preset_id == "iridium-default"
        else (
            "<color=0xFFFFFF66>✥ Target: Titans</color>",
            [30, 90, 863, 864],
            [11, 12, 14, 15, 16, 21, 45, 49],
        )
    )
    assert saved[f"utf8:{filter_name}"] == {
        "bytes:groups": groups,
        "bytes:filteredStates": filtered,
        "bytes:alwaysShownStates": [],
    }
    tabs = value(account, "overview", "tabsettings_new")
    assert len(tabs) == facts["counts"][1]
    for tab in overview["tabs"]:
        record = tabs[f"int:{tab['id']}"]
        for field in ("name", "overview", "bracket"):
            assert record[f"bytes:{field}"] == f"utf8:{tab[field]}"
        for field in ("color", "showAll", "showNone", "showSpecials"):
            assert record[f"bytes:{field}"] == tab[field]
        for field in ("tabColumns", "tabColumnOrder"):
            assert record[f"bytes:{field}"] == [f"bytes:{v}" for v in tab[field]]

    labels = value(account, "overview", "shipLabels")
    semantic_labels = [
        {
            key.removeprefix("bytes:"): item.removeprefix("utf8:")
            if isinstance(item, str)
            else item
            for key, item in record.items()
        }
        for record in labels
    ]
    # Whole ordered sequence, including repeated records if introduced later;
    # JSON equality also catches bool/int changes and optional-field loss.
    assert json.dumps(semantic_labels, sort_keys=True) == json.dumps(
        overview["shipLabels"], sort_keys=True
    )
    assert [(r["type"], r["pre"], r["post"], r["state"]) for r in semantic_labels] == (
        [
            ("pilot name", "", " ", 1),
            ("alliance", "[", "]", 1),
            ("corporation", "[", "]", 1),
            ("linebreak", None, None, None),
            ("ship type", "", "", 1),
            ("ship name", " - ", "", 0),
            (None, "", "", 0),
        ]
        if preset_id == "iridium-default"
        else [
            ("ship type", " ", "", 1),
            ("alliance", " [", "]", 1),
            ("corporation", " [", "]", 1),
            ("ship name", " ", "", 0),
            (None, "", "", 1),
            ("linebreak", None, None, None),
            ("pilot name", " [", "]<color=0xFFFFFFFF><b> -", 1),
        ]
    )
    positions = value(character, "windows", "windowSizesAndPositions_1")
    assert positions["bytes:overview"] == {"tuple": facts["overview_geometry"]}
    state_maps = {
        "open": "openWindows",
        "minimized": "minimizedWindows",
        "collapsed": "collapsedWindows",
        "compact": "compactWindows",
        "locked": "lockedWindows",
        "overlay": "isOverlayedWindows",
        "lightBackground": "isLightBackgroundWindows",
    }
    for window in artifact["layout"]["windows"]:
        key = f"bytes:{window['key']}"
        if window["geometry"] is None:
            assert key not in positions
        else:
            assert window["geometry"][4:] == [2560, 1440]
            assert positions[key] == {"tuple": window["geometry"]}
        for field, mapping in state_maps.items():
            wrapped = character.doc["bytes:windows"].get(f"bytes:{mapping}")
            records = wrapped["tuple"][1] if wrapped is not None else {}
            if field in window["state"]:
                assert records[key] is window["state"][field]
            else:
                assert key not in records
    assert positions["utf8:SyntheticPrivateChat"] == {
        "tuple": [50, 60, 200, 300, 1280, 720]
    }
    assert value(character, "windows", "openWindows")["bytes:overview_3"] is False
    assert "bytes:targetOrigin" not in account.doc["bytes:ui"]
    assert "bytes:targetOriginLocked" not in account.doc["bytes:ui"]
    assert "bytes:shipuialignleftoffset" not in character.doc["bytes:windows"]
    for field, physical in (
        ("flagOrder", "flagOrder2"),
        ("flagStates", "flagStates2"),
        ("backgroundOrder", "backgroundOrder2"),
        ("backgroundStates", "backgroundStates2"),
    ):
        assert value(account, "overview", physical) == overview["settings"][field]
    assert value(account, "overview", "useSmallText") is False

    # Attribution/display metadata is distribution-only, never recipient state.
    recipient_text = json.dumps([account.doc, character.doc], ensure_ascii=False)
    for marker in (
        "overview_sources",
        "layout_author",
        "ui_scale_percent",
        "license_file",
        entry["title"],
        entry["sha256"],
        entry["id"],
        entry["layout_author"],
        *(source["reference"] for source in entry["overview_sources"]),
    ):
        assert marker not in text and marker not in recipient_text
    assert not queued.queued
    assert len(fakes.payloads(sent, "onEveSettingsDone")) == 1


@pytest.mark.parametrize("pipeline", ["native"], indirect=True)
@pytest.mark.parametrize("preset_id", ADMITTED_SETUPS)
def test_shipped_catalog_cannot_publish_a_stale_recipient_review(pipeline, preset_id):
    api, _source, base, queued, sent = pipeline
    _entry, text = selected_catalog_text(api, preset_id)
    reviewed = review(api, base, text)
    assert reviewed["ok"], reviewed
    changed = base.profile / "core_char_31.dat"
    changed.write_bytes(b"unselected RECIPIENT character")
    before = files_under(base.root)
    refused = api.eve_settings_setup_create(reviewed["review_id"], "stale-catalog")
    assert not refused["accepted"] and "changed" in refused["error"]
    assert files_under(base.root) == before
    assert not (base.server / "settings_Imported").exists()
    assert not queued.queued and not fakes.payloads(sent, "onEveSettingsDone")
    fresh = review(api, base, text)
    assert fresh["ok"] and fresh["review_id"] != reviewed["review_id"]
    assert api.eve_settings_setup_discard(fresh["review_id"])
