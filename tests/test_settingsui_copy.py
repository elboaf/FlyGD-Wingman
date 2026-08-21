"""Pure copy helpers in the settings dialog.

Same rationale as tests/test_app_upload_copy.py: the dialog itself has no
test harness, so every string it shows is decided in a module-level function
that can be tested without standing one up.
"""
import pytest

from obs_youtube_uploader.ui import copy as copy_mod


# --- webhook_status --------------------------------------------------------

def test_empty_webhook_reads_as_not_configured():
    assert copy_mod.webhook_status("") == "not configured"
    assert copy_mod.webhook_status("   ") == "not configured"


def test_valid_webhook_is_described_without_its_token():
    """The field is masked, so this line is the only confirmation of WHICH
    webhook is stored. It must never carry the token."""
    url = "https://discord.com/api/webhooks/1538615213203656754/s3cr3t-token"
    shown = copy_mod.webhook_status(url)
    assert "1538615213203656754" in shown
    assert "s3cr3t-token" not in shown


def test_an_invalid_webhook_says_what_is_wrong_instead_of_not_configured():
    """"not configured" for a URL the user has clearly typed reads as the
    app ignoring them, and hides the actual problem."""
    shown = copy_mod.webhook_status("http://discord.com/api/webhooks/1/2")
    assert shown != "not configured"
    assert "https" in shown.lower()


def test_a_non_discord_host_is_named_in_the_error():
    shown = copy_mod.webhook_status("https://evil.example.com/api/webhooks/1/2")
    assert "evil.example.com" in shown
