"""Copy one settings file onto many. Backup and copy are both injected, so
every failure path is reachable without a real filesystem fault."""
import os

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
    report = ops.copy_to_targets(source, targets, root=tmp_path,
                                 backup=lambda _p: None)
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
    report = ops.copy_to_targets(source, [target], root=tmp_path,
                                 backup=lambda _p: None)
    assert report.succeeded == [] and len(report.failed) == 1
    assert "account" in report.failed[0].reason


def test_refuses_a_source_that_is_not_a_settings_file(tmp_path):
    source = make(tmp_path, "notes.txt")
    target = make(tmp_path, "core_char_2.dat")
    with pytest.raises(ValueError):
        ops.copy_to_targets(source, [target], root=tmp_path,
                            backup=lambda _p: None)


def test_excludes_the_source_from_its_own_targets(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    other = make(tmp_path, "core_char_2.dat")
    report = ops.copy_to_targets(source, [source, other],
                                 root=tmp_path, backup=lambda _p: None)
    assert [o.path for o in report.succeeded] == [other]


def test_collapses_duplicate_targets(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = make(tmp_path, "core_char_2.dat")
    report = ops.copy_to_targets(source, [target, target],
                                 root=tmp_path, backup=lambda _p: None)
    assert len(report.outcomes) == 1


def test_a_failing_backup_leaves_the_target_untouched(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = make(tmp_path, "core_char_2.dat", b"original")

    def refuse(_path):
        raise OSError("disk full")

    report = ops.copy_to_targets(source, [target], root=tmp_path,
                                 backup=refuse)
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
                                 root=tmp_path, backup=lambda _p: None,
                                 copy=flaky)
    assert attempted == [first, second]
    assert [o.path for o in report.succeeded] == [second]
    assert [o.path for o in report.failed] == [first]


def test_a_locked_target_explains_what_to_do(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = make(tmp_path, "core_char_2.dat")

    def locked(src, dst, **kwargs):
        raise PermissionError(32, "in use")

    report = ops.copy_to_targets(source, [target],
                                 root=tmp_path, backup=lambda _p: None,
                                 copy=locked)
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
    report = ops.copy_to_targets(source, [outside, inside], root=root,
                                 backup=lambda _p: None)
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
        ops.copy_to_targets(source, [target], root=root,
                            backup=lambda _p: None)
    assert target.read_bytes() == b"target"


@pytest.mark.skipif(os.path.normcase("A") != "A",
                    reason="normcase folds case here, so these two paths "
                           "genuinely are the same file")
def test_case_distinct_targets_are_not_collapsed(tmp_path):
    """settings_Alt and settings_alt are two profiles on a case-sensitive
    filesystem, each with its own core_char_2.dat.

    Dedup used str().casefold(), which treats them as one and silently
    drops the second from the target list -- a target the user selected,
    reported neither as copied nor as failed. Exclusion meanwhile used
    Path equality, which does not fold. The two halves disagreed about
    what "the same file" means; both now ask os.path.normcase.
    """
    source = make(tmp_path, "core_char_1.dat", b"source")
    upper = tmp_path / "settings_Alt"
    lower = tmp_path / "settings_alt"
    upper.mkdir()
    lower.mkdir()
    targets = [make(upper, "core_char_2.dat", b"upper"),
               make(lower, "core_char_2.dat", b"lower")]
    report = ops.copy_to_targets(source, targets, root=tmp_path,
                                 backup=lambda _p: None)
    assert len(report.succeeded) == 2 and report.failed == []
    assert all(t.read_bytes() == b"source" for t in targets)


def test_the_source_is_excluded_on_the_same_terms_dedup_uses(tmp_path):
    """Whatever comparison collapses duplicates must also recognise the
    source, or a file is excluded by one half and admitted by the other."""
    source = make(tmp_path, "core_char_1.dat", b"source")
    other = make(tmp_path, "core_char_2.dat")
    report = ops.copy_to_targets(
        source, [source, str(source), other, str(other)],
        root=tmp_path, backup=lambda _p: None)
    assert [o.path for o in report.outcomes] == [other]


def test_copies_onto_a_target_that_does_not_exist_yet(tmp_path):
    """The `if target.exists()` false branch: a first copy has nothing to
    back up, so backup must not be called and the copy must still happen."""
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = tmp_path / "core_char_2.dat"
    backed_up = []
    report = ops.copy_to_targets(source, [target], root=tmp_path,
                                 backup=backed_up.append)
    assert backed_up == []
    assert [o.path for o in report.succeeded] == [target]
    assert target.read_bytes() == b"source"
