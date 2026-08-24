"""Windows-only at runtime, importable on Linux -- the ui/chrome.py pattern
(window-resize-plan.md:130-140). The enumerator is injected so the matching
and de-duplication logic is testable off-platform."""
from obs_youtube_uploader import bookmarks, evewindows


def test_returns_empty_off_windows(monkeypatch):
    monkeypatch.setattr(evewindows.sys, "platform", "linux")
    assert evewindows.list_eve_windows() == []


def test_keeps_only_eve_titles(monkeypatch):
    monkeypatch.setattr(evewindows.sys, "platform", "win32")
    titles = ["EVE - Pilot One", "Notepad", "EVE - Alt Two", "eve online"]
    assert evewindows.list_eve_windows(enumerator=lambda: titles) == [
        "EVE - Alt Two", "EVE - Pilot One"]


def test_deduplicates(monkeypatch):
    """Multiboxing routinely produces two handles reporting one title."""
    monkeypatch.setattr(evewindows.sys, "platform", "win32")
    titles = ["EVE - Pilot", "EVE - Pilot"]
    assert evewindows.list_eve_windows(enumerator=lambda: titles) == ["EVE - Pilot"]


def test_prefix_match_is_case_sensitive_like_the_script(monkeypatch):
    """The engine matches ^EVE -  (111unified.ahk:248). If Wingman offered a
    window the engine will never match, the checkbox would do nothing."""
    monkeypatch.setattr(evewindows.sys, "platform", "win32")
    assert evewindows.list_eve_windows(enumerator=lambda: ["Eve - Pilot"]) == []


def test_enumerator_failure_is_survivable(monkeypatch):
    monkeypatch.setattr(evewindows.sys, "platform", "win32")

    def boom():
        raise OSError("no window station")

    assert evewindows.list_eve_windows(enumerator=boom) == []


def test_titles_the_engine_would_drop_are_not_offered(monkeypatch):
    """A title offered here but rejected by the INI writer gives the user a
    checkbox that silently does nothing. The rule lives in one place."""
    monkeypatch.setattr(evewindows.sys, "platform", "win32")
    titles = ["EVE - Ok", "EVE - Bad=Title"]
    assert evewindows.list_eve_windows(enumerator=lambda: titles) == ["EVE - Ok"]


def test_the_offered_rule_is_the_written_rule(monkeypatch):
    """Not a duplicate of the above: this pins that the two layers share one
    predicate rather than happening to agree today."""
    monkeypatch.setattr(evewindows.sys, "platform", "win32")
    for title in ["EVE - Ok", "EVE - Bad=Title", "Notepad", "eve - lower"]:
        offered = evewindows.list_eve_windows(enumerator=lambda t=title: [t]) == [title]
        assert offered == bookmarks.is_engine_window_title(title), title
