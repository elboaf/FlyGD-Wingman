"""Distribution metadata is independent of full setup parsing and local state."""

import copy
import hashlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from wingman import paths
from wingman.evesettings import setup_catalog, setup_model, setup_sharing

FIXTURES = Path(__file__).parent / "fixtures" / "ui_setup"


def write_catalog(directory, entries):
    (directory / "catalog.json").write_text(
        json.dumps(
            {"format": "wingman-setup-catalog", "version": 1, "entries": entries},
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )


@pytest.fixture
def catalog_fixture(tmp_path, monkeypatch):
    directory = tmp_path / "setup-presets"
    directory.mkdir()
    raw = (FIXTURES / "wingman-preset.json").read_bytes()
    entry = {
        "id": "synthetic-fleet",
        "revision": 1,
        "title": "Synthetic fleet — test only",
        "description": "Invented catalog metadata, not an admitted preset.",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "overview_sources": [
            {
                "name": "Synthetic overview",
                "author": "Test author",
                "reference": "https://example.invalid/not-fetched",
                "version": "test-1",
                "license": "Test permission only",
                "license_file": "Test-License.txt",
            }
        ],
        "layout_author": "Test contributor",
        "display": {"width": 1920, "height": 1080, "ui_scale_percent": 100},
        "verification": "Synthetic parser fixture; evidence: tests/fixtures/ui_setup.",
    }
    (directory / "synthetic-fleet-r1.json").write_bytes(raw)
    (directory / "Test-License.txt").write_text(
        "Invented permission text for automated tests only.\n", encoding="utf-8"
    )
    write_catalog(directory, [entry])
    monkeypatch.setattr(paths, "setup_presets_dir", lambda: directory)
    return entry, raw.decode("utf-8"), directory


def read_selected(entry):
    return setup_catalog.read_entry(entry["id"], entry["revision"], entry["sha256"])


def test_list_returns_metadata_without_loading_artifacts(catalog_fixture):
    entry, _, directory = catalog_fixture
    (directory / "synthetic-fleet-r1.json").unlink()
    assert setup_catalog.list_entries() == [entry]


def test_read_returns_exact_full_artifact_and_derived_summary(catalog_fixture):
    entry, text, directory = catalog_fixture
    # CRLF and surrounding whitespace must survive; text-mode reads normalize them.
    text = " \r\n" + text.replace("\n", "\r\n") + "\r\n "
    raw = text.encode("utf-8")
    (directory / "synthetic-fleet-r1.json").write_bytes(raw)
    entry["sha256"] = hashlib.sha256(raw).hexdigest()
    write_catalog(directory, [entry])
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    result = read_selected(entry)
    assert set(result) == {"entry", "text", "summary"}
    assert result["text"] == text
    assert result["entry"] == entry
    parsed = setup_sharing.parse_text(result["text"])
    assert parsed.source_kind == "wingman"
    assert parsed.layout is not None
    assert result["summary"] == setup_model.summarize(parsed)
    assert result["summary"]["counts"] == {
        "presets": 3,
        "tabs": 8,
        "windowGroups": 3,
        "shipLabels": 9,
        "layoutWindows": 12,
    }
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before
    assert not paths.state_dir().exists()


def test_calls_reread_manifest_and_return_detached_metadata(catalog_fixture):
    entry, _, directory = catalog_fixture
    listed = setup_catalog.list_entries()
    listed[0]["display"]["width"] = 1
    assert read_selected(entry)["entry"]["display"]["width"] == 1920
    entry["title"] = "Editorial correction"
    write_catalog(directory, [entry])
    assert read_selected(entry)["entry"]["title"] == "Editorial correction"
    entry["revision"] = 2
    write_catalog(directory, [entry])
    with pytest.raises(setup_catalog.SetupCatalogError, match=r"match|changed"):
        setup_catalog.read_entry(entry["id"], 1, entry["sha256"])
    write_catalog(directory, [])
    assert setup_catalog.list_entries() == []
    with pytest.raises(setup_catalog.SetupCatalogError, match=r"match|available"):
        read_selected(entry)


@pytest.mark.parametrize("revision", [True, False, 0, -1, 2147483648, 1.0, "1", None])
def test_revision_is_a_bounded_nonboolean_integer(catalog_fixture, revision):
    entry, _, directory = catalog_fixture
    entry["revision"] = revision
    write_catalog(directory, [entry])
    with pytest.raises(setup_catalog.SetupCatalogError, match="revision"):
        setup_catalog.list_entries()


@pytest.mark.parametrize(
    "field,bad",
    [
        ("id", "../outside"),
        ("id", "C:\\outside"),
        ("id", "https://a.invalid"),
        ("id", "Upper"),
        ("id", "a--b"),
        ("id", "-a"),
        ("id", "a-"),
        ("id", "é"),
        ("id", "a" * 65),
        ("id", "a\n"),
        ("id", 1),
        ("sha256", "a" * 63),
        ("sha256", "A" * 64),
        ("sha256", "g" * 64),
        ("sha256", "a" * 64 + "\n"),
        ("sha256", None),
    ],
    ids=[
        "traversal",
        "drive",
        "url",
        "upper",
        "double",
        "leading",
        "trailing",
        "unicode",
        "long",
        "newline",
        "number",
        "short-hash",
        "upper-hash",
        "bad-hash",
        "hash-newline",
        "null-hash",
    ],
)
def test_rejects_bad_identity_metadata(catalog_fixture, field, bad):
    entry, _, directory = catalog_fixture
    entry[field] = bad
    write_catalog(directory, [entry])
    with pytest.raises(setup_catalog.SetupCatalogError, match=field):
        setup_catalog.list_entries()


TEXT_FIELDS = [
    ("title", 128),
    ("description", 2048),
    ("layout_author", 128),
    ("verification", 2048),
    *(
        (f"overview_sources.{field}", 512)
        for field in ("name", "author", "reference", "version", "license")
    ),
]


@pytest.mark.parametrize("field,limit", TEXT_FIELDS, ids=[x[0] for x in TEXT_FIELDS])
def test_text_limits_use_codepoints_and_reject_controls(catalog_fixture, field, limit):
    entry, _, directory = catalog_fixture
    record, key = (
        (entry["overview_sources"][0], field.split(".")[1])
        if "." in field
        else (entry, field)
    )
    record[key] = "é" * limit
    write_catalog(directory, [entry])
    assert setup_catalog.list_entries() == [entry]
    for bad in (
        "é" * (limit + 1),
        "",
        None,
        1,
        "x\n",
        "x\x00",
        "x\x7f",
        "x\x85",
        "\ud800",
    ):
        record[key] = bad
        write_catalog(directory, [entry])
        with pytest.raises(setup_catalog.SetupCatalogError, match=key):
            setup_catalog.list_entries()


@pytest.mark.parametrize(
    "field,maximum", [("width", 32768), ("height", 32768), ("ui_scale_percent", 1000)]
)
def test_display_bounds_are_metadata_not_scale_support(catalog_fixture, field, maximum):
    entry, _, directory = catalog_fixture
    for good in (1, maximum):
        entry["display"][field] = good
        write_catalog(directory, [entry])
        assert setup_catalog.list_entries() == [entry]
    for bad in (True, False, 0, -1, maximum + 1, 1.0, "1", None):
        entry["display"][field] = bad
        write_catalog(directory, [entry])
        with pytest.raises(setup_catalog.SetupCatalogError, match=field):
            setup_catalog.list_entries()


@pytest.mark.parametrize("location", ["manifest", "entry", "source", "display"])
@pytest.mark.parametrize("change", ["unknown", "missing", "duplicate", "type"])
def test_each_record_has_exact_unique_fields(catalog_fixture, location, change):
    entry, _, directory = catalog_fixture
    manifest = {"format": "wingman-setup-catalog", "version": 1, "entries": [entry]}
    record = {
        "manifest": manifest,
        "entry": entry,
        "source": entry["overview_sources"][0],
        "display": entry["display"],
    }[location]
    key = next(iter(record))
    if change == "unknown":
        record["path"] = "../outside.json"
    elif change == "missing":
        del record[key]
    elif change == "type":
        if location == "manifest":
            manifest = []
        elif location == "entry":
            manifest["entries"] = [None]
        elif location == "source":
            entry["overview_sources"] = [None]
        else:
            entry["display"] = []
    raw = json.dumps(manifest)
    if change == "duplicate":
        needle = json.dumps(key) + ":"
        raw = raw.replace(needle, f"{json.dumps(key)}: null, {needle}", 1)
    (directory / "catalog.json").write_text(raw, encoding="utf-8")
    with pytest.raises(setup_catalog.SetupCatalogError, match=r"field|object"):
        setup_catalog.list_entries()


@pytest.mark.parametrize(
    "field,value",
    [
        ("format", "other"),
        ("format", 1),
        ("version", True),
        ("version", 1.0),
        ("version", 2),
        ("version", "1"),
        ("entries", {}),
        ("entries", None),
    ],
    ids=["format", "format-type", "bool", "float", "future", "str", "dict", "null"],
)
def test_manifest_format_version_and_entries_are_strict(catalog_fixture, field, value):
    _, _, directory = catalog_fixture
    manifest = json.loads((directory / "catalog.json").read_text(encoding="utf-8"))
    manifest[field] = value
    (directory / "catalog.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(setup_catalog.SetupCatalogError, match=field):
        setup_catalog.list_entries()


def test_entry_collection_budget_and_unique_ids(catalog_fixture):
    entry, _, directory = catalog_fixture
    entries = [{**entry, "id": f"test-{i}"} for i in range(64)]
    write_catalog(directory, entries)
    assert setup_catalog.list_entries() == entries
    write_catalog(directory, [*entries, {**entry, "id": "extra"}])
    with pytest.raises(setup_catalog.SetupCatalogError, match=r"64|entries"):
        setup_catalog.list_entries()
    write_catalog(directory, [entry, {**entry, "revision": 2}])
    with pytest.raises(
        setup_catalog.SetupCatalogError, match=r"Duplicate.*id|duplicate.*id"
    ):
        setup_catalog.list_entries()


def test_overview_source_collection_budget(catalog_fixture):
    entry, _, directory = catalog_fixture
    source = entry["overview_sources"][0]
    entry["overview_sources"] = [copy.deepcopy(source) for _ in range(8)]
    write_catalog(directory, [entry])
    assert setup_catalog.list_entries() == [entry]
    for bad in ([], [source] * 9, {}, None):
        entry["overview_sources"] = bad
        write_catalog(directory, [entry])
        with pytest.raises(setup_catalog.SetupCatalogError, match="overview_sources"):
            setup_catalog.list_entries()


@pytest.mark.parametrize(
    "name",
    [
        "../outside.txt",
        "/outside.txt",
        "C:\\outside.txt",
        "a/b.txt",
        "a\\b.txt",
        "a.txt:stream",
        "a.txt.",
        "a.txt ",
        "a.TXT",
        ".txt",
        "a" * 125 + ".txt",
        "é.txt",
        None,
    ],
    ids=[
        "parent",
        "absolute",
        "drive",
        "slash",
        "backslash",
        "ads",
        "dot",
        "space",
        "extension",
        "empty",
        "long",
        "unicode",
        "null",
    ],
)
def test_license_names_cannot_supply_paths(catalog_fixture, name):
    entry, _, directory = catalog_fixture
    entry["overview_sources"][0]["license_file"] = name
    write_catalog(directory, [entry])
    with pytest.raises(setup_catalog.SetupCatalogError, match="license_file"):
        setup_catalog.list_entries()


def test_identity_and_license_maxima_are_accepted(catalog_fixture):
    entry, text, directory = catalog_fixture
    entry.update(id="a" * 64, revision=2147483647)
    name = "a" * 124 + ".txt"
    entry["overview_sources"][0]["license_file"] = name
    (directory / name).write_text("Invented test permission", encoding="utf-8")
    (directory / f"{entry['id']}-r2147483647.json").write_bytes(text.encode("utf-8"))
    write_catalog(directory, [entry])
    assert read_selected(entry)["entry"] == entry


@pytest.mark.parametrize(
    "kind", ["invalid-json", "utf8", "surrogate", "deep", "nan", "huge-int"]
)
def test_malformed_manifest_errors_keep_their_cause(catalog_fixture, kind):
    _, _, directory = catalog_fixture
    raw = {
        "invalid-json": b'{"format":',
        "utf8": b"\xff",
        "surrogate": b'{"format":"\\ud800","version":1,"entries":[]}',
        "deep": b"[" * 2000 + b"]" * 2000,
        "nan": b'{"format":"wingman-setup-catalog","version":NaN,"entries":[]}',
        "huge-int": b'{"version":' + b"1" * 10000 + b"}",
    }[kind]
    (directory / "catalog.json").write_bytes(raw)
    with pytest.raises(setup_catalog.SetupCatalogError) as caught:
        setup_catalog.list_entries()
    # Schema-level invalid constants need no decoder cause; decoder exceptions do.
    if kind in ("invalid-json", "utf8", "deep", "huge-int"):
        assert caught.value.__cause__ is not None
    assert str(directory) not in str(caught.value)


def test_manifest_byte_budget_is_checked_before_decode(catalog_fixture):
    _, _, directory = catalog_fixture
    raw = (directory / "catalog.json").read_bytes()
    (directory / "catalog.json").write_bytes(raw + b" " * (128 * 1024 - len(raw)))
    assert len(setup_catalog.list_entries()) == 1
    (directory / "catalog.json").write_bytes(b"\xff" * (128 * 1024 + 1))
    with pytest.raises(setup_catalog.SetupCatalogError, match=r"byte|KiB"):
        setup_catalog.list_entries()


@pytest.mark.parametrize(
    "field,bad",
    [
        ("id", "missing"),
        ("id", "../outside"),
        ("id", "/tmp/outside.json"),
        ("id", None),
        ("revision", 2),
        ("revision", True),
        ("revision", 1.0),
        ("sha256", "0" * 64),
        ("sha256", None),
    ],
    ids=[
        "missing",
        "parent",
        "absolute",
        "null",
        "revision",
        "bool",
        "float",
        "hash",
        "null-hash",
    ],
)
def test_selection_requires_exact_valid_identity(catalog_fixture, field, bad):
    entry, _, _ = catalog_fixture
    request = {**entry, field: bad}
    with pytest.raises(
        setup_catalog.SetupCatalogError, match=field + "|match|available"
    ):
        read_selected(request)


def test_artifact_hash_checks_bytes_before_parser(catalog_fixture):
    entry, _, directory = catalog_fixture
    (directory / "synthetic-fleet-r1.json").write_bytes(b"\xff")
    with pytest.raises(setup_catalog.SetupCatalogError, match=r"hash|SHA-256"):
        read_selected(entry)


@pytest.mark.parametrize(
    "kind", ["native", "probe", "no-layout", "invalid", "utf8", "oversize"]
)
def test_selection_requires_a_bounded_full_wingman_setup(catalog_fixture, kind):
    entry, text, directory = catalog_fixture
    artifact = json.loads(text)
    if kind == "native":
        raw = (FIXTURES / "native-complete.yaml").read_bytes()
        parsed = setup_sharing.parse_text(raw.decode("utf-8"))
        assert parsed.source_kind == "native-yaml" and parsed.layout is None
    elif kind == "probe":
        artifact["type"] = "probe-formations"
        raw = json.dumps(artifact).encode("utf-8")
    elif kind == "no-layout":
        artifact["layout"] = None
        raw = json.dumps(artifact).encode("utf-8")
    elif kind == "invalid":
        artifact["layout"]["windows"][0]["geometry"] = [1]
        raw = json.dumps(artifact).encode("utf-8")
    elif kind == "utf8":
        raw = b"\xff"
    else:
        raw = text.encode("utf-8") + b" " * (2 * 1024 * 1024)
    (directory / "synthetic-fleet-r1.json").write_bytes(raw)
    entry["sha256"] = hashlib.sha256(raw).hexdigest()
    write_catalog(directory, [entry])
    with pytest.raises(setup_catalog.SetupCatalogError) as caught:
        read_selected(entry)
    assert "synthetic-fleet" in str(caught.value)
    assert str(directory) not in str(caught.value)
    if kind in ("probe", "no-layout", "invalid"):
        assert isinstance(caught.value.__cause__, setup_model.SetupError)
    elif kind == "utf8":
        assert isinstance(caught.value.__cause__, UnicodeDecodeError)


@pytest.mark.parametrize(
    "asset", ["catalog.json", "synthetic-fleet-r1.json", "Test-License.txt"]
)
@pytest.mark.parametrize("kind", ["absent", "directory", "symlink", "hardlink"])
def test_assets_must_be_regular_nonlinked_files(catalog_fixture, asset, kind):
    entry, _, directory = catalog_fixture
    file = directory / asset
    outside = directory.parent / "outside"
    file.rename(outside)
    if kind == "directory":
        file.mkdir()
    elif kind == "symlink":
        file.symlink_to(outside)
    elif kind == "hardlink":
        os.link(outside, file)
    with pytest.raises(setup_catalog.SetupCatalogError) as caught:
        if asset == "synthetic-fleet-r1.json":
            read_selected(entry)
        else:
            setup_catalog.list_entries()
    assert asset in str(caught.value)
    assert str(directory.parent) not in str(caught.value)
    if kind == "absent":
        assert isinstance(caught.value.__cause__, FileNotFoundError)


@pytest.mark.parametrize("kind", ["missing", "file", "symlink"])
def test_catalog_directory_is_not_created_or_followed(catalog_fixture, kind):
    _, _, directory = catalog_fixture
    outside = directory.parent / "outside"
    directory.rename(outside)
    if kind == "file":
        directory.write_text("Not a directory", encoding="utf-8")
    elif kind == "symlink":
        directory.symlink_to(outside, target_is_directory=True)
    with pytest.raises(setup_catalog.SetupCatalogError, match="directory"):
        setup_catalog.list_entries()
    if kind == "missing":
        assert not directory.exists()


@pytest.mark.parametrize(
    "asset", [".", "catalog.json", "synthetic-fleet-r1.json", "Test-License.txt"]
)
def test_windows_reparse_aliases_are_refused(catalog_fixture, monkeypatch, asset):
    entry, _, directory = catalog_fixture
    original = Path.lstat
    target = directory if asset == "." else directory / asset

    def reparse(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if path == target:
            return SimpleNamespace(
                st_mode=info.st_mode,
                st_nlink=info.st_nlink,
                st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
            )
        return info

    monkeypatch.setattr(Path, "lstat", reparse)
    with pytest.raises(setup_catalog.SetupCatalogError, match=r"link|alias"):
        read_selected(entry)
