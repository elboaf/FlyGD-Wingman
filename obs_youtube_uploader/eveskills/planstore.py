"""The plans folder: listing, reading, and the name rules.

The name rules are Windows' rules and are enforced even when this runs
on Linux, because the released application is Windows-only: a name this
module accepted on a developer's machine would fail at the write on a
user's. Plan names also arrive from the bridge, which is to say from the
page, so they are validated as untrusted input rather than as a typo
check.

Ported from TriffView's PlanStore.cs / PlanNameValidator.cs.
"""
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import plans

MAX_PLAN_FILES = 200
MAX_PLAN_NAME_CHARS = 120

STARTER_PLAN_NAME = "Core Ship Skills"

# The nine characters Windows refuses in a filename outright. `/` and `\`
# are also the traversal primitives, so this set does two jobs.
_INVALID_CHARS = frozenset('<>:"/\\|?*')

# Device names, not files: CreateFile on CON.txt opens the console, the
# write appears to succeed, and nothing lands on disk. Windows applies
# the rule to the base name, so an extension does not escape it.
_RESERVED = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{n}" for n in range(1, 10)]
    + [f"LPT{n}" for n in range(1, 10)]
)


def validate_plan_name(name) -> str:
    """Return "" when *name* is a usable plan stem, else the reason why.

    A reason string rather than an exception because every caller wants
    to show it: the bridge returns it to the page verbatim.
    """
    if not isinstance(name, str):
        # The name crosses the bridge from JavaScript, so its type is
        # not guaranteed. A TypeError here lands on the bridge thread.
        return "Plan name is not text."
    normalised = unicodedata.normalize("NFC", name)
    if not normalised.strip():
        return "Plan name is empty."
    if normalised != normalised.strip():
        # Rejected rather than trimmed: the name is the identity stored
        # in selected_plan_name, and trimming would make the stored name
        # differ from the one the user typed.
        return "Plan name has leading or trailing whitespace."
    if len(normalised) > MAX_PLAN_NAME_CHARS:
        return ("Plan name is longer than "
                f"{MAX_PLAN_NAME_CHARS} characters.")
    if any(unicodedata.category(ch) == "Cc" for ch in normalised):
        return "Plan name contains a control character."
    if any(ch in _INVALID_CHARS for ch in normalised):
        return 'Plan name cannot contain < > : " / \\ | ? *'
    if ".." in normalised:
        # Not covered by _INVALID_CHARS, which has no dot in it. ".." is
        # a legal filename fragment right up until it is joined to a
        # path, and then it escapes the folder.
        return "Plan name cannot contain '..'."
    if normalised.endswith("."):
        # Windows strips a trailing dot when creating the file, so
        # "Core." becomes "Core" on disk and the selected name matches
        # nothing on reload -- which reads as data loss. A trailing
        # space is already rejected by the whitespace check above.
        return "Plan name cannot end with a dot."
    if normalised.split(".", 1)[0].upper() in _RESERVED:
        return "Plan name is a reserved Windows device name."
    return ""


@dataclass(frozen=True)
class PlanFile:
    name: str           # the (NFC-normalised) filename stem; the plan's
                         # identity everywhere else in the app
    requirements: tuple
    diagnostics: tuple

    @property
    def ok(self) -> bool:
        return not self.diagnostics


def list_plans(plans_dir: Path):
    """Read every *.txt in *plans_dir*. Returns (plans, warnings).

    Never raises. A broken plan is still listed -- it is the row that
    carries its diagnostics into the plan-issues disclosure, and
    dropping it would leave the user with a file on disk and no
    explanation anywhere in the UI.
    """
    warnings = []
    try:
        # is_file() because glob("*.txt") matches directories too, and
        # read_text() on one raises IsADirectoryError -- which would
        # become a warning about a file the user never created.
        entries = [p for p in plans_dir.glob("*.txt") if p.is_file()]
    except OSError as exc:
        # A deleted or permission-denied folder costs an empty roster,
        # not a crash. `Open plans folder` reports the real failure.
        return [], [f"The plans folder could not be read: {exc}"]

    # Sorted BEFORE the cap so the same 200 plans appear on every
    # reload, rather than whichever 200 the filesystem enumerated first.
    # Case-insensitive because byte order puts every capitalised name
    # ahead of every lowercase one and scatters related plans.
    entries.sort(key=lambda p: p.stem.casefold())
    if len(entries) > MAX_PLAN_FILES:
        warnings.append(
            f"Only the first {MAX_PLAN_FILES} of {len(entries)} plan files "
            "were read.")
        entries = entries[:MAX_PLAN_FILES]

    found = []
    # Case-insensitive, matching PlanStore.cs's OrdinalIgnoreCase
    # seenNames set: two stems differing only by case (or by Unicode
    # normalisation, hence the NFC fold below) would otherwise both load
    # and silently shadow each other in the rail.
    seen_names = set()
    for path in entries:
        # Validated before anything else is trusted about this entry --
        # PlanStore.cs:81-85. Without this, a device name like "CON.txt"
        # or a stem carrying a Windows-invalid character would be handed
        # to the parser as an ordinary plan identity, even though it
        # could never have been created as a *file* on the Windows
        # release this app actually ships as.
        reason = validate_plan_name(path.stem)
        if reason:
            warnings.append(f"{path.name}: {reason}")
            continue
        # NFC-normalised, case-folded key: validate_plan_name already
        # NFC-normalises internally, but it doesn't hand the normalised
        # form back, so it is redone here for the identity used as both
        # the collision key and the PlanFile.name.
        normalised_name = unicodedata.normalize("NFC", path.stem)
        collision_key = normalised_name.casefold()
        if collision_key in seen_names:
            # PlanStore.cs:86-90. Two files whose stems differ only by
            # case or by NFC/NFD normalisation both look like distinct,
            # valid plans on their own -- it is only in relation to each
            # other that one has to lose, silently, on every reload.
            warnings.append(
                f"{path.name}: Plan name collides case-insensitively "
                "with another file.")
            continue
        seen_names.add(collision_key)

        # Bounded by SIZE before the content is ever read into memory --
        # PlanStore.cs:92-97, which checks FileInfo.Length before calling
        # AtomicFile.ReadBoundedText. plans.MAX_CONTENT_CHARS bounds
        # *characters already loaded*; consulting it after
        # path.read_text() has already pulled the whole file into memory
        # is too late to protect against a multi-gigabyte .txt dropped in
        # the folder. Bytes and characters are not the same unit -- this
        # is a cheap pre-filter on disk size, not a replacement for the
        # character cap plans.parse still enforces on what it decodes.
        try:
            size = path.stat().st_size
        except OSError as exc:
            warnings.append(f"{path.name} could not be read: {exc}")
            continue
        if size > plans.MAX_CONTENT_CHARS:
            warnings.append(
                f"{path.name}: Plan exceeds the "
                f"{plans.MAX_CONTENT_CHARS // 1024} KiB file limit.")
            continue

        try:
            contents = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # A .txt Notepad saved as UTF-16, or a binary file renamed.
            # One unreadable file costs its own row, not the folder --
            # the same per-entry tolerance preview/layout.py takes.
            warnings.append(f"{path.name} could not be read: {exc}")
            continue
        result = plans.parse(contents)
        found.append(PlanFile(normalised_name, result.requirements,
                              result.diagnostics))
    return found, warnings


# Real skill names, at modest levels, and it must parse without a single
# diagnostic: a seeded plan that complained would greet every new user
# with a plan-issues disclosure about a file they did not write. The
# comment header doubles as the format documentation, because this file
# is the only instruction most users will ever read.
_STARTER_PLAN = """\
# Core Ship Skills - a starter plan, safe to edit or delete.
#
# One skill per line: the skill name, a space, then the level as
# I II III IV V or 1 2 3 4 5. Lines starting with # are ignored.
#
Spaceship Command III
Navigation IV
Evasive Maneuvering III
Warp Drive Operation III
Hull Upgrades IV
Mechanics IV
Shield Operation III
Power Grid Management IV
CPU Management IV
Capacitor Systems Operation III
Capacitor Management III
Targeting III
"""


def seed_starter_plan(plans_dir: Path) -> bool:
    """Write the starter plan when *plans_dir* holds no .txt at all.

    Keyed on "the folder has no plans" rather than "this file is
    missing", so a user who deletes the starter does not get it back on
    every launch.

    Returns False rather than raising on any filesystem failure: a
    read-only or occupied state directory costs the starter plan, not
    the launch, which is the same policy paths.resolve_binary() and
    configure_logging() take with a missing resource.
    """
    try:
        plans_dir.mkdir(parents=True, exist_ok=True)
        if any(plans_dir.glob("*.txt")):
            return False
        (plans_dir / f"{STARTER_PLAN_NAME}.txt").write_text(
            _STARTER_PLAN, encoding="utf-8")
    except OSError:
        return False
    return True
