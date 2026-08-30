"""Copy one settings file onto many. Backup and copy are both injected, so
every failure path is reachable without a real filesystem fault."""

import pytest

from wingman.evesettings import codec, ops


def make(tmp_path, name, body=b"payload"):
    path = tmp_path / name
    path.write_bytes(body)
    return path


def test_copies_to_every_target(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    targets = [make(tmp_path, "core_char_2.dat"), make(tmp_path, "core_char_3.dat")]
    report = ops.copy_to_targets(source, targets, root=tmp_path, backup=lambda _p: None)
    assert len(report.succeeded) == 2 and report.failed == []
    assert all(t.read_bytes() == b"source" for t in targets)


def test_backs_up_each_target_before_writing(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = make(tmp_path, "core_char_2.dat", b"original")
    seen = []

    def record(path):
        seen.append(path.read_bytes())

    ops.copy_to_targets(source, [target], root=tmp_path, backup=record)
    assert seen == [b"original"]


def test_refuses_a_kind_mismatch(tmp_path):
    source = make(tmp_path, "core_char_1.dat")
    target = make(tmp_path, "core_user_2.dat")
    report = ops.copy_to_targets(
        source, [target], root=tmp_path, backup=lambda _p: None
    )
    assert report.succeeded == [] and len(report.failed) == 1
    assert "account" in report.failed[0].reason


def test_refuses_a_source_that_is_not_a_settings_file(tmp_path):
    source = make(tmp_path, "notes.txt")
    target = make(tmp_path, "core_char_2.dat")
    with pytest.raises(ValueError):
        ops.copy_to_targets(source, [target], root=tmp_path, backup=lambda _p: None)


def test_excludes_the_source_from_its_own_targets(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    other = make(tmp_path, "core_char_2.dat")
    report = ops.copy_to_targets(
        source, [source, other], root=tmp_path, backup=lambda _p: None
    )
    assert [o.path for o in report.succeeded] == [other]


def test_collapses_duplicate_targets(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = make(tmp_path, "core_char_2.dat")
    report = ops.copy_to_targets(
        source, [target, target], root=tmp_path, backup=lambda _p: None
    )
    assert len(report.outcomes) == 1


def test_a_failing_backup_leaves_the_target_untouched(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = make(tmp_path, "core_char_2.dat", b"original")

    def refuse(_path):
        raise OSError("disk full")

    report = ops.copy_to_targets(source, [target], root=tmp_path, backup=refuse)
    assert report.succeeded == [] and len(report.failed) == 1
    assert target.read_bytes() == b"original"


def test_a_failing_write_is_reported_and_the_loop_continues(tmp_path):
    """TriffView throws on the first failure, leaving an unknown mix of
    copied and uncopied targets."""
    source = make(tmp_path, "core_char_1.dat", b"source")
    first = make(tmp_path, "core_char_2.dat")
    second = make(tmp_path, "core_char_3.dat")
    attempted = []

    def flaky(src, dst, **kwargs):
        attempted.append(dst)
        if dst == first:
            raise PermissionError(32, "in use")
        dst.write_bytes(src.read_bytes())

    report = ops.copy_to_targets(
        source, [first, second], root=tmp_path, backup=lambda _p: None, copy=flaky
    )
    assert attempted == [first, second]
    assert [o.path for o in report.succeeded] == [second]
    assert [o.path for o in report.failed] == [first]


def test_a_locked_target_explains_what_to_do(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = make(tmp_path, "core_char_2.dat")

    def locked(src, dst, **kwargs):
        raise PermissionError(32, "in use")

    report = ops.copy_to_targets(
        source, [target], root=tmp_path, backup=lambda _p: None, copy=locked
    )
    assert "close eve" in report.failed[0].reason.lower()


def test_no_targets_is_an_error(tmp_path):
    source = make(tmp_path, "core_char_1.dat")
    with pytest.raises(ValueError):
        ops.copy_to_targets(source, [], root=tmp_path, backup=lambda _p: None)


def test_a_target_outside_the_root_is_reported_not_written(tmp_path):
    """The batch continues: one target through a junction pointing outside
    the tree must not abort the other thirty-nine."""
    root = tmp_path / "EVE"
    root.mkdir()
    source = make(root, "core_char_1.dat", b"source")
    inside = make(root, "core_char_2.dat", b"inside")
    outside = tmp_path / "elsewhere" / "core_char_3.dat"
    report = ops.copy_to_targets(
        source, [outside, inside], root=root, backup=lambda _p: None
    )
    assert [o.path for o in report.failed] == [outside]
    assert [o.path for o in report.succeeded] == [inside]
    # copy_atomic creates missing parents, so "not written" has to mean the
    # directory was never made either.
    assert not outside.exists() and not outside.parent.exists()


def test_a_source_outside_the_root_raises(tmp_path):
    root = tmp_path / "EVE"
    root.mkdir()
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = make(root, "core_char_2.dat", b"target")
    with pytest.raises(ValueError):
        ops.copy_to_targets(source, [target], root=root, backup=lambda _p: None)
    assert target.read_bytes() == b"target"


def case_sensitive(tmp_path) -> bool:
    """Does THIS filesystem distinguish settings_Alt from settings_alt?

    A platform check (`os.path.normcase("A") != "A"`) is the wrong
    question: on macOS, and on any case-insensitive volume mounted under
    Linux, normcase is the identity so the test would run -- and then the
    second mkdir below raises FileExistsError, erroring instead of
    skipping. Ask the filesystem in front of us.
    """
    probe = tmp_path / "_CaseProbe"
    probe.mkdir()
    return not (tmp_path / "_caseprobe").exists()


def test_case_distinct_targets_are_not_collapsed(tmp_path):
    """settings_Alt and settings_alt are two profiles on a case-sensitive
    filesystem, each with its own core_char_2.dat.

    Dedup used str().casefold(), which treats them as one and silently
    drops the second from the target list -- a target the user selected,
    reported neither as copied nor as failed. Exclusion meanwhile used
    Path equality, which does not fold. The two halves disagreed about
    what "the same file" means; both now ask os.path.normcase.
    """
    probe_dir = tmp_path / "probe"
    probe_dir.mkdir()
    if not case_sensitive(probe_dir):
        pytest.skip(
            "this filesystem folds case, so these two paths "
            "genuinely are the same directory"
        )
    source = make(tmp_path, "core_char_1.dat", b"source")
    upper = tmp_path / "settings_Alt"
    lower = tmp_path / "settings_alt"
    upper.mkdir()
    lower.mkdir()
    targets = [
        make(upper, "core_char_2.dat", b"upper"),
        make(lower, "core_char_2.dat", b"lower"),
    ]
    report = ops.copy_to_targets(source, targets, root=tmp_path, backup=lambda _p: None)
    assert len(report.succeeded) == 2 and report.failed == []
    assert all(t.read_bytes() == b"source" for t in targets)


def test_duplicates_collapse_and_the_source_is_excluded(tmp_path):
    """Both halves of the filter, over a list spelling each path twice.

    Not a regression test, and deliberately not named as one: on POSIX
    there is no spelling that normcase equates but Path equality does not,
    so this passes against the pre-fix code too. It pins the behaviour the
    filter is FOR -- the source never copied onto itself, no target
    visited twice -- while test_case_distinct_targets_are_not_collapsed
    above is the one that actually fails without the fix.
    """
    source = make(tmp_path, "core_char_1.dat", b"source")
    other = make(tmp_path, "core_char_2.dat")
    report = ops.copy_to_targets(
        source,
        [source, str(source), other, str(other)],
        root=tmp_path,
        backup=lambda _p: None,
    )
    assert [o.path for o in report.outcomes] == [other]


def test_selective_copy_reads_source_once_and_each_target_once(tmp_path):
    source = make(tmp_path, "core_char_1.dat")
    first = make(tmp_path, "core_char_2.dat")
    second = make(tmp_path, "core_char_3.dat")
    documents = {
        source: codec.Document(
            doc={"bytes:windows": {"tuple": ["source"]}, "bytes:ui": {}},
            had_crc=False,
        ),
        first: codec.Document(
            doc={"bytes:windows": {"tuple": ["first"]}, "bytes:ui": {}},
            had_crc=True,
        ),
        second: codec.Document(
            doc={"bytes:windows": {"tuple": ["second"]}, "bytes:ui": {}},
            had_crc=False,
        ),
    }
    reads = []
    writes = []
    backup = object()

    def read(path):
        reads.append(path)
        return documents[path]

    def write(path, document, **kwargs):
        writes.append((path, document, kwargs))

    report = ops.copy_selected_to_targets(
        source,
        [first, second],
        selected_groups=["windows"],
        root=tmp_path,
        backup=backup,
        read=read,
        write=write,
    )

    assert reads == [source, first, second]
    assert [o.path for o in report.succeeded] == [first, second]
    assert report.failed == []
    assert writes == [
        (
            first,
            codec.Document(doc=documents[source].doc, had_crc=True),
            {"backup": backup},
        ),
        (
            second,
            codec.Document(doc=documents[source].doc, had_crc=False),
            {"backup": backup},
        ),
    ]
    assert writes[0][1].had_crc is documents[first].had_crc
    assert writes[1][1].had_crc is documents[second].had_crc


def test_selective_copy_filters_targets_like_plain_copy(tmp_path):
    source = make(tmp_path, "core_char_1.dat")
    good_target = make(tmp_path, "core_char_2.dat")
    wrong_kind = make(tmp_path, "core_user_3.dat")
    outside = make(tmp_path.parent, "core_char_4.dat")
    documents = {
        source: codec.Document(doc={"bytes:ui": {}}, had_crc=False),
        good_target: codec.Document(doc={"bytes:ui": {}}, had_crc=True),
    }
    reads = []
    writes = []

    def read(path):
        reads.append(path)
        return documents[path]

    report = ops.copy_selected_to_targets(
        source,
        [source, good_target, str(good_target), wrong_kind, outside],
        selected_groups=[],
        root=tmp_path,
        backup=lambda _path: None,
        read=read,
        write=lambda path, document, **kwargs: writes.append(path),
    )

    assert reads == [source, good_target]
    assert writes == [good_target]
    assert [o.path for o in report.succeeded] == [good_target]
    assert [o.path for o in report.failed] == [wrong_kind, outside]


def test_selective_copy_reports_unreadable_target_and_continues(tmp_path):
    source = make(tmp_path, "core_char_1.dat")
    bad_target = make(tmp_path, "core_char_2.dat")
    good_target = make(tmp_path, "core_char_3.dat")
    target_documents = {good_target: codec.Document(doc={"bytes:ui": {}}, had_crc=True)}
    writes = []

    def read(path):
        if path == source:
            return codec.Document(doc={"bytes:ui": {}}, had_crc=False)
        if path == bad_target:
            raise codec.CodecError("cannot decode")
        return target_documents[path]

    report = ops.copy_selected_to_targets(
        source,
        [bad_target, good_target],
        selected_groups=[],
        root=tmp_path,
        backup=lambda _path: None,
        read=read,
        write=lambda path, document, **kwargs: writes.append((path, document)),
    )

    assert [o.path for o in report.failed] == [bad_target]
    assert [o.path for o in report.succeeded] == [good_target]
    assert writes[0][1].had_crc is target_documents[good_target].had_crc


def test_selective_copy_requires_each_target_to_exist(tmp_path):
    source = make(tmp_path, "core_char_1.dat")
    missing = tmp_path / "core_char_2.dat"
    good_target = make(tmp_path, "core_char_3.dat")
    reads = []
    writes = []

    def read(path):
        reads.append(path)
        return codec.Document(doc={"bytes:ui": {}}, had_crc=False)

    report = ops.copy_selected_to_targets(
        source,
        [missing, good_target],
        selected_groups=[],
        root=tmp_path,
        backup=lambda _path: None,
        read=read,
        write=lambda path, document, **kwargs: writes.append(path),
    )

    assert reads == [source, good_target]
    assert [o.path for o in report.failed] == [missing]
    assert [o.path for o in report.succeeded] == [good_target]
    assert writes == [good_target]


def test_selective_copy_reports_transform_failure_per_target(tmp_path):
    source = make(tmp_path, "core_char_1.dat")
    malformed = make(tmp_path, "core_char_2.dat")
    good_target = make(tmp_path, "core_char_3.dat")
    documents = {
        source: codec.Document(doc={"bytes:ui": {}}, had_crc=False),
        malformed: codec.Document(doc={"bytes:ui": []}, had_crc=False),
        good_target: codec.Document(doc={"bytes:ui": {}}, had_crc=True),
    }
    writes = []

    report = ops.copy_selected_to_targets(
        source,
        [malformed, good_target],
        selected_groups=[],
        root=tmp_path,
        backup=lambda _path: None,
        read=documents.__getitem__,
        write=lambda path, document, **kwargs: writes.append(path),
    )

    assert [o.path for o in report.failed] == [malformed]
    assert [o.path for o in report.succeeded] == [good_target]
    assert writes == [good_target]


def test_selective_copy_reports_write_failure_and_delegates_backup(tmp_path):
    source = make(tmp_path, "core_char_1.dat")
    bad_target = make(tmp_path, "core_char_2.dat")
    good_target = make(tmp_path, "core_char_3.dat")
    backup = object()
    calls = []

    def read(path):
        return codec.Document(doc={"bytes:ui": {}}, had_crc=False)

    def write(path, document, **kwargs):
        calls.append((path, kwargs))
        if path == bad_target:
            raise OSError("backup failed")

    report = ops.copy_selected_to_targets(
        source,
        [bad_target, good_target],
        selected_groups=[],
        root=tmp_path,
        backup=backup,
        read=read,
        write=write,
    )

    assert [o.path for o in report.failed] == [bad_target]
    assert [o.path for o in report.succeeded] == [good_target]
    assert calls == [
        (bad_target, {"backup": backup}),
        (good_target, {"backup": backup}),
    ]


def test_selective_copy_source_decode_failure_raises_before_writes(tmp_path):
    source = make(tmp_path, "core_char_1.dat")
    target = make(tmp_path, "core_char_2.dat")
    writes = []

    def unreadable(_path):
        raise codec.CodecError("source cannot decode")

    with pytest.raises(codec.CodecError, match="source cannot decode"):
        ops.copy_selected_to_targets(
            source,
            [target],
            selected_groups=[],
            root=tmp_path,
            backup=lambda _path: None,
            read=unreadable,
            write=lambda path, document, **kwargs: writes.append(path),
        )

    assert writes == []


def test_copies_onto_a_target_that_does_not_exist_yet(tmp_path):
    """The `if target.exists()` false branch: a first copy has nothing to
    back up, so backup must not be called and the copy must still happen."""
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = tmp_path / "core_char_2.dat"
    backed_up = []
    report = ops.copy_to_targets(
        source, [target], root=tmp_path, backup=backed_up.append
    )
    assert backed_up == []
    assert [o.path for o in report.succeeded] == [target]
    assert target.read_bytes() == b"source"
