# packaging/uploader.spec
# One-folder build. Deliberately not one-file: one-file unpacks to temp on
# every launch (slow with ffmpeg bundled) and trips antivirus heuristics
# markedly more often.
from pathlib import Path

ROOT = Path(SPECPATH).parent
BIN = ROOT / "packaging" / "bin"
ICON = ROOT / "wingman" / "assets" / "app.ico"
WEB = ROOT / "wingman" / "web"

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[
        (str(BIN / "ffmpeg.exe"), "bin"),
        (str(BIN / "ffprobe.exe"), "bin"),
        # v1.1 interpreter. Bundled-only by design: paths.engine_exe()
        # deliberately does not fall back to PATH, because a user's
        # AutoHotkey v2 handed a v1 script fails with parse errors that
        # read like a bug in the script.
        (str(BIN / "AutoHotkeyU64.exe"), "bin"),
    ],
    datas=[
        # The page is data, not code: modulegraph only follows Python
        # imports, so nothing under web/ reaches the bundle unless it is
        # listed here. PyInstaller exits 0 either way (see the ffmpeg
        # comment in build.yml), and the failure is total rather than
        # partial -- window.py loads index.html by path, so a web/ that did
        # not get collected means a blank window with no error. Both
        # build.yml and release.yml therefore carry a post-build assertion.
        # Destination is "web" (not "."), so the runtime lookup is
        # bundle_dir() / "web" / "index.html" and resolves to
        # _internal/web/index.html under PyInstaller 6.x's one-folder
        # layout -- the exact path the spike confirmed.
        (str(WEB), "web"),
        # Collected at the bundle root so paths.icon_file()'s frozen-case
        # lookup (bundle_dir() / "app.ico") finds it directly.
        (str(ICON), "."),
        # Must reach the installed tree, not just the repository: the offer
        # has to travel with the binaries it covers.
        (str(ROOT / "THIRD-PARTY-NOTICES.md"), "."),
        # The GPL text itself, which section 1 requires accompany the
        # binary. Renamed by fetch_autohotkey.py at fetch time (not here --
        # a `datas` tuple's second element is a destination directory, not a
        # filename, so it cannot rename on the way in) so it cannot be
        # mistaken for a licence covering Wingman, which is MIT.
        (str(BIN / "AutoHotkey-COPYING.txt"), "."),
        # FFmpeg is GPL v3 where AutoHotkey is v2, so it needs its own
        # copy -- one shared text would misstate the terms for one of them.
        # Also renamed at fetch time by fetch_ffmpeg.py, for the same reason.
        (str(BIN / "ffmpeg-COPYING.txt"), "."),
        # The engine is data, not code -- modulegraph cannot see it, and
        # PyInstaller exits 0 when a datas entry fails to collect. Without
        # the post-build assertion below, a missing script produces a green
        # build and an engine that never starts.
        (str(ROOT / "wingman" / "engine"), "engine"),
        # Pillow loads this by path at render time, so modulegraph never
        # sees it -- same class of miss as web/ above, and the same silent
        # outcome: chrome.py logs a warning and falls back to Pillow's
        # bitmap default, so every preview label ships in the wrong face
        # with no failure anywhere in the build.
        (str(ROOT / "wingman" / "assets" / "fonts"), "assets/fonts"),
        # Alert sounds, resolved by alerts.service.sound_path() through
        # paths.bundle_dir() -- the same web/-style precedent as above, not
        # chrome.py's font lookup, which this destination does not match.
        (str(ROOT / "wingman" / "assets" / "sounds"), "assets/sounds"),
    ],
    hiddenimports=[
        # pystray selects its backend implementation dynamically at
        # runtime, which modulegraph cannot follow statically.
        "pystray._win32",
        # Required, not precautionary: pywebview picks its rendering
        # backend at runtime from a string, so modulegraph never sees this
        # import. Without it the frozen app reaches webview.start(), finds
        # no backend, and -- per spike Q7 -- returns normally and exits 0
        # with no window and no error. The build-time import check in
        # build.yml is what catches a missing/renamed module here, because
        # PyInstaller reports "Hidden import not found" as an ERROR line
        # and still exits 0.
        "webview.platforms.edgechromium",
        # google.* and googleapiclient.* are PEP 420 namespace packages.
        # modulegraph has a known history of mishandling namespace-package
        # resolution, so these are listed explicitly as a safety net -- not
        # because the imports below are lazy/function-level (modulegraph
        # scans bytecode for IMPORT_NAME regardless of function nesting, so
        # it normally does find those just fine).
        "googleapiclient.discovery",
        "googleapiclient.http",
        "google_auth_oauthlib.flow",
        "google.oauth2.credentials",
        "google.auth.transport.requests",
        # Not imported by name anywhere in this package, but
        # googleapiclient.discovery.build() uses it internally to wrap
        # google.auth credentials in an httplib2 transport.
        "google_auth_httplib2",
    ],
    hookspath=[],
    runtime_hooks=[],
    # tkinter is excluded, not merely unused: the replatform removed every
    # import of it, and leaving it in drags the whole Tcl/Tk tree into the
    # bundle for nothing. The spike's spec excluded it the same way. A
    # residual `import tkinter` left somewhere fails LOUDLY at startup with
    # ImportError, unlike the silent datas/hiddenimports failures above, so
    # this needs no post-build assertion of its own.
    excludes=["pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Wingman",
    console=False,          # No console window behind the GUI.
    disable_windowed_traceback=False,
    icon=str(ICON),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,              # UPX compression increases antivirus false positives.
    name="Wingman",
)
