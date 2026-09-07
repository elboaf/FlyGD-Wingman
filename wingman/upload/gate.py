"""The work gate: one process-wide arbiter for upload, update handoff and Quit.

Shared between `upload.controller` and `ui/api.py` on purpose; see
`WorkGate`'s docstring for why it is constructed once and injected into both.
"""

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class ClaimResult:
    """One locked claim decision, including why a caller was refused."""

    ok: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.ok


class WorkGate:
    """Atomically arbitrate uploads, updater handoff, and process shutdown.

    The lock protects state transitions only. Prompts, page pushes, I/O, worker
    creation, and shutdown all happen after it has been released so no external
    operation can park every claimant behind it.

    ONE instance per process, shared by reference. The gate has three
    tenants that live in two places: the upload claim belongs to
    `upload.controller.UploaderController`, while the handoff claim (the
    app updater) and the quit claim (`__main__.on_quit` via
    `Api._claim_quit`) still live in `ui/api.py`. The composition root
    (`Api.__init__`) therefore constructs the gate once and injects the
    same object into both -- it was deliberately NOT moved wholesale into
    the uploader controller when that controller was extracted, because a
    gate the updater cannot see would let an installer launch over a
    running upload, which is the exact race this class exists to close.
    A second instance anywhere is a bug: each tenant would then be
    arbitrating against nobody.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._upload = False
        self._handoff = ""
        self._quitting = False

    def claim_upload(self) -> ClaimResult:
        with self._lock:
            if self._handoff:
                return ClaimResult(False, "handoff")
            if self._quitting:
                return ClaimResult(False, "quitting")
            if self._upload:
                return ClaimResult(False, "upload")
            self._upload = True
            return ClaimResult(True)

    def upload_claimed(self) -> bool:
        with self._lock:
            return self._upload

    def release_upload(self) -> None:
        with self._lock:
            self._upload = False

    def claim_handoff(self, phase: str) -> ClaimResult:
        with self._lock:
            if self._upload:
                return ClaimResult(False, "upload")
            if self._quitting:
                return ClaimResult(False, "quitting")
            # The updater's own runtime lock excludes a second installer.
            # Reusing this transition lets that owner advance the phase
            # without releasing the claim between revalidation and launch.
            self._handoff = phase
            return ClaimResult(True)

    def release_handoff(self) -> None:
        with self._lock:
            self._handoff = ""

    def handoff_phase(self) -> str:
        with self._lock:
            return self._handoff

    def claim_quit(self, *, force_upload: bool) -> ClaimResult:
        with self._lock:
            if self._quitting:
                return ClaimResult(True)
            if self._handoff:
                return ClaimResult(False, "handoff")
            if self._upload and not force_upload:
                return ClaimResult(False, "upload")
            self._quitting = True
            return ClaimResult(True)

    def begin_update_shutdown(self) -> bool:
        with self._lock:
            if not self._handoff:
                return False
            self._quitting = True
            return True
