import copy

import pytest

from wingman.evesettings import formations as fm

STAMP = "long:134325209689294194"


def probe(x, y=0.0, z=0.0, r=598391482800.0):
    return {"tuple": [{"tuple": [x, y, z]}, r]}


def doc_with(entries, selected=0):
    return {
        "bytes:windows": {"bytes:untouched": {"tuple": [STAMP, True]}},
        fm.UI_KEY: {
            "bytes:other": {"tuple": [STAMP, "utf8:keep"]},
            fm.FORMATIONS_KEY: {"tuple": [STAMP, entries]},
            fm.SELECTED_KEY: {"tuple": [STAMP, selected]},
        },
    }


REAL = doc_with(
    {
        "int:0": {
            "tuple": ["utf8:Test", [probe(-2048.0), probe(-2048.0, 299195727872.0)]]
        },
        "int:-4": {"tuple": ["bytes:tempFormation", [probe(262144.0, 28672.0)]]},
    }
)


def test_filetime_matches_the_windows_epoch():
    assert fm.filetime(0.0) == 116_444_736_000_000_000
    assert fm.filetime(1_700_000_000.0) == (1_700_000_000 + 11_644_473_600) * 10_000_000


def test_read_hides_scratch_entries_and_strips_the_name_prefix():
    got = fm.read_formations(REAL)
    assert got == [
        fm.Formation(
            id=0,
            name="Test",
            probes=(
                fm.Probe(-2048.0, 0.0, 0.0, 598391482800.0),
                fm.Probe(-2048.0, 299195727872.0, 0.0, 598391482800.0),
            ),
        )
    ]


def test_read_accepts_a_bytes_name_and_a_name_with_colons():
    doc = doc_with({"int:3": {"tuple": ["bytes:a:b:c", [probe(1.0)]]}})
    assert fm.read_formations(doc)[0].name == "a:b:c"


def test_read_of_a_file_with_no_formations_key_is_empty():
    assert fm.read_formations({fm.UI_KEY: {}}) == []
    assert fm.read_formations({}) == []


def test_read_sorts_by_id():
    doc = doc_with(
        {
            "int:5": {"tuple": ["utf8:B", [probe(1.0)]]},
            "int:2": {"tuple": ["utf8:A", [probe(1.0)]]},
        }
    )
    assert [f.id for f in fm.read_formations(doc)] == [2, 5]


@pytest.mark.parametrize(
    "entries",
    [
        {"int:7": "garbage"},
        {"utf8:x": {"tuple": ["utf8:not an id", []]}},
        {"int:1": {"tuple": ["utf8:A", [{"tuple": [[1, 2], 3]}]]}},
        {"int:1": {"tuple": ["utf8:A", [probe(1.0), "not a probe"]]}},
    ],
)
def test_read_refuses_a_file_it_does_not_fully_understand(entries):
    """Skipping a malformed entry on read would delete it on the next write,
    because write rebuilds the whole key from what read returned. Refusing
    keeps the editor from opening — the file is left exactly as it was."""
    with pytest.raises(ValueError, match="not understand"):
        fm.read_formations(doc_with(entries))


@pytest.mark.parametrize(
    "bad_value",
    [
        "not a dict",
        {"nope": "no tuple key"},
        {"tuple": ["long:1"]},
        {"tuple": ["long:1", "not a dict", "extra"]},
        {"tuple": ["long:1", ["not", "a", "dict"]]},
    ],
)
def test_read_refuses_a_present_but_malformed_customformations_container(bad_value):
    """A present customFormations value that isn't {"tuple": [stamp, dict]}
    must refuse rather than be silently treated as empty — otherwise
    read_formations reports "no formations" with no error, and the next
    write_formations rebuilds the key as {}, discarding what was there."""
    doc = {fm.UI_KEY: {fm.FORMATIONS_KEY: bad_value}}
    with pytest.raises(ValueError, match="not understand"):
        fm.read_formations(doc)
    with pytest.raises(ValueError, match="not understand"):
        fm.write_formations(doc, [], now=0.0)


def test_write_replaces_only_the_formations_key_and_restamps_both_keys():
    before = copy.deepcopy(REAL)
    new = [fm.Formation(id=0, name="Renamed", probes=(fm.Probe(1.0, 2.0, 3.0, 4.0),))]
    out = fm.write_formations(REAL, new, now=1_700_000_000.0)
    assert before == REAL, "input document must not be mutated"
    stamp = "long:" + str(fm.filetime(1_700_000_000.0))
    ui = out[fm.UI_KEY]
    assert out["bytes:windows"] == REAL["bytes:windows"]
    assert ui["bytes:other"] == REAL[fm.UI_KEY]["bytes:other"]
    assert ui[fm.FORMATIONS_KEY]["tuple"][0] == stamp
    assert ui[fm.SELECTED_KEY]["tuple"] == [stamp, 0]
    entries = ui[fm.FORMATIONS_KEY]["tuple"][1]
    assert entries["int:0"] == {
        "tuple": ["utf8:Renamed", [{"tuple": [{"tuple": [1.0, 2.0, 3.0]}, 4.0]}]]
    }


def test_write_carries_scratch_entries_through_untouched():
    out = fm.write_formations(REAL, [], now=0.0)
    entries = out[fm.UI_KEY][fm.FORMATIONS_KEY]["tuple"][1]
    assert list(entries) == ["int:-4"]
    assert entries["int:-4"] == REAL[fm.UI_KEY][fm.FORMATIONS_KEY]["tuple"][1]["int:-4"]


def test_write_mints_ids_for_new_formations_above_every_existing_one():
    doc = doc_with(
        {
            "int:0": {"tuple": ["utf8:A", [probe(1.0)]]},
            "int:4": {"tuple": ["utf8:B", [probe(1.0)]]},
        }
    )
    kept = fm.read_formations(doc)
    new = [
        *kept,
        fm.Formation(None, "C", (fm.Probe(0, 0, 0, 1.0),)),
        fm.Formation(None, "D", (fm.Probe(0, 0, 0, 1.0),)),
    ]
    out = fm.write_formations(doc, new, now=0.0)
    assert sorted(out[fm.UI_KEY][fm.FORMATIONS_KEY]["tuple"][1]) == [
        "int:0",
        "int:4",
        "int:5",
        "int:6",
    ]


def test_write_keeps_the_selection_pointing_at_the_same_formation_after_a_reorder():
    doc = doc_with(
        {
            "int:0": {"tuple": ["utf8:A", [probe(1.0)]]},
            "int:1": {"tuple": ["utf8:B", [probe(1.0)]]},
        },
        selected=1,
    )
    a, b = fm.read_formations(doc)
    out = fm.write_formations(
        doc, [b, a], now=0.0
    )  # reordered; ids travel with the formations
    assert out[fm.UI_KEY][fm.SELECTED_KEY]["tuple"][1] == 1
    assert (
        out[fm.UI_KEY][fm.FORMATIONS_KEY]["tuple"][1]["int:1"]["tuple"][0] == "utf8:B"
    )


def test_write_repoints_a_selection_whose_formation_was_deleted():
    doc = doc_with(
        {
            "int:0": {"tuple": ["utf8:A", [probe(1.0)]]},
            "int:1": {"tuple": ["utf8:B", [probe(1.0)]]},
        },
        selected=1,
    )
    a, _b = fm.read_formations(doc)
    out = fm.write_formations(doc, [a], now=0.0)
    assert out[fm.UI_KEY][fm.SELECTED_KEY]["tuple"][1] == 0


def test_write_clears_the_selection_when_no_formations_remain():
    out = fm.write_formations(REAL, [], now=0.0)
    assert out[fm.UI_KEY][fm.SELECTED_KEY]["tuple"][1] is None


def test_write_creates_the_keys_when_the_file_never_had_them():
    out = fm.write_formations(
        {}, [fm.Formation(None, "A", (fm.Probe(0, 0, 0, 1.0),))], now=0.0
    )
    assert list(out[fm.UI_KEY][fm.FORMATIONS_KEY]["tuple"][1]) == ["int:0"]
    assert out[fm.UI_KEY][fm.SELECTED_KEY]["tuple"][1] == 0


@pytest.mark.parametrize(
    "bad, message",
    [
        ([fm.Formation(None, "", (fm.Probe(0, 0, 0, 1.0),))], "needs a name"),
        ([fm.Formation(None, "A", ())], "at least one probe"),
        (
            [fm.Formation(None, "A", tuple(fm.Probe(0, 0, 0, 1.0) for _ in range(9)))],
            "at most 8",
        ),
        (
            [fm.Formation(None, "A", (fm.Probe(float("nan"), 0, 0, 1.0),))],
            "not a number",
        ),
        (
            [fm.Formation(None, "A", (fm.Probe(0, 0, 0, 0.0),))],
            "range must be positive",
        ),
        (
            [
                fm.Formation(None, "A", (fm.Probe(0, 0, 0, 1.0),)),
                fm.Formation(None, "A", (fm.Probe(0, 0, 0, 1.0),)),
            ],
            "twice",
        ),
    ],
)
def test_validate_rejects(bad, message):
    with pytest.raises(ValueError, match=message):
        fm.validate(bad)


def test_payload_round_trip():
    items = [
        {"id": 0, "name": "A", "probes": [{"x": 1, "y": 2, "z": 3, "range": 4}]},
        {"id": None, "name": "B", "probes": [{"x": 0, "y": 0, "z": 0, "range": 1}]},
    ]
    got = fm.from_payload(items)
    assert got[0] == fm.Formation(0, "A", (fm.Probe(1.0, 2.0, 3.0, 4.0),))
    assert got[1].id is None
    assert fm.to_payload(got) == [
        {
            "id": 0,
            "name": "A",
            "probes": [{"x": 1.0, "y": 2.0, "z": 3.0, "range": 4.0}],
        },
        {
            "id": None,
            "name": "B",
            "probes": [{"x": 0.0, "y": 0.0, "z": 0.0, "range": 1.0}],
        },
    ]


@pytest.mark.parametrize(
    "bad",
    [
        "nope",
        [1],
        [{"name": "A"}],
        [{"id": "x", "name": "A", "probes": []}],
        [{"id": 0, "name": 3, "probes": []}],
        [{"id": 0, "name": "A", "probes": [{"x": "a"}]}],
    ],
)
def test_from_payload_rejects_malformed_input(bad):
    with pytest.raises(ValueError):
        fm.from_payload(bad)


def test_from_payload_rejects_a_negative_id():
    """The design treats negative ids as client scratch state carried
    through write_formations untouched (e.g. -4 is tempFormation); a
    page-supplied negative id must never reach that path or a save would
    overwrite scratch state the client itself owns."""
    with pytest.raises(ValueError, match="cannot be negative"):
        fm.from_payload([{"id": -4, "name": "A", "probes": []}])
