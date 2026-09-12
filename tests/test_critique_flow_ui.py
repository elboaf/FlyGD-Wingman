"""Source conventions for the critique fixes; browser checks prove their layout."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "wingman" / "web"


def test_preview_help_matches_the_native_mouse_gestures():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    guide = html.split("How previews behave</summary>", 1)[1].split("</details>", 1)[0]
    text = " ".join(re.sub(r"<[^>]+>", " ", guide).split())
    assert "Left-drag to move" in text
    assert "right-drag or drag the bottom-right corner to resize" in text
    assert "both mouse buttons" in text
    assert "Locked previews ignore drag gestures" in text
    assert "including locked ones" in text
    assert "Right-drag to move" not in text


def test_preview_tabs_replace_mixed_scroll_and_cross_section_shortcuts():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    section = html.split('id="section-previews"', 1)[1].split('id="section-fleet"', 1)[
        0
    ]
    assert 'data-settings-section="previews"' in section
    assert re.findall(r'data-settings-tab="([^"]+)"', section) == [
        "windows",
        "characters",
        "wanderer",
    ]
    assert "data-preview-jump" not in section
    assert 'id="preview-fleet-settings"' not in section
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert ".settings-subpage[hidden]" in css


def test_subpage_vertical_padding_does_not_leave_a_gap_above_sticky_headers():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    panel = re.search(r"\.settings-subpage\s*\{([^}]*)\}", css)
    assert panel and re.search(r"padding:\s*0\s+\d+px", panel.group(1))
    assert ".settings-subpage > .card:first-child" in css
    assert ".settings-subpage > .card:last-child" in css


def test_fleet_character_keeps_full_name_available_on_hover():
    code = (WEB / "fleetbar.js").read_text(encoding="utf-8")
    assert "character.title = character.textContent" in code


def test_backup_recovery_controls_exist_in_the_shipped_page():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for ident in (
        "es-backup-recovery",
        "es-backup-recovery-path",
        "es-backup-recovery-open",
        "es-backup-recovery-note",
    ):
        assert f'id="{ident}"' in html
    assert 'placeholder="Target, date, or filename"' in html


def test_rollback_fixture_supplies_the_structured_archive_identity():
    code = (WEB / "dev.js").read_text(encoding="utf-8")
    assert "backups_folder:" in code
    rollback = code.split("} else if (profileCopyScenario === 'rollback-failed') {", 1)[
        1
    ]
    rollback = rollback.split("window.onEveSettingsDone(payload)", 1)[0]
    assert "payload.recovery_backup =" in rollback
    assert "path: payload.recovery_backup" in rollback


def test_native_update_progress_does_not_animate_layout():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    progress = re.search(r"#update-progress::-webkit-progress-value\s*\{([^}]+)\}", css)
    assert progress
    assert "transition:" not in progress.group(1)
