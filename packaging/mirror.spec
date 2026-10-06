# packaging/mirror.spec
# The capture-visibility probe build of the rev-3 mirror (issue #315):
# a standalone wingman-mirror.exe whose whole purpose is to be registered
# in Discord's Registered Games under an image name no other process on
# the box shares -- registering python.exe (the original probe plan) made
# every Python process on the machine the "game", which can land the pin
# leg on the wrong window and poison the evidence.
#
# Not the production packaging (that is ticket #318): this is the test
# build the user runs from a checkout to execute the runbook in
# docs/combat-golive-probe.md. One-folder like the main app, for the same
# reasons uploader.spec records: one-file unpacks to temp on every launch
# and trips antivirus heuristics.
from pathlib import Path

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "wingman" / "streaming" / "mirror.py")],
    pathex=[str(ROOT)],
    # No binaries, no datas: the mirror is pure ctypes over the OS
    # libraries. If it ever needs an icon, add ICON here and the runtime
    # lookup with it.
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
    console=True,  # the console IS the probe interface (runbook commands)
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="wingman-mirror",
)
