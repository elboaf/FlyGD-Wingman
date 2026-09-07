import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from wingman.evesettings import codec

ENVELOPE = {"had_crc": False, "doc": {"bytes:ui": {}}}


class FakeRun:
    """Stands in for subprocess.run: records the call, returns canned output."""

    def __init__(self, stdout=b"", returncode=0, stderr=b"", raise_=None):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr
        self.raise_ = raise_
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        if self.raise_:
            raise self.raise_
        return subprocess.CompletedProcess(
            cmd, self.returncode, stdout=self.stdout, stderr=self.stderr
        )


def dat(tmp_path, data=b"\x7e\x01"):
    p = tmp_path / "core_user_1.dat"
    p.write_bytes(data)
    return p


def test_codec_available_follows_the_exe_lookup():
    assert codec.codec_available(exe=lambda: "/x/codec") is True
    assert codec.codec_available(exe=lambda: None) is False


def test_read_document_feeds_the_file_bytes_to_decode(tmp_path):
    run = FakeRun(stdout=json.dumps(ENVELOPE).encode())
    doc = codec.read_document(dat(tmp_path, b"RAW"), runner=run, exe=lambda: "/x/codec")
    assert doc == codec.Document(doc={"bytes:ui": {}}, had_crc=False)
    cmd, kwargs = run.calls[0]
    assert cmd == ["/x/codec", "decode"]
    assert kwargs["input"] == b"RAW"
    assert kwargs["capture_output"] is True
    assert "timeout" in kwargs


def test_snapshot_hashes_the_bytes_it_decoded(tmp_path):
    target = dat(tmp_path, b"ORIGINAL")

    def run(cmd, **kwargs):
        assert kwargs["input"] == b"ORIGINAL"
        target.write_bytes(b"EXTERNAL")
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps(ENVELOPE).encode(), stderr=b""
        )

    snapshot = codec.read_snapshot(target, runner=run, exe=lambda: "/x/codec")
    assert snapshot.content_revision == hashlib.sha256(b"ORIGINAL").hexdigest()
    assert snapshot.document == codec.Document(ENVELOPE["doc"], False)


def test_backup_time_change_refuses_publication(tmp_path):
    target = dat(tmp_path, b"OLD")
    published = []

    def backup(path):
        path.write_bytes(b"EXTERNAL")

    with pytest.raises(codec.ContentChangedError):
        codec.write_document(
            target,
            codec.Document(ENVELOPE["doc"], False),
            backup=backup,
            runner=TwoStepRun(b"\x7dNEW", json.dumps(ENVELOPE).encode()),
            exe=lambda: "/x/codec",
            publish=lambda p, data: published.append(data),
            expected_content_revision=hashlib.sha256(b"OLD").hexdigest(),
        )
    assert published == []
    assert target.read_bytes() == b"EXTERNAL"


@pytest.mark.parametrize("reader", ["read_document", "read_snapshot"])
def test_read_without_a_codec_is_a_codec_error(tmp_path, reader):
    with pytest.raises(codec.CodecError, match="not available"):
        getattr(codec, reader)(dat(tmp_path), runner=FakeRun(), exe=lambda: None)


@pytest.mark.parametrize(
    "run, fragment",
    [
        (FakeRun(returncode=1, stderr=b"error: bad header"), "bad header"),
        (FakeRun(stdout=b"not json"), "could not be read"),
        (FakeRun(stdout=b'{"doc": 1}'), "could not be read"),
        (FakeRun(raise_=subprocess.TimeoutExpired("codec", 30)), "took too long"),
        (FakeRun(raise_=OSError("no such file")), "no such file"),
    ],
)
@pytest.mark.parametrize("reader", ["read_document", "read_snapshot"])
def test_read_surfaces_every_failure_as_codec_error(tmp_path, run, fragment, reader):
    with pytest.raises(codec.CodecError, match=fragment):
        getattr(codec, reader)(dat(tmp_path), runner=run, exe=lambda: "/x/codec")


def test_write_document_encodes_then_backs_up_then_publishes(tmp_path):
    target = dat(tmp_path, b"OLD")
    run = TwoStepRun(
        b"\x7d\x01NEWBYTES",
        json.dumps({"had_crc": True, "doc": {"bytes:ui": {}}}).encode(),
    )
    events = []
    codec.write_document(
        target,
        codec.Document(doc={"bytes:ui": {}}, had_crc=True),
        backup=lambda p: events.append(("backup", p)),
        runner=run,
        exe=lambda: "/x/codec",
        publish=lambda p, data: events.append(("publish", p, data)),
    )
    assert run.calls == ["encode", "decode"]
    assert events == [("backup", target), ("publish", target, b"\x7d\x01NEWBYTES")]


def test_write_document_takes_no_backup_when_the_codec_fails(tmp_path):
    target = dat(tmp_path, b"OLD")
    events = []
    with pytest.raises(codec.CodecError):
        codec.write_document(
            target,
            codec.Document(doc={}, had_crc=False),
            backup=lambda p: events.append("backup"),
            runner=FakeRun(returncode=1, stderr=b"error: nope"),
            exe=lambda: "/x/codec",
        )
    assert events == []
    assert target.read_bytes() == b"OLD"


class TwoStepRun:
    """encode returns *encoded*; the verifying decode returns *decoded*."""

    def __init__(self, encoded, decoded):
        self.replies = {"encode": encoded, "decode": decoded}
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd[1])
        return subprocess.CompletedProcess(
            cmd, 0, stdout=self.replies[cmd[1]], stderr=b""
        )


@pytest.mark.parametrize(
    "encoded, decoded, fragment",
    [
        (b"", b"", "empty"),
        (b"\x7e\x00junk", b"", "not a settings file"),
        (b"\x7d\x01ok", b"not json", "could not be verified"),
        (
            b"\x7d\x01ok",
            json.dumps({"had_crc": False, "doc": {"other": 1}}).encode(),
            "did not read back",
        ),
    ],
)
@pytest.mark.parametrize("guarded", [False, True])
def test_write_document_refuses_output_that_does_not_verify(
    tmp_path, encoded, decoded, fragment, guarded
):
    """A faulty codec must never replace a valid file with arbitrary bytes."""
    target = dat(tmp_path, b"OLD")
    events = []
    with pytest.raises(codec.CodecError, match=fragment):
        codec.write_document(
            target,
            codec.Document(doc={"bytes:ui": {}}, had_crc=False),
            backup=lambda p: events.append("backup"),
            runner=TwoStepRun(encoded, decoded),
            exe=lambda: "/x/codec",
            expected_content_revision=(
                hashlib.sha256(b"OLD").hexdigest() if guarded else None
            ),
        )
    assert target.read_bytes() == b"OLD" and events == []


def test_write_document_verifies_by_decoding_its_own_output(tmp_path):
    target = dat(tmp_path, b"OLD")
    doc = {"bytes:ui": {"bytes:k": {"tuple": ["long:1", 2.5]}}}
    run = TwoStepRun(b"\x7d\x01NEW", json.dumps({"had_crc": True, "doc": doc}).encode())
    codec.write_document(
        target,
        codec.Document(doc=doc, had_crc=True),
        backup=lambda p: None,
        runner=run,
        exe=lambda: "/x/codec",
    )
    assert run.calls == ["encode", "decode"]
    assert target.read_bytes() == b"\x7d\x01NEW"


def test_write_document_really_publishes_atomically(tmp_path):
    target = dat(tmp_path, b"OLD")
    codec.write_document(
        target,
        codec.Document(doc={}, had_crc=False),
        backup=lambda p: None,
        runner=TwoStepRun(
            b"\x7d\x01NEW", json.dumps({"had_crc": False, "doc": {}}).encode()
        ),
        exe=lambda: "/x/codec",
    )
    assert target.read_bytes() == b"\x7d\x01NEW"
    assert [p.name for p in tmp_path.iterdir()] == ["core_user_1.dat"]


def test_require_content_revision_accepts_matching_bytes(tmp_path):
    target = dat(tmp_path, b"OLD")
    assert (
        codec.require_content_revision(target, hashlib.sha256(b"OLD").hexdigest())
        is None
    )


def test_require_content_revision_refuses_mismatching_bytes(tmp_path):
    target = dat(tmp_path, b"EXTERNAL")
    with pytest.raises(codec.ContentChangedError):
        codec.require_content_revision(target, hashlib.sha256(b"OLD").hexdigest())
    assert target.read_bytes() == b"EXTERNAL"


@pytest.mark.parametrize("operation", ["require", "write"])
@pytest.mark.parametrize(
    "expected",
    [
        "",
        "0" * 63,
        "0" * 65,
        "A" * 64,
        "g" * 64,
        "0" * 64 + "\n",
        " " + "0" * 64,
        "\uff10" * 64,
        b"0" * 64,
        False,
        1,
    ],
)
def test_malformed_content_revision_is_rejected_before_codec_runs(
    tmp_path, operation, expected
):
    target = dat(tmp_path, b"OLD")
    run = FakeRun()
    events = []
    with pytest.raises(codec.CodecError):
        if operation == "require":
            codec.require_content_revision(target, expected)
        else:
            codec.write_document(
                target,
                codec.Document(ENVELOPE["doc"], False),
                backup=lambda p: events.append("backup"),
                runner=run,
                exe=lambda: "/x/codec",
                publish=lambda p, data: events.append("publish"),
                expected_content_revision=expected,
            )
    assert run.calls == []
    assert events == []
    assert target.read_bytes() == b"OLD"


def test_require_content_revision_does_not_accept_none(tmp_path):
    with pytest.raises(codec.CodecError):
        codec.require_content_revision(dat(tmp_path, b"OLD"), None)


@pytest.mark.parametrize("restore_metadata", [False, True])
def test_conflicting_content_is_refused_before_backup(tmp_path, restore_metadata):
    target = dat(tmp_path, b"OLD")
    original_stat = target.stat()
    target.write_bytes(b"NEW")
    if restore_metadata:
        os.utime(target, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        assert target.stat().st_mtime_ns == original_stat.st_mtime_ns
        assert target.stat().st_size == original_stat.st_size
    events = []
    with pytest.raises(codec.ContentChangedError):
        codec.write_document(
            target,
            codec.Document(ENVELOPE["doc"], False),
            backup=lambda p: events.append("backup"),
            runner=TwoStepRun(b"\x7dNEW", json.dumps(ENVELOPE).encode()),
            exe=lambda: "/x/codec",
            publish=lambda p, data: events.append("publish"),
            expected_content_revision=hashlib.sha256(b"OLD").hexdigest(),
        )
    assert events == []
    assert target.read_bytes() == b"NEW"


@pytest.mark.parametrize("mutation_step", ["encode", "decode"])
def test_codec_time_change_is_refused_before_backup(tmp_path, mutation_step):
    target = dat(tmp_path, b"OLD")
    external = TwoStepRun(b"\x7dNEW", json.dumps(ENVELOPE).encode())
    events = []

    def run(cmd, **kwargs):
        if cmd[1] == mutation_step:
            target.write_bytes(b"EXTERNAL")
        return external(cmd, **kwargs)

    with pytest.raises(codec.ContentChangedError):
        codec.write_document(
            target,
            codec.Document(ENVELOPE["doc"], False),
            backup=lambda p: events.append("backup"),
            runner=run,
            exe=lambda: "/x/codec",
            publish=lambda p, data: events.append("publish"),
            expected_content_revision=hashlib.sha256(b"OLD").hexdigest(),
        )
    assert external.calls == ["encode", "decode"]
    assert events == []
    assert target.read_bytes() == b"EXTERNAL"


@pytest.mark.parametrize("failure", ["missing", "unreadable"])
@pytest.mark.parametrize("stage", ["require", "before_backup", "during_backup"])
def test_unavailable_content_raises_conflict_with_io_cause(
    tmp_path, monkeypatch, failure, stage
):
    target = dat(tmp_path, b"OLD")
    events = []
    open_file = Path.open
    denied = PermissionError("file is locked")

    def open_unless_target(path, *args, **kwargs):
        if path == target:
            raise denied
        return open_file(path, *args, **kwargs)

    def make_unavailable():
        if failure == "missing":
            target.unlink()
        else:
            # chmod is not a reliable denial on Windows or for privileged users.
            # Replace only the OS read boundary; hashing/guards stay real.
            monkeypatch.setattr(Path, "open", open_unless_target)

    def backup(path):
        events.append("backup")
        if stage == "during_backup":
            make_unavailable()

    if stage != "during_backup":
        make_unavailable()
    with pytest.raises(codec.ContentChangedError) as caught:
        if stage == "require":
            codec.require_content_revision(target, hashlib.sha256(b"OLD").hexdigest())
        else:
            codec.write_document(
                target,
                codec.Document(ENVELOPE["doc"], False),
                backup=backup,
                runner=TwoStepRun(b"\x7dNEW", json.dumps(ENVELOPE).encode()),
                exe=lambda: "/x/codec",
                publish=lambda p, data: events.append("publish"),
                expected_content_revision=hashlib.sha256(b"OLD").hexdigest(),
            )
    assert isinstance(caught.value, codec.CodecError)
    if failure == "missing":
        assert isinstance(caught.value.__cause__, FileNotFoundError)
        assert not target.exists()
    else:
        assert caught.value.__cause__ is denied
        with open_file(target, "rb") as stream:
            assert stream.read() == b"OLD"
    assert events == (["backup"] if stage == "during_backup" else [])


@pytest.mark.parametrize("failure_step", ["backup", "publish"])
@pytest.mark.parametrize("guarded", [False, True])
def test_failed_backup_or_publish_propagates_without_returning_revision(
    tmp_path, failure_step, guarded
):
    target = dat(tmp_path, b"OLD")
    saved = tmp_path / "backup.dat"
    events = []
    error = OSError("disk full")

    def backup(path):
        events.append("backup")
        if failure_step == "backup":
            raise error
        saved.write_bytes(path.read_bytes())

    def publish(path, data):
        events.append("publish")
        raise error

    revision = None
    with pytest.raises(OSError) as caught:
        revision = codec.write_document(
            target,
            codec.Document(ENVELOPE["doc"], False),
            backup=backup,
            runner=TwoStepRun(b"\x7dNEW", json.dumps(ENVELOPE).encode()),
            exe=lambda: "/x/codec",
            publish=publish,
            expected_content_revision=(
                hashlib.sha256(b"OLD").hexdigest() if guarded else None
            ),
        )
    assert caught.value is error
    assert revision is None
    assert target.read_bytes() == b"OLD"
    assert events == (["backup"] if failure_step == "backup" else ["backup", "publish"])
    if failure_step == "publish":
        assert saved.read_bytes() == b"OLD"
    else:
        assert not saved.exists()


@pytest.mark.parametrize("guarded", [False, True])
def test_success_returns_verified_bytes_revision_after_real_publication(
    tmp_path, guarded
):
    target = dat(tmp_path, b"OLD")
    saved = tmp_path / "backup.dat"
    run = TwoStepRun(b"\x7dNEW", json.dumps(ENVELOPE).encode())

    def backup(path):
        assert run.calls == ["encode", "decode"]
        saved.write_bytes(path.read_bytes())

    revision = codec.write_document(
        target,
        codec.Document(ENVELOPE["doc"], False),
        backup=backup,
        runner=run,
        exe=lambda: "/x/codec",
        expected_content_revision=(
            hashlib.sha256(b"OLD").hexdigest() if guarded else None
        ),
    )
    assert revision == hashlib.sha256(b"\x7dNEW").hexdigest()
    assert target.read_bytes() == b"\x7dNEW"
    assert saved.read_bytes() == b"OLD"


def test_returned_revision_is_not_a_reread_after_publication(tmp_path):
    target = dat(tmp_path, b"OLD")

    def publish(path, data):
        assert data == b"\x7dNEW"
        path.write_bytes(data)
        # The next external writer must not become our successful save's baseline.
        path.write_bytes(b"EXTERNAL")

    revision = codec.write_document(
        target,
        codec.Document(ENVELOPE["doc"], False),
        backup=lambda p: None,
        runner=TwoStepRun(b"\x7dNEW", json.dumps(ENVELOPE).encode()),
        exe=lambda: "/x/codec",
        publish=publish,
        expected_content_revision=hashlib.sha256(b"OLD").hexdigest(),
    )
    assert revision == hashlib.sha256(b"\x7dNEW").hexdigest()
    assert target.read_bytes() == b"EXTERNAL"


def test_unguarded_write_allows_backup_time_change(tmp_path):
    target = dat(tmp_path, b"OLD")

    def backup(path):
        path.write_bytes(b"EXTERNAL")

    revision = codec.write_document(
        target,
        codec.Document(ENVELOPE["doc"], False),
        backup=backup,
        runner=TwoStepRun(b"\x7dNEW", json.dumps(ENVELOPE).encode()),
        exe=lambda: "/x/codec",
    )
    assert revision == hashlib.sha256(b"\x7dNEW").hexdigest()
    assert target.read_bytes() == b"\x7dNEW"


# The same platform branch test_packaging_completeness.py uses. Without it
# this path omits .exe, so on Windows -- the only platform that ships the
# codec -- the skipif always fires and the one test that exercises the real
# binary silently never runs.
CODEC = (
    Path(__file__).resolve().parent.parent
    / "packaging"
    / "bin"
    / (
        "wingman-settings-codec.exe"
        if sys.platform == "win32"
        else "wingman-settings-codec"
    )
)


@pytest.mark.skipif(not CODEC.is_file(), reason="settings codec not built")
def test_the_real_codec_round_trips_through_the_seam(tmp_path):
    target = dat(tmp_path, b"")
    doc = codec.Document(
        doc={"bytes:ui": {"bytes:k": {"tuple": ["long:134251880277573607", 2.5]}}},
        had_crc=False,
    )
    codec.write_document(target, doc, backup=lambda p: None, exe=lambda: str(CODEC))
    assert codec.read_document(target, exe=lambda: str(CODEC)) == doc
