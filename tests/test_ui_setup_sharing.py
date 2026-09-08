"""Exercise actual JSON boundaries independently of any document adapter."""

import copy
import json

import pytest

from tests.setup_fixtures import wire
from wingman.evesettings import setup_model as model
from wingman.evesettings import setup_sharing as sharing


def test_json_roundtrip_preserves_order_and_geometry():
    original = wire()
    parsed = sharing.parse_text(sharing.export_text(original))
    assert parsed.overview["shipLabels"] == original["overview"]["shipLabels"]
    assert parsed.overview["windowGroups"] == original["overview"]["windowGroups"]
    assert parsed.layout == original["layout"]
    assert parsed.source_kind == "wingman"


def test_json_parse_and_export_preserve_repeated_preset_groups_exactly():
    source = wire()
    source["overview"]["presets"][0]["groups"] = [73, 11, 73, 0, 11, 2147483647, 73]
    before = copy.deepcopy(source)
    assert sharing.parse_text(json.dumps(source)).overview["presets"][0]["groups"] == [
        73,
        11,
        73,
        0,
        11,
        2147483647,
        73,
    ]
    text = sharing.export_text(source)
    assert json.loads(text)["overview"]["presets"][0]["groups"] == [
        73,
        11,
        73,
        0,
        11,
        2147483647,
        73,
    ]
    assert sharing.parse_text(text).overview == source["overview"]
    assert source == before


def test_canonical_export_is_compact_unicode_json_without_private_metadata():
    original = wire()
    before = copy.deepcopy(original)
    text = sharing.export_text(original)
    # Decode independently: a buggy exporter must not hide behind its own parser.
    assert json.loads(text) == original
    assert text == json.dumps(
        json.loads(text), ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )
    assert " — " in text
    assert original == before
    reordered = {key: original[key] for key in reversed(original)}
    reordered["overview"] = {
        key: original["overview"][key] for key in reversed(original["overview"])
    }
    assert sharing.export_text(reordered) == text


def test_canonical_export_includes_explicit_clear_settings_without_mutation():
    original = wire()
    original["overview"]["settings"] = {"useSmallText": False}
    decoded = json.loads(sharing.export_text(original))
    assert decoded["overview"]["settings"]["useSmallText"] is False
    assert decoded["overview"]["settings"]["flagOrder"] is None
    assert original["overview"]["settings"] == {"useSmallText": False}
    assert (
        sharing.parse_text(sharing.export_text(original)).overview
        == decoded["overview"]
    )


@pytest.mark.parametrize("operation", ["parse", "export"])
@pytest.mark.parametrize(
    "case,code",
    [
        ("format", "unsupported_format"),
        ("version", "unsupported_version"),
        ("type", "unsupported_type"),
        ("metadata", "invalid_fields"),
        ("duplicate", "duplicate_name"),
        ("reference", "dangling_reference"),
        ("geometry", "invalid_number"),
        ("boolean", "invalid_type"),
        ("text", "invalid_text"),
    ],
    ids=[
        "format",
        "version",
        "type",
        "metadata",
        "duplicate",
        "reference",
        "geometry",
        "boolean",
        "text",
    ],
)
def test_both_transports_validate_the_complete_envelope(operation, case, code):
    source = wire()
    if case == "format":
        source["format"] = "other"
    elif case == "version":
        source["version"] = True
    elif case == "type":
        source["type"] = "probe-formations"
    elif case == "metadata":
        source["sourcePath"] = "C:/synthetic/private.dat"
    elif case == "duplicate":
        source["overview"]["presets"][1] = copy.deepcopy(
            source["overview"]["presets"][0]
        )
    elif case == "reference":
        source["overview"]["tabs"][0]["overview"] = "missing"
    elif case == "geometry":
        source["layout"]["windows"][0]["geometry"][0] = True
    elif case == "boolean":
        source["layout"]["targetOriginLocked"] = 1
    else:
        source["overview"]["shipLabels"][0]["pre"] = "\x00"
    before = copy.deepcopy(source)
    with pytest.raises(model.SetupError) as caught:
        if operation == "parse":
            sharing.parse_text(json.dumps(source))
        else:
            sharing.export_text(source)
    assert caught.value.code == code
    assert source == before


@pytest.mark.parametrize(
    "original,repeated",
    [
        ('"version": 1', '"version": 2, "version": 1'),
        ('"name": "Synthetic Fleet"', '"name": "Other", "name": "Synthetic Fleet"'),
        ('"hudOffset": -160', '"hudOffset": 0, "hudOffset": -160'),
        ('"bold": false', '"bold": true, "bold": false'),
    ],
    ids=["root", "preset", "layout", "label"],
)
def test_duplicate_json_fields_are_rejected_before_last_wins_conversion(
    original, repeated
):
    text = json.dumps(wire()).replace(original, repeated, 1)
    with pytest.raises(model.SetupError, match="Duplicate field") as caught:
        sharing.parse_text(text)
    assert caught.value.code == "duplicate_field"


@pytest.mark.parametrize(
    "text",
    [
        "{",
        '{"format": "wingman-preset",',
        "{} {}",
        '{"format":"wingman-preset", "overview":}',
    ],
    ids=["open", "claimed", "trailing", "broken"],
)
def test_malformed_claimed_json_never_falls_back_to_native_input(text):
    with pytest.raises(model.SetupError) as caught:
        sharing.parse_text(text)
    assert caught.value.code == "invalid_json"


@pytest.mark.parametrize(
    "text,code",
    [
        ("format: wingman-preset\nversion: 99\n", "unsupported_input"),
        ("", "invalid_type"),
        (" \n\t", "invalid_yaml"),
        ("https://example.invalid/setup", "invalid_type"),
        ("```json\n{}\n```", "invalid_yaml"),
    ],
    ids=["claimed-native", "empty", "space", "url", "fence"],
)
def test_claimed_yaml_envelopes_and_wrapped_or_nonsetup_input_still_refuse(text, code):
    with pytest.raises(model.SetupError) as caught:
        sharing.parse_text(text)
    assert caught.value.code == code


@pytest.mark.parametrize(
    "text",
    ["null", "true", "1", '"text"', "[]"],
    ids=["null", "bool", "number", "string", "array"],
)
def test_valid_json_nonobjects_refuse_as_domain_errors(text):
    with pytest.raises(model.SetupError) as caught:
        sharing.parse_text(text)
    assert caught.value.code == "invalid_type"


@pytest.mark.parametrize(
    "text",
    [None, 1, True, b"{}", [], {}],
    ids=["null", "int", "bool", "bytes", "list", "object"],
)
def test_parser_requires_text_without_implicit_decoding(text):
    with pytest.raises(model.SetupError) as caught:
        sharing.parse_text(text)
    assert caught.value.code == "invalid_text"


@pytest.mark.parametrize("escaped", [True, False], ids=["escaped", "raw"])
@pytest.mark.parametrize(
    "text", ["\ud800", "\udfff", "\x00"], ids=["high", "low", "nul"]
)
def test_escaped_and_raw_invalid_text_are_rejected(escaped, text):
    source = wire()
    source["overview"]["shipLabels"][0]["pre"] = text
    with pytest.raises(model.SetupError) as caught:
        sharing.parse_text(json.dumps(source, ensure_ascii=escaped))
    assert caught.value.code == "invalid_text"


@pytest.mark.parametrize(
    "token,code",
    [
        ("NaN", "invalid_json"),
        ("Infinity", "invalid_json"),
        ("-Infinity", "invalid_json"),
        ("1e10000", "invalid_number"),
        ("9" * 400, "invalid_number"),
        ("9" * 5000, "invalid_json"),
    ],
    ids=["nan", "inf", "negative-inf", "overflow", "huge", "decoder-limit"],
)
def test_nonstandard_constants_and_huge_numeric_errors_are_contained(token, code):
    text = json.dumps(wire()).replace('"hudOffset": -160', '"hudOffset": ' + token)
    with pytest.raises(model.SetupError) as caught:
        sharing.parse_text(text)
    assert caught.value.code == code


def test_json_recursion_and_structural_budgets_precede_domain_conversion():
    for text, code in [
        ("[" * 2000 + "0" + "]" * 2000, "depth_limit"),
        ("[" * 17 + "0" + "]" * 17, "depth_limit"),
        ("[" + "0," * 99999 + "0]", "node_limit"),
    ]:
        with pytest.raises(model.SetupError) as caught:
            sharing.parse_text(text)
        assert caught.value.code == code


def test_exact_utf8_byte_budget_and_one_byte_over():
    source = wire()
    source["overview"]["tabs"][0]["name"] = "𐐀é"
    text = json.dumps(source, ensure_ascii=False)
    padded = text + " " * (2097152 - len(text.encode("utf-8")))
    assert sharing.parse_text(padded).overview["tabs"][0]["name"] == "𐐀é"
    with pytest.raises(model.SetupError, match="2097152") as caught:
        sharing.parse_text(padded + " ")
    assert caught.value.code == "byte_limit"


@pytest.mark.parametrize(
    "text",
    ["{" + " " * 2097152, "𐐀" * 524289, "\ud800" * 2097153],
    ids=["ascii-limit", "utf8-limit", "surrogate-limit"],
)
def test_size_refusal_precedes_decoding_for_oversized_input(text):
    with pytest.raises(model.SetupError) as caught:
        sharing.parse_text(text)
    assert caught.value.code == "byte_limit"


def test_output_byte_limit_is_real_and_does_not_truncate():
    source = wire()
    # Individually valid label fields alone consume exactly 2 MiB of UTF-8;
    # JSON punctuation and the rest of the model necessarily exceed the budget.
    source["overview"]["shipLabels"] = [
        {"type": None, "pre": "𐐀" * 4096, "post": "𐐀" * 4096, "state": 1}
        for _ in range(64)
    ]
    assert len(model.validate_wingman(source).overview["shipLabels"]) == 64
    before = copy.deepcopy(source)
    with pytest.raises(model.SetupError) as caught:
        sharing.export_text(source)
    assert caught.value.code == "byte_limit"
    assert source == before


def test_export_uses_the_same_authoritative_budget_as_parse_and_limits(monkeypatch):
    source = wire()
    text = sharing.export_text(source)
    size = len(text.encode("utf-8"))
    monkeypatch.setattr(model, "MAX_BYTES", size)
    assert model.limits_payload()["max_bytes"] == size
    assert sharing.export_text(source) == text
    assert sharing.parse_text(text).layout == source["layout"]
    monkeypatch.setattr(model, "MAX_BYTES", size - 1)
    for function, value in ((sharing.export_text, source), (sharing.parse_text, text)):
        with pytest.raises(model.SetupError) as caught:
            function(value)
        assert caught.value.code == "byte_limit"


def test_export_canonical_clear_expansion_must_still_fit_structural_budget():
    source = wire()
    for preset in source["overview"]["presets"]:
        for field in ("groups", "filteredStates", "alwaysShownStates"):
            preset[field] = list(range(8192))
    source["overview"]["settings"] = {
        "flagStates": list(range(8192)),
        "flagOrder": list(range(8192)),
        "backgroundStates": list(range(8192)),
        "backgroundOrder": list(range(1110)),
    }
    # Exactly 100,000 nodes before normalizing 19 omitted setting overrides.
    # An exporter must not emit JSON that its own structural gate cannot read.
    assert model.check_structure_budget(source) is None
    assert len(sharing.parse_text(json.dumps(source)).overview["presets"]) == 3
    with pytest.raises(model.SetupError) as caught:
        sharing.export_text(source)
    assert caught.value.code == "node_limit"


def test_each_parse_has_owned_nested_values():
    text = json.dumps(wire())
    first = sharing.parse_text(text)
    first.overview["shipLabels"].clear()
    first.layout["windows"][0]["state"].clear()
    second = sharing.parse_text(text)
    assert len(second.overview["shipLabels"]) == 9
    assert second.layout["windows"][0]["state"]["open"] is True
