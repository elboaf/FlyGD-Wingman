"""Copy one settings file onto many. Backup and copy are both injected, so
every failure path is reachable without a real filesystem fault."""
import pytest

from obs_youtube_uploader.evesettings import ops


def make(tmp_path, name, body=b"payload"):
    path = tmp_path / name
    path.write_bytes(body)
    return path


def test_copies_to_every_target(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    targets = [make(tmp_path, "core_char_2.dat"),
               make(tmp_path, "core_char_3.dat")]
    report = ops.copy_to_targets(source, targets, backup=lambda _p: None)
    assert len(report.succeeded) == 2 and report.failed == []
    assert all(t.read_bytes() == b"source" for t in targets)


def test_backs_up_each_target_before_writing(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = make(tmp_path, "core_char_2.dat", b"original")
    seen = []

    def record(path):
        seen.append(path.read_bytes())

    ops.copy_to_targets(source, [target], backup=record)
    assert seen == [b"original"]


def test_refuses_a_kind_mismatch(tmp_path):
    source = make(tmp_path, "core_char_1.dat")
    target = make(tmp_path, "core_user_2.dat")
    report = ops.copy_to_targets(source, [target], backup=lambda _p: None)
    assert report.succeeded == [] and len(report.failed) == 1
    assert "account" in report.failed[0].reason


def test_refuses_a_source_that_is_not_a_settings_file(tmp_path):
    source = make(tmp_path, "notes.txt")
    target = make(tmp_path, "core_char_2.dat")
    with pytest.raises(ValueError):
        ops.copy_to_targets(source, [target], backup=lambda _p: None)


def test_excludes_the_source_from_its_own_targets(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    other = make(tmp_path, "core_char_2.dat")
    report = ops.copy_to_targets(source, [source, other],
                                 backup=lambda _p: None)
    assert [o.path for o in report.succeeded] == [other]


def test_collapses_duplicate_targets(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = make(tmp_path, "core_char_2.dat")
    report = ops.copy_to_targets(source, [target, target],
                                 backup=lambda _p: None)
    assert len(report.outcomes) == 1


def test_a_failing_backup_leaves_the_target_untouched(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = make(tmp_path, "core_char_2.dat", b"original")

    def refuse(_path):
        raise OSError("disk full")

    report = ops.copy_to_targets(source, [target], backup=refuse)
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

    report = ops.copy_to_targets(source, [first, second],
                                 backup=lambda _p: None, copy=flaky)
    assert attempted == [first, second]
    assert [o.path for o in report.succeeded] == [second]
    assert [o.path for o in report.failed] == [first]


def test_a_locked_target_explains_what_to_do(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = make(tmp_path, "core_char_2.dat")

    def locked(src, dst, **kwargs):
        raise PermissionError(32, "in use")

    report = ops.copy_to_targets(source, [target],
                                 backup=lambda _p: None, copy=locked)
    assert "close eve" in report.failed[0].reason.lower()


def test_no_targets_is_an_error(tmp_path):
    source = make(tmp_path, "core_char_1.dat")
    with pytest.raises(ValueError):
        ops.copy_to_targets(source, [], backup=lambda _p: None)
