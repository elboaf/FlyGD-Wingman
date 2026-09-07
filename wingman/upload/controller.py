"""Uploader runtime ownership: the recording list, uploads, retries and log posts.

Every lock, cache, worker handle and queue the Uploader route runs on lives
here. Named ports keep the page, the dialogs and the status strip outside
this module without exposing bridge transport: nothing here knows a handler
name, holds a window, or can push. The work gate is SHARED with the app
updater and Quit, which still live in `ui/api.py`; see `upload.gate`.

`state` is the bridge's AppState, shared by reference and read live:
`recording_dir` is rebound by Settings' folder commit and `settings` is
mutated in place, so nothing here may copy either at construction.
"""

import datetime
from dataclasses import dataclass
from pathlib import Path

# 100ms, carried over from app.PROBE_DRAIN_MS: fast enough that durations
# appear to fill in live, slow enough that a folder of a hundred recordings
# is batched into a handful of drains rather than a hundred saves.
PROBE_DRAIN_S = 0.1


def folder_note(folder: Path, suppressed: int) -> str:
    """What just happened to the recording folder, with the real number.

    Round 3's B11: the two fields with a data-loss history said nothing
    about how they commit. The answer settled on was not a confirm and not
    an Apply button -- Browse and Detect rebind in one click and would
    bypass both -- but a report, written after the commit, where the count
    is knowable.

    The cost is deliberately stated as what it is and no worse. Those
    recordings are not announced and arrive unticked, but they are still
    listed: list_rows() rebuilds from the folder and only the watcher's
    poll result is preselected (__main__.py's poll_tick). Calling it data
    loss would be the same overstatement DESIGN.md carried for a release.

    Zero says nothing about announcements, because there was nothing to
    suppress and a "0 recordings were not announced" is a sentence the
    reader has to parse twice to learn nothing.
    """
    where = f"Now watching {folder}."
    if suppressed == 0:
        return where
    # Singular by hand rather than a pluralise helper: this is the only
    # counted noun on the Settings route, and copy.py's number formatting
    # is another lane's region.
    if suppressed == 1:
        return f"{where} 1 recording already there was not announced."
    return f"{where} {suppressed} recordings already there were not announced."


@dataclass(frozen=True)
class LogTarget:
    """Where a combat-log post would go, or why it cannot go anywhere.

    Resolving this was inline in `_post_combat_logs` until the Uploader
    grew a standalone `Post the last hour`. Two callers needing the same
    three answers -- parse the webhook, tell absent from unusable, find the
    Gamelogs folder -- is exactly the shape that drifts when it is written
    twice, and one of the two copies would be the one a user reads.

    `problem` is a CLAUSE, not a sentence, because the two callers frame it
    differently: "Combat logs skipped: ..." after an upload that succeeded,
    "Combat logs not posted: ..." when the post was the whole action.

    `configured` is the one case the callers must disagree about. No
    webhook at all is a fact about the INSTALL rather than a failure: the
    upload tail stays silent (a WARNING strip on every upload forever is
    the recurring-failure pattern `format_upload_confirm`'s docstring
    records, and the panel states the fact instead), while a standalone
    post has to say it -- the user asked for exactly this, and nothing else
    would answer them.
    """

    hook: object | None
    gamelogs_dir: Path | None
    problem: str
    configured: bool


# The standalone post's window. One hour, ending at the click: it is not
# derived from any recording, which is the whole point of the control --
# the fight that was not recorded, or was recorded and is not worth
# uploading. combatlog.WINDOW_PADDING widens what actually gets selected by
# five minutes each side, as it does for the upload tail.
RECENT_LOG_WINDOW = datetime.timedelta(hours=1)


@dataclass
class UploadJob:
    """Every value the upload worker needs, captured before dispatch.

    `ids` runs parallel to `items` so a finished upload can be linked back
    to the row the page is showing without the worker re-resolving an id
    against a snapshot that may have been rebuilt underneath it.

    `start_index` lets a retry resume partway through without renumbering
    the "(2/3)" title suffixes: the worker skips earlier indices but still
    computes totals from the full list.
    """

    items: list
    ids: list[str]
    title: str
    description: str
    stitch: bool
    privacy: str
    category: str
    # Carried on the job rather than read from settings at post time so a
    # Retry posts logs exactly as the confirmed upload promised, even if the
    # user has since unchecked the box.
    logs: bool = False
    start_index: int = 0


@dataclass
class RetryState:
    """What a manual Retry needs to resume rather than restart."""

    job: UploadJob
    resume_index: int
    request: object | None
