"""The pin is the security boundary for a binary that installs a keyboard
hook. A placeholder digest shipping to CI would defeat it entirely."""
import re
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "packaging" / "fetch_autohotkey.py"


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
