# packaging/mirror.spec
# The production packaging of the stream mirror (issue #318): one
# wingman-mirror.exe built as its own frozen process, collected into the
# app tree at _internal/bin -- the exact path paths.mirror_exe() resolves
# in a frozen build, beside the AutoHotkey interpreter and the settings
# codec. The registered game (#312 rev 3) must be THIS exe, never the
# main wingman.exe, and the process must contain exactly one top-level
# window for Discord's pin to land on by construction -- which is why the
# exe is windowed (console=False): a console is a second top-level window
# in the registered process, the exact ambiguity the dedicated process
# exists to remove.
#
# (This file was the #315 probe build before the harvest. That build's
# reason to exist -- a console to type runbook commands into -- stopped
# being true when the shipping mirror was harvested out of
# wingman/streaming/mirror.py with no console interface, and the
# interactive probe lives on unworn as scripts/capture_visibility_probe.py.
# The build command in docs/combat-golive-probe.md produces this exe.)
#
# Built by the shared build action AFTER the app build, with
# --distpath dist/Wingman/_internal, aiming the COLLECT at
# dist/Wingman/_internal/bin. After, because the app build's own COLLECT
# resets dist/Wingman and would take the mirror with it. installer.iss
# ships dist/Wingman/* recursively, so the exe needs no installer-script
# edit.
#
# One-folder like the main app, for the same reasons uploader.spec records:
# one-file unpacks to temp on every launch and trips antivirus heuristics
# markedly more often.
from pathlib import Path

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "wingman" / "streaming" / "mirror.py")],
    pathex=[str(ROOT)],
    # No binaries, no datas: the mirror is pure ctypes over the OS
    # libraries (wingman.preview.thumbnail/win32). If it ever needs an
    # icon, add ICON here and the runtime lookup with it.
    binaries=[],
    datas=[],
    hiddenimports=[],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="wingman-mirror",
    debug=False,
    console=False,  # see header: the registered process holds one window
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="bin",
)
