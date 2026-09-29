"""The pre-jump prime relay (#295).

Two seams, per spec #292's testing decisions:

- the engine invariants (lexical, since pytest cannot run AHK): the prime
  is captured only on the single-bookmark Set Root path, and its parse of
  the finisher-tag vocabulary matches the engine's own writer (the shared
  vectors also agreed with the server-side flag vocabulary);
- the status-relay seam (hotkeys.status): the prime surfaces as a typed,
  strictly validated record, and a malformed or oversized one is rejected
  without disturbing the existing status fields.
"""

import json
import re

import pytest

from tests.test_engine_invariants import _code, _label_body
from tests.test_hotkeys_lifecycle import FakeSpawner, engine, section
from wingman import paths
from wingman.hotkeys import PrimeRecord

# --- Shared finisher-tag test vectors -------------------------------------
# Same bookmark first-fields -> same flag sets, agreed with the server-side
# flag vocabulary (spec #292). `e` stacks; `/` and `c` are mutually
# exclusive; `f` is independent; the legacy uppercase frig tag `S` still
# reads as `f`. The class/size finisher suffixes (1-6, 13, H/L/N, T/D) are
# the class vocabulary, not flags, and never appear in `flags`.
VECTORS = [
    # (bookmark first field, expected flag set)
    ("J123456-ABC", ""),  # bare bookmark: no tags
    ("J123456-ABC e", "e"),
    ("J123456-ABC /", "/"),
    ("J123456-ABC f", "f"),
    ("J123456-ABC c", "c"),
    ("J123456-ABC e /", "e/"),  # e stacks with /
    ("J123456-ABC e c", "ec"),  # e stacks with c
    ("J123456-ABC e f", "ef"),  # e stacks with f
    ("J123456-ABC / f", "/f"),
    ("J123456-ABC c f", "cf"),
    ("J123456-ABC e / f", "e/f"),
    ("J123456-ABC e c f", "ecf"),
    ("J123456-ABC S", "f"),  # legacy frig tag reads as f
    ("J123456-ABC e e", "e"),  # duplicate token collapses
    ("J123456-ABC 3 e", "e"),  # class suffix is not a flag
    ("J123456-ABC 13", ""),
    ("J123456-ABC H", ""),
    ("J123456-ABC T", ""),
    ("J123456-ABC D", ""),
    ("J123456-ABC 3 / f", "/f"),
    # Digit-prefix J-code shapes (#297 field report): the class suffix and
    # the flags coexist in one field.
    ("12-FFC 3 e c", "ec"),
    ("12-FFC 3", ""),
    ("12-FFC 3 / f", "/f"),
    ("12-REZ", ""),
    # A letter inside a word is not a tag.
    ("J123456-ABC extra", ""),
    ("J123456-ABC eve", ""),
    # Not a system bookmark shape at all.
    ("some text", ""),
    ("-", ""),
]


# --- Engine invariants -----------------------------------------------------


@pytest.fixture
def source():
    script = paths.engine_script()
    assert script is not None, "vendored engine script is missing"
    return _code(script.read_text(encoding="utf-8", errors="replace"))


def _parse_flags_ahk(source, field):
    """Run the engine's ParsePrimeFlags against `field`, in Python.

    The AHK function is simple enough to transliterate exactly: uppercase
    the field, split the token after the hyphen off as the system code,
    then map whole tokens. Keeping this a transliteration (rather than a
    lexical assertion) lets the shared vectors run against the real logic;
    test_prime_parser_shape pins the transliteration to the script.
    """
    del source
    field = field.upper()
    pos = field.find("-")
    if pos < 1:
        return ""
    rest = field[pos + 1 :]
    tokens = [t for t in rest.split(" ") if t]
    if not tokens or not re.fullmatch(r"[A-Z]{3}", tokens[0]):
        return ""
    flags = ""
    for t in tokens[1:]:
        if t == "E":
            if "e" not in flags:
                flags += "e"
        elif t == "/":
            if "/" not in flags:
                flags += "/"
        elif t in ("F", "S"):
            if "f" not in flags:
                flags += "f"
        elif t == "C" and "c" not in flags:
            flags += "c"
    return flags


@pytest.mark.parametrize("field,expected", VECTORS)
def test_shared_finisher_tag_vectors(field, expected):
    assert _parse_flags_ahk(None, field) == expected


def test_prime_parser_shape(source):
    """The vectors above are only worth something if the Python
    transliteration matches the script. Pin the engine function's tokens:
    uppercase-first, hyphen split, a three-letter code token, and the
    whole-token flag mapping including the legacy S."""
    body = re.search(
        r"^ParsePrimeFlags\(field\) \{\n(.*?)^}", source, re.DOTALL | re.MULTILINE
    )
    assert body, "ParsePrimeFlags not found"
    text = body.group(1)
    assert "StringUpper, field, field" in text
    assert 'InStr(field, "-")' in text
    assert "^[A-Z]{3}$" in text
    for token in ('t = "e"', 't = "/"', 't = "f" || t = "S"', 't = "c"'):
        assert token in text, token


def test_prime_is_captured_only_on_the_single_bookmark_paths(source):
    """No-selection (empty clipboard) and whole-list (ZeroMode or a multi-
    line list) Set Root must leave the prime fields empty. The capture sits
    inside the loop that fires once, gated on the same text's ValidCount
    being 1 -- in BOTH single-bookmark shapes: a bare A-Z0-9 first field
    and a hyphenated system bookmark (CODE-SYS ...), whose branch used to
    set the root while silently priming nothing (#297 field report)."""
    body = _label_body(source, "DoSemi")
    assert "PrimeJCode    := RootKey" in body
    # The ZeroMode branch (the whole-list path) sets no prime field: the only
    # prime writes in DoSemi sit inside the two single-bookmark captures,
    # each gated on ValidCount = 1 (the reset block at the top writes the
    # empty state, which the earlier test_prime_fields_are_reset_on_every_
    # set_root covers).
    for name in ("PrimeJCode", "PrimeFlags", "PrimeEvent", "PrimeCaptured"):
        writes = [
            w
            for w in re.findall(rf"^\s*{name}\s+:=\s*(.+)", body, re.MULTILINE)
            if w not in ('""', "0")
        ]
        assert len(writes) == 2, (name, writes)
    captures = re.findall(
        r"if \(ValidCount = 1\) \{\n(.*?)\n            \}", body, re.DOTALL
    )
    assert len(captures) == 2, "expected exactly two ValidCount = 1 captures"
    for capture in captures:
        for name in ("PrimeJCode", "PrimeFlags", "PrimeEvent", "PrimeCaptured"):
            assert re.search(rf"^\s*{name}\s+:=", capture, re.MULTILINE), (
                name,
                capture,
            )
    # The hyphenated capture parses the same first field the loop matched,
    # so its flags come from the bookmark text, not from a different line.
    hyphen_capture = [c for c in captures if "ParsePrimeFlags(FirstField)" in c]
    assert len(hyphen_capture) == 2, "both captures must parse FirstField"
    # The empty-clipboard early return happens before either capture.
    assert body.index('if (ClipSaved = "")') < body.index("PrimeJCode    := RootKey")


def test_prime_fields_are_reset_on_every_set_root(source):
    """A newer Set Root that does not prime (whole list, no selection) must
    replace the earlier prime with nothing: stale data must never survive
    into the next jump."""
    body = _label_body(source, "DoSemi")
    for name in ("PrimeJCode", "PrimeEvent", "PrimeFlags", "PrimeCaptured"):
        assert re.search(rf"^{name}\s+:=", body, re.MULTILINE), name


def test_prime_globals_are_declared(source):
    """test_globals_written_inside_functions_is_declared watches a fixed
    set; the prime fields are written inside DoSemi (a label, so already
    global) but read inside a function, where AHK v1 would make an
    undeclared name local."""
    fn = re.search(r"^BuildPrimeJson\(\) \{\n(.*?)^}", source, re.DOTALL | re.MULTILINE)
    assert fn
    assert re.search(r"^\s*global\s+.*PrimeJCode", fn.group(1), re.MULTILINE)


def test_prime_is_published_in_the_status_document(source):
    body = re.search(
        r"^RefreshStatusTab:\n(.*?)^Return$", source, re.DOTALL | re.MULTILINE
    )
    assert body
    assert '"""prime"":" . BuildPrimeJson()' in body.group(1)


def test_prime_json_is_bounded_and_versioned(source):
    body = re.search(
        r"^BuildPrimeJson\(\) \{\n(.*?)^}", source, re.DOTALL | re.MULTILINE
    )
    assert body
    text = body.group(1)
    for key in ("jcode", "flags", "event", "captured"):
        assert f'""{key}""' in text
    assert 'return "null"' in text


# --- Status relay seam -----------------------------------------------------


VALUES = {
    "sig": "-ABC",
    "root": "J1234",
    "next_num": "J12345",
    "next_alpha": "J1234A",
    "failed_binds": [],
    "prime": {
        "jcode": "J123456",
        "flags": ["e", "f"],
        "event": "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
        "captured": 1000.0,
    },
    "written": 1000.0,
}

PRIME = PrimeRecord(
    jcode="J123456", flags=("e", "f"), event=VALUES["prime"]["event"], captured=1000.0
)


def write_status(tmp_path, **over):
    (tmp_path / "eve_status.json").write_text(json.dumps({**VALUES, **over}))


def relay(tmp_path):
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    return eng.status(enabled=True, now=1001.0)


def test_a_single_bookmark_set_root_surfaces_the_prime(tmp_path):
    write_status(tmp_path)
    got = relay(tmp_path)
    assert got.prime == PRIME
    # The other fields are untouched by the prime's presence.
    assert got.state == "running"
    assert got.root == "J1234"
    assert got.failed_binds == []


def test_no_prime_is_the_normal_case(tmp_path):
    write_status(tmp_path, prime=None)
    got = relay(tmp_path)
    assert got.state == "running"
    assert got.prime is None
    assert got.root == "J1234"


@pytest.mark.parametrize(
    "bad",
    [
        "J123456",  # a string, not a record
        ["J123456"],  # a list
        42,
        {},  # empty record
        {"jcode": "J123456"},  # missing fields
        {"jcode": "J123456", "flags": ["e"], "event": "abc", "captured": 1.0},
        {  # malformed jcode: a lowercase or oversized one is not the engine's
            "jcode": "j123456",
            "flags": [],
            "event": "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
            "captured": 1.0,
        },
        {  # malformed jcode: 8 chars exceeds any J-code
            "jcode": "J12345678",
            "flags": [],
            "event": "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
            "captured": 1.0,
        },
        {  # malformed event id
            "jcode": "J123456",
            "flags": [],
            "event": "not-a-hex-uuid!!",
            "captured": 1.0,
        },
        {  # captured must be a number, not a bool
            "jcode": "J123456",
            "flags": [],
            "event": "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
            "captured": True,
        },
        {  # flags must be a list
            "jcode": "J123456",
            "flags": "ef",
            "event": "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
            "captured": 1.0,
        },
        {  # oversized flag list
            "jcode": "J123456",
            "flags": ["e", "/", "f", "c"],
            "event": "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
            "captured": 1.0,
        },
        {  # unknown flag token
            "jcode": "J123456",
            "flags": ["x"],
            "event": "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
            "captured": 1.0,
        },
        {  # non-string flag
            "jcode": "J123456",
            "flags": [1],
            "event": "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
            "captured": 1.0,
        },
        {  # the engine never emits / and c together
            "jcode": "J123456",
            "flags": ["/", "c"],
            "event": "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
            "captured": 1.0,
        },
        {  # duplicate flags are not a real record either
            "jcode": "J123456",
            "flags": ["e", "e"],
            "event": "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
            "captured": 1.0,
        },
    ],
)
def test_a_malformed_prime_is_rejected_without_touching_other_fields(tmp_path, bad):
    write_status(tmp_path, prime=bad)
    got = relay(tmp_path)
    assert got.state == "running"
    assert got.prime is None
    assert got.root == "J1234"
    assert got.next_alpha == "J1234A"


def test_an_oversized_prime_is_rejected(tmp_path):
    write_status(tmp_path, prime={"jcode": "J" * 300})
    got = relay(tmp_path)
    assert got.prime is None
    assert got.root == "J1234"


def test_an_oversized_status_document_is_refused_whole(tmp_path):
    """The bound exists so json.loads never sees attacker-sized input; a
    document over it is not the engine's, so nothing in it is believed."""
    (tmp_path / "eve_status.json").write_text(json.dumps(VALUES) + " " * 8192)
    got = relay(tmp_path)
    assert got.state == "stale"
    assert got.prime is None
    assert got.root is None
