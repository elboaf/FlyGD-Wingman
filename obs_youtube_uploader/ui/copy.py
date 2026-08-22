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
from .. import discord, library, uploader

# --- main window -----------------------------------------------------------


def format_selection_summary(infos: list[library.VideoInfo]) -> str:
    """The panel's "3 selected · 1.2 GB · 2:04:35" line.

    Two asymmetries are deliberate:

    * The "+" marks the duration total as a floor, not a value. A recording
      whose probe is still outstanding contributes 0, so an unmarked total
      would read as complete while being short. It reuses the duration
      column's own vocabulary for the same state ("…" per row) rather than
      inventing a second one.
    * Size is never marked partial: info.size comes from stat, so it is
      final from the moment the row exists, whatever the probe is doing.

    A probed recording with duration None is a finished verdict (ffprobe
    could not read it), so it also contributes 0 but leaves the total exact.
    Its own row already shows "?"; repeating that diagnosis in an aggregate
    would say nothing the user can act on.

    The count carries no noun ("3 selected"), which sidesteps agreement at
    every value instead of special-casing 1.
    """
    if not infos:
        return "Nothing selected"
    total_size = sum(info.size for info in infos)
    total_seconds = int(sum(info.duration or 0.0 for info in infos))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    partial = "+" if any(not info.probed for info in infos) else ""
    return (f"{len(infos)} selected · {library.format_size(total_size)}"
            f" · {hours}:{minutes:02d}:{seconds:02d}{partial}")


def _hms(total_seconds: int) -> str:
    hours, remainder = divmod(int(total_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def format_upload_confirm(infos: list[library.VideoInfo], title: str,
                          privacy: str, channel_title: str,
                          stitch: bool, logs: bool) -> str:
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

    `logs` adds one line rather than a second dialog. One button now
    publishes to two places, and this is the only screen a user sees
    between pressing it and the upload starting, so the Discord half has to
    be named here or it is never disclosed at all.
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
        first = uploader.build_body(title, "", privacy, "", 0, count)["snippet"]["title"]
        what = f"{count} recording{'s' if count != 1 else ''}"
        titles = f'"{first}"'
        if count > 1:
            last = uploader.build_body(title, "", privacy, "", count - 1,
                                       count)["snippet"]["title"]
            titles += f' … "{last}"'

    logs_line = ("Logs:     combat logs posted to Discord afterwards\n"
                 if logs else "")
    final = ("Publishing to YouTube and posting to Discord cannot be undone "
             "from this app." if logs else
             "Publishing to YouTube cannot be undone from this app.")

    return (f"Upload {what} to YouTube?\n\n"
            f"Channel:  {where}\n"
            f"Privacy:  {privacy}\n"
            f"Title:    {titles}\n"
            f"Total:    {library.format_size(total_size)} · "
            f"{_hms(total_seconds)}\n"
            f"{logs_line}\n"
            f"{final}")


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
