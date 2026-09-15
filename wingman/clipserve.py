"""Loopback HTTP server that serves registered recordings to the clip editor.

WebView2's URL safety check rejects <video> loads from a file:// page even
when both the page and the media are local files -- the load fails with
`MEDIA_ELEMENT_ERROR: Media load rejected by URL safety check`, and
pywebview's ALLOW_FILE_URLS flag only covers fetch/XHR, not media elements
(measured: an AV1 Main recording WebView2 can decode fine was refused on
the file route). A media element loading `http://127.0.0.1`, though, is a
plain no-cors load, so clip_source registers the selected recording here
and hands the page a token URL instead of a file URI.

Bound to 127.0.0.1 on an ephemeral port; the token is a uuid4, so nothing
outside this process's editor session can name a file; only paths the
controller explicitly registers are ever served. Range requests are the
whole point: scrubbing in a <video> is a series of Range fetches, and a
server that cannot answer 206 leaves the seek bar dead.
"""

import logging
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

logger = logging.getLogger(__name__)

# /<token>/<filename> -- the filename is cosmetic (it names the download in
# a devtools trace); the token is the whole authority.
_ROUTE = re.compile(r"^/([0-9a-f]{32})/")

_server = None
_server_lock = threading.Lock()
_files: dict[str, Path] = {}
_files_lock = threading.Lock()

_CHUNK = 256 * 1024


class _Handler(BaseHTTPRequestHandler):
    # Quiet by design: every scrub is a request, and the default logging
    # would write a line per drag tick.
    def log_message(self, *args):
        pass

    def _file_for(self, token: str) -> Path | None:
        with _files_lock:
            return _files.get(token)

    def _serve(self, send_body: bool) -> None:
        match = _ROUTE.match(self.path)
        path = self._file_for(match.group(1)) if match else None
        if path is None or not path.is_file():
            self.send_error(404)
            return
        size = path.stat().st_size
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        partial = False
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size - 1)
                else:
                    # bytes=-N: the final N bytes.
                    start = max(0, size - int(m.group(2)))
                partial = True
        if start > end or start >= size:
            self.send_error(416)
            return
        length = end - start + 1
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", "video/x-matroska")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if not send_body:
            return
        with path.open("rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(_CHUNK, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (ConnectionError, BrokenPipeError):
                    # A scrub abandons requests mid-flight constantly.
                    return
                remaining -= len(chunk)

    def do_GET(self):
        self._serve(send_body=True)

    def do_HEAD(self):
        self._serve(send_body=False)


def _ensure_server() -> "ThreadingHTTPServer":
    global _server
    with _server_lock:
        if _server is None:
            _server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
            thread = threading.Thread(
                target=_server.serve_forever, daemon=True, name="clipserve"
            )
            thread.start()
    return _server


def url_for(path: Path) -> str:
    """Register `path` and return its loopback URL for the page.

    Each ask mints a fresh token, so a URL from a previous selection
    simply stops resolving -- revocation is the default, not a cleanup
    step. Registered paths live for the process lifetime; they are names
    of recordings the user already has, on a port only the local machine
    can reach, so the cost of an entry is one dict slot, not an exposure.
    """
    path = Path(path)
    token = uuid.uuid4().hex
    with _files_lock:
        _files[token] = path
    server = _ensure_server()
    port = server.server_address[1]
    return f"http://127.0.0.1:{port}/{token}/{path.name}"
