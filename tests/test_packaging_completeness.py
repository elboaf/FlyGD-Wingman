"""Every importable subpackage must be listed in pyproject's `packages`.

pyproject.toml:38-49 records why this is not paranoia: discovery is
enumerated by hand, subpackages are NOT implied by their parent, and a
missing entry "installs cleanly and fails at import time in the built
artifact, not in the checkout where the source tree makes it work anyway."
A source checkout passes every test while the frozen release dies on
launch, so only a test that reads the manifest can catch it here.
"""

import json
import pathlib
import re
import subprocess
import sys
import tomllib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_every_subpackage_is_declared():
    with (ROOT / "pyproject.toml").open("rb") as fh:
        declared = set(tomllib.load(fh)["tool"]["setuptools"]["packages"])
    on_disk = {
        ".".join(p.parent.relative_to(ROOT).parts)
        for p in (ROOT / "wingman").rglob("__init__.py")
    }
    assert on_disk <= declared, f"undeclared packages: {sorted(on_disk - declared)}"


def test_profilecopy_module_ships_under_the_already_declared_evesettings_package():
    """Whole-profile copy (wingman/evesettings/profilecopy.py) added no new
    subpackage -- it is a module inside wingman.evesettings, which
    pyproject.toml already lists. `test_every_subpackage_is_declared` above
    only ever sees __init__.py directories, so it would stay silent if this
    file were ever hoisted into its own undeclared subpackage (e.g.
    wingman.evesettings.profilecopy as a package). This pins both halves of
    that assumption directly, without touching pyproject.toml."""
    module = ROOT / "wingman" / "evesettings" / "profilecopy.py"
    assert module.is_file(), "profilecopy.py must live inside wingman/evesettings/"
    with (ROOT / "pyproject.toml").open("rb") as fh:
        declared = set(tomllib.load(fh)["tool"]["setuptools"]["packages"])
    assert "wingman.evesettings" in declared


CODEC = (
    ROOT
    / "packaging"
    / "bin"
    / (
        "wingman-settings-codec.exe"
        if sys.platform == "win32"
        else "wingman-settings-codec"
    )
)


def test_the_spec_bundles_the_settings_codec_and_its_licence():
    spec = (ROOT / "packaging" / "uploader.spec").read_text(encoding="utf-8")
    assert 'BIN / "wingman-settings-codec.exe"' in spec
    # One combined licence file for the whole static link, not one per
    # crate. Named here and in the action's licence assertion; both have to
    # move together or the build throws on a file the spec never shipped.
    assert 'BIN / "settings-codec-COPYING.txt"' in spec
    action = (
        ROOT / ".github" / "actions" / "build-installer" / "action.yml"
    ).read_text(encoding="utf-8")
    assert "settings-codec-COPYING.txt" in action
    assert "blue-marshal-COPYING.txt" not in action + spec, (
        "the per-crate licence file was replaced by the combined one; a "
        "surviving reference names a file nothing generates any more"
    )


def test_the_notices_name_the_pinned_codec_dependency():
    cargo = (ROOT / "packaging" / "settings-codec" / "Cargo.toml").read_text(
        encoding="utf-8"
    )
    notices = (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    assert 'blue-marshal = "=1.0.1"' in cargo
    assert "blue-marshal and its dependencies" in notices
    assert "Version: 1.0.1" in notices


def test_the_notices_list_every_crate_the_codec_links():
    """The codec is statically linked, so MIT's notice condition covers the
    whole dependency closure and not just blue-marshal. The list is derived
    from Cargo.lock rather than retyped: a `cargo update` that adds or drops
    a crate would otherwise leave the notices quietly wrong, which is the
    one failure mode here that nothing at runtime can reveal.
    """
    lock = (ROOT / "packaging" / "settings-codec" / "Cargo.lock").read_text(
        encoding="utf-8"
    )
    linked = set(re.findall(r'^name = "([^"]+)"', lock, re.MULTILINE))
    linked.discard("wingman-settings-codec")  # our own crate, GPL with the app
    notices = (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    named = set(re.findall(r"[A-Za-z0-9_-]+", notices))
    assert linked <= named, (
        "THIRD-PARTY-NOTICES.md does not name every crate linked into "
        f"wingman-settings-codec.exe: {sorted(linked - named)}"
    )


@pytest.mark.skipif(not CODEC.is_file(), reason="settings codec not built")
def test_the_built_codec_round_trips_large_floats_exactly():
    doc = {
        "had_crc": False,
        "doc": {
            "bytes:ui": {
                "bytes:plex_value": {
                    "tuple": ["long:134251880277573607", 93668995514.40001]
                }
            }
        },
    }
    encoded = subprocess.run(
        [str(CODEC), "encode"], input=json.dumps(doc).encode(), capture_output=True
    )
    assert encoded.returncode == 0, encoded.stderr
    assert encoded.stdout[:1] == b"\x7d"
    decoded = subprocess.run(
        [str(CODEC), "decode"], input=encoded.stdout, capture_output=True
    )
    assert decoded.returncode == 0, decoded.stderr
    assert json.loads(decoded.stdout) == doc


def test_the_installer_fightrecorder_feature_is_wired():
    """The FightRecorder task, its bundled DLL and its install-time code
    must all be present in installer.iss. Any one going missing has a
    specific symptom: no task (feature gone), no [Files] entry (iscc
    fails at compile), no code (a checkbox that does nothing)."""
    iss = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
    assert 'Name: "fightrecorder"' in iss
    assert r'Source: "bin\obs-fightrecorder.dll"; Flags: dontcopy noencryption' in iss
    assert "procedure InstallFightRecorder();" in iss
    assert "WizardIsTaskSelected('fightrecorder')" in iss


def test_the_fightrecorder_fetcher_is_on_the_ci_allowlist():
    """ci.yml refuses bare `python` invocations in the build action
    except for the stdlib-only fetch scripts. A new fetcher not on the
    list turns every push red with a bypass error; this pins the
    allowlist entry so removing the fetcher from the action is a
    deliberate act."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "fetch_fightrecorder" in ci
    action = (
        ROOT / ".github" / "actions" / "build-installer" / "action.yml"
    ).read_text(encoding="utf-8")
    assert "packaging/fetch_fightrecorder.py" in action
