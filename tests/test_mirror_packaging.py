"""The mirror exe's packaging contract (#318).

The registered game (#312 rev 3) is wingman-mirror.exe: a second frozen
process built by packaging/mirror.spec and collected into the app tree at
_internal/bin -- the path paths.mirror_exe() resolves frozen, found the
way the engine exe is found (tests/test_main_mirror.py holds that side).
These guards hold the other half, the properties nothing at runtime can
prove because the build only happens in CI:

- the exe is windowed -- the registered process must hold exactly ONE
  top-level window for Discord's pin to land on by construction, and a
  console would be a second;
- the COLLECT is named bin, built into a scratch distpath strictly AFTER
  the app build (whose COLLECT resets dist/Wingman and would delete the
  mirror) and copied ADDITIVELY into dist/Wingman/_internal/bin --
  PyInstaller --noconfirm removes its output directory before collecting,
  so aiming the COLLECT at the app tree would delete the app's own bin
  (ffmpeg, the codec, AutoHotkey; run 37530006761 died on it);
- the post-build assertion checks the real path, next to the engine's;
- installer.iss still ships dist/Wingman recursively -- the premise that
  makes "no installer-script edit" true.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ACTION = ROOT / ".github" / "actions" / "build-installer" / "action.yml"
SPEC = ROOT / "packaging" / "mirror.spec"


def _call(tree, name):
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
    )


def _keyword(call, name):
    return next(item for item in call.keywords if item.arg == name)


def test_spec_builds_the_windowed_mirror_exe():
    tree = ast.parse(SPEC.read_text(encoding="utf-8"))
    analysis = _call(tree, "Analysis")
    assert "mirror.py" in ast.unparse(analysis.args[0]), (
        "mirror.spec no longer freezes wingman/streaming/mirror.py -- "
        "whatever it freezes now is not the window Discord pins"
    )
    exe = _call(tree, "EXE")
    assert _keyword(exe, "name").value.value == "wingman-mirror"
    console = _keyword(exe, "console").value
    assert isinstance(console, ast.Constant) and console.value is False, (
        "the mirror exe must stay windowed: a console is a second top-level "
        "window in the registered process (packaging/mirror.spec header)"
    )
    collect = _call(tree, "COLLECT")
    assert _keyword(collect, "name").value.value == "bin"


def test_action_builds_the_mirror_after_the_app_and_verifies_it():
    action = ACTION.read_text(encoding="utf-8")
    # A scratch distpath, then an ADDITIVE copy: PyInstaller --noconfirm
    # removes the COLLECT's output directory before writing it, and the
    # spec's COLLECT is named "bin" -- a distpath of
    # dist/Wingman/_internal would delete the app's own _internal/bin
    # (ffmpeg, ffprobe, the codec, AutoHotkey) on its way in (run
    # 37530006761: "ffmpeg.exe missing from the bundle").
    build = "uv run python -m PyInstaller packaging/mirror.spec --noconfirm --distpath dist/mirror-build"
    assert build in action
    assert action.index("packaging/uploader.spec --noconfirm") < action.index(
        "packaging/mirror.spec --noconfirm"
    ), (
        "the mirror build must come after the app build, whose COLLECT resets dist/Wingman"
    )
    copy = (
        "Copy-Item -Recurse -Force dist/mirror-build/bin/* dist/Wingman/_internal/bin/"
    )
    assert copy in action, (
        "the mirror built into the scratch distpath must be copied into "
        "the app tree, or paths.mirror_exe() and the installer both miss it"
    )
    assert action.index("packaging/mirror.spec --noconfirm") < action.index(copy), (
        "the copy must follow the mirror build it publishes"
    )
    assert "dist/Wingman/_internal/bin/wingman-mirror.exe" in action, (
        "no post-build assertion for the mirror exe -- PyInstaller exits 0 "
        "when a COLLECT silently fails to land"
    )


def test_installer_ships_the_app_tree_recursively():
    """The whole packaging rests on installer.iss copying everything under
    dist/Wingman into {app}; the mirror rides along under _internal/bin
    with no installer-script edit only while that flag is there."""
    iss = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
    line = next(line for line in iss.splitlines() if "dist\\Wingman\\*" in line)
    assert "recursesubdirs" in line and "createallsubdirs" in line
