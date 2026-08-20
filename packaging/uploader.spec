# packaging/uploader.spec
# One-folder build. Deliberately not one-file: one-file unpacks to temp on
# every launch (slow with ffmpeg bundled) and trips antivirus heuristics
# markedly more often.
from pathlib import Path

ROOT = Path(SPECPATH).parent
BIN = ROOT / "packaging" / "bin"

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[
        (str(BIN / "ffmpeg.exe"), "bin"),
        (str(BIN / "ffprobe.exe"), "bin"),
    ],
    datas=[],
    hiddenimports=[
        "pystray._win32",
        "PIL._tkinter_finder",
        # googleapiclient and google-auth pieces are imported lazily inside
        # functions (see uploader.py and app.py) so the test suite can run
        # without them installed. PyInstaller's static analysis cannot see
        # those imports, so every one of them must be listed explicitly or
        # the frozen app fails at first upload instead of at startup.
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
    excludes=["pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OBSYouTubeUploader",
    console=False,          # No console window behind the GUI.
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,              # UPX compression increases antivirus false positives.
    name="OBSYouTubeUploader",
)
