"""Preparatory fixture contracts, NOT setup importer or live-EVE acceptance.

Independent literals catch lost label multiplicity, shared mutable factories,
source/recipient conflation, and bypassed codec/file boundaries. Pure projection
and current-client behavior are exercised separately in the adapter tests.
"""

import copy
import hashlib
import json

import pytest

from tests.setup_fixtures import documents, install_lossless_codec, seed_profile, wire
from tests.test_evesettings_codec import CODEC
from wingman.evesettings import codec, formations, tree


def test_fixture_has_the_label_multiplicity_native_yaml_lost():
    labels = wire()["overview"]["shipLabels"]
    assert len(labels) == 9
    assert sum(row["type"] is None for row in labels) == 4
    assert len(wire()["overview"]["tabs"]) == 8
    assert [row["pre"] for row in labels] == [
        "<b>Synthetic flight</b>",
        "Pilot: ",
        "[",
        "",
        "<br>",
        "(",
        " — ",
        " / ",
        "'",
    ]


def test_fixture_preserves_both_observed_label_field_variants():
    account, _ = documents()
    labels = account.doc["bytes:overview"]["bytes:shipLabels"]["tuple"][1]
    assert labels[0] == {
        "utf8:type": None,
        "utf8:pre": "utf8:<b>Synthetic flight</b>",
        "utf8:post": "utf8:",
        "utf8:state": 1,
    }
    assert labels[8] == {
        "bytes:type": "bytes:ship name",
        "bytes:pre": "bytes:'",
        "bytes:post": "bytes:'",
        "bytes:state": 0,
        "bytes:bold": False,
        "bytes:italic": False,
        "bytes:underline": False,
        "bytes:fontsize": None,
        "bytes:color": None,
    }
    assert wire()["overview"]["shipLabels"][8] == {
        "type": "ship name",
        "pre": "'",
        "post": "'",
        "state": 0,
        "bold": False,
        "italic": False,
        "underline": False,
        "fontsize": None,
        "color": None,
    }


def test_fixture_distinguishes_saved_definition_from_effective_override():
    account, _ = documents()
    section = account.doc["bytes:overview"]
    saved = section["bytes:overviewProfilePresets"]["tuple"][1]
    unsaved = section["bytes:overviewProfilePresets_notSaved"]["tuple"][1]
    assert saved["utf8:Synthetic Fleet"]["bytes:groups"] == [25, 26]
    assert unsaved["utf8:Synthetic Fleet"] == {
        "bytes:groups": [25, 27],
        "bytes:filteredStates": [9],
        "bytes:alwaysShownStates": [12],
    }
    assert wire()["overview"]["presets"][0] == {
        "name": "Synthetic Fleet",
        "groups": [25, 27],
        "filteredStates": [9],
        "alwaysShownStates": [12],
    }


def test_fixture_groups_do_not_activate_stale_overview_geometry():
    value = wire()
    assert value["overview"]["windowGroups"] == [[0, 1, 2], [3, 4, 5], [6, 7]]
    assert [row["id"] for row in value["overview"]["tabs"]] == list(range(8))
    assert [row["key"] for row in value["layout"]["windows"]] == [
        "overview",
        "overview_1",
        "overview_2",
        "selecteditemview",
        "probeScannerWindow",
        "directionalScannerWindow",
        "droneview",
        "fleetwindow",
        "watchlistpanel",
        "standaloneBookmarkWnd",
        "solar_system_map_panel",
        "primary_map_panel",
    ]
    _, character = documents()
    windows = character.doc["bytes:windows"]
    assert windows["bytes:windowSizesAndPositions_1"]["tuple"][1][
        "bytes:overview_3"
    ] == {"tuple": [70, 80, 300, 240, 1600, 900]}
    # A stale association must not be erased wholesale as a cache shortcut.
    assert (
        windows["bytes:stacksWindows"]["tuple"][1]["bytes:overview_3"]
        == "bytes:SyntheticStack"
    )


def test_fixture_distinguishes_absent_false_and_default_layout_overrides():
    layout = wire()["layout"]
    assert layout["windows"][0] == {
        "key": "overview",
        "geometry": [100, 120, 340, 500, 1920, 1080],
        "state": {
            "open": True,
            "minimized": False,
            "collapsed": False,
            "compact": True,
            "locked": False,
            "overlay": False,
            "lightBackground": True,
        },
    }
    assert layout["windows"][1]["geometry"] == [-20, 200, 320, 420, 1600, 900]
    assert layout["windows"][-1] == {
        "key": "primary_map_panel",
        "geometry": None,
        "state": {},
    }
    assert layout["targetOrigin"] == [0.25, 0.75]
    assert layout["targetOriginLocked"] is False
    assert layout["hudOffset"] == -160
    _, character = documents()
    windows = character.doc["bytes:windows"]
    assert windows["bytes:openWindows"]["tuple"][1]["bytes:droneview"] is False
    assert "bytes:primary_map_panel" not in windows["bytes:openWindows"]["tuple"][1]
    assert windows["bytes:minimizedWindows"]["tuple"][1]["bytes:overview"] is False
    assert "bytes:overview_2" not in windows["bytes:minimizedWindows"]["tuple"][1]


def test_fixture_encodes_state_keys_and_colours_without_css_substitution():
    account, _ = documents()
    section = account.doc["bytes:overview"]
    assert section["bytes:stateColors"]["tuple"][1] == {
        'json:{"tuple":["bytes:background",9]}': {"tuple": [0.75, 0.0, 0.0, 1.0]},
        'json:{"tuple":["bytes:flag",12]}': {"tuple": [0.0, 0.15, 0.6, 1.0]},
    }
    assert section["bytes:stateBlinks"]["tuple"][1] == {
        'json:{"tuple":["bytes:background",9]}': True,
        'json:{"tuple":["bytes:flag",12]}': False,
    }
    assert wire()["overview"]["settings"]["stateColors"] == [
        {"category": "background", "state": 9, "color": [0.75, 0.0, 0.0, 1.0]},
        {"category": "flag", "state": 12, "color": [0.0, 0.15, 0.6, 1.0]},
    ]


def test_fixture_uses_synthetic_filetime_not_capture_timestamps():
    account, character = documents()
    stamp = account.doc["bytes:overview"]["bytes:shipLabels"]["tuple"][0]
    assert stamp == "long:116444736000000000"
    assert int(stamp.removeprefix("long:")) == formations.filetime(0)
    assert character.doc["bytes:windows"]["bytes:shipuialignleftoffset"] == {
        "tuple": ["long:116444736000000000", -160]
    }


def test_wire_factory_returns_fresh_nested_values():
    first = wire()
    first["overview"]["presets"][0]["groups"].clear()
    first["overview"]["shipLabels"][0]["pre"] = "changed"
    first["layout"]["windows"][0]["geometry"][0] = 999
    second = wire()
    assert second["overview"]["presets"][0]["groups"] == [25, 27]
    assert second["overview"]["shipLabels"][0]["pre"] == "<b>Synthetic flight</b>"
    assert second["layout"]["windows"][0]["geometry"][0] == 100


@pytest.mark.parametrize(
    "case,want_groups,want_x", [("source", [25, 26], 100), ("recipient", [88], 600)]
)
def test_document_factory_is_fresh_and_recipient_is_not_a_sender_clone(
    case, want_groups, want_x
):
    account, character = documents(case)
    account.doc["bytes:overview"]["bytes:overviewProfilePresets"]["tuple"][1][
        "utf8:Synthetic Fleet"
    ]["bytes:groups"].clear()
    character.doc["bytes:windows"]["bytes:windowSizesAndPositions_1"]["tuple"][1][
        "bytes:overview"
    ]["tuple"][0] = 999
    fresh_account, fresh_character = documents(case)
    assert (
        fresh_account.doc["bytes:overview"]["bytes:overviewProfilePresets"]["tuple"][1][
            "utf8:Synthetic Fleet"
        ]["bytes:groups"]
        == want_groups
    )
    assert (
        fresh_character.doc["bytes:windows"]["bytes:windowSizesAndPositions_1"][
            "tuple"
        ][1]["bytes:overview"]["tuple"][0]
        == want_x
    )
    assert fresh_account.had_crc is (case == "source")
    assert fresh_character.had_crc is (case == "source")


def test_portable_fixture_contains_no_internal_or_private_sentinels():
    value = wire()
    assert set(value) == {"format", "version", "type", "overview", "layout"}
    assert (value["format"], value["version"], value["type"]) == (
        "wingman-preset",
        1,
        "ui-setup",
    )
    serialized = json.dumps(value)
    for excluded in (
        "bytes:",
        "utf8:",
        "long:",
        "json:",
        "Synthetic private",
        "SyntheticStack",
        "had_crc",
        "core_user_",
        "core_char_",
        "DefaultPreset_SyntheticBuiltin",
    ):
        assert excluded not in serialized
    # These are invented exclusion probes, not sanitized personal documents.
    account, character = documents("recipient")
    assert account.doc["bytes:syntheticPrivate"]["bytes:accountID"] == 20
    assert character.doc["bytes:syntheticPrivate"]["bytes:characterID"] == 30
    assert account.doc["bytes:ui"]["bytes:editHistory"]["tuple"][1] == [
        "utf8:Synthetic private recipient history"
    ]


def test_seed_profile_exercises_real_discovery_and_preserves_local_bytes(
    tmp_path, monkeypatch
):
    install_lossless_codec(monkeypatch)
    base = seed_profile(tmp_path)
    assert base.root == tmp_path / "EVE"
    assert base.server == base.root / "c_eve_sharedcache_tq_tranquility"
    assert base.profile == base.server / "settings_Base"
    assert base.account_path == base.profile / "core_user_20.dat"
    assert base.character_path == base.profile / "core_char_30.dat"
    found = tree.discover(base.root, server=base.server, profile=base.profile)
    assert [(f.kind, f.file_id) for f in found.accounts] == [("account", "20")]
    assert [(f.kind, f.file_id) for f in found.characters] == [("character", "30")]
    assert tree.is_tranquility_server(base.server)
    assert (
        base.profile / "core_public__.yaml"
    ).read_bytes() == b"# synthetic recipient local preferences\r\nuiScale: 1.25\r\n"
    assert (
        base.profile / "prefs.ini"
    ).read_bytes() == b"; synthetic recipient local preferences\r\nmonitor=2\r\n"
    snapshot = codec.read_snapshot(base.account_path)
    assert snapshot.document.doc["bytes:syntheticPrivate"]["bytes:accountID"] == 20
    assert (
        snapshot.content_revision
        == hashlib.sha256(base.account_path.read_bytes()).hexdigest()
    )


def test_source_seed_has_distinct_documents_ids_and_local_preferences(
    tmp_path, monkeypatch
):
    install_lossless_codec(monkeypatch)
    source = seed_profile(tmp_path, case="source", name="Sender")
    assert source.profile.name == "settings_Sender"
    assert source.account_path.name == "core_user_10.dat"
    assert source.character_path.name == "core_char_11.dat"
    assert (
        codec.read_document(source.account_path).doc["bytes:syntheticPrivate"][
            "bytes:accountID"
        ]
        == 10
    )
    assert (
        source.profile / "core_public__.yaml"
    ).read_bytes() == b"# synthetic source local preferences\nuiScale: 1.0\n"
    assert (
        source.profile / "prefs.ini"
    ).read_bytes() == b"; synthetic source local preferences\nmonitor=1\n"


def test_lossless_transport_keeps_real_revision_and_publication_guards(
    tmp_path, monkeypatch
):
    install_lossless_codec(monkeypatch)
    base = seed_profile(tmp_path)
    snapshot = codec.read_snapshot(base.account_path)
    replacement, _ = documents()
    saved = tmp_path / "backup.dat"
    revision = codec.write_document(
        base.account_path,
        replacement,
        backup=lambda path: saved.write_bytes(path.read_bytes()),
        expected_content_revision=snapshot.content_revision,
    )
    assert (
        codec.read_document(saved).doc["bytes:syntheticPrivate"]["bytes:accountID"]
        == 20
    )
    assert (
        codec.read_document(base.account_path).doc["bytes:syntheticPrivate"][
            "bytes:accountID"
        ]
        == 10
    )
    assert revision == hashlib.sha256(base.account_path.read_bytes()).hexdigest()
    with pytest.raises(codec.ContentChangedError):
        codec.write_document(
            base.account_path,
            snapshot.document,
            backup=lambda path: None,
            expected_content_revision=snapshot.content_revision,
        )
    assert (
        codec.read_document(base.account_path).doc["bytes:syntheticPrivate"][
            "bytes:accountID"
        ]
        == 10
    )


def test_lossless_transport_does_not_bypass_verification_before_publish(
    tmp_path, monkeypatch
):
    install_lossless_codec(monkeypatch)
    base = seed_profile(tmp_path)
    before = base.account_path.read_bytes()
    transport = codec._run
    saved = tmp_path / "backup.dat"

    def damaged_decode(mode, payload, **kwargs):
        result = transport(mode, payload, **kwargs)
        if mode == "decode":
            envelope = json.loads(result)
            envelope["doc"] = {}
            return json.dumps(envelope).encode("utf-8")
        return result

    monkeypatch.setattr(codec, "_run", damaged_decode)
    with pytest.raises(codec.CodecError, match="did not read back identically"):
        codec.write_document(
            base.account_path,
            documents()[0],
            backup=lambda path: saved.write_bytes(path.read_bytes()),
        )
    assert base.account_path.read_bytes() == before
    assert not saved.exists()


@pytest.mark.skipif(not CODEC.is_file(), reason="settings codec not built")
@pytest.mark.parametrize("case", ["source", "recipient"])
@pytest.mark.parametrize("index", [0, 1], ids=["account", "character"])
def test_synthetic_documents_survive_the_real_native_codec_boundary(
    tmp_path, case, index
):
    document = documents(case)[index]
    expected = copy.deepcopy(document)
    target = tmp_path / "synthetic.dat"
    revision = codec.write_document(
        target, document, backup=lambda path: None, exe=lambda: str(CODEC)
    )
    snapshot = codec.read_snapshot(target, exe=lambda: str(CODEC))
    assert snapshot.document == expected
    # Python equality conflates 0/False and 1/True; codec fidelity must not.
    assert json.dumps(snapshot.document.doc, sort_keys=True) == json.dumps(
        expected.doc, sort_keys=True
    )
    assert document == expected, "encoding must not mutate the supplied fixture"
    assert snapshot.content_revision == revision
    if case == "source" and index == 0:
        labels = snapshot.document.doc["bytes:overview"]["bytes:shipLabels"]["tuple"][1]
        assert len(labels) == 9
        assert (
            sum(row.get("bytes:type", row.get("utf8:type")) is None for row in labels)
            == 4
        )
