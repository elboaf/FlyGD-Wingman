"""Guard current Settings directions, not historical records or card labels."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_DOCS = ("README.md", "DESIGN.md", "docs/smoke-checklist.md")


def normalized_doc(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    # Markdown emphasis, breadcrumb styles and line wrapping aren't navigation.
    text = text.replace("**", "").replace("`", "")
    text = text.replace("→", ">").replace("\u203a", ">")
    return " ".join(text.split())


@pytest.mark.parametrize("path", ACTIVE_DOCS)
def test_active_docs_do_not_direct_readers_to_retired_settings_entries(path):
    text = normalized_doc(path)
    obsolete = (
        "Settings > Connect Google Account",
        "Settings > Google account",
        "Settings > Folders",
        "Settings > Discord",
        "Settings > Uploads",
        "click Folders in the rail",
        "come back to Discord",
    )
    found = [phrase for phrase in obsolete if phrase in text]
    assert not found, f"{path}: obsolete Settings navigation: {found}"


@pytest.mark.parametrize(
    ("path", "expected"),
    (
        (
            "README.md",
            (
                "Google account, recording folder, and Discord webhook in Settings > Uploading",
                "Gamelogs folder in Settings > Alerts",
                "Settings > Characters is the only place to authorize",
            ),
        ),
        (
            "DESIGN.md",
            (
                "webhook from Settings > Uploading",
                "EVE credential cleanup lives under Settings > Characters",
            ),
        ),
        (
            "docs/smoke-checklist.md",
            (
                "Google account card in Settings > Uploading",
                "choose a folder in Settings > Uploading",
                "Clear the webhook in Settings > Uploading",
                "Gamelogs folder in Settings > Alerts",
                "Settings > Characters is the only EVE authorization surface",
            ),
        ),
    ),
)
def test_active_docs_name_current_settings_paths(path, expected):
    text = normalized_doc(path)
    for phrase in expected:
        assert phrase in text, f"{path}: missing current Settings direction: {phrase}"
