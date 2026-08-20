# packaging/uploader.spec
# One-folder build. Deliberately not one-file: one-file unpacks to temp on
# every launch (slow with ffmpeg bundled) and trips antivirus heuristics
# markedly more often.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
BIN = ROOT / "packaging" / "bin"

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[
        (str(BIN / "ffmpeg.exe"), "bin"),
        (str(BIN / "ffprobe.exe"), "bin"),
    ],
    # sv-ttk ships its theme as .tcl files (sun-valley.tcl,
    # theme/light.tcl, theme/dark.tcl) plus image assets. modulegraph only
    # follows Python imports, so without this the package's .py file lands
    # in the bundle but sv_ttk.set_theme() fails at runtime looking for
    # data that was never copied. PyInstaller exits 0 either way (see the
    # ffmpeg comment below), which is why build.yml also gets a post-build
    # assertion in Step 4.
    datas=collect_data_files("sv_ttk"),
    hiddenimports=[
        # pystray selects its backend implementation dynamically at
        # runtime, which modulegraph cannot follow statically.
        "pystray._win32",
        # Precautionary, not known-required: the package never imports
        # ImageTk, so PIL._tkinter_finder may be unused here. Kept because
        # it is harmless and we cannot test the Windows-only alternative.
        "PIL._tkinter_finder",
        # google.* and googleapiclient.* are PEP 420 namespace packages.
        # modulegraph has a known history of mishandling namespace-package
        # resolution, so these are listed explicitly as a safety net — not
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
