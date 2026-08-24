"""Copy one settings file onto many, reporting per target.

The loop never aborts. TriffView throws on the first failure, leaving an
unknown mix of copied and uncopied targets and discarding the count it
computed; library.delete's (deleted, failures) shape is the one followed here.
"""
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


def copy_to_targets(source, targets, *, backup,
                    copy=atomicio.copy_atomic) -> CopyReport:
    """Copy *source* onto each of *targets*, backing each one up first.

    `backup` is called with the target path before it is overwritten and
    must raise on failure -- a target whose backup could not be taken is
    skipped untouched rather than overwritten unprotected.
    """
    source = Path(source)
    source_kind = tree.file_kind(source)
    if source_kind is None:
        raise ValueError("Only EVE settings files can be copied.")

    chosen = []
    seen = set()
    for candidate in targets:
        candidate = Path(candidate)
        key = str(candidate).casefold()
        if key in seen or candidate == source:
            continue
        seen.add(key)
        chosen.append(candidate)
    if not chosen:
        raise ValueError("Choose at least one target to copy to.")

    outcomes = []
    for target in chosen:
        target_kind = tree.file_kind(target)
        if target_kind != source_kind:
            outcomes.append(TargetOutcome(
                target, False,
                f"Cannot copy {source_kind} settings onto "
                f"{target_kind or 'an unknown file'}."))
            continue
        if target.exists():
            try:
                backup(target)
            except Exception as error:  # noqa: BLE001 - reported per target
                outcomes.append(TargetOutcome(
                    target, False,
                    f"Skipped: its backup could not be made. {_describe(error)}"))
                continue
        try:
            copy(source, target)
        except Exception as error:  # noqa: BLE001 - reported per target
            outcomes.append(TargetOutcome(target, False, _describe(error)))
            continue
        outcomes.append(TargetOutcome(target, True))
    return CopyReport(outcomes)
