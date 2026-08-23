"""Publish a file so a concurrent reader never sees it half-written.

Every file crossing the Wingman/engine boundary goes through here. Single
writer ownership settles who may write; it says nothing about what a reader
polling on a timer observes mid-write, and both sides poll.
"""
import os
import tempfile
from pathlib import Path


def write_atomic(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Write *text* to *path* by rename, leaving the old file intact on error.

    The temporary file is created in the destination directory on purpose:
    os.replace is only atomic within one filesystem, so a temp elsewhere
    would degrade to a non-atomic copy across a volume boundary.
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
        os.replace(tmp_name, path)
    except BaseException:
        # Leave no debris: a stray .tmp beside the real file is confusing
        # and, in state_dir, indistinguishable from state that matters.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
