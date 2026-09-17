"""The loopback server that feeds the clip editor its bytes.

WebView2 refuses <video> loads from a file:// page outright, so the
editor's media comes from this server. What the tests pin: Range support
(scrubbing IS Range requests), token authority (nothing unregistered is
served, unknown tokens 404), and loopback-only binding.
"""

import os
import urllib.error
import urllib.request

import pytest

from wingman import clipserve


def fetch(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, dict(r.headers), r.read()


def test_url_for_serves_the_registered_file(tmp_path):
    src = tmp_path / "fight.mkv"
    src.write_bytes(b"0123456789abcdef")
    url = clipserve.url_for(src)
    status, headers, body = fetch(url)
    assert status == 200
    assert body == b"0123456789abcdef"
    assert headers["Accept-Ranges"] == "bytes"


def test_range_requests_are_answered_with_206(tmp_path):
    """A <video> seek is a Range fetch; a server that cannot answer 206
    leaves the scrub bar dead."""
    src = tmp_path / "fight.mkv"
    src.write_bytes(b"0123456789abcdef")
    url = clipserve.url_for(src)
    status, headers, body = fetch(url, {"Range": "bytes=4-9"})
    assert status == 206
    assert body == b"456789"
    assert headers["Content-Range"] == "bytes 4-9/16"

    status, _, body = fetch(url, {"Range": "bytes=12-"})
    assert status == 206 and body == b"cdef"

    status, _, body = fetch(url, {"Range": "bytes=-4"})
    assert status == 206 and body == b"cdef"


def test_unknown_tokens_404():
    server = clipserve._ensure_server()
    url = f"http://127.0.0.1:{server.server_address[1]}/{'0' * 32}/nope.mkv"
    try:
        fetch(url)
        raise AssertionError("unknown token must not serve")
    except urllib.error.HTTPError as e:
        assert e.code == 404


def test_the_server_binds_loopback_only():
    server = clipserve._ensure_server()
    assert server.server_address[0] == "127.0.0.1"


def test_a_fresh_ask_mints_a_fresh_token(tmp_path):
    src = tmp_path / "a.mkv"
    src.write_bytes(b"x")
    one = clipserve.url_for(src)
    two = clipserve.url_for(src)
    assert one != two  # revocation is the default: old links stop mattering


def test_open_shared_reads_the_whole_file(tmp_path):
    src = tmp_path / "fight.mkv"
    src.write_bytes(b"0123456789abcdef")
    with clipserve._open_shared(src) as f:
        assert f.read() == b"0123456789abcdef"


@pytest.mark.skipif(
    os.name != "nt", reason="delete-while-open is a Windows sharing rule"
)
def test_a_live_reader_does_not_block_deletion(tmp_path):
    """The reason _open_shared exists: Python's open() shares read/write on
    Windows but not delete, so a mid-scrub Range fetch made unlink() fail
    with WinError 32. With FILE_SHARE_DELETE the delete wins and the
    reader drains the unlinked file to EOF."""
    src = tmp_path / "fight.mkv"
    src.write_bytes(b"0123456789abcdef")
    with clipserve._open_shared(src) as f:
        f.seek(4)
        src.unlink()  # plain open() here raises PermissionError
        assert f.read(6) == b"456789"
        assert f.read() == b"abcdef"


def teardown_module(module):
    """Stop the server so a daemon thread never leaks between modules."""
    if clipserve._server is not None:
        clipserve._server.shutdown()
        clipserve._server.server_close()
        clipserve._server = None
    clipserve._files.clear()
