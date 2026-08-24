"""The pin is the security boundary for a binary that installs a keyboard
hook. A placeholder digest shipping to CI would defeat it entirely."""
import importlib.util
import re
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "packaging" / "fetch_autohotkey.py"


def _load_module():
    # Imported rather than grepped for the rename test below: WANTED and
    # OUTPUT_NAMES are two separate dicts/tuples, and a text search can't
    # confirm they actually agree with each other the way a real lookup can.
    spec = importlib.util.spec_from_file_location("fetch_autohotkey", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_digest_is_a_real_sha256():
    text = SOURCE.read_text()
    match = re.search(r'AHK_SHA256 = "([^"]+)"', text)
    assert match, "AHK_SHA256 not found"
    assert re.fullmatch(r"[0-9a-f]{64}", match.group(1)), \
        "AHK_SHA256 is not a measured digest"


def test_url_and_wanted_agree_on_v1():
    text = SOURCE.read_text()
    assert "v1.1" in text
    assert "AutoHotkeyU64.exe" in text


def test_licence_text_is_wanted_and_renamed():
    """license.txt is the archive member THIRD-PARTY-NOTICES.md's written
    offer depends on; OUTPUT_NAMES is what renames it to
    AutoHotkey-COPYING.txt on disk so it can't be mistaken for a licence
    covering Wingman itself (GPL-3.0-only -- and the rename matters more
    now than it did under MIT, since both are GPL and a stray COPYING.txt
    is far easier to mistake for ours). uploader.spec's `datas` can't do that
    rename -- its second element is a destination directory, not a
    filename -- so the rename has to happen here, and both pieces need to
    agree for the notice's promised filename to actually exist."""
    module = _load_module()
    assert "license.txt" in module.WANTED
    assert module.OUTPUT_NAMES.get("license.txt") == "AutoHotkey-COPYING.txt"

