"""Copy one settings file onto many, reporting per target.

The loop never aborts. TriffView throws on the first failure, leaving an
unknown mix of copied and uncopied targets and discarding the count it
computed; library.delete's (deleted, failures) shape is the one followed here.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from .. import atomicio
from . import tree


@dataclass(frozen=True)
class TargetOutcome:
    path: Path
    ok: bool
    reason: str = ""


@dataclass(frozen=True)
class CopyReport:
    outcomes: list = field(default_factory=list)

    @property
    def succeeded(self) -> list:
        return [o for o in self.outcomes if o.ok]

    @property
    def failed(self) -> list:
        return [o for o in self.outcomes if not o.ok]


def _describe(error: BaseException) -> str:
    if isinstance(error, PermissionError):
        # The visible cost of temp-then-replace: os.replace needs
        # FILE_SHARE_DELETE, which EVE does not grant while it is running.
        # Reported as an instruction rather than an OS error code.
        return "The file is in use. Close EVE and retry."
    return str(error) or error.__class__.__name__


def copy_to_targets(
    source, targets, *, root, backup, copy=atomicio.copy_atomic
) -> CopyReport:
    """Copy *source* onto each of *targets*, backing each one up first.

    `root` is the configured EVE folder. Every path is resolved and checked
    to be under it before anything is read or written -- a junction inside
    the settings tree pointing outside it is what this catches, and
    copy_atomic creates missing parent directories, so an unchecked target
    does not merely fail.

    `backup` is called with the target path before it is overwritten and
    must raise on failure -- a target whose backup could not be taken is
    skipped untouched rather than overwritten unprotected.
    """
    source = Path(source)
    # A bad source is the whole batch's problem, so it raises; a bad target
    # is that target's problem and is reported in the loop below.
    tree.require_under(root, source, suffix=".dat")
    source_kind = tree.file_kind(source)
    if source_kind is None:
        raise ValueError("Only EVE settings files can be copied.")

    # Both halves of "is this the same file?" use os.path.normcase, so they
    # cannot disagree. They did: dedup keyed on str().casefold() while
    # exclusion used Path equality. On Windows those agree by accident,
    # because WindowsPath.__eq__ normalises case itself -- but on POSIX
    # casefold() collapses settings_Alt/ and settings_alt/, two genuinely
    # distinct profiles, and one of them was silently dropped from the
    # target list. normcase is the identity on POSIX and lowercases (and
    # normalises separators) on Windows: the platform's own answer.
    source_key = os.path.normcase(str(source))
    chosen = []
    seen = set()
    for candidate in targets:
        candidate = Path(candidate)
        key = os.path.normcase(str(candidate))
        if key in seen or key == source_key:
            continue
        seen.add(key)
        chosen.append(candidate)
    if not chosen:
        raise ValueError("Choose at least one target to copy to.")

    outcomes = []
    for target in chosen:
        try:
            tree.require_under(root, target, suffix=".dat")
        except ValueError as error:
            outcomes.append(TargetOutcome(target, False, str(error)))
            continue
        target_kind = tree.file_kind(target)
        if target_kind != source_kind:
            outcomes.append(
                TargetOutcome(
                    target,
                    False,
                    f"Cannot copy {source_kind} settings onto "
                    f"{target_kind or 'an unknown file'}.",
                )
            )
            continue
        if target.exists():
            try:
                backup(target)
            except Exception as error:  # noqa: BLE001 - reported per target
                outcomes.append(
                    TargetOutcome(
                        target,
                        False,
                        f"Skipped: its backup could not be made. {_describe(error)}",
                    )
                )
                continue
        try:
            copy(source, target)
        except Exception as error:  # noqa: BLE001 - reported per target
            outcomes.append(TargetOutcome(target, False, _describe(error)))
            continue
        outcomes.append(TargetOutcome(target, True))
    return CopyReport(outcomes)
