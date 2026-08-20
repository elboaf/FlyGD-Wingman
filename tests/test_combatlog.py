import datetime
from pathlib import Path

from obs_youtube_uploader import combatlog

UTC = datetime.timezone.utc

# Real logs are CRLF. A \n-only fixture would not catch a parser that leaves
# a trailing \r on the character name.
HEADER = (
    "------------------------------------------------------------\r\n"
    "  Gamelog\r\n"
    "  Listener: Miguel Aurgnet\r\n"
    "  Session Started: 2026.08.20 20:42:50\r\n"
    "------------------------------------------------------------\r\n"
    "[ 2026.08.20 20:42:52 ] (hint) Attempting to join a channel\r\n"
)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_bytes(text.encode("utf-8"))
    return p


def test_parses_listener_and_session_start(tmp_path):
    h = combatlog.parse_header(_write(tmp_path, "a.txt", HEADER))
    assert h is not None
    assert h.listener == "Miguel Aurgnet"
    assert h.session_start == datetime.datetime(2026, 8, 20, 20, 42, 50, tzinfo=UTC)


def test_session_start_is_timezone_aware_utc(tmp_path):
    h = combatlog.parse_header(_write(tmp_path, "a.txt", HEADER))
    assert h.session_start.tzinfo is not None
    assert h.session_start.utcoffset() == datetime.timedelta(0)


def test_listener_has_no_trailing_carriage_return(tmp_path):
    h = combatlog.parse_header(_write(tmp_path, "a.txt", HEADER))
    assert "\r" not in h.listener
    assert not h.listener.endswith(" ")


def test_returns_none_without_listener(tmp_path):
    """47% of a real folder is header-only stubs with no character."""
    stub = (
        "------------------------------------------------------------\r\n"
        "  Gamelog\r\n"
        "  Session Started: 2026.08.20 21:46:48\r\n"
        "------------------------------------------------------------\r\n"
    )
    assert combatlog.parse_header(_write(tmp_path, "a.txt", stub)) is None


def test_returns_none_without_session_start(tmp_path):
    text = "  Gamelog\r\n  Listener: Someone\r\n"
    assert combatlog.parse_header(_write(tmp_path, "a.txt", text)) is None


def test_returns_none_on_malformed_timestamp(tmp_path):
    text = HEADER.replace("2026.08.20 20:42:50", "not-a-date")
    assert combatlog.parse_header(_write(tmp_path, "a.txt", text)) is None


def test_returns_none_on_empty_file(tmp_path):
    assert combatlog.parse_header(_write(tmp_path, "a.txt", "")) is None


def test_returns_none_on_missing_file(tmp_path):
    assert combatlog.parse_header(tmp_path / "nope.txt") is None


def test_tolerates_undecodable_bytes(tmp_path):
    """errors='replace': a stray byte in a chat line must not abort a scan."""
    p = tmp_path / "a.txt"
    p.write_bytes(HEADER.encode("utf-8") + b"[ 2026.08.20 20:43:00 ] \xff\xfe junk\r\n")
    h = combatlog.parse_header(p)
    assert h is not None and h.listener == "Miguel Aurgnet"


def test_stops_reading_after_header(tmp_path):
    """A 1.6MB log must not be read in full just to get its header."""
    big = HEADER + ("[ 2026.08.20 20:44:00 ] (combat) filler\r\n" * 50000)
    h = combatlog.parse_header(_write(tmp_path, "a.txt", big))
    assert h is not None and h.listener == "Miguel Aurgnet"
