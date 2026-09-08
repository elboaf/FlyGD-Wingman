"""Hidden setup construction on synthetic recipient files only."""

import hashlib
import os
import socket
import zipfile
from contextlib import contextmanager, nullcontext
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from tests.setup_fixtures import documents, install_lossless_codec, seed_profile
from tests.test_evesettings_codec import CODEC
from tests.test_evesettings_profilecopy import _make_junction
from tests.test_ui_setup_documents import incoming, supported_recipient, value
from wingman.evesettings import (
    backup,
    codec,
    profilecopy,
    setup_model,
    setup_sharing,
    tree,
)


@pytest.fixture
def base(tmp_path, monkeypatch):
    install_lossless_codec(monkeypatch)
    base = seed_profile(tmp_path)
    # The original rich recipient exercises real replacement and retirement;
    # neither a sender clone nor a mocked application/relaxed staging guard.
    (base.profile / "core_char_31.dat").write_bytes(b"unselected character")
    (base.profile / "core_user_21.dat").write_bytes(b"unselected account")
    (base.profile / "notes.txt").write_bytes(b"unrelated notes")
    (base.profile / "extras").mkdir()
    (base.profile / "extras" / "core_char_999.dat").write_bytes(b"nested, not copied")
    return base


def plan_for(base):
    found = tree.discover(base.root, base.server, base.profile)
    return profilecopy.prepare_copy(found, base.profile, "new", "Imported")


def files_at(profile):
    return {p.name: p.read_bytes() for p in profile.iterdir() if p.is_file()}


def assert_unchanged(base, before, *, destination=False, debris=False):
    assert files_at(base.profile) == before
    assert (
        base.profile / "extras" / "core_char_999.dat"
    ).read_bytes() == b"nested, not copied"
    plan = plan_for(base) if not destination else None
    if plan is not None:
        assert not plan.destination.exists()
    found = tree.discover(base.root, base.server, base.profile)
    assert {p.path for p in found.profiles} == (
        {base.profile, base.server / "settings_Imported"}
        if destination
        else {base.profile}
    )
    if not debris:
        assert not list(base.server.glob(f"{profilecopy.STAGE_PREFIX}*"))


def stage(base, plan, manifest, *, parsed=None, keep=False):
    from wingman.evesettings import setup_profile

    return setup_profile.stage_setup(
        plan,
        manifest,
        base.account_path.name,
        base.character_path.name,
        parsed or incoming(),
        keep_ship_labels=keep,
        now=1000.0,
    )


def test_manifest_exact_membership_hashes_and_immutable_records(base):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    manifest = setup_profile.capture_manifest(plan)
    assert manifest.profile == base.profile
    names = (
        "core_char_30.dat",
        "core_char_31.dat",
        "core_public__.yaml",
        "core_user_20.dat",
        "core_user_21.dat",
        "prefs.ini",
    )
    assert isinstance(manifest.files, tuple)
    assert tuple(row.name for row in manifest.files) == names
    for row in manifest.files:
        raw = (base.profile / row.name).read_bytes()
        assert row.size == len(raw)
        assert row.sha256 == hashlib.sha256(raw).hexdigest()
    with pytest.raises(FrozenInstanceError):
        manifest.profile = base.server
    with pytest.raises(FrozenInstanceError):
        manifest.files[0].size = 0
    assert setup_profile.require_manifest(plan, manifest) is None


def test_hidden_stage_patches_both_selected_documents_and_preserves_base(base):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    manifest = setup_profile.capture_manifest(plan)
    before = files_at(base.profile)
    original_account = codec.read_document(base.account_path)
    original_character = codec.read_document(base.character_path)
    with stage(base, plan, manifest) as staged:
        assert isinstance(staged, profilecopy.StagedProfileCopy)
        assert staged.plan is plan
        assert not staged.published
        assert not plan.destination.exists()
        found = tree.discover(base.root, base.server, base.profile)
        assert [p.path for p in found.profiles] == [base.profile]
        assert set(files_at(staged.path)) == {row.name for row in manifest.files}
        for name in (
            "core_public__.yaml",
            "prefs.ini",
            "core_char_31.dat",
            "core_user_21.dat",
        ):
            assert (staged.path / name).read_bytes() == before[name]
        account = codec.read_document(staged.path / base.account_path.name)
        character = codec.read_document(staged.path / base.character_path.name)
        assert account != original_account and character != original_character
        assert value(account, "overview", "tabsByWindowInstanceID") == [
            [0, 1, 2],
            [3, 4, 5],
            [6, 7],
        ]
        assert (
            value(account, "overview", "tabsettings_new")["int:0"]["bytes:overview"]
            == "utf8:Incoming Fleet"
        )
        assert value(character, "windows", "windowSizesAndPositions_1")[
            "bytes:overview"
        ] == {"tuple": [100, 120, 340, 500, 1920, 1080]}
        assert (
            character.doc["bytes:windows"]["bytes:shipuialignleftoffset"]["tuple"][0]
            == "long:116444746000000000"
        )
        assert value(character, "windows", "openWindows")["bytes:overview_3"] is False
        assert value(account, "tabgroups", "overviewTabs") == 0
        assert "bytes:overviewTabs_names" not in account.doc["bytes:tabgroups"]
        assert (
            account.doc["bytes:tabgroups"]["bytes:syntheticUnrelatedTab"]
            == original_account.doc["bytes:tabgroups"]["bytes:syntheticUnrelatedTab"]
        )
        for section in ("syntheticPrivate", "defaultoverview", "audio"):
            assert (
                account.doc[f"bytes:{section}"]
                == original_account.doc[f"bytes:{section}"]
            )
        for section in ("syntheticPrivate", "ui"):
            assert (
                character.doc[f"bytes:{section}"]
                == original_character.doc[f"bytes:{section}"]
            )
        setup_profile.require_manifest(plan, manifest)
        assert files_at(base.profile) == before
    assert_unchanged(base, before)


def test_publication_uses_original_stage_and_cleanup_never_removes_destination(
    base, monkeypatch
):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    manifest = setup_profile.capture_manifest(plan)
    before = files_at(base.profile)
    original_stage_copy = profilecopy.stage_copy
    originals = []

    @contextmanager
    def observe_stage(plan):
        with original_stage_copy(plan) as staged:
            originals.append(staged)
            yield staged

    monkeypatch.setattr(profilecopy, "stage_copy", observe_stage)
    with stage(base, plan, manifest) as staged:
        assert staged is originals[0]
        created = profilecopy.publish_new(staged)
        expected_files = files_at(created)
    assert staged.published
    assert created == plan.destination
    assert files_at(created) == expected_files
    assert set(expected_files) == {row.name for row in manifest.files}
    assert_unchanged(base, before, destination=True)


@pytest.mark.parametrize("name", ["core_public__.yaml", "prefs.ini"])
def test_missing_local_preferences_name_the_missing_file(base, name):
    from wingman.evesettings import setup_profile

    (base.profile / name).unlink()
    before = files_at(base.profile)
    with pytest.raises((ValueError, OSError), match=name):
        setup_profile.capture_manifest(plan_for(base))
    assert_unchanged(base, before)


@pytest.mark.parametrize(
    "change", ["add", "remove", "replace", "same-size", "local-same-size"]
)
def test_manifest_reenumerates_and_rehashes_instead_of_trusting_metadata(base, change):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    expected = setup_profile.capture_manifest(plan)
    path = base.profile / (
        "prefs.ini" if change == "local-same-size" else "core_char_31.dat"
    )
    stat = path.stat()
    if change == "add":
        (base.profile / "core_char_99.dat").write_bytes(b"added")
    elif change == "remove":
        path.unlink()
    elif change == "replace":
        path.unlink()
        path.write_bytes(b"replacement")
    else:
        path.write_bytes(b"x" * stat.st_size)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        assert path.stat().st_size == stat.st_size
        assert path.stat().st_mtime_ns == stat.st_mtime_ns
    before = files_at(base.profile)
    with pytest.raises((ValueError, OSError)):
        setup_profile.require_manifest(plan, expected)
    with pytest.raises((ValueError, OSError)), stage(base, plan, expected):
        pytest.fail("changed base must not yield")
    assert_unchanged(base, before)


def test_manifest_cannot_be_reused_for_another_profile(base):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    expected = setup_profile.capture_manifest(plan)
    with pytest.raises(ValueError):
        setup_profile.require_manifest(plan, replace(expected, profile=base.server))


def test_setup_refuses_replacement_mode(base):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    expected = setup_profile.capture_manifest(plan)
    with (
        pytest.raises(ValueError, match="new"),
        stage(base, replace(plan, mode="replace"), expected),
    ):
        pytest.fail("setup must not stage replacement plans")


@pytest.mark.parametrize("field", ["account", "character"])
@pytest.mark.parametrize(
    "name",
    [
        "../core_user_20.dat",
        "sub/core_user_20.dat",
        "sub\\core_user_20.dat",
        "C:core_user_20.dat",
        "core_user_999.dat",
        "prefs.ini",
        "",
    ],
)
def test_selected_names_must_be_present_kind_correct_basenames(base, field, name):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    expected = setup_profile.capture_manifest(plan)
    before = files_at(base.profile)
    account = name if field == "account" else base.account_path.name
    character = name if field == "character" else base.character_path.name
    with (
        pytest.raises(ValueError),
        setup_profile.stage_setup(
            plan,
            expected,
            account,
            character,
            incoming(),
            keep_ship_labels=False,
            now=1000.0,
        ),
    ):
        pytest.fail("invalid selection must not yield")
    assert_unchanged(base, before)


def test_selected_pair_cannot_swap_kinds(base):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    with (
        pytest.raises(ValueError),
        setup_profile.stage_setup(
            plan,
            setup_profile.capture_manifest(plan),
            base.character_path.name,
            base.account_path.name,
            incoming(),
            keep_ship_labels=False,
            now=1000.0,
        ),
    ):
        pytest.fail("wrong kinds must not yield")


def test_ordinary_copy_and_backup_remain_dat_only(base, tmp_path):
    plan = plan_for(base)
    with profilecopy.stage_copy(plan) as staged:
        assert set(files_at(staged.path)) == {
            "core_char_30.dat",
            "core_char_31.dat",
            "core_user_20.dat",
            "core_user_21.dat",
        }
    saved = backup.create_profile_backup(
        tmp_path / "backups", base.profile, origin="manual"
    )
    with zipfile.ZipFile(saved) as archive:
        assert set(archive.namelist()) == {
            "core_char_30.dat",
            "core_char_31.dat",
            "core_user_20.dat",
            "core_user_21.dat",
            backup.MANIFEST_NAME,
        }
    assert tree.file_kind("prefs.ini") is None
    assert tree.file_kind("core_public__.yaml") is None


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX special files and unprivileged symlinks"
)
@pytest.mark.parametrize(
    "name", ["core_char_31.dat", "core_public__.yaml", "prefs.ini"]
)
@pytest.mark.parametrize(
    "kind",
    [
        "directory",
        "fifo",
        "socket",
        "link-inside",
        "link-outside",
        "link-broken",
        "hardlink",
    ],
)
def test_manifest_refuses_special_files_and_aliases_before_reading(
    base, tmp_path, monkeypatch, name, kind
):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    path = base.profile / name
    raw = path.read_bytes()
    path.unlink()
    outside = tmp_path / "outside"
    outside.write_bytes(raw)
    sock = None
    if kind == "directory":
        path.mkdir()
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind == "socket":
        sock = socket.socket(socket.AF_UNIX)
        # Keep the Unix socket pathname under its platform length ceiling.
        cwd = Path.cwd()
        try:
            os.chdir(base.profile)
            sock.bind(name)
        finally:
            os.chdir(cwd)
    elif kind == "hardlink":
        os.link(outside, path)
    else:
        target = {
            "link-inside": base.profile / "notes.txt",
            "link-outside": outside,
            "link-broken": tmp_path / "missing",
        }[kind]
        path.symlink_to(target)
    real_open = os.open
    real_path_open = Path.open

    def checked_open(filename, *args, **kwargs):
        assert Path(filename) != path, "must reject special entries before opening"
        return real_open(filename, *args, **kwargs)

    def checked_path_open(filename, *args, **kwargs):
        assert filename != path, "must reject special entries before opening"
        return real_path_open(filename, *args, **kwargs)

    monkeypatch.setattr(os, "open", checked_open)
    monkeypatch.setattr(Path, "open", checked_path_open)
    try:
        with pytest.raises((ValueError, OSError), match=name):
            setup_profile.capture_manifest(plan)
        assert not plan.destination.exists()
        assert outside.read_bytes() == raw
    finally:
        if sock is not None:
            sock.close()


@pytest.mark.skipif(os.name == "nt", reason="case-sensitive POSIX alias fabrication")
@pytest.mark.parametrize(
    "name", ["CORE_CHAR_31.DAT", "PREFS.INI", "core_public__.yaml.", "prefs.ini "]
)
def test_windows_name_aliases_are_refused_not_ignored(base, name):
    from wingman.evesettings import setup_profile

    (base.profile / name).write_bytes(b"alias")
    with pytest.raises(ValueError, match="alias"):
        setup_profile.capture_manifest(plan_for(base))


@pytest.mark.parametrize("edge", ["root", "server", "source"])
def test_changed_hierarchy_links_refuse_even_when_resolving_within_root(base, edge):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    expected = setup_profile.capture_manifest(plan)
    path = getattr(plan, edge)
    real = path.with_name("moved-" + path.name)
    path.rename(real)
    if os.name == "nt":
        _make_junction(path, real)
    else:
        path.symlink_to(real, target_is_directory=True)
    try:
        with pytest.raises(ValueError), stage(base, plan, expected):
            pytest.fail("linked hierarchy must not yield")
        assert not plan.destination.exists()
    finally:
        if os.name == "nt":
            path.rmdir()
        else:
            path.unlink()
        real.rename(path)


@pytest.mark.skipif(os.name != "nt", reason="requires real Windows junction")
@pytest.mark.parametrize("name", ["core_char_31.dat", "prefs.ini"])
def test_recognized_file_shaped_junction_refuses(base, tmp_path, name):
    from wingman.evesettings import setup_profile

    path = base.profile / name
    path.unlink()
    target = tmp_path / "outside"
    target.mkdir()
    _make_junction(path, target)
    try:
        with pytest.raises(ValueError, match=name):
            setup_profile.capture_manifest(plan_for(base))
    finally:
        path.rmdir()


@pytest.mark.parametrize("edge", ["server", "source", "destination"])
def test_plan_edges_must_remain_direct_contained_children(base, tmp_path, edge):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    expected = setup_profile.capture_manifest(plan)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with (
        pytest.raises(ValueError),
        stage(base, replace(plan, **{edge: outside}), expected),
    ):
        pytest.fail("escaping plan must not yield")
    assert list(outside.iterdir()) == []


def test_capture_reenumerates_after_hashing(base, monkeypatch):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    real_iterdir = Path.iterdir
    visits = 0

    def adding_entry(path):
        nonlocal visits
        yield from real_iterdir(path)
        if path == base.profile:
            visits += 1
            if visits == 1:
                (path / "core_char_99.dat").write_bytes(b"added while snapshotting")

    monkeypatch.setattr(Path, "iterdir", adding_entry)
    with pytest.raises(ValueError, match="changed"):
        setup_profile.capture_manifest(plan)


@pytest.mark.parametrize("name", ["core_public__.yaml", "prefs.ini"])
@pytest.mark.parametrize("failure", ["copy-error", "corrupt-copy"])
def test_each_local_copy_failure_discards_entire_stage(
    base, monkeypatch, name, failure
):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    expected = setup_profile.capture_manifest(plan)
    before = files_at(base.profile)
    real_copy = profilecopy.atomicio.copy_atomic

    def copy(source, target):
        if source.name == name and failure == "copy-error":
            raise OSError(f"copy failed: {name}")
        real_copy(source, target)
        if source.name == name:
            target.write_bytes(b"bad copy")

    monkeypatch.setattr(profilecopy.atomicio, "copy_atomic", copy)
    with pytest.raises((OSError, ValueError)), stage(base, plan, expected):
        pytest.fail("failed or corrupt copy must not yield")
    assert_unchanged(base, before)


@pytest.mark.parametrize("change", ["add", "remove", "replace", "same-size", "local"])
def test_source_changes_during_staging_are_not_rebased(base, monkeypatch, change):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    expected = setup_profile.capture_manifest(plan)
    real_copy = profilecopy.atomicio.copy_atomic
    changed = None

    def copy(source, target):
        nonlocal changed
        real_copy(source, target)
        if source.name != "prefs.ini":
            return
        path = base.profile / ("prefs.ini" if change == "local" else "core_char_31.dat")
        stat = path.stat()
        if change == "add":
            (base.profile / "core_user_99.dat").write_bytes(b"added")
        elif change == "remove":
            path.unlink()
        else:
            if change == "replace":
                path.unlink()
            path.write_bytes(b"x" * stat.st_size)
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        changed = files_at(base.profile)

    monkeypatch.setattr(profilecopy.atomicio, "copy_atomic", copy)
    with pytest.raises(ValueError, match="changed"), stage(base, plan, expected):
        pytest.fail("source mutation must not yield")
    assert changed is not None
    assert_unchanged(base, changed)


@pytest.mark.parametrize(
    "name", ["core_char_31.dat", "core_public__.yaml", "prefs.ini", "core_user_20.dat"]
)
@pytest.mark.parametrize("change", ["modify", "remove", "add"])
def test_all_staged_bytes_and_membership_are_verified_after_patching(
    base, monkeypatch, name, change
):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    expected = setup_profile.capture_manifest(plan)
    before = files_at(base.profile)
    real_write = codec.write_document

    def write(path, document, **kwargs):
        revision = real_write(path, document, **kwargs)
        if path.name == base.character_path.name:
            target = path.parent / name
            if change == "remove":
                target.unlink()
            elif change == "add":
                (path.parent / "core_char_99.dat").write_bytes(b"injected")
            else:
                target.write_bytes(b"modified")
        return revision

    monkeypatch.setattr(codec, "write_document", write)
    with pytest.raises((ValueError, OSError)), stage(base, plan, expected):
        pytest.fail("a modified staged base must not yield")
    assert_unchanged(base, before)


@pytest.mark.parametrize("which", [1, 2], ids=["account", "character"])
@pytest.mark.parametrize("failure", ["encode", "verify-json", "verify-mismatch"])
def test_codec_encoding_and_verification_failures_never_publish(
    base, monkeypatch, which, failure
):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    expected = setup_profile.capture_manifest(plan)
    before = files_at(base.profile)
    transport = codec._run
    writes = 0

    def run(mode, payload, **kwargs):
        nonlocal writes
        if mode == "encode":
            writes += 1
            if writes == which and failure == "encode":
                raise codec.CodecError("synthetic encoding refusal")
        elif writes == which:
            if failure == "verify-json":
                return b"not JSON"
            if failure == "verify-mismatch":
                return b'{"had_crc": false, "doc": {}}'
        return transport(mode, payload, **kwargs)

    monkeypatch.setattr(codec, "_run", run)
    with pytest.raises(codec.CodecError), stage(base, plan, expected):
        pytest.fail("failed codec must not yield")
    assert writes == which
    assert_unchanged(base, before)


@pytest.mark.parametrize("which", [1, 2], ids=["account", "character"])
def test_codec_writes_are_guarded_by_reviewed_revisions(base, monkeypatch, which):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    expected = setup_profile.capture_manifest(plan)
    before = files_at(base.profile)
    real_write = codec.write_document
    calls = []

    def write(path, document, **kwargs):
        calls.append(path.name)
        assert path.parent != base.profile
        assert kwargs["expected_content_revision"] == next(
            row.sha256 for row in expected.files if row.name == path.name
        )
        if len(calls) == which:
            path.write_bytes(b"changed while encoding")
        return real_write(path, document, **kwargs)

    monkeypatch.setattr(codec, "write_document", write)
    with pytest.raises(codec.ContentChangedError), stage(base, plan, expected):
        pytest.fail("revision conflict must not yield")
    assert calls == [base.account_path.name, base.character_path.name][:which]
    assert_unchanged(base, before)


@pytest.mark.parametrize(
    "case,code",
    [
        ("surplus-stack", "affected_stack"),
        ("collision", "protected_definition"),
        ("bad-character", "recipient_shape"),
        ("stack", "affected_stack"),
    ],
)
def test_adapter_refusals_propagate_before_either_document_is_encoded(
    base, monkeypatch, case, code
):
    from tests.setup_fixtures import wire
    from wingman.evesettings import setup_profile

    parsed = incoming()
    if case == "surplus-stack":
        account, character = documents("recipient")
        value(character, "windows", "stacksWindows")["bytes:overview_3"] = "bytes:Mixed"
    else:
        account, character = supported_recipient()
        if case == "collision":
            data = wire()
            data["overview"]["presets"][0]["name"] = "DefaultPreset_639431"
            for tab in data["overview"]["tabs"]:
                if tab["overview"] == "Synthetic Fleet":
                    tab["overview"] = "DefaultPreset_639431"
            parsed = setup_model.validate_wingman(data)
        elif case == "bad-character":
            character.doc["bytes:windows"]["bytes:shipuialignleftoffset"]["tuple"][
                1
            ] = True
        else:
            value(character, "windows", "stacksWindows")["bytes:overview"] = (
                "bytes:Mixed"
            )
    for path, document in zip(
        (base.account_path, base.character_path), (account, character), strict=True
    ):
        codec.write_document(path, document, backup=lambda path: None)
    before = files_at(base.profile)
    plan = plan_for(base)
    expected = setup_profile.capture_manifest(plan)
    transport = codec._run
    encodes = []

    def run(mode, payload, **kwargs):
        if mode == "encode":
            encodes.append(payload)
        return transport(mode, payload, **kwargs)

    monkeypatch.setattr(codec, "_run", run)
    with (
        pytest.raises(setup_model.SetupError) as caught,
        stage(base, plan, expected, parsed=parsed),
    ):
        pytest.fail("unsupported application must not yield")
    assert caught.value.code == code
    assert encodes == []
    assert_unchanged(base, before)


def test_native_configuration_keeps_labels_and_all_character_layout(base):
    from wingman.evesettings import setup_profile

    parsed = setup_sharing.parse_text(
        (
            Path(__file__).parent / "fixtures" / "ui_setup" / "native-complete.yaml"
        ).read_text(encoding="utf-8")
    )
    before = files_at(base.profile)
    plan = plan_for(base)
    expected = setup_profile.capture_manifest(plan)
    with (
        pytest.raises(setup_model.SetupError, match="Keep my ship labels"),
        stage(base, plan, expected, parsed=parsed),
    ):
        pytest.fail("ambiguous labels require an explicit choice")
    with stage(base, plan, expected, parsed=parsed, keep=True) as staged:
        account = codec.read_document(staged.path / base.account_path.name)
        original = codec.read_document(base.account_path)
        assert (
            account.doc["bytes:overview"]["bytes:shipLabels"]
            == original.doc["bytes:overview"]["bytes:shipLabels"]
        )
        assert value(account, "overview", "tabsByWindowInstanceID") == [
            [0, 1, 2, 3, 4, 5, 6, 7]
        ]
        character = codec.read_document(staged.path / base.character_path.name)
        original_character = codec.read_document(base.character_path)
        assert value(character, "windows", "windowSizesAndPositions_1") == value(
            original_character, "windows", "windowSizesAndPositions_1"
        )
        for key in ("bytes:overview_1", "bytes:overview_2", "bytes:overview_3"):
            assert value(character, "windows", "openWindows")[key] is False
    assert_unchanged(base, before)


def test_destination_race_does_not_overwrite_existing_profile(base):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    before = files_at(base.profile)
    with stage(base, plan, setup_profile.capture_manifest(plan)) as staged:
        plan.destination.mkdir()
        (plan.destination / "core_char_30.dat").write_bytes(b"other actor's profile")
        with pytest.raises(FileExistsError):
            profilecopy.publish_new(staged)
    assert files_at(plan.destination) == {"core_char_30.dat": b"other actor's profile"}
    assert_unchanged(base, before, destination=True)


@pytest.mark.parametrize(
    "published", [False, True], ids=["before-publication", "after-publication"]
)
def test_cleanup_failure_uses_original_stage_publication_state(
    base, monkeypatch, caplog, published
):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    expected = setup_profile.capture_manifest(plan)
    before = files_at(base.profile)
    real_rmtree = profilecopy.shutil.rmtree

    def refuse_cleanup(path):
        raise OSError("synthetic cleanup failure")

    monkeypatch.setattr(profilecopy.shutil, "rmtree", refuse_cleanup)
    guard = (
        nullcontext() if published else pytest.raises(OSError, match="cleanup failure")
    )
    with guard, stage(base, plan, expected) as staged:
        if published:
            profilecopy.publish_new(staged)
            # Recreate housekeeping debris after the successful rename to
            # exercise stage_copy's post-publication cleanup distinction.
            staged.path.mkdir()
    assert staged.path.is_dir()
    if published:
        assert "after publishing" in caplog.text
    assert_unchanged(base, before, destination=published, debris=True)
    monkeypatch.setattr(profilecopy.shutil, "rmtree", real_rmtree)
    profilecopy.cleanup_abandoned_stages(base.server)
    assert not staged.path.exists()


@pytest.mark.skipif(not CODEC.is_file(), reason="settings codec not built")
@pytest.mark.parametrize("crc", [False, True], ids=["plain", "crc"])
def test_synthetic_staging_round_trips_two_documents_through_native_codec(
    tmp_path, monkeypatch, crc
):
    from wingman.evesettings import setup_profile

    native_run = codec._run

    def run(mode, payload, **kwargs):
        return native_run(
            mode, payload, runner=kwargs["runner"], exe=lambda: str(CODEC)
        )

    monkeypatch.setattr(codec, "_run", run)
    base = seed_profile(tmp_path)
    for path, document in zip(
        (base.account_path, base.character_path), documents("recipient"), strict=True
    ):
        codec.write_document(
            path, codec.Document(document.doc, crc), backup=lambda path: None
        )
    plan = plan_for(base)
    before = files_at(base.profile)
    with stage(base, plan, setup_profile.capture_manifest(plan)) as staged:
        account = codec.read_document(staged.path / base.account_path.name)
        character = codec.read_document(staged.path / base.character_path.name)
        assert account.had_crc is crc and character.had_crc is crc
        assert value(account, "overview", "tabsByWindowInstanceID") == [
            [0, 1, 2],
            [3, 4, 5],
            [6, 7],
        ]
        assert list(value(account, "overview", "tabsettings_new")) == [
            f"int:{i}" for i in range(8)
        ]
        assert value(character, "windows", "windowSizesAndPositions_1")[
            "bytes:overview_1"
        ] == {"tuple": [-20, 200, 320, 420, 1600, 900]}
        for name in ("prefs.ini", "core_public__.yaml"):
            assert (staged.path / name).read_bytes() == before[name]
    assert files_at(base.profile) == before
    assert not plan.destination.exists()


@pytest.mark.parametrize(
    "name", ["core_user_20.dat", "core_char_30.dat", "core_char_31.dat"]
)
def test_complete_staged_base_must_match_review_before_codec_runs(
    base, monkeypatch, name
):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    expected = setup_profile.capture_manifest(plan)
    before = files_at(base.profile)
    real_stage_copy = profilecopy.stage_copy

    @contextmanager
    def corrupt_stage(plan):
        with real_stage_copy(plan) as staged:
            target = staged.path / name
            target.write_bytes(target.read_bytes() + b" ")
            yield staged

    monkeypatch.setattr(profilecopy, "stage_copy", corrupt_stage)
    monkeypatch.setattr(
        codec,
        "_run",
        lambda *a, **kw: pytest.fail("do not decode or encode an unreviewed base"),
    )
    with pytest.raises(ValueError, match="changed"), stage(base, plan, expected):
        pytest.fail("staged base differs from review")
    assert_unchanged(base, before)


def test_final_source_recheck_catches_mutation_during_encoding(base, monkeypatch):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    expected = setup_profile.capture_manifest(plan)
    real_write = codec.write_document
    changed = None

    def write(path, document, **kwargs):
        nonlocal changed
        revision = real_write(path, document, **kwargs)
        if path.name == base.character_path.name:
            (base.profile / "prefs.ini").write_bytes(b"external edit during encoding")
            changed = files_at(base.profile)
        return revision

    monkeypatch.setattr(codec, "write_document", write)
    with pytest.raises(ValueError, match="changed"), stage(base, plan, expected):
        pytest.fail("a changed base must be reviewed again")
    assert changed is not None
    assert_unchanged(base, changed)


def test_caller_failure_after_publication_does_not_remove_created_profile(base):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    before = files_at(base.profile)
    with (
        pytest.raises(RuntimeError, match="remembering selection"),
        stage(base, plan, setup_profile.capture_manifest(plan)) as staged,
    ):
        profilecopy.publish_new(staged)
        created = files_at(plan.destination)
        raise RuntimeError("remembering selection failed")
    assert staged.published
    assert files_at(plan.destination) == created
    assert_unchanged(base, before, destination=True)


def test_unreadable_base_is_reported_not_interpreted_as_empty(base, monkeypatch):
    from wingman.evesettings import setup_profile

    plan = plan_for(base)
    real_iterdir = Path.iterdir
    error = PermissionError("synthetic permission denied")

    def iterdir(path):
        if path == base.profile:
            raise error
        return real_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    with pytest.raises(PermissionError) as caught:
        setup_profile.capture_manifest(plan)
    assert caught.value is error
    assert not plan.destination.exists()
