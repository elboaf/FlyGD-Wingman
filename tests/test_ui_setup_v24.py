"""V24.01 compatibility rules; synthetic documents and one public default body."""

import copy

import pytest

from tests.setup_fixtures import documents, wire
from tests.test_evesettings_codec import CODEC
from tests.test_ui_setup_documents import apply, incoming, stamp, value
from wingman.evesettings import codec
from wingman.evesettings import setup_documents as adapter
from wingman.evesettings import setup_model as model
from wingman.evesettings.setup_sharing import parse_text


@pytest.mark.parametrize(
    "bracket", [None, "_BracketFilterShowAll"], ids=["null", "all"]
)
def test_brackets_and_flags_preserve_values_without_named_sentinel_definitions(bracket):
    data = wire()
    data["overview"]["tabs"][0].update(
        bracket=bracket, showAll=True, showNone=True, showSpecials=False
    )
    tab = model.validate_wingman(data).overview["tabs"][0]
    assert tab["bracket"] == bracket
    assert tab["showAll"] is True and tab["showNone"] is True
    assert tab["showSpecials"] is False
    assert model.validate_wingman(data).overview["tabs"][1]["showAll"] is False


@pytest.mark.parametrize("field", ["showAll", "showNone", "showSpecials"])
def test_bracket_flags_refuse_integer_truthiness(field):
    data = wire()
    data["overview"]["tabs"][0][field] = 1
    with pytest.raises(model.SetupError):
        model.validate_wingman(data)


def test_native_tab_columns_omissions_remain_partial_not_synthetic_defaults():
    parsed = parse_text(
        "presets: [[Custom, [[groups, []], [filteredStates, []], [alwaysShownStates, []]]]]\n"
        "tabSetup: [[9, [[name, New], [overview, Custom], [bracket, null], [color, null], [showSpecials, true]]]]"
    )
    assert parsed.overview["tabs"] == [
        {
            "id": 9,
            "name": "New",
            "overview": "Custom",
            "bracket": None,
            "color": None,
            "showAll": False,
            "showNone": False,
            "showSpecials": True,
        }
    ]
    assert parsed.overview["windowGroups"] == [[9]]


def test_portable_group_member_order_must_agree_with_tab_sequence():
    data = wire()
    data["overview"]["windowGroups"][0].reverse()
    with pytest.raises(model.SetupError) as caught:
        model.validate_wingman(data)
    assert caught.value.code == "invalid_order"


def test_definition_membership_order_and_duplicates_are_preserved_for_every_field():
    data = wire()
    for field in ("groups", "filteredStates", "alwaysShownStates"):
        data["overview"]["presets"][0][field] = [12, 9, 12]
    parsed = model.validate_wingman(data)
    for field in ("groups", "filteredStates", "alwaysShownStates"):
        assert parsed.overview["presets"][0][field] == [12, 9, 12]


def test_labels_support_only_evidenced_nullable_specials_and_formatting_without_coercion():
    data = wire()
    labels = [
        {"type": "linebreak", "pre": None, "post": None, "state": None},
        {
            "type": None,
            "pre": "literal",
            "post": "",
            "state": 1,
            "bold": 1,
            "italic": 1,
            "fontsize": 11,
            "color": [1.0, 0.9, 0.0],
        },
        {
            "type": "pilot name",
            "pre": "",
            "post": "",
            "state": 0,
            "bold": True,
            "italic": False,
            "underline": True,
            "fontsize": 12,
            "color": None,
        },
    ]
    data["overview"]["shipLabels"] = labels
    result = model.validate_wingman(data).overview["shipLabels"]
    assert result == labels
    assert type(result[1]["bold"]) is int
    assert type(result[2]["bold"]) is bool
    assert set(result[0]) == {"type", "pre", "post", "state"}
    result[1]["color"].clear()
    assert labels[1]["color"] == [1.0, 0.9, 0.0]


@pytest.mark.parametrize(
    "field,value",
    [
        ("fontsize", 13),
        ("fontsize", True),
        ("color", [1, 1, float("nan")]),
        ("bold", 0),
        ("italic", 2),
        ("underline", 1),
    ],
    ids=["font", "font-bool", "nan", "bold0", "italic2", "underline1"],
)
def test_label_extension_does_not_accept_arbitrary_formatting(field, value):
    data = wire()
    data["overview"]["shipLabels"][0][field] = value
    with pytest.raises(model.SetupError):
        model.validate_wingman(data)


def test_native_repeated_linebreak_order_is_unambiguous_but_null_literals_are_not():
    text = (
        "shipLabels: [[linebreak, [[type, linebreak], [pre, null], [post, null], [state, null]]], "
        "[pilot name, [[type, pilot name], [pre, Pilot], [post, ''], [state, 1]]]]\n"
        "shipLabelOrder: [linebreak, pilot name, linebreak]"
    )
    parsed = parse_text(text)
    assert not parsed.ambiguous_labels
    assert [label["type"] for label in parsed.overview["shipLabels"]] == [
        "linebreak",
        "pilot name",
        "linebreak",
    ]
    before = copy.deepcopy(parsed.overview["shipLabels"][2])
    parsed.overview["shipLabels"][0]["pre"] = "changed"
    assert parsed.overview["shipLabels"][2] == before


# Public Jotunn functional data, NOT an invented/private profile record.
# jotunn_default.pyj YAML SHA256 2e89abe9207dd5e166c0c8b2908ccfee07054a7fe4d6af79457c41efc4387185.
PUBLIC_NAME = "DefaultPreset_639431"
PUBLIC_BODY = {
    "groups": [90, 547, 863, 864],
    "filteredStates": [11, 12, 14, 15, 16, 21, 45, 49],
    "alwaysShownStates": [],
}


def physical(body):
    return {f"bytes:{key}": copy.deepcopy(item) for key, item in body.items()}


def native_definition(name, body):
    return model.ParsedSetup(
        "native-yaml", {"presets": [{"name": name, **copy.deepcopy(body)}]}, None
    )


def external_native(*, field="overview", name=PUBLIC_NAME):
    """Bypass parsing to exercise apply's own validation boundary independently."""
    tab = {"id": 0, "name": "General", "overview": name, "bracket": None, "color": None}
    if field == "bracket":
        tab.update(overview="Custom", bracket=name)
    return model.ParsedSetup(
        "native-yaml",
        {
            "presets": [{"name": "Custom", **copy.deepcopy(PUBLIC_BODY)}],
            "tabs": [tab],
            "windowGroups": [[0]],
        },
        None,
    )


@pytest.mark.parametrize("field", ["overview", "bracket"])
@pytest.mark.parametrize(
    "name", [PUBLIC_NAME, "DefaultPreset_639452"], ids=["public", "reported"]
)
def test_native_parser_accepts_exact_external_defaults_without_fabricating_bodies(
    field, name
):
    tab = f"[name, General], [overview, {name}], [bracket, null], [color, null]"
    if field == "bracket":
        tab = f"[name, General], [overview, {name}], [bracket, {name}], [color, null]"
    parsed = parse_text(f"tabSetup: [[0, [{tab}]]]")
    assert parsed.source_kind == "native-yaml"
    assert "presets" not in parsed.overview
    assert parsed.overview["tabs"][0][field] == name
    assert parsed.overview["windowGroups"] == [[0]]


@pytest.mark.parametrize("field", ["overview", "bracket"])
def test_native_mixed_custom_and_external_default_resolves_saved_canonical_body(field):
    account, character = documents("recipient")
    overview = account.doc["bytes:overview"]
    saved = value(account, "overview", "overviewProfilePresets")
    saved[f"bytes:{PUBLIC_NAME}"] = physical(PUBLIC_BODY)
    saved["bytes:DefaultPreset_639432"] = {"future": "unused protected body"}
    parsed = external_native(field=field)
    before = copy.deepcopy((account, character, parsed))
    out_a, out_c = apply(account, character, parsed)
    output_saved = value(out_a, "overview", "overviewProfilePresets")
    assert output_saved == {**saved, "utf8:Custom": physical(PUBLIC_BODY)}
    assert output_saved[f"bytes:{PUBLIC_NAME}"] == physical(PUBLIC_BODY)
    assert (
        value(out_a, "overview", "tabsettings_new")["int:0"][f"bytes:{field}"]
        == f"utf8:{PUBLIC_NAME}"
    )
    assert value(out_a, "overview", "tabsByWindowInstanceID") == [[0]]
    for key in ("overviewProfilePresets_notSaved", "overviewProfilePresets_notSaved2"):
        assert out_a.doc["bytes:overview"].get(f"bytes:{key}") == overview.get(
            f"bytes:{key}"
        )
    assert out_a.doc["bytes:defaultoverview"] == account.doc["bytes:defaultoverview"]
    assert value(out_c, "windows", "windowSizesAndPositions_1") == value(
        character, "windows", "windowSizesAndPositions_1"
    )
    assert (account, character, parsed) == before


@pytest.mark.parametrize("encoding", ["bytes", "utf8"])
def test_native_external_only_preserves_saved_map_stamp_encoding_and_active_reference(
    encoding,
):
    account, character = documents("recipient")
    overview = account.doc["bytes:overview"]
    value(account, "overview", "overviewProfilePresets")[
        f"{encoding}:{PUBLIC_NAME}"
    ] = physical(PUBLIC_BODY)
    overview["bytes:activeOverviewPreset"] = stamp(f"{encoding}:{PUBLIC_NAME}")
    overview["bytes:overviewProfilePresets_notSaved2"] = stamp(
        {f"utf8:{PUBLIC_NAME}": physical({**PUBLIC_BODY, "groups": [1]})}
    )
    parsed = parse_text(
        f"tabSetup: [[0, [[name, General], [overview, {PUBLIC_NAME}], [bracket, {PUBLIC_NAME}], [color, null]]]]"
    )
    before = copy.deepcopy((account, character, parsed))
    out_a, _ = apply(account, character, parsed)
    for key in ("overviewProfilePresets", "activeOverviewPreset"):
        assert out_a.doc["bytes:overview"][f"bytes:{key}"] == overview[f"bytes:{key}"]
    assert value(out_a, "overview", "overviewProfilePresets_notSaved2") == {}
    assert "presets" not in parsed.overview
    assert (account, character, parsed) == before


@pytest.mark.parametrize("generation", ["first", "second", "both", "empty-second"])
def test_native_external_defaults_cleanup_only_imported_names_from_present_overrides(
    generation,
):
    account, character = documents("recipient")
    overview = account.doc["bytes:overview"]
    value(account, "overview", "overviewProfilePresets")[f"utf8:{PUBLIC_NAME}"] = (
        physical(PUBLIC_BODY)
    )
    keys = ("overviewProfilePresets_notSaved", "overviewProfilePresets_notSaved2")
    changed = {**PUBLIC_BODY, "groups": [1]}
    for i, key in enumerate(keys):
        overview.pop(f"bytes:{key}", None)
        if (generation == "first" and i == 1) or (generation == "second" and i == 0):
            continue
        overview[f"bytes:{key}"] = stamp(
            {}
            if generation == "empty-second" and i == 1
            else {
                f"{('bytes', 'utf8')[i]}:{PUBLIC_NAME}": physical(changed),
                "utf8:Custom": physical(changed),
                "bytes:Unrelated": {"future": [1]},
                "bytes:DefaultPreset_639432": {"future": "unreferenced"},
            }
        )
    before = copy.deepcopy((account, character))
    out_a, _ = apply(account, character, external_native())
    for key in keys:
        old = overview.get(f"bytes:{key}")
        current = out_a.doc["bytes:overview"].get(f"bytes:{key}")
        if old is None or not old["tuple"][1]:
            assert current == old
        else:
            assert current["tuple"][1] == {
                "bytes:Unrelated": {"future": [1]},
                "bytes:DefaultPreset_639432": {"future": "unreferenced"},
            }
    assert value(out_a, "overview", "overviewProfilePresets")[
        f"utf8:{PUBLIC_NAME}"
    ] == physical(PUBLIC_BODY)
    assert (account, character) == before


@pytest.mark.parametrize("field", ["overview", "bracket"])
@pytest.mark.parametrize(
    "bad", ["missing", "wrong", "malformed", "unknown-context", "missing-context"]
)
def test_native_external_defaults_refuse_without_supported_canonical_saved_body(
    field, bad
):
    account, character = documents("recipient")
    saved = value(account, "overview", "overviewProfilePresets")
    if bad != "missing":
        saved[f"bytes:{PUBLIC_NAME}"] = (
            {"future": [1]}
            if bad == "malformed"
            else physical(
                {**PUBLIC_BODY, "groups": [1]} if bad == "wrong" else PUBLIC_BODY
            )
        )
    # Even a canonical effective override cannot substitute for a saved body.
    account.doc["bytes:overview"]["bytes:overviewProfilePresets_notSaved2"] = stamp(
        {f"bytes:{PUBLIC_NAME}": physical(PUBLIC_BODY)}
    )
    if bad == "unknown-context":
        account.doc["bytes:defaultoverview"]["bytes:defaultOverviewID"] = stamp(
            "bytes:unknown"
        )
    elif bad == "missing-context":
        del account.doc["bytes:defaultoverview"]["bytes:defaultOverviewID"]
    before = copy.deepcopy((account, character))
    with pytest.raises(model.SetupError) as caught:
        apply(account, character, external_native(field=field))
    assert caught.value.code == (
        "default_context"
        if bad.endswith("context")
        else "recipient_shape"
        if bad == "malformed"
        else "protected_definition"
    )
    assert (account, character) == before


@pytest.mark.parametrize(
    "key",
    ["overviewProfilePresets_notSaved", "overviewProfilePresets_notSaved2"],
    ids=["first", "second"],
)
@pytest.mark.parametrize("bad", ["body", "map", "stamp", "alias"])
def test_native_external_defaults_refuse_malformed_affected_overrides(key, bad):
    account, character = documents("recipient")
    overview = account.doc["bytes:overview"]
    value(account, "overview", "overviewProfilePresets")[f"bytes:{PUBLIC_NAME}"] = (
        physical(PUBLIC_BODY)
    )
    overview["bytes:overviewProfilePresets_notSaved2"] = stamp({})
    body = {f"bytes:{PUBLIC_NAME}": physical(PUBLIC_BODY)}
    if bad == "body":
        body[f"bytes:{PUBLIC_NAME}"] = {"future": [1]}
    elif bad == "alias":
        body[f"utf8:{PUBLIC_NAME}"] = physical(PUBLIC_BODY)
    overview[f"bytes:{key}"] = stamp([] if bad == "map" else body)
    if bad == "stamp":
        overview[f"bytes:{key}"]["tuple"][0] = "not a timestamp"
    before = copy.deepcopy((account, character))
    with pytest.raises(model.SetupError) as caught:
        apply(account, character, external_native())
    assert caught.value.code == "recipient_shape"
    assert (account, character) == before


@pytest.mark.parametrize(
    "name",
    [
        "Recipient Only",
        "defaultpreset_639431",
        "DefaultPreset_639431x",
        "DefaultPreset_639430",
    ],
    ids=["custom", "case", "suffix", "outside"],
)
@pytest.mark.parametrize("field", ["overview", "bracket"])
def test_native_missing_custom_or_lookalike_body_never_borrows_recipient_definition(
    name, field
):
    account, character = documents("recipient")
    value(account, "overview", "overviewProfilePresets")[f"utf8:{name}"] = physical(
        PUBLIC_BODY
    )
    parsed = external_native(field=field, name=name)
    with pytest.raises(model.SetupError) as caught:
        apply(account, character, parsed)
    assert caught.value.code == "dangling_reference"
    tab = f"[name, General], [overview, {name}], [bracket, {name}], [color, null]"
    with pytest.raises(model.SetupError) as caught:
        parse_text(f"tabSetup: [[0, [{tab}]]]")
    assert caught.value.code == "dangling_reference"


@pytest.mark.parametrize("field", ["overview", "bracket"])
def test_full_wingman_still_requires_bodies_for_external_default_names(field):
    data = wire()
    data["overview"]["tabs"][0][field] = PUBLIC_NAME
    with pytest.raises(model.SetupError) as caught:
        model.validate_wingman(data)
    assert caught.value.code == "dangling_reference"
    account, character = documents("recipient")
    value(account, "overview", "overviewProfilePresets")[f"bytes:{PUBLIC_NAME}"] = (
        physical(PUBLIC_BODY)
    )
    parsed = model.ParsedSetup("wingman", data["overview"], data["layout"])
    with pytest.raises(model.SetupError) as caught:
        apply(account, character, parsed)
    assert caught.value.code == "dangling_reference"


@pytest.mark.skipif(not CODEC.is_file(), reason="settings codec not built")
@pytest.mark.parametrize("crc", [False, True], ids=["plain", "crc"])
def test_native_external_default_application_survives_native_codec(tmp_path, crc):
    account, character = documents("recipient")
    value(account, "overview", "overviewProfilePresets")[f"bytes:{PUBLIC_NAME}"] = (
        physical(PUBLIC_BODY)
    )
    account.doc["bytes:overview"]["bytes:overviewProfilePresets_notSaved2"] = stamp(
        {f"bytes:{PUBLIC_NAME}": physical({**PUBLIC_BODY, "groups": [1]})}
    )
    parsed = parse_text(
        "presets: [[Custom, [[groups, [9]], [filteredStates, [12, 9, 12]], [alwaysShownStates, [1, 1]]]]]\n"
        f"tabSetup: [[0, [[name, General], [overview, Custom], [bracket, {PUBLIC_NAME}], [color, null]]]]"
    )
    out = apply(
        codec.Document(account.doc, crc), codec.Document(character.doc, crc), parsed
    )
    readback = []
    for i, document in enumerate(out):
        path = tmp_path / f"ext-{i}.dat"
        codec.write_document(
            path, document, backup=lambda path: None, exe=lambda: str(CODEC)
        )
        readback.append(codec.read_document(path, exe=lambda: str(CODEC)))
    assert tuple(readback) == out
    overview = readback[0].doc["bytes:overview"]
    assert overview["bytes:overviewProfilePresets_notSaved2"]["tuple"][1] == {}
    saved = value(readback[0], "overview", "overviewProfilePresets")
    assert saved[f"bytes:{PUBLIC_NAME}"] == physical(PUBLIC_BODY)
    assert saved["utf8:Custom"] == physical(
        {"groups": [9], "filteredStates": [12, 9, 12], "alwaysShownStates": [1, 1]}
    )
    assert (
        value(readback[0], "overview", "tabsettings_new")["int:0"]["bytes:bracket"]
        == f"utf8:{PUBLIC_NAME}"
    )


def test_exact_jotunn_catalogue_does_not_protect_case_prefix_or_old_pack_names():
    account, _ = documents()
    assert callable(getattr(adapter, "protected_definition_names", None))
    names = adapter.protected_definition_names(account.doc)
    assert names == frozenset(f"DefaultPreset_{i}" for i in range(639431, 639467))
    assert not names.intersection(
        {
            "default",
            "defaultpvp",
            "DefaultPreset_SyntheticBuiltin",
            "DefaultPreset_639431x",
            "defaultpreset_639431",
        }
    )
    # overviewID is recipient metadata, not an alternate catalogue selector.
    account.doc["bytes:defaultoverview"]["bytes:overviewID"] = stamp(
        "utf8:other metadata"
    )
    assert adapter.protected_definition_names(account.doc) == names


@pytest.mark.parametrize(
    "context", [None, "old_default", "unknown"], ids=["absent", "old", "unknown"]
)
def test_context_requires_default_id_not_overview_id_fallback(context):
    account, character = documents("recipient")
    default = account.doc["bytes:defaultoverview"]
    default["bytes:overviewID"] = stamp("bytes:jotunn_default")
    if context is None:
        del default["bytes:defaultOverviewID"]
    else:
        default["bytes:defaultOverviewID"] = stamp(f"bytes:{context}")
    with pytest.raises(model.SetupError) as caught:
        apply(account, character, native_definition("Custom", PUBLIC_BODY))
    assert caught.value.code == "default_context"


@pytest.mark.parametrize(
    "name",
    [
        "Synthetic Fleet",
        "DefaultPreset_SyntheticBuiltin",
        "DefaultPreset_639431x",
        "defaultpreset_639431",
        "defaultpvp",
    ],
    ids=["custom", "prefix", "suffix", "case", "legacy"],
)
def test_custom_upsert_uses_exact_names_and_cleans_both_unsaved_maps(name):
    account, character = documents("recipient")
    overview = account.doc["bytes:overview"]
    value(account, "overview", "overviewProfilePresets")[f"utf8:{name}"] = physical(
        {"groups": [8], "filteredStates": [], "alwaysShownStates": []}
    )
    # Avoid a deliberately invalid dual encoding of the prefix-lookalike fixture.
    if name == "DefaultPreset_SyntheticBuiltin":
        del value(account, "overview", "overviewProfilePresets")[f"bytes:{name}"]
    for key in ("overviewProfilePresets_notSaved", "overviewProfilePresets_notSaved2"):
        overview[f"bytes:{key}"] = stamp(
            {f"utf8:{name}": physical(PUBLIC_BODY), "bytes:Unrelated": {"future": [1]}}
        )
    before = copy.deepcopy((account, character))
    out_a, out_c = apply(account, character, native_definition(name, PUBLIC_BODY))
    assert value(out_a, "overview", "overviewProfilePresets")[
        f"utf8:{name}"
    ] == physical(PUBLIC_BODY)
    for key in ("overviewProfilePresets_notSaved", "overviewProfilePresets_notSaved2"):
        assert value(out_a, "overview", key) == {"bytes:Unrelated": {"future": [1]}}
    assert (account, character) == before and out_c == character
    assert out_a.doc["bytes:defaultoverview"] == account.doc["bytes:defaultoverview"]


@pytest.mark.parametrize(
    "bad",
    ["incoming", "recipient", "both"],
    ids=["incoming", "recipient", "identical-wrong"],
)
def test_protected_bodies_require_public_fingerprint_not_mutual_equality(bad):
    account, character = documents("recipient")
    current = copy.deepcopy(PUBLIC_BODY)
    supplied = copy.deepcopy(PUBLIC_BODY)
    if bad in ("recipient", "both"):
        current["groups"] = [1]
    if bad in ("incoming", "both"):
        supplied["groups"] = [1]
    value(account, "overview", "overviewProfilePresets")[f"bytes:{PUBLIC_NAME}"] = (
        physical(current)
    )
    with pytest.raises(model.SetupError) as caught:
        apply(account, character, native_definition(PUBLIC_NAME, supplied))
    assert caught.value.code == "protected_definition"
    assert PUBLIC_NAME in str(caught.value)


def test_canonical_protected_record_keeps_encoding_and_unused_bad_builtin_is_opaque():
    account, character = documents("recipient")
    presets = value(account, "overview", "overviewProfilePresets")
    presets[f"bytes:{PUBLIC_NAME}"] = physical(PUBLIC_BODY)
    presets["bytes:DefaultPreset_639432"] = {"future": "unused"}
    out_a, out_c = apply(
        account, character, native_definition(PUBLIC_NAME, PUBLIC_BODY)
    )
    assert out_a == account and out_c == character


def test_full_export_is_effective_owned_projection_with_all_customs_and_no_private_state():
    account, character = documents()
    before = copy.deepcopy((account, character))
    assert callable(getattr(adapter, "export_setup", None))
    envelope, warnings = adapter.export_setup(account, character)
    expected = wire()
    expected["overview"]["presets"].append(
        {
            "name": "DefaultPreset_SyntheticBuiltin",
            "groups": [90],
            "filteredStates": [],
            "alwaysShownStates": [],
        }
    )
    assert envelope == expected
    assert type(warnings) is tuple and len(warnings) == 1 and "1" in warnings[0]
    assert (account, character) == before
    envelope["overview"]["presets"][0]["groups"].clear()
    envelope["layout"]["windows"][0]["geometry"].clear()
    assert (account, character) == before


@pytest.mark.parametrize(
    "second",
    [None, {}, {"utf8:Synthetic Fleet": physical(PUBLIC_BODY)}],
    ids=["absent", "empty", "effective"],
)
def test_export_unsaved2_presence_wins_and_orphan_cache_entries_do_not_leak(second):
    account, character = documents()
    overview = account.doc["bytes:overview"]
    value(account, "overview", "overviewProfilePresets_notSaved")["bytes:Orphan"] = {
        "private": "must not export"
    }
    if second is not None:
        overview["bytes:overviewProfilePresets_notSaved2"] = stamp(second)
    envelope, warnings = adapter.export_setup(account, character)
    presets = {row["name"]: row for row in envelope["overview"]["presets"]}
    assert "Orphan" not in presets
    assert presets["Synthetic Fleet"]["groups"] == (
        [25, 27] if second is None else [90, 547, 863, 864] if second else [25, 26]
    )
    assert len(warnings) == (0 if second == {} else 1)


@pytest.mark.parametrize(
    "case", ["missing", "wrong", "canonical"], ids=["missing", "wrong", "canonical"]
)
def test_export_protected_dependencies_only_when_present_and_canonical(case):
    account, character = documents()
    value(account, "overview", "tabsettings_new")["int:0"]["bytes:overview"] = (
        f"bytes:{PUBLIC_NAME}"
    )
    if case != "missing":
        body = (
            PUBLIC_BODY
            if case == "canonical"
            else {"groups": [1], "filteredStates": [], "alwaysShownStates": []}
        )
        value(account, "overview", "overviewProfilePresets")[f"bytes:{PUBLIC_NAME}"] = (
            physical(body)
        )
    if case == "canonical":
        envelope, _ = adapter.export_setup(account, character)
        assert envelope["overview"]["presets"][-1] == {
            "name": PUBLIC_NAME,
            **PUBLIC_BODY,
        }
    else:
        with pytest.raises(model.SetupError):
            adapter.export_setup(account, character)


def test_export_malformed_custom_is_not_silently_skipped_and_unused_builtin_is():
    account, character = documents()
    saved = value(account, "overview", "overviewProfilePresets")
    saved["bytes:DefaultPreset_639432"] = {"future": [1]}
    assert len(adapter.export_setup(account, character)[0]["overview"]["presets"]) == 4
    saved["bytes:Unused custom"] = {"future": [1]}
    with pytest.raises(model.SetupError, match="Unused custom"):
        adapter.export_setup(account, character)


def test_sparse_source_export_sorts_physical_ids_and_normalizes_only_inner_groups():
    account, character = documents()
    records = value(account, "overview", "tabsettings_new")
    records["int:19"] = records.pop("int:0")
    account.doc["bytes:overview"]["bytes:tabsByWindowInstanceID"] = stamp(
        [[19, 2, 1], [5, 4, 3], [7, 6]]
    )
    envelope, _ = adapter.export_setup(account, character)
    assert [tab["id"] for tab in envelope["overview"]["tabs"]] == [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        19,
    ]
    assert envelope["overview"]["windowGroups"] == [[1, 2, 19], [3, 4, 5], [6, 7]]
    out_a, _ = apply(*documents("recipient"), model.validate_wingman(envelope))
    assert value(out_a, "overview", "tabsByWindowInstanceID") == [
        [0, 1, 7],
        [2, 3, 4],
        [5, 6],
    ]
    tabs = value(out_a, "overview", "tabsettings_new")
    assert tabs["int:0"]["bytes:name"] == "utf8:Synthetic far"
    assert tabs["int:7"]["bytes:name"] == "utf8:Synthetic near"


def test_missing_grouping_means_one_existing_group_not_cached_windows():
    account, character = documents()
    del account.doc["bytes:overview"]["bytes:tabsByWindowInstanceID"]
    envelope, _ = adapter.export_setup(account, character)
    assert envelope["overview"]["windowGroups"] == [list(range(8))]
    assert [
        row["key"]
        for row in envelope["layout"]["windows"]
        if row["key"].startswith("overview")
    ] == ["overview"]
    account.doc["bytes:overview"]["bytes:tabsByWindowInstanceID"] = stamp(None)
    with pytest.raises(model.SetupError):
        adapter.export_setup(account, character)


def test_export_tab_column_defaults_follow_physical_keys_not_global_order():
    account, character = documents()
    tab = value(account, "overview", "tabsettings_new")["int:0"]
    del tab["bytes:tabColumns"]
    del tab["bytes:tabColumnOrder"]
    tab["bytes:bracket"] = None
    tab["bytes:showAll"] = True
    tab["bytes:showNone"] = False
    tab["bytes:showSpecials"] = True
    account.doc["bytes:overview"]["bytes:overviewColumnOrder"] = stamp(["bytes:TAG"])
    exported = adapter.export_setup(account, character)[0]["overview"]["tabs"][0]
    assert exported["tabColumns"] == ["ICON", "DISTANCE", "NAME"]
    assert exported["tabColumnOrder"] == [
        "ICON",
        "DISTANCE",
        "NAME",
        "TYPE",
        "TAG",
        "CORPORATION",
        "ALLIANCE",
        "FACTION",
        "MILITIA",
        "SIZE",
        "VELOCITY",
        "RADIALVELOCITY",
        "TRANSVERSALVELOCITY",
        "ANGULARVELOCITY",
    ]
    assert (
        exported["bracket"] is None
        and exported["showAll"] is True
        and exported["showSpecials"] is True
    )
    del account.doc["bytes:overview"]["bytes:overviewColumns"]
    exported = adapter.export_setup(account, character)[0]["overview"]["tabs"][0]
    assert exported["tabColumns"] == ["ICON", "DISTANCE", "NAME", "TYPE", "VELOCITY"]


def test_native_tab_column_omission_keeps_recipient_physical_override_and_retires_surplus():
    account, character = documents("recipient")
    parsed = parse_text(
        "presets: [[Custom, [[groups, []], [filteredStates, []], [alwaysShownStates, []]]]]\n"
        "tabSetup: [[9, [[name, New], [overview, Custom], [bracket, _BracketFilterShowAll], [color, null]]]]"
    )
    out_a, out_c = apply(account, character, parsed)
    tab = value(out_a, "overview", "tabsettings_new")["int:0"]
    assert tab["bytes:tabColumns"] == ["bytes:NAME", "bytes:TYPE"]
    assert tab["bytes:tabColumnOrder"] == ["bytes:NAME", "bytes:TYPE", "bytes:ICON"]
    assert tab["bytes:bracket"] == "utf8:_BracketFilterShowAll"
    assert tab["bytes:showAll"] is False
    assert value(out_a, "overview", "tabsByWindowInstanceID") == [[0]]
    for name in ("overview_1", "overview_2", "overview_3"):
        assert value(out_c, "windows", "openWindows")[f"bytes:{name}"] is False
    assert value(out_c, "windows", "windowSizesAndPositions_1") == value(
        character, "windows", "windowSizesAndPositions_1"
    )
    assert out_a.doc["bytes:ui"] == account.doc["bytes:ui"]


def test_selection_reset_uses_ordinal_zero_and_deletes_markup_name_only():
    account, character = documents("recipient")
    account.doc["bytes:tabgroups"]["bytes:overviewTabs"] = stamp(99)
    account.doc["bytes:tabgroups"]["bytes:overviewTabs_names"] = stamp(
        "utf8:<color=red>old name</color>"
    )
    out_a, _ = apply(account, character)
    assert value(out_a, "tabgroups", "overviewTabs") == 0
    assert type(value(out_a, "tabgroups", "overviewTabs")) is int
    assert "bytes:overviewTabs_names" not in out_a.doc["bytes:tabgroups"]
    assert (
        out_a.doc["bytes:tabgroups"]["bytes:syntheticUnrelatedTab"]
        == account.doc["bytes:tabgroups"]["bytes:syntheticUnrelatedTab"]
    )
    assert value(out_a, "overview", "activeOverviewPreset") == "utf8:Synthetic Local"


@pytest.mark.parametrize("cache", ["SortHeadersSettings2", "SortHeadersSizes"])
def test_tab_cache_reset_removes_only_reused_physical_ids_with_real_tuple_keys(cache):
    account, character = documents("recipient")
    records = {
        'json:{"tuple":["bytes:overviewScroll2",0]}': {"opaque": 1},
        'json:{"tuple":["bytes:overviewScroll2",7]}': ["new slot stale cache"],
        'json:{"tuple":["bytes:overviewScroll2",19]}': ["retired inactive"],
        'json:{"tuple":["bytes:otherScroll",0]}': ["unrelated"],
        "bytes:overviewScroll2": ["different key"],
    }
    character.doc["bytes:ui"][f"bytes:{cache}"] = stamp(records)
    out_a, out_c = apply(account, character)
    assert value(out_c, "ui", cache) == {
        key: item
        for key, item in records.items()
        if key
        not in (
            'json:{"tuple":["bytes:overviewScroll2",0]}',
            'json:{"tuple":["bytes:overviewScroll2",7]}',
        )
    }
    assert out_a.doc["bytes:syntheticPrivate"] == account.doc["bytes:syntheticPrivate"]


def test_labels_integer_vs_boolean_replacement_is_representation_sensitive():
    account, character = documents("recipient")
    old = {"type": "pilot name", "pre": "", "post": "", "state": 1, "bold": True}
    account.doc["bytes:overview"]["bytes:shipLabels"] = stamp(
        [
            {
                "bytes:type": "utf8:pilot name",
                "bytes:pre": "utf8:",
                "bytes:post": "utf8:",
                "bytes:state": 1,
                "bytes:bold": True,
            }
        ]
    )
    supplied = {**old, "bold": 1}
    parsed = model.ParsedSetup("native-yaml", {"shipLabels": [supplied]}, None)
    out_a, _ = apply(account, character, parsed)
    assert type(value(out_a, "overview", "shipLabels")[0]["bytes:bold"]) is int
    supplied["bold"] = True
    out_a, _ = apply(out_a, character, parsed)
    assert type(value(out_a, "overview", "shipLabels")[0]["bytes:bold"]) is bool


def test_target_lock_true_is_integer_one_on_write_and_bool_on_export():
    account, character = documents("recipient")
    parsed = incoming()
    parsed.layout["targetOriginLocked"] = True
    out_a, out_c = apply(account, character, parsed)
    assert value(out_a, "ui", "targetOriginLocked") == 1
    assert type(value(out_a, "ui", "targetOriginLocked")) is int
    envelope, _ = adapter.export_setup(out_a, out_c)
    assert envelope["layout"]["targetOriginLocked"] is True
    assert envelope["layout"]["targetOrigin"] == [0.25, 0.75]


@pytest.mark.parametrize("which", ["stacksWindows", "preferredIdxInStack3"])
def test_source_affected_stack_refuses_but_unrelated_stacks_remain_opaque(which):
    account, character = documents()
    if which == "stacksWindows":
        value(character, "windows", which)["bytes:overview"] = "bytes:Stack"
    else:
        value(character, "windows", which)["bytes:Stack"] = {"bytes:overview": 0}
    with pytest.raises(model.SetupError) as caught:
        adapter.export_setup(account, character)
    assert caught.value.code == "affected_stack"


def test_native_identical_linebreak_records_can_repeat_without_forcing_keep():
    parsed = parse_text(
        "shipLabels: [[linebreak, [[type, linebreak], [pre, null], [post, null], [state, null]]], "
        "[linebreak, [[type, linebreak], [pre, null], [post, null], [state, null]]]]\n"
        "shipLabelOrder: [linebreak, linebreak]"
    )
    assert not parsed.ambiguous_labels
    assert (
        parsed.overview["shipLabels"]
        == [{"type": "linebreak", "pre": None, "post": None, "state": None}] * 2
    )


def test_active_reset_uses_primary_group_not_first_definition_or_first_global_tab():
    account, character = documents("recipient")
    account.doc["bytes:overview"]["bytes:activeOverviewPreset"] = stamp("utf8:Dangling")
    parsed = incoming()
    parsed.overview["windowGroups"] = [[5], [0, 1, 2, 3, 4], [6, 7]]
    out_a, _ = apply(account, character, parsed)
    assert value(out_a, "overview", "activeOverviewPreset") == "utf8:Synthetic Brackets"


def test_native_filter_only_dangling_active_reference_remains_a_local_refusal():
    account, character = documents("recipient")
    account.doc["bytes:overview"]["bytes:activeOverviewPreset"] = stamp("utf8:Dangling")
    with pytest.raises(model.SetupError) as caught:
        apply(account, character, native_definition("Added", PUBLIC_BODY))
    assert caught.value.code == "active_reference"


def test_native_missing_columns_do_not_create_overrides_in_absent_destination_slots():
    account, character = documents("recipient")
    tab = value(account, "overview", "tabsettings_new")["int:0"]
    del tab["bytes:tabColumns"]
    del tab["bytes:tabColumnOrder"]
    parsed = parse_text(
        "presets: [[New, [[groups, []], [filteredStates, []], [alwaysShownStates, []]]]]\n"
        "tabSetup: [[0, [[name, New], [overview, New], [bracket, null], [color, null]]]]"
    )
    out_a, _ = apply(account, character, parsed)
    tab = value(out_a, "overview", "tabsettings_new")["int:0"]
    assert "bytes:tabColumns" not in tab and "bytes:tabColumnOrder" not in tab
    assert value(out_a, "overview", "overviewColumnOrder") == [
        "bytes:NAME",
        "bytes:TYPE",
        "bytes:ICON",
    ]


@pytest.mark.parametrize(
    "case",
    [
        "id20",
        "missing-tabs",
        "malformed-groups",
        "legacy-tuple",
        "unknown-bracket",
        "bad-lock",
        "missing-labels",
        "missing-geometry",
    ],
    ids=[
        "id20",
        "missing-tabs",
        "groups",
        "tuple",
        "bracket",
        "lock",
        "labels",
        "geometry",
    ],
)
def test_export_refuses_specific_unsupported_or_malformed_records_without_mutation(
    case,
):
    account, character = documents()
    overview = account.doc["bytes:overview"]
    tabs = value(account, "overview", "tabsettings_new")
    if case == "id20":
        tabs["int:20"] = tabs.pop("int:0")
    elif case == "missing-tabs":
        del overview["bytes:tabsettings_new"]
    elif case == "malformed-groups":
        overview["bytes:tabsByWindowInstanceID"] = stamp([[0], [0]])
    elif case == "legacy-tuple":
        tabs["int:0"]["bytes:overview"] = {
            "tuple": ["bytes:unsaved", "utf8:Synthetic Fleet"]
        }
    elif case == "unknown-bracket":
        tabs["int:0"]["bytes:bracket"] = "bytes:_OtherSentinel"
    elif case == "bad-lock":
        account.doc["bytes:ui"]["bytes:targetOriginLocked"] = stamp(True)
    elif case == "missing-labels":
        del overview["bytes:shipLabels"]
    else:
        del value(character, "windows", "windowSizesAndPositions_1")["bytes:overview"]
    before = copy.deepcopy((account, character))
    with pytest.raises(model.SetupError):
        adapter.export_setup(account, character)
    assert (account, character) == before


def test_export_optional_window_maps_origin_and_hud_absence_are_explicit_clear_intent():
    account, character = documents()
    del character.doc["bytes:windows"]["bytes:minimizedWindows"]
    del character.doc["bytes:windows"]["bytes:shipuialignleftoffset"]
    del account.doc["bytes:ui"]["bytes:targetOrigin"]
    del account.doc["bytes:ui"]["bytes:targetOriginLocked"]
    envelope, _ = adapter.export_setup(account, character)
    assert all("minimized" not in row["state"] for row in envelope["layout"]["windows"])
    assert envelope["layout"]["targetOrigin"] is None
    assert envelope["layout"]["targetOriginLocked"] is None
    assert envelope["layout"]["hudOffset"] is None


def test_export_apply_roundtrip_preserves_source_setup_but_not_recipient_identity():
    source_a, source_c = documents()
    recipient_a, recipient_c = documents("recipient")
    source_a.doc["bytes:overview"]["bytes:shipLabels"] = stamp(
        [
            {
                "bytes:type": "bytes:linebreak",
                "bytes:pre": None,
                "bytes:post": None,
                "bytes:state": None,
            },
            {
                "bytes:type": "utf8:pilot name",
                "bytes:pre": "utf8:<b>text</b>",
                "bytes:post": "bytes:",
                "bytes:state": 1,
                "bytes:bold": 1,
                "bytes:fontsize": 12,
                "bytes:color": [1.0, 0.9, 0.0],
            },
        ]
    )
    source_a.doc["bytes:ui"]["bytes:targetOriginLocked"] = stamp(1)
    artifact, _ = adapter.export_setup(source_a, source_c)
    out_a, out_c = apply(recipient_a, recipient_c, model.validate_wingman(artifact))
    exported, _ = adapter.export_setup(out_a, out_c)
    for field in ("tabs", "windowGroups", "shipLabels", "settings"):
        assert exported["overview"][field] == artifact["overview"][field]
    assert type(exported["overview"]["shipLabels"][1]["bold"]) is int
    assert exported["layout"] == artifact["layout"]
    # Recipient-only saved custom definitions deliberately survive application.
    assert {row["name"] for row in exported["overview"]["presets"]} == {
        row["name"] for row in artifact["overview"]["presets"]
    } | {"Synthetic Local"}
    assert out_a.doc["bytes:syntheticPrivate"]["bytes:accountID"] == 20
    assert out_c.doc["bytes:syntheticPrivate"]["bytes:characterID"] == 30
    assert "bytes:SortHeadersSettings2" not in out_c.doc["bytes:ui"]


def test_public_column_catalogue_and_supported_enums_cannot_drift():
    from wingman.evesettings.setup_compat import ALL_COLUMNS, DEFAULT_COLUMNS

    assert set(ALL_COLUMNS) == set(model.COLUMNS)
    assert len(ALL_COLUMNS) == len(set(ALL_COLUMNS))
    assert set(DEFAULT_COLUMNS) <= set(ALL_COLUMNS)


@pytest.mark.skipif(not CODEC.is_file(), reason="settings codec not built")
@pytest.mark.parametrize("crc", [False, True], ids=["plain", "crc"])
def test_v24_synthetic_and_public_records_survive_native_transport(tmp_path, crc):
    account, character = documents("recipient")
    account = codec.Document(account.doc, crc)
    character = codec.Document(character.doc, crc)
    character.doc["bytes:ui"]["bytes:SortHeadersSizes"] = stamp(
        {
            'json:{"tuple":["bytes:overviewScroll2",0]}': {"bytes:NAME": 100},
            'json:{"tuple":["bytes:overviewScroll2",19]}': {"bytes:NAME": 90},
        }
    )
    parsed = incoming()
    parsed.overview["presets"].append(
        {"name": PUBLIC_NAME, **copy.deepcopy(PUBLIC_BODY)}
    )
    parsed.overview["tabs"][0].update(
        overview=PUBLIC_NAME, bracket=None, showAll=True, showSpecials=True
    )
    parsed.overview["tabs"][1]["bracket"] = "_BracketFilterShowAll"
    parsed.overview["shipLabels"] = [
        {"type": "linebreak", "pre": None, "post": None, "state": None},
        {
            "type": "pilot name",
            "pre": "Literal markup <b>",
            "post": "",
            "state": 1,
            "bold": 1,
            "italic": True,
            "fontsize": 11,
            "color": [1.0, 0.9, 0.0],
        },
    ]
    parsed.layout["targetOriginLocked"] = True
    out = apply(account, character, parsed)
    readback = []
    for index, document in enumerate(out):
        path = tmp_path / f"v24-{index}.dat"
        codec.write_document(
            path, document, backup=lambda path: None, exe=lambda: str(CODEC)
        )
        readback.append(codec.read_document(path, exe=lambda: str(CODEC)))
    out_a, out_c = readback
    assert out_a.had_crc is crc and out_c.had_crc is crc
    tabs = value(out_a, "overview", "tabsettings_new")
    assert tabs["int:0"]["bytes:bracket"] is None
    assert tabs["int:1"]["bytes:bracket"] == "utf8:_BracketFilterShowAll"
    assert tabs["int:0"]["bytes:showAll"] is True
    assert tabs["int:0"]["bytes:showSpecials"] is True
    assert value(out_c, "ui", "SortHeadersSizes") == {
        'json:{"tuple":["bytes:overviewScroll2",19]}': {"bytes:NAME": 90}
    }
    assert value(out_c, "windows", "openWindows")["bytes:overview_3"] is False
    labels = value(out_a, "overview", "shipLabels")
    assert labels[0] == {
        "bytes:type": "utf8:linebreak",
        "bytes:pre": None,
        "bytes:post": None,
        "bytes:state": None,
    }
    assert type(labels[1]["bytes:bold"]) is int and labels[1]["bytes:bold"] == 1
    assert labels[1]["bytes:italic"] is True
    assert type(value(out_a, "ui", "targetOriginLocked")) is int
    assert value(out_a, "ui", "targetOriginLocked") == 1
    artifact, _ = adapter.export_setup(out_a, out_c)
    assert artifact["overview"]["shipLabels"] == parsed.overview["shipLabels"]
    assert artifact["layout"] == parsed.layout


def test_native_linebreak_expansion_checks_label_budget_before_copying(monkeypatch):
    import json

    from wingman.evesettings import overview_yaml

    def must_not_copy(*args, **kwargs):
        pytest.fail("Oversized linebreak expansion reached copying")

    monkeypatch.setattr(overview_yaml.copy, "deepcopy", must_not_copy)
    data = {
        "shipLabels": [
            [
                "linebreak",
                [["type", "linebreak"], ["pre", None], ["post", None], ["state", None]],
            ]
        ],
        "shipLabelOrder": ["linebreak"] * 65,
    }
    with pytest.raises(model.SetupError) as caught:
        parse_text(json.dumps(data))
    assert caught.value.code == "collection_limit"


def test_export_error_context_does_not_rewrite_user_authored_definition_names():
    account, character = documents()
    value(account, "overview", "overviewProfilePresets")["utf8:recipient filter"] = {
        "future": [1]
    }
    with pytest.raises(model.SetupError) as caught:
        adapter.export_setup(account, character)
    assert caught.value.code == "source_shape"
    assert "recipient filter" in str(caught.value)
    assert "Unsupported source" in str(caught.value)


def test_unused_first_unsaved_generation_is_not_validated_when_second_is_present():
    account, character = documents()
    account.doc["bytes:overview"]["bytes:overviewProfilePresets_notSaved"] = stamp(
        ["unknown old generation"]
    )
    account.doc["bytes:overview"]["bytes:overviewProfilePresets_notSaved2"] = stamp({})
    envelope, warnings = adapter.export_setup(account, character)
    assert envelope["overview"]["presets"][0]["groups"] == [25, 26]
    assert warnings == ()


@pytest.mark.parametrize("change", ["groups-order", "state-order", "duplicates"])
def test_protected_fingerprints_do_not_resort_or_deduplicate_incoming_bodies(change):
    body = copy.deepcopy(PUBLIC_BODY)
    if change == "groups-order":
        body["groups"].reverse()
    elif change == "state-order":
        body["filteredStates"].reverse()
    else:
        body["groups"].append(864)
    with pytest.raises(model.SetupError) as caught:
        apply(*documents("recipient"), native_definition(PUBLIC_NAME, body))
    assert caught.value.code == "protected_definition"
