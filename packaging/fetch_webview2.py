# packaging/fetch_webview2.py
"""Download the WebView2 Evergreen bootstrapper at build time.

Bundled rather than downloaded during installation: a failed download then
fails the BUILD, loudly, instead of failing silently inside a user's install
wizard. See packaging/installer.iss for how it is invoked.

Deliberately NOT sha256-pinned, unlike fetch_ffmpeg.py. Microsoft rotates the
artifact behind the stable fwlink below, so a pin would break the build every
few weeks and teach whoever maintains it to bump the hash without looking.
Integrity comes from the Authenticode signature instead, checked on a Windows
runner by the "Verify the WebView2 bootstrapper is signed by Microsoft" step
in build.yml and release.yml -- that verifies the publisher, which a hash of
an ever-changing file never did.

What IS checked here, because none of it needs Windows:
  * the redirect chain terminates on a microsoft.com host
  * the payload is a PE executable
  * the size is within an order of magnitude of the ~1.7MB stub

The observed digest is printed and recorded in a sidecar so a change in the
artifact is at least visible in the build log.
"""
import hashlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Microsoft's documented permalink for the Evergreen Bootstrapper. It is a
# stub that downloads the runtime itself; it is not the offline installer.
BOOTSTRAPPER_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
OUT_DIR = Path(__file__).parent / "bin"
OUT_NAME = "MicrosoftEdgeWebview2Setup.exe"
# The stub has sat near 1.7MB for years. The bounds are loose on purpose --
# they exist to catch an HTML error page or a truncated read, not to pin a
# size. An error page is a few KB; the standalone installer is ~150MB.
MIN_BYTES = 500_000
MAX_BYTES = 20_000_000
ALLOWED_HOST_SUFFIX = ".microsoft.com"
# Records the digest the bundled stub was fetched with, so a silent swap of
# the artifact shows up as a diff in the build log rather than nowhere.
DIGEST_FILE = OUT_DIR / ".webview2-sha256"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / OUT_NAME

    print(f"Downloading {BOOTSTRAPPER_URL}")
    try:
        with urllib.request.urlopen(BOOTSTRAPPER_URL) as response:
            final_url = response.geturl()
            payload = response.read()
    except (urllib.error.URLError, OSError) as exc:
        print(f"ERROR: download failed: {exc}")
        return 1

    # urlopen follows redirects, so this is the host that actually served the
    # bytes -- go.microsoft.com redirects to a msedge.sf.dl.delivery CDN host
    # under microsoft.com. A redirect landing anywhere else means the link was
    # repointed and must be reviewed by hand, not shipped.
    host = (urllib.parse.urlsplit(final_url).hostname or "").lower()
    if not (host == "microsoft.com" or host.endswith(ALLOWED_HOST_SUFFIX)):
        print(f"ERROR: redirect ended on an unexpected host: {final_url}")
        return 1
    print(f"  served by {host}")

    if not (MIN_BYTES <= len(payload) <= MAX_BYTES):
        print(
            f"ERROR: payload is {len(payload)} bytes, outside the expected "
            f"{MIN_BYTES}-{MAX_BYTES} range - this is probably an error page "
            f"or the wrong artifact"
        )
        return 1

    # 'MZ'. A captive-portal or error page fails here rather than being
    # bundled and handed to Exec() at install time.
    if payload[:2] != b"MZ":
        print("ERROR: payload is not a PE executable (no MZ header)")
        return 1

    digest = hashlib.sha256(payload).hexdigest()
    out_path.write_bytes(payload)
    DIGEST_FILE.write_text(digest)
    print(f"  wrote {out_path} ({len(payload)} bytes)")
    print(f"  sha256={digest}")
    print("  NOTE: the Authenticode signature check in CI is the real gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
