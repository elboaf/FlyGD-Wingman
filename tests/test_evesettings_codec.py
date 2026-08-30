import json
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


def test_read_document_without_a_codec_is_a_codec_error(tmp_path):
    with pytest.raises(codec.CodecError, match="not available"):
        codec.read_document(dat(tmp_path), runner=FakeRun(), exe=lambda: None)


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
def test_read_document_surfaces_every_failure_as_codec_error(tmp_path, run, fragment):
    with pytest.raises(codec.CodecError, match=fragment):
        codec.read_document(dat(tmp_path), runner=run, exe=lambda: "/x/codec")


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
def test_write_document_refuses_output_that_does_not_verify(
    tmp_path, encoded, decoded, fragment
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
