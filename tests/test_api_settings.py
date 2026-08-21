"""Settings across the bridge.

The dialog is gone; what survives is the behaviour 2.2.0 put into it -- a
masked webhook that reports parse errors, an account control that tracks
four states, two independent Detect actions, and a Save that reaches the
live watcher and not just the settings file.
"""
import types

import pytest

from obs_youtube_uploader import uploader
from obs_youtube_uploader.ui import api as api_mod
from obs_youtube_uploader.ui import copy as copy_mod
from tests import fakes


def test_connected_offers_to_switch_rather_than_to_connect():
    """The button read "Connect Google Account" while the line above it read
    "Connected", which gave no clue what pressing it would do -- and it is
    exactly the control someone reaches for when they suspect the wrong
    account is signed in."""
    message, label, enabled = copy_mod.auth_state("connected")
    assert (message, label, enabled) == ("Connected", "Switch account", True)


def test_disconnected_asks_for_sign_in():
    assert copy_mod.auth_state("disconnected") == (
        "Not connected", "Sign in with Google", True)


def test_both_transient_states_disable_the_button():
    """A second press during the lookup races it, and during the browser
    flow it starts a second OAuth flow on top of the first."""
    for state in ("connecting", "revoking"):
        _message, _label, enabled = copy_mod.auth_state(state)
        assert enabled is False, state


def test_an_unknown_state_stays_usable():
    """Nothing should be able to leave the user with a dead button."""
    assert copy_mod.auth_state("nonsense") == (
        "Not connected", "Sign in with Google", True)


def test_the_page_can_read_the_whole_label_table_in_one_call(tmp_path):
    """Kept in Python, where it is tested, rather than duplicated in JS."""
    api, _window = fakes.build_api(tmp_path)
    table = api.auth_labels()
    assert table["connected"] == {"message": "Connected",
                                  "label": "Switch account", "enabled": True}
    assert set(table) == {"disconnected", "connecting", "connected", "revoking"}


