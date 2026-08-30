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
    assert 'BIN / "blue-marshal-COPYING.txt"' in spec


def test_the_notices_name_the_pinned_codec_dependency():
    cargo = (ROOT / "packaging" / "settings-codec" / "Cargo.toml").read_text(
        encoding="utf-8"
    )
    notices = (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    assert 'blue-marshal = "=1.0.1"' in cargo
    assert "## blue-marshal" in notices and "Version: 1.0.1" in notices


@pytest.mark.skipif(not CODEC.is_file(), reason="settings codec not built")
def test_the_built_codec_round_trips_a_document():
    doc = {
        "had_crc": False,
        "doc": {"bytes:ui": {"bytes:k": {"tuple": ["long:134251880277573607", 1.5]}}},
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
