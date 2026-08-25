# obs_youtube_uploader/ui/copy.py
"""Every user-visible string the UI decides, as pure module-level functions.

2.2.0 established this split one function at a time (format_selection_summary,
webhook_status, tooltip's cell help) for one reason: copy is what regresses,
and widgets are the one layer this repo has no test harness for. Collecting
them here makes the reason structural instead of incidental -- the strings
now live in a module with no toolkit import at all, so they cross the
Tk-to-webview port untouched, along with their tests.

Nothing in here may import tkinter, pywebview, or any widget module. That is
the whole point: if it needs a window to test, it does not belong here.
"""

import datetime

from .. import discord, library, uploader

# --- main window -----------------------------------------------------------


def format_selection_summary(infos: list[library.VideoInfo]) -> str:
    """The panel's "3 selected · 1.2 GB · 2:04:35" line.

    Two asymmetries are deliberate:

    * The "+" marks the duration total as a floor, not a value. A recording
      whose probe is still outstanding contributes 0, so an unmarked total
      would read as complete while being short. It reuses the duration
      column's own vocabulary for the same state ("…" per row) rather than
      inventing a second one. A recording whose probe never reached a
      verdict -- no ffprobe on the machine, a launch failure, a timeout --
      contributes 0 for the same reason and is marked the same way. That
      one was missing, and on an install with no ffprobe at all it made
      every total read "0:00:00" with no marker: a stated zero for a
      108.8 MB recording, which is the one thing a blank never claims.
    * Size is never marked partial: info.size comes from stat, so it is
      final from the moment the row exists, whatever the probe is doing.

    A probed recording with duration None AND a verdict is a finished
    answer (ffprobe ran and could not read it), so it contributes 0 and
    leaves the total exact. Its own row already shows "?"; repeating that
    diagnosis in an aggregate would say nothing the user can act on.

    The count carries no noun ("3 selected"), which sidesteps agreement at
    every value instead of special-casing 1.
    """
    if not infos:
        return "Nothing selected"
    total_size = sum(info.size for info in infos)
    total_seconds = int(sum(info.duration or 0.0 for info in infos))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    partial = "+" if any(not (info.probed and info.answered) for info in infos) else ""
    return (
        f"{len(infos)} selected · {library.format_size(total_size)}"
        f" · {hours}:{minutes:02d}:{seconds:02d}{partial}"
    )


def _hms(total_seconds: int) -> str:
    hours, remainder = divmod(int(total_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def format_upload_confirm(
    infos: list[library.VideoInfo],
    title: str,
    privacy: str,
    channel_title: str,
    stitch: bool,
    discord_webhook: str,
) -> str:
    """The body of the confirm shown before anything is published.

    This dialog guards the app's irreversible actions, and it was the only
    one with no confirmation: deleting local files, which are recoverable
    from the recycle bin, already confirmed with a full file list. Since the
    upload button merged, it guards TWO of them -- posting to a Discord
    webhook has no undo here either -- which is why the closing line names
    whichever ones this particular press will perform.

    The title preview is built through uploader.build_body rather than
    reformatted here, so the numbering shown is the numbering that will be
    sent. A second implementation of that rule would drift from it.

    The log line is not conditional on a control any more. Uploader 8
    removed the checkbox -- it had no true second state for the people who
    use this -- so what decides whether logs are posted is whether a
    webhook is configured, and this dialog states which of those two
    worlds the user is in. One button publishes to two places, and this is
    the only screen seen between pressing it and the upload starting, so
    the Discord half has to be named here or it is never disclosed at all.

    The RAW webhook is taken rather than a "is one configured" boolean, and
    parsed here with the same discord.parse_webhook the upload half uses
    (Api._post_combat_logs). That is the point: this dialog used to promise
    a Discord post whenever the checkbox was ticked, while the post itself
    was gated on a webhook that parses -- so on a fresh install the confirm
    stated a cost that was never paid, and the run ended on a WARNING strip
    reading like a recurring failure rather than an unconfigured option. A
    boolean would leave the two predicates free to drift apart again; a
    string cannot, because there is only one of them.

    PRODUCT.md's rule is to state cost before an irreversible action. An
    overstated cost breaks it in the direction that teaches the user to
    stop reading the dialog.
    """
    total_size = sum(i.size for i in infos)
    total_seconds = int(sum(i.duration or 0.0 for i in infos))
    count = len(infos)
    where = channel_title or "not known yet (learned from this upload)"

    if stitch:
        shown = uploader.build_body(title, "", privacy, "", 0, 1)["snippet"]["title"]
        what = f"{count} recordings stitched into one video"
        titles = f'"{shown}"'
    else:
        first = uploader.build_body(title, "", privacy, "", 0, count)["snippet"][
            "title"
        ]
        what = f"{count} recording{'s' if count != 1 else ''}"
        titles = f'"{first}"'
        if count > 1:
            last = uploader.build_body(title, "", privacy, "", count - 1, count)[
                "snippet"
            ]["title"]
            titles += f' … "{last}"'

    # The same predicate _post_combat_logs runs, not a paraphrase of it:
    # anything that parses to a hook gets posted, and nothing else does.
    posting = bool(discord.parse_webhook(discord_webhook)[0])

    if posting:
        logs_line = "Logs:     combat logs posted to Discord afterwards\n"
    elif not discord_webhook.strip():
        # Stated as a fact about the install, not as a skipped request --
        # there is no checkbox to have ticked any more. It stays in the
        # dialog because this is a cost summary and the reader needs to
        # know the Discord half will not happen; the wording no longer
        # implies they asked for it and were refused.
        logs_line = (
            "Logs:     not posted — no Discord webhook is configured\n"
            "          (set one in Settings)\n"
        )
    else:
        # Configured and unusable is NOT the same as never configured, and
        # telling this user "no webhook is configured" is simply false --
        # they set one, and it is wrong. They would go to Settings, see a
        # populated field, and have no idea what the dialog meant.
        #
        # Api._post_combat_logs draws the same line for the same reason
        # (empty stays silent, broken gets a WARNING strip). The two have
        # to agree: this dialog is read before the upload and that strip
        # after it, about one webhook.
        logs_line = (
            "Logs:     not posted — the Discord webhook is not valid\n"
            "          (check it in Settings)\n"
        )

    final = (
        "Publishing to YouTube and posting to Discord cannot be undone from this app."
        if posting
        else "Publishing to YouTube cannot be undone from this app."
    )

    return (
        f"Upload {what} to YouTube?\n\n"
        f"Channel:  {where}\n"
        f"Privacy:  {privacy}\n"
        f"Title:    {titles}\n"
        f"Total:    {library.format_size(total_size)} · "
        f"{_hms(total_seconds)}\n"
        f"{logs_line}\n"
        f"{final}"
    )


def format_progress(index: int, total: int, fraction: float) -> str:
    """The status line during an upload.

    The progress BAR is driven by ((index + fraction) / total), so it tracks
    the whole batch. This text tracks the file. Saying so is the whole point
    of the function: the previous wording was "Uploading 3/10 — 94.8%" beside
    a bar sitting at 34%, and the two read as a contradiction rather than as
    two different measurements.

    A single-file upload gets no "file 1 of 1", which would be noise.
    """
    pct = f"{fraction * 100:.1f}%"
    if total <= 1:
        return f"Uploading… {pct}"
    return f"Uploading file {index + 1} of {total}… {pct}"


def format_destination(channel_title: str, privacy: str) -> str:
    """The line above the Upload button naming where the video will land.

    Privacy is deliberately NOT in this string. It was, and "Uploads go to
    Tommy · unlisted" read as one compound name rather than two facts --
    the privacy setting lives in Settings, and repeating it here bought a
    misreading rather than reassurance. `privacy` stays in the signature
    because every caller already passes it and the decision to leave it out
    is worth being able to reverse in one line.

    Empty channel_title is the normal state before the first successful
    upload, not an error: SCOPES holds youtube.upload alone, which cannot
    call channels.list, so the destination is learned from an insert
    response (uploader.channel_of) rather than looked up. Saying that
    plainly beats an empty gap where a channel name should be.
    """
    if not channel_title:
        return "Channel confirmed after the first upload"
    return f"Uploads go to {channel_title}"


def format_title_hint(count: int, stitch: bool) -> str:
    """The Title field's label, which depends on what is selected.

    uploader.build_body appends "(n/total)" to every title in a batch and
    substitutes "Untitled" for an empty one. Neither was disclosed anywhere,
    so a user typing one title got ten differently-named public videos and
    found out afterwards. The label is the cheapest place to say it, because
    it is already beside the field being misunderstood.
    """
    if count <= 1 or (stitch and count <= 1):
        return "Title"
    if stitch:
        return "Title (one stitched video)"
    return f"Title (applies to all {count}, numbered 1-{count})"


# --- settings --------------------------------------------------------------


def webhook_status(raw: str) -> str:
    """The line under the webhook field, describing what is stored.

    The field itself is masked, so this is the only confirmation of WHICH
    webhook is configured; discord.describe omits the token by construction.

    An unparseable value reports the parse error rather than "not
    configured", which is what it used to say for anything invalid -- a URL
    the user has visibly typed being described as absent reads as the app
    ignoring them and hides the actual mistake.
    """
    if not raw or not raw.strip():
        return "not configured"
    hook, error = discord.parse_webhook(raw)
    return discord.describe(hook) if hook else error


# --- fetch age -------------------------------------------------------------


def format_fetched(iso: str, now: "datetime.datetime | None" = None) -> str:
    """ "Last fetched 5h ago", in the app's one time vocabulary.

    Skills 8: the Uploader renders a file's age as "5h ago" and Skills
    rendered its fetch time as "8/25/2026, 12:12:28 AM" -- the same class of
    fact in two formats, one of them carrying seconds precision on a value
    where seconds cannot matter. The page built the second one itself with
    toLocaleString, which is why it never had to agree with anything.

    Delegates to library.format_date rather than reimplementing the
    thresholds. That function's precision degrades with age on purpose
    (minutes for something from this session, a calendar date for something
    from March), which is the property that makes it right here too: nobody
    needs the second a skill fetch landed, and everybody wants to know
    whether it was recent.

    The value is UTC and format_date works in local wall-clock. That is
    correct for both halves: the relative branches only need the delta,
    which is preserved through the POSIX timestamp, and the calendar
    fallback SHOULD render in the reader's own timezone.

    `now` is injectable for the same reason format_date's is -- every
    threshold is relative to it, and a test cannot wait for the clock.
    """
    parsed = _parse_iso_utc(iso)
    if parsed is None:
        # Covers absent ("" from eveskills.state._iso, which never writes
        # None) and unparseable alike. The page said "Never fetched" for
        # both and that stays true: a value we cannot read is a value we
        # cannot claim a time for.
        return "Never fetched"
    return f"Last fetched {library.format_date(parsed.timestamp(), now=now)}"


def _parse_iso_utc(raw: str):
    """ISO 8601 to an aware UTC datetime, or None.

    Naive input is read as UTC, matching eveskills.state._parse_utc: this
    package writes UTC everywhere, so a naive string can only be a hand
    edit, and reading it as local would shift the age by the machine's
    offset. Duplicated rather than imported to keep ui/ from depending on
    eveskills' private helpers -- the behaviour is asserted in tests.
    """
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.UTC)
    return parsed


# --- preconditions not met -------------------------------------------------
#
# Settings 1: one release rendered "this control cannot act yet" two
# opposite ways. The Uploader disabled the combat-log checkbox and explained
# why; Settings > Previews left every keybind below a switched-off feature
# fully live and explained why. Same situation, same release, opposite
# answers -- so a user could not learn the rule.
#
# app.js's WM.setEnabled settled the TREATMENT half (a control is disabled
# when the app already knows the action cannot be carried out from the state
# it holds; not for an action that might merely fail once attempted). This
# table is the WORDS half, and the two are deliberately separate: the
# Previews keybinds stay LIVE under that rule, because recording a keybind
# for later is an action that can be carried out -- but they still need to
# say that nothing is registered yet. Explaining and disabling are not the
# same decision, which is most of why the screens diverged.
#
# One table rather than prose in each screen's markup, for the reason
# AUTH_STATES is a table: these sentences are read seconds apart by someone
# forming a model of one app, and a second copy drifts within a release.
# index.html carried the Previews one as static markup, where nothing could
# test it and no other screen could reuse its voice.
#
# The shape every entry keeps: name the STATE, then the CONSEQUENCE, then
# the WAY OUT. PRODUCT.md's "Say what happened and what to do" -- and the
# way out is not decoration here, because WM.setEnabled forbids disabling
# the only route to a control's own precondition. A note with no remedy is
# a dead end the user cannot see the exit from. tests/test_app_copy.py
# asserts the shape rather than trusting each entry to remember it.
INERT_NOTES = {
    "previews_off": (
        "Previews are off, so every keybind below is unregistered "
        "until you turn them back on."
    ),
    "no_webhook": (
        "No Discord webhook is configured, so combat logs are not "
        "posted. Set one in Settings \u203a Discord."
    ),
}


def inert_note(key: str) -> str:
    """The sentence for one unmet precondition, or "" if there is none.

    Empty string for an unknown key rather than a raised error or a
    placeholder: this renders into a hint slot on a live screen, and a
    KeyError from a note is a worse outcome than a missing note. The page
    hides the slot when the string is empty, so "" is already the shape it
    handles.
    """
    return INERT_NOTES.get(key, "")


# --- EVE settings profiles -------------------------------------------------

# What the user ticked, per evesettings.tree.file_kind. The page offers the
# two as a Characters / Accounts switch, so the dialog uses the same two
# words rather than naming the files underneath them.
_COPY_NOUNS = {"character": "character", "account": "account"}
# A selection that is neither (or is mixed, which the page cannot currently
# produce but the bridge does not forbid) falls back to naming the files.
# Degraded, not wrong: it is what the dialog said for every selection
# before it could tell the difference.
_COPY_NOUN_FALLBACK = "settings file"


def _copy_noun(count: int, kind: str | None) -> str:
    """ "characters", "account", "settings files" -- the noun alone.

    The count is left to the caller because the two sentences place it
    differently ("3 other characters", "Copied to 3 characters"), but the
    NOUN is shared deliberately: those two are a second apart on the same
    screen, and a dialog saying "characters" followed by a strip saying
    "file(s)" would be a worse disagreement than the one this replaced.
    """
    noun = _COPY_NOUNS.get(kind or "", _COPY_NOUN_FALLBACK)
    return noun if count == 1 else f"{noun}s"


def format_eve_copy_done(count: int, kind: str | None) -> str:
    """The status line after a copy that wrote everything it was asked to."""
    return f"Copied to {count} {_copy_noun(count, kind)}."


def format_eve_copy_confirm(count: int, kind: str | None, eve_running: bool) -> str:
    """The confirm shown before one profile's settings overwrite others.

    Two things this says that its predecessor did not.

    It counts what the user selected. The dialog said "3 other file(s)" at
    someone who had just ticked three character names -- the wrong noun and
    the "(s)" padding PRODUCT.md's tone rule rules out, in the last thing
    shown before an irreversible write. `kind` comes from the target paths
    (evesettings.tree.file_kind), not from a mode flag the page would have
    to pass and keep in step.

    It repeats the running-client hazard. The screen already renders a
    warn-toned "EVE running" pill precisely because EVE rewrites its own
    settings on exit and will overwrite whatever was copied underneath it
    -- but the pill is advisory and easy to miss, and this dialog is modal
    and unmissable. The warning was on the wrong one of the two.

    It stays advisory here as well: nothing is blocked, because the probe
    is best-effort (Api._eve_client_running swallows its own failures) and
    a false positive must not be able to lock a user out of their own
    profiles.
    """
    running = ""
    if eve_running:
        running = (
            "EVE is running. Close every client first — EVE rewrites "
            "its own settings when it exits, which would overwrite "
            "what is copied now.\n\n"
        )

    return (
        f"Copy these settings onto {count} other {_copy_noun(count, kind)}?\n\n"
        f"Each one is backed up first.\n\n"
        f"{running}"
        "This cannot be undone except by restoring a backup."
    )


# --- list cell help --------------------------------------------------------

# Keyed by column identifier, then by the exact cell text library.VideoInfo
# renders. Both glyphs were unexplained: the list showed "?" and "↗" with
# nothing anywhere saying what either meant.
#
# Keyed on rendered text rather than on the underlying value so the help
# cannot disagree with what the user is actually looking at -- which also
# means a change to duration_str's glyphs silently orphans these entries.
# tests/test_tooltip.py guards exactly that coupling.
#
# The page carries a second copy of this table (web/list.js): tooltips are
# needed synchronously while a row is built, so unlike auth_labels() and
# panel_text() there is no round trip to put the strings behind. That makes
# THIS table unreachable from the running product, so a change here would
# otherwise pass its own tests and reach no user. test_tooltip.py's
# cross-check against list.js is what stops that being silent.
CELL_HELP: dict[str, dict[str, str]] = {
    "duration": {
        "?": "Length could not be read. ffprobe could not open this file, so\n"
        "combat-log upload is unavailable for it.",
        # The dash is about the INSTALL, the "?" about the file. They shared
        # the "?" glyph until round 2, so an install with no ffprobe accused
        # every recording in the folder of being unreadable.
        "—": "Length was not measured: ffprobe was not found.\n"
        "Wingman bundles it, so reinstalling restores lengths and\n"
        "combat-log upload.",
        "…": "Measuring length…",
    },
    "link": {
        "↗": "Uploaded to YouTube.\n"
        "Double-click to open it, or right-click to copy the link.",
    },
}


def tooltip_for_cell(column: str, text: str) -> str | None:
    """Help for one list cell, or None if it needs none.

    Keyed on the rendered text rather than on the underlying value so it
    cannot disagree with what the user is actually looking at.
    """
    return CELL_HELP.get(column, {}).get(text)


# --- account control ---------------------------------------------------

# (status message, button label, button enabled) per bridge auth state.
# The two transient states disable the button: a second press during the
# credential lookup races it, and during the browser flow it starts a
# second OAuth flow on top of the first.
AUTH_STATES = {
    "disconnected": ("Not connected", "Sign in with Google", True),
    "connecting": ("Waiting for browser…", "Connecting…", False),
    "connected": ("Connected", "Switch account", True),
    "revoking": ("Signing out…", "Signing out…", False),
}
_AUTH_DEFAULT = AUTH_STATES["disconnected"]


def auth_state(state: str) -> tuple[str, str, bool]:
    """(message, button label, button enabled) for one account state.

    Unknown states, including anything a future revision adds before this
    table learns about it, fall back to an enabled "Sign in with Google":
    an optimistic label on a working button beats a dead one.
    """
    return AUTH_STATES.get(state, _AUTH_DEFAULT)


def account_line(state: str, channel_title: str = "") -> str:
    """The Settings account message, naming the channel when one is known.

    "Connected" alone left the user unable to tell WHICH account they were
    signed in as, which matters here precisely because the app can upload
    to the wrong channel without ever saying so.

    What this names is the YouTube CHANNEL, not the Google account email.
    The app holds the youtube.upload scope alone, which cannot call
    channels.list, so the title is learned from an insert response
    (uploader.channel_of) -- meaning it is empty until the first successful
    upload and the line correctly stays a bare "Connected" until then.
    Showing the email instead would need an added scope and re-consent.

    Only the connected state is decorated: "Not connected as Tommy" is
    nonsense, and "Signing out… as Tommy" is noise.
    """
    message = auth_state(state)[0]
    if state == "connected" and channel_title:
        return f"{message} as {channel_title}"
    return message
