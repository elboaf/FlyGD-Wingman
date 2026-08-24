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

# PlanStore.cs:19's MaxPlanFileBytes, kept as its own constant rather
# than reusing plans.MAX_CONTENT_CHARS: the two happen to be the same
# number today but bound different things in different units -- this is
# a byte count checked against a file's size on disk before it is read,
# plans.MAX_CONTENT_CHARS is a character count checked against text
# already decoded into memory. A future change to the parser's
# character cap must not silently move this file-size gate.
MAX_PLAN_FILE_BYTES = 512 * 1024

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
    diagnostics: tuple  # always () -- a plan that failed to parse never
                         # reaches `found`; it becomes a PlanIssue instead

    @property
    def ok(self) -> bool:
        return not self.diagnostics


@dataclass(frozen=True)
class PlanIssue:
    """One file that did not become a listed plan, and why.

    Mirrors PlanStore.cs:8's PlanFileIssue record as a structured type
    rather than a formatted string: the bridge payload needs the
    filename and message as separate fields, and recovering the
    filename by splitting a flat string on some separator would break
    the moment a user names a plan file containing that separator.
    """
    file_name: str
    message: str
    diagnostics: tuple   # the plan's own diagnostics when the issue is a
                         # parse failure; () for every other kind of issue


def _sort_key(path: Path):
    """A TOTAL order over plan files, not merely a case-insensitive one.

    Case-folding alone is not a total order here: "Rifter" and "rifter"
    fold to the same key, and Python's sort is stable, so their relative
    order falls through to whatever the filesystem enumerated. The
    collision loop below resolves such a pair positionally -- first one
    wins -- which made the SURVIVING plan filesystem-dependent. The same
    two files kept "Rifter" on one machine and "rifter" on CI.

    The normalised stem breaks the tie identically everywhere. Byte
    order decides it, so the capitalised stem wins; which one survives
    matters far less than that it is the same one every time, on every
    machine. This is also what makes the MAX_PLAN_FILES cap reproducible
    for a pair straddling the boundary.

    NFC-normalised to agree with `collision_key` below: a tiebreak that
    ordered on a different form than the dedup compares could rank two
    stems by one identity and then discard by another.
    """
    normalised = unicodedata.normalize("NFC", path.stem)
    return (normalised.casefold(), normalised)


def list_plans(plans_dir: Path):
    """Read every *.txt in *plans_dir*. Returns (plans, issues).

    Never raises. A plan that fails to parse is never listed --
    PlanStore.cs:99-104 drops it from Plans entirely, because a broken
    plan offered in the rail selects to zero requirements and scores
    every character Unknown: the same silent-poisoning failure the
    empty-plan diagnostic in plans.parse exists to prevent. Its
    diagnostics still reach the user, carried by its PlanIssue instead.
    """
    issues = []
    try:
        # is_file() because glob("*.txt") matches directories too, and
        # read_text() on one raises IsADirectoryError -- which would
        # become a warning about a file the user never created.
        entries = [p for p in plans_dir.glob("*.txt") if p.is_file()]
    except OSError as exc:
        # A deleted or permission-denied folder costs an empty roster,
        # not a crash. `Open plans folder` reports the real failure.
        return [], [PlanIssue(
            "plans", f"The plans folder could not be read: {exc}", ())]

    # Sorted BEFORE the cap so the same 200 plans appear on every
    # reload, rather than whichever 200 the filesystem enumerated first.
    # Case-insensitive because byte order puts every capitalised name
    # ahead of every lowercase one and scatters related plans.
    entries.sort(key=_sort_key)
    if len(entries) > MAX_PLAN_FILES:
        issues.append(PlanIssue(
            "plans",
            f"Only the first {MAX_PLAN_FILES} of {len(entries)} plan "
            "files were read.", ()))
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
            issues.append(PlanIssue(path.name, reason, ()))
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
            issues.append(PlanIssue(
                path.name,
                "Plan name collides case-insensitively with another "
                "file.", ()))
            continue
        seen_names.add(collision_key)

        # Bounded by SIZE before the content is ever read into memory --
        # PlanStore.cs:92-97, which checks FileInfo.Length before calling
        # AtomicFile.ReadBoundedText. MAX_PLAN_FILE_BYTES bounds bytes on
        # disk; consulting plans.MAX_CONTENT_CHARS (a character count)
        # after path.read_text() has already pulled the whole file into
        # memory is too late to protect against a multi-gigabyte .txt
        # dropped in the folder. Bytes and characters are different
        # units bounding different moments -- this is a cheap pre-filter
        # on disk size, independent of the character cap plans.parse
        # still enforces on what it decodes.
        try:
            size = path.stat().st_size
        except OSError as exc:
            issues.append(PlanIssue(
                path.name, f"Could not read plan: {exc}", ()))
            continue
        if size > MAX_PLAN_FILE_BYTES:
            issues.append(PlanIssue(
                path.name,
                f"Plan exceeds the {MAX_PLAN_FILE_BYTES // 1024} KiB "
                "file limit.", ()))
            continue

        try:
            # utf-8-sig, not utf-8: Notepad writes a BOM by default, and a
            # plain utf-8 decode leaves it as a literal U+FEFF prefixed onto
            # the first line -- which plans.parse then sees as leading junk
            # on whatever that first line is (a comment marker, a skill
            # name), silently corrupting just that one line rather than
            # raising. utf-8-sig strips the BOM when present and is a
            # no-op on files that never had one.
            contents = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            # A .txt Notepad saved as UTF-16, or a binary file renamed.
            # One unreadable file costs its own row, not the folder --
            # the same per-entry tolerance preview/layout.py takes.
            issues.append(PlanIssue(
                path.name, f"Could not read plan: {exc}", ()))
            continue
        result = plans.parse(contents)
        if not result.ok:
            # PlanStore.cs:100-104. Excluded from `found` rather than
            # listed-but-broken: a plan offered for selection that
            # cannot produce a single requirement is the silent-
            # poisoning failure plans.parse's own empty-plan diagnostic
            # exists to prevent, just reached from a different angle.
            issues.append(PlanIssue(
                path.name, "Plan has invalid lines and was not loaded.",
                result.diagnostics))
            continue
        found.append(PlanFile(normalised_name, result.requirements, ()))
    return found, issues


# The skill list is PlanStore.cs:21-35's StarterPlanContents verbatim --
# not re-derived, because these are the exact names known to resolve
# through ESI's /universe/ids/ today. A plausible-looking substitute
# risks an unresolved skill name (EVE has renamed skills before, e.g.
# the old "Targeting" split into Target Management / Long Range
# Targeting), and one unresolved name poisons the whole plan to Unknown
# -- the worst possible first run for a plan we shipped ourselves. Only
# the explanatory header comment is ours; comments are skipped by the
# parser, so it changes nothing the C# original resolves.
_STARTER_PLAN = """\
# Core Ship Skills - a starter plan, safe to edit or delete.
#
# One skill per line: the skill name, a space, then the level as
# I II III IV V or 1 2 3 4 5. Lines starting with # are ignored.
#
CPU Management IV
Power Grid Management IV
Capacitor Management III
Capacitor Systems Operation III
Mechanics IV
Hull Upgrades III
Shield Operation III
Shield Management III
Navigation IV
Afterburner III
Evasive Maneuvering III
Warp Drive Operation II
Long Range Targeting III
Target Management III
"""


def seed_starter_plan(plans_dir: Path) -> bool:
    """Write the starter plan the first time *plans_dir* is created.

    Gated on the directory's EXISTENCE (PlanStore.cs:44's
    `if (Directory.Exists(plansDir)) return`), not on whether it
    currently holds any .txt file: a user who deletes their last plan
    must not get the starter back on the next launch. Keying on "is
    currently empty" instead would make "I deleted it" and "I never had
    one" indistinguishable, and reseed every time the folder empties out.

    Returns False rather than raising on any filesystem failure: a
    read-only or occupied state directory costs the starter plan, not
    the launch, which is the same policy paths.resolve_binary() and
    configure_logging() take with a missing resource.
    """
    try:
        if plans_dir.is_dir():
            return False
        plans_dir.mkdir(parents=True)
        (plans_dir / f"{STARTER_PLAN_NAME}.txt").write_text(
            _STARTER_PLAN, encoding="utf-8")
    except OSError:
        return False
    return True
