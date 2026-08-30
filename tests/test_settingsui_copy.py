"""Pure copy helpers in the settings dialog.

Same rationale as tests/test_app_upload_copy.py: the dialog itself has no
test harness, so every string it shows is decided in a module-level function
that can be tested without standing one up.
"""

import datetime

from wingman.ui import copy as copy_mod

# --- EVE selective-copy confirmation --------------------------------------


def test_selective_copy_names_what_each_target_keeps_before_the_backup_promise():
    body = copy_mod.format_eve_copy_confirm(
        ["Target"],
        "character",
        eve_running=False,
        source_name="Source",
        preserved_groups=["Search history & suggestions", "Chat channels"],
    )
    preserved = "Search history & suggestions, Chat channels"
    assert preserved in body
    assert body.index(preserved) < body.index("backed up first")


def test_plain_copy_confirmation_output_is_unchanged_when_groups_are_unspecified():
    expected = copy_mod.format_eve_copy_confirm(
        ["Target"], "character", False, source_name="Source"
    )
    assert (
        copy_mod.format_eve_copy_confirm(
            ["Target"],
            "character",
            False,
            source_name="Source",
            preserved_groups=None,
        )
        == expected
    )


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
    """ "not configured" for a URL the user has clearly typed reads as the
    app ignoring them, and hides the actual problem."""
    shown = copy_mod.webhook_status("http://discord.com/api/webhooks/1/2")
    assert shown != "not configured"
    assert "https" in shown.lower()


def test_a_non_discord_host_is_named_in_the_error():
    shown = copy_mod.webhook_status("https://evil.example.com/api/webhooks/1/2")
    assert "evil.example.com" in shown


# library.format_date compares against a naive LOCAL clock
# (datetime.now(), its own noqa: DTZ005), so `now` here must be naive local
# too or every delta is off by the machine's UTC offset. One constant rather
# than four suppressions.
_NOON = datetime.datetime(2026, 8, 25, 12, 0)  # noqa: DTZ001 - naive local, see above


# --- inert notes -----------------------------------------------------------
#
# Settings 1. The shape is asserted rather than the exact wording: these
# sentences will be reworded, and a test that pins the prose would be
# rewritten alongside every edit until someone deletes it. What must not
# change is that each one names a way out.


def test_every_inert_note_names_a_way_out():
    """WM.setEnabled forbids disabling the only route to a control's own
    precondition, so a note with no remedy would describe a dead end the
    user cannot see the exit from. PRODUCT.md: say what happened AND what
    to do.

    "Settings" covers a pointer to a section; the imperative openers cover
    a note whose remedy is an action on the screen already in front of the
    reader ("turn them back on").
    """
    assert copy_mod.INERT_NOTES, "the table must not be empty"
    for key, note in copy_mod.INERT_NOTES.items():
        assert note.endswith("."), f"{key} is not a sentence"
        remedies = ("Settings", "turn them", "Set one", "Choose", "Start")
        assert any(word in note for word in remedies), (
            f"{key} states a problem with no way out: {note!r}"
        )


def test_an_inert_note_states_the_consequence_not_just_the_state():
    """ "Previews are off" alone tells a reader something they can see. The
    sentence exists for what they cannot see -- that the keybinds below it
    are unregistered as a result."""
    for key, note in copy_mod.INERT_NOTES.items():
        assert ", so " in note or ". " in note, (
            f"{key} states a bare fact with no consequence: {note!r}"
        )


def test_an_unknown_note_key_is_empty_not_an_error():
    """This renders into a hint slot on a live screen. The page hides the
    slot on an empty string, so "" is already the shape it handles -- and a
    KeyError from a note is a worse outcome than a missing note."""
    assert copy_mod.inert_note("no-such-precondition") == ""
    assert copy_mod.inert_note("previews_off") == copy_mod.INERT_NOTES["previews_off"]


# --- format_fetched --------------------------------------------------------
#
# Skills 8. `now` is injected throughout: every threshold is relative to it
# and a test cannot wait for the clock.


def test_a_fetch_time_reads_in_the_same_vocabulary_as_the_uploader():
    """The Uploader says "5h ago"; Skills said "8/25/2026, 12:12:28 AM".
    One app, one way of saying how old something is."""
    now = _NOON
    five_hours_back = (now - datetime.timedelta(hours=5)).astimezone(datetime.UTC)
    assert (
        copy_mod.format_fetched(five_hours_back.isoformat(), now=now)
        == "Last fetched 5h ago"
    )


def test_seconds_precision_is_dropped_because_it_cannot_matter():
    now = _NOON
    just_now = (now - datetime.timedelta(seconds=12)).astimezone(datetime.UTC)
    shown = copy_mod.format_fetched(just_now.isoformat(), now=now)
    assert shown == "Last fetched just now"
    assert ":" not in shown


def test_an_absent_or_unreadable_fetch_time_says_never():
    """Both, and for one reason: a value we cannot read is a value we
    cannot claim a time for. eveskills.state._iso writes "" not None."""
    now = _NOON
    assert copy_mod.format_fetched("", now=now) == "Never fetched"
    assert copy_mod.format_fetched("not-a-date", now=now) == "Never fetched"
    assert copy_mod.format_fetched(None, now=now) == "Never fetched"


def test_a_naive_timestamp_is_read_as_utc_not_local():
    """Everything eveskills writes is UTC, so a naive string can only be a
    hand edit. Reading it as local would shift the age by the machine's
    offset -- the same rule eveskills.state._parse_utc follows."""
    aware = copy_mod._parse_iso_utc("2026-08-25T04:00:00")
    assert aware is not None
    assert aware.tzinfo is not None
    assert aware.utcoffset() == datetime.timedelta(0)


def test_an_old_fetch_falls_back_to_a_calendar_date():
    """library.format_date's precision degrades with age on purpose, which
    is the property that makes it right here: nobody needs the minute a
    fetch landed three weeks ago."""
    now = _NOON
    old = (now - datetime.timedelta(days=21)).astimezone(datetime.UTC)
    shown = copy_mod.format_fetched(old.isoformat(), now=now)
    assert "ago" not in shown
    assert "Aug 04" in shown
