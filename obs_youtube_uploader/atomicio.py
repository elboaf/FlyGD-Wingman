"""Publish a file so a concurrent reader never sees it half-written.

Every file crossing the Wingman/engine boundary goes through here. Single
writer ownership settles who may write; it says nothing about what a reader
polling on a timer observes mid-write, and both sides poll.
"""
import os
import tempfile
import time
from pathlib import Path


def write_atomic(path: Path, text: str, encoding: str = "utf-8", *,
                 attempts: int = 5, sleep=time.sleep) -> None:
    """Write *text* to *path* by rename, leaving the old file intact on error.

    The temporary file is created in the destination directory on purpose:
    os.replace is only atomic within one filesystem, so a temp elsewhere
    would degrade to a non-atomic copy across a volume boundary.

    Two deliberate limits. The parent directory is not fsynced after the
    rename, so a crash-plus-reboot landing exactly between the two can lose
    the new content -- every file written through here is regenerated on the
    next save or engine start, so durability of that window buys nothing.
    And a hard kill between the write and the rename leaves the temporary
    file behind; it is inert, and sweeping it would be racy against a
    concurrent write.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=str(path.parent),
                                        prefix=path.name + ".",
                                        suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding=encoding, newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        # Windows only: os.replace maps to MoveFileExW, which raises a
        # sharing violation if the destination is open by a reader that did
        # not grant FILE_SHARE_DELETE -- and GetPrivateProfileString, which
        # the engine uses to poll these files every 2-10 seconds, does not.
        # The reads are brief, so a short bounded retry clears it; failing
        # outright would surface as settings mysteriously not saving.
        for attempt in range(attempts):
            try:
                os.replace(tmp_name, path)
                break
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                sleep(0.05 * (attempt + 1))
    except BaseException:
        # Leave no debris: a stray .tmp beside the real file is confusing
        # and, in state_dir, indistinguishable from state that matters.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
