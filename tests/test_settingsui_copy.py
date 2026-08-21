"""Pure copy helpers in the settings dialog.

Same rationale as tests/test_app_upload_copy.py: the dialog itself has no
test harness, so every string it shows is decided in a module-level function
that can be tested without standing one up.
"""
import pytest

from obs_youtube_uploader import settingsui
from obs_youtube_uploader.ui import copy as copy_mod


# --- auth_button_state -----------------------------------------------------

def test_connected_offers_to_switch_rather_than_to_connect():
    """The button read "Connect Google Account" while the line above it read
    "Connected", which gave no clue what pressing it would do -- and it is
    exactly the control someone reaches for when they suspect the wrong
    account is signed in."""
    assert settingsui.auth_button_state("SUCCESS") == ("Switch account", True)


def test_not_connected_asks_for_sign_in():
    assert settingsui.auth_button_state("ERROR") == ("Sign in with Google", True)


def test_button_is_disabled_while_the_lookup_is_running():
    text, enabled = settingsui.auth_button_state("MUTED")
    assert enabled is False
    assert text == "Checking…"


def test_button_is_disabled_while_the_browser_is_open():
    """_connect sets WARNING and opens a browser; a second press would start
    a second OAuth flow over the first."""
    text, enabled = settingsui.auth_button_state("WARNING")
    assert enabled is False
    assert "browser" in text.lower()


def test_unknown_state_falls_back_to_sign_in_and_stays_usable():
    """_auth_kind is None until the first status lands. A dead button in
    that window would be worse than an optimistic label."""
    assert settingsui.auth_button_state(None) == ("Sign in with Google", True)
    assert settingsui.auth_button_state("NONSENSE") == ("Sign in with Google", True)


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
