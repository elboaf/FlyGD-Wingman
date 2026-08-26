"""The plans folder: listing, reading, and the name rules.

Filesystem-only -- tmp_path, no network, no EVE client. The name rules
are Windows' rules even when the suite runs on Linux, because the
released application is Windows-only and a name accepted here would fail
at the write.
"""

import pytest

from wingman.eveskills import planstore

# ---------------------------------------------------------------------------
# Cycle A -- name validation
# ---------------------------------------------------------------------------


def test_an_ordinary_name_is_valid():
    assert planstore.validate_plan_name("Core Ship Skills") == ""


def test_an_empty_or_blank_name_is_rejected():
    assert planstore.validate_plan_name("") != ""
    assert planstore.validate_plan_name("   ") != ""


def test_leading_or_trailing_whitespace_is_rejected():
    """Rejected rather than silently trimmed: the name is the identity
    the selected_plan_name field stores, and trimming here would make
    the stored name and the typed name differ."""
    assert planstore.validate_plan_name(" Core") != ""
    assert planstore.validate_plan_name("Core ") != ""


def test_a_name_over_120_characters_is_rejected():
    assert planstore.validate_plan_name("N" * 120) == ""
    assert planstore.validate_plan_name("N" * 121) != ""


@pytest.mark.parametrize(
    "bad", ["a<b", "a>b", "a:b", 'a"b', "a/b", "a\\b", "a|b", "a?b", "a*b"]
)
def test_path_invalid_characters_are_rejected(bad):
    """Windows refuses all nine outright. `/` and `\\` are also the
    traversal primitives, so this check is doing two jobs."""
    assert planstore.validate_plan_name(bad) != ""


def test_a_control_character_is_rejected():
    assert planstore.validate_plan_name("Core\x00Ship") != ""
    assert planstore.validate_plan_name("Core\x1bShip") != ""


def test_dot_dot_is_rejected():
    """ ".." is not in the invalid-character set -- there is no dot in it
    -- and ".." is a perfectly legal filename fragment right up until it
    is joined to a path. `plans_dir / ".."` escapes the folder, and the
    plan name arrives from the bridge, which is to say from the page."""
    assert planstore.validate_plan_name("..") != ""
    assert planstore.validate_plan_name("Core..Ship") != ""
    assert planstore.validate_plan_name("../secrets") != ""


def test_a_single_dot_inside_a_name_is_allowed():
    """v1.2 is a name a user will reasonably type. Only the doubled dot
    is a traversal primitive."""
    assert planstore.validate_plan_name("Rifter v1.2") == ""


def test_a_trailing_dot_is_rejected():
    """Windows silently strips a trailing dot when creating the file, so
    "Core." becomes "Core" on disk and the name the user selected no
    longer matches any file. The failure is a plan that vanishes on
    reload, which reads as data loss."""
    assert planstore.validate_plan_name("Core.") != ""


@pytest.mark.parametrize(
    "reserved", ["CON", "PRN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9"]
)
def test_reserved_windows_device_names_are_rejected(reserved):
    """These are device names, not files. CreateFile on CON.txt opens the
    console; the write appears to succeed and nothing lands on disk."""
    assert planstore.validate_plan_name(reserved) != ""
    assert planstore.validate_plan_name(reserved.lower()) != ""


def test_the_reserved_check_looks_at_the_stem_before_the_first_dot():
    """Windows applies the device rule to the base name, so "NUL.txt"
    and even "NUL.plan.txt" are the device -- the reserved-ness is not
    escaped by adding an extension."""
    assert planstore.validate_plan_name("NUL.plan") != ""


def test_a_name_merely_starting_with_a_device_name_is_fine():
    """ "CONVOY" is not CON. Matching by prefix rather than by the whole
    stem would reject ordinary names."""
    assert planstore.validate_plan_name("CONVOY") == ""
    assert planstore.validate_plan_name("COM10") == ""


def test_a_non_string_name_is_rejected_rather_than_raising():
    """The name crosses the bridge from JavaScript, so its type is not
    guaranteed. A TypeError here would surface on the bridge thread."""
    assert planstore.validate_plan_name(None) != ""
    assert planstore.validate_plan_name(5) != ""


# ---------------------------------------------------------------------------
# Cycle B -- listing the folder
# ---------------------------------------------------------------------------


def write_plan(folder, stem, body="Navigation IV\n"):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stem}.txt"
    path.write_text(body, encoding="utf-8")
    return path


class _NamedProxy:
    """A Path-like directory entry with a chosen *name*, whose file
    operations forward to a different, real file (or to nothing, when
    the stem is expected to be rejected before any file op runs).

    Stands in for a filename that cannot exist as its own real file on
    every platform this suite runs on: one that collides
    case-insensitively with a real file already on disk (Windows'
    filesystem is case-insensitive -- writing "rifter.txt" next to an
    existing "Rifter.txt" just overwrites it, so two case-variant stems
    can never both be real files there), or one containing a character
    Windows refuses at the write outright (a colon).
    """

    def __init__(self, name, backing=None):
        self.name = name
        self.stem = name.removesuffix(".txt")
        self._backing = backing

    def is_file(self):
        return True

    def stat(self):
        assert self._backing is not None, (
            "stat() on a proxy expected to be rejected before any file op"
        )
        return self._backing.stat()

    def read_text(self, encoding=None):
        return self._backing.read_text(encoding=encoding)


class FixedEntries:
    """A plans folder whose glob() returns exactly the given entries, in
    the given order, instead of enumerating real files. Also pins
    enumeration order for a test that must not depend on the
    filesystem's own -- the defect this guards was invisible to a test
    that merely created two files and asserted a winner: the machine it
    was written on enumerated the capitalised stem first and passed,
    with and without the fix, while CI enumerated the other way and
    failed.

    entries may include _NamedProxy stand-ins for a directory entry that
    cannot exist as its own real file on every platform this suite runs
    on.
    """

    def __init__(self, entries):
        self._entries = entries

    def glob(self, pattern):
        # Coupled to the production call the way ReversedGlob (which this
        # replaced) was, via a real folder.glob(pattern) -- so a change to
        # list_plans's glob pattern, a second glob, or a move to iterdir()
        # fails loudly here instead of these tests quietly testing nothing.
        assert pattern == "*.txt", pattern
        return list(self._entries)


def test_a_missing_folder_lists_nothing_without_raising(tmp_path):
    """The folder is created on first launch, but a user can delete it
    while the app is running. That costs an empty roster, not a crash."""
    found, issues = planstore.list_plans(tmp_path / "gone")
    assert found == [] and issues == []


def test_each_txt_file_becomes_a_plan_named_by_its_stem(tmp_path):
    write_plan(tmp_path, "Core Ship Skills")
    found, issues = planstore.list_plans(tmp_path)
    assert [p.name for p in found] == ["Core Ship Skills"]
    assert issues == []


def test_the_contents_are_parsed(tmp_path):
    write_plan(tmp_path, "Rifter", "Navigation IV\nMechanics III\n")
    found, _ = planstore.list_plans(tmp_path)
    assert found[0].ok
    assert [(r.skill_name, r.level) for r in found[0].requirements] == [
        ("Navigation", 4),
        ("Mechanics", 3),
    ]


def test_a_plan_that_fails_to_parse_is_excluded_and_reported_as_an_issue(
    tmp_path,
):
    """PlanStore.cs:99-104 drops a plan that fails to parse from Plans
    entirely -- it becomes an issue only, never selectable. Listing it
    anyway would let a user select a plan that scores every character
    Unknown, the same silent-poisoning failure plans.parse's own
    empty-plan diagnostic exists to prevent."""
    write_plan(tmp_path, "Broken", "Navigation nope\n")
    found, issues = planstore.list_plans(tmp_path)
    assert found == []
    assert len(issues) == 1
    assert issues[0].file_name == "Broken.txt"
    assert issues[0].message == "Plan has invalid lines and was not loaded."
    assert issues[0].diagnostics[0].line == 1


def test_non_txt_files_are_ignored(tmp_path):
    write_plan(tmp_path, "Real")
    (tmp_path / "notes.md").write_text("Navigation IV\n", encoding="utf-8")
    (tmp_path / "Old.txt.bak").write_text("Navigation IV\n", encoding="utf-8")
    found, _ = planstore.list_plans(tmp_path)
    assert [p.name for p in found] == ["Real"]


def test_a_directory_named_like_a_plan_is_ignored(tmp_path):
    """glob("*.txt") matches directories too, and read_text() on one
    raises IsADirectoryError -- which would become a warning about a
    file the user never created."""
    (tmp_path / "Folder.txt").mkdir(parents=True)
    write_plan(tmp_path, "Real")
    found, issues = planstore.list_plans(tmp_path)
    assert [p.name for p in found] == ["Real"]
    assert issues == []


def test_plans_are_sorted_case_insensitively(tmp_path):
    """Byte order puts every capitalised name before every lowercase
    one, which scatters "Rifter" and "rifter alt" across the rail."""
    for stem in ("zeta", "Alpha", "beta"):
        write_plan(tmp_path, stem)
    found, _ = planstore.list_plans(tmp_path)
    assert [p.name for p in found] == ["Alpha", "beta", "zeta"]


def test_an_undecodable_file_warns_and_does_not_stop_the_others(tmp_path):
    """A .txt saved as UTF-16 by Notepad, or a binary file renamed. One
    unreadable file costs its own row, not the folder -- the same
    per-entry tolerance preview/layout.py takes."""
    write_plan(tmp_path, "Good")
    (tmp_path / "Bad.txt").write_bytes(b"\xff\xfe\x00\x00Navigation")
    found, issues = planstore.list_plans(tmp_path)
    assert [p.name for p in found] == ["Good"]
    assert len(issues) == 1 and issues[0].file_name == "Bad.txt"


def test_a_bom_before_a_comment_line_does_not_corrupt_it(tmp_path):
    """Notepad writes a UTF-8 BOM by default. A plain utf-8 decode leaves
    it as a literal U+FEFF glued onto the first line -- here a comment
    marker, which would then no longer be recognised as one."""
    (tmp_path / "Commented.txt").write_bytes(
        "# a note\nNavigation IV\n".encode("utf-8-sig")
    )
    found, issues = planstore.list_plans(tmp_path)
    assert issues == []
    assert [(r.skill_name, r.level) for r in found[0].requirements] == [
        ("Navigation", 4)
    ]


def test_a_bom_before_the_first_skill_name_does_not_corrupt_it(tmp_path):
    """Same BOM hazard, but landing directly on a skill name rather than
    a comment -- the more common case, since most plans have no leading
    comment line at all."""
    (tmp_path / "Rifter.txt").write_bytes(
        "Navigation IV\nMechanics III\n".encode("utf-8-sig")
    )
    found, issues = planstore.list_plans(tmp_path)
    assert issues == []
    assert [(r.skill_name, r.level) for r in found[0].requirements] == [
        ("Navigation", 4),
        ("Mechanics", 3),
    ]


def test_at_most_200_files_are_read(tmp_path):
    """The cap bounds the work one `Reload plans` click can do. It warns
    rather than failing, because the plans the user can see still work."""
    for n in range(planstore.MAX_PLAN_FILES + 5):
        write_plan(tmp_path, f"Plan{n:04d}")
    found, issues = planstore.list_plans(tmp_path)
    assert len(found) == planstore.MAX_PLAN_FILES
    assert len(issues) == 1 and "200" in issues[0].message


def test_the_cap_keeps_the_first_files_in_sort_order(tmp_path):
    """Truncating after the sort rather than before means the same 200
    plans appear on every reload, instead of whichever 200 the
    filesystem happened to enumerate first."""
    for n in range(planstore.MAX_PLAN_FILES + 5):
        write_plan(tmp_path, f"Plan{n:04d}")
    found, _ = planstore.list_plans(tmp_path)
    assert found[0].name == "Plan0000"
    assert found[-1].name == f"Plan{planstore.MAX_PLAN_FILES - 1:04d}"


# --- Mandatory correction 1: each stem is run through validate_plan_name ---


def test_a_file_whose_stem_fails_validation_is_skipped_with_an_issue(tmp_path):
    """PlanStore.cs:81-85 -- a stem is validated before it is trusted as
    a plan identity. Without this, "CON.txt" -- a Windows device name,
    not a file -- would be handed to the parser as an ordinary plan."""
    write_plan(tmp_path, "CON")
    write_plan(tmp_path, "Real")
    found, issues = planstore.list_plans(tmp_path)
    assert [p.name for p in found] == ["Real"]
    assert len(issues) == 1
    assert issues[0].file_name == "CON.txt"
    assert "reserved" in issues[0].message.lower()
    assert issues[0].diagnostics == ()


def test_a_stem_with_a_windows_invalid_character_is_skipped(tmp_path):
    """A colon is a legal filename byte on Linux, which is exactly why
    this must be caught here rather than assumed away by the OS: the
    released application is Windows-only, and this stem would never
    reach disk there in the first place -- Windows refuses to create
    such a file at all, so this fakes the directory entry instead of
    writing it. Same validator, same path as a user-typed name
    (PlanStore.cs:81-85)."""
    real = write_plan(tmp_path, "Real")
    found, issues = planstore.list_plans(
        FixedEntries([_NamedProxy("Bad:Name.txt"), real])
    )
    assert [p.name for p in found] == ["Real"]
    assert len(issues) == 1 and issues[0].file_name == "Bad:Name.txt"


# --- Mandatory correction 2: reject stems colliding case-insensitively ---


def test_a_case_differing_pair_of_stems_collides(tmp_path):
    """PlanStore.cs:86-90 -- the seenNames set is case-insensitive.
    Without this, "Rifter.txt" and "rifter.txt" both load and silently
    shadow each other in the rail: whichever the UI picks last wins,
    invisibly, on every reload. The pair is faked rather than written
    as two real files: on Windows the filesystem is case-insensitive,
    so writing "rifter.txt" once "Rifter.txt" already exists just
    overwrites that same file."""
    rifter = write_plan(tmp_path, "Rifter")
    found, issues = planstore.list_plans(
        FixedEntries([rifter, _NamedProxy("rifter.txt", backing=rifter)])
    )
    assert [p.name for p in found] == ["Rifter"]
    assert len(issues) == 1
    assert issues[0].file_name == "rifter.txt"
    assert issues[0].message == (
        "Plan name collides case-insensitively with another file."
    )


def test_the_surviving_stem_does_not_depend_on_enumeration_order(tmp_path):
    """The collision is resolved positionally -- first entry wins -- so
    the sort ahead of it must be a TOTAL order. Case-folding alone is
    not: both stems fold to the same key and Python's sort is stable, so
    the winner falls through to the filesystem. Both orders must name
    the same survivor."""
    rifter = write_plan(tmp_path, "Rifter")
    proxy = _NamedProxy("rifter.txt", backing=rifter)
    for entries in ([rifter, proxy], [proxy, rifter]):
        found, issues = planstore.list_plans(FixedEntries(entries))
        assert [p.name for p in found] == ["Rifter"], entries
        assert [i.file_name for i in issues] == ["rifter.txt"], entries


def test_the_cap_drops_the_same_plan_whatever_the_enumeration_order(tmp_path):
    """The cap slices the sorted list, so a tie at the boundary decides
    which plan is dropped. With a non-total sort that choice was the
    filesystem's, and `Only the first N of M` would name a different
    casualty per machine while reading as deterministic."""
    alpha = write_plan(tmp_path, "Alpha")
    alpha_lower = _NamedProxy("alpha.txt", backing=alpha)
    plans_ = [
        write_plan(tmp_path, f"Plan{n:03d}")
        for n in range(planstore.MAX_PLAN_FILES - 1)
    ]
    entries = [alpha, alpha_lower, *plans_]

    for order in (entries, list(reversed(entries))):
        found, issues = planstore.list_plans(FixedEntries(order))
        kept = [p.name for p in found]
        assert "Alpha" in kept and "alpha" not in kept, order
        assert any(
            i.file_name == "plans" and "Only the first" in i.message for i in issues
        ), order


def test_an_nfc_vs_nfd_pair_of_stems_collides(tmp_path):
    """Two byte-distinct filenames that normalise to the same NFC text
    (e cedilla as one code point vs. e + combining acute) are the same
    plan identity once validate_plan_name's NFC pass runs. Comparing raw
    bytes would miss this collision entirely."""
    nfc = "Caf\u00e9"  # U+00E9 LATIN SMALL LETTER E WITH ACUTE
    nfd = "Cafe\u0301"  # e + U+0301 COMBINING ACUTE ACCENT
    assert nfc != nfd  # distinct code points, or this test
    # proves nothing
    write_plan(tmp_path, nfc)
    write_plan(tmp_path, nfd)
    found, issues = planstore.list_plans(tmp_path)
    assert len(found) == 1
    assert len(issues) == 1
    assert "collides case-insensitively" in issues[0].message


# --- Mandatory correction 3: bound the read by file size before reading ---


def test_an_oversized_file_is_rejected_by_size_before_its_contents_are_read(
    tmp_path,
):
    """PlanStore.cs:92-97 checks FileInfo.Length against the 512 KiB cap
    before calling AtomicFile.ReadBoundedText. plans.parse's own
    MAX_CONTENT_CHARS cap only runs after read_text() has already loaded
    the whole file, so an unconditional read_text() would pull a
    multi-gigabyte file fully into memory before anything rejects it --
    this test only proves the *outcome* (skipped, warned, others still
    load), not that the read was actually skipped; that guarantee is
    structural, in the code path, not in what a unit test can observe."""
    write_plan(tmp_path, "Good")
    oversized = tmp_path / "Huge.txt"
    oversized.write_bytes(b"x" * (planstore.MAX_PLAN_FILE_BYTES + 1))
    found, issues = planstore.list_plans(tmp_path)
    assert [p.name for p in found] == ["Good"]
    assert len(issues) == 1
    assert issues[0].file_name == "Huge.txt"
    assert "512" in issues[0].message


# ---------------------------------------------------------------------------
# Cycle C -- the starter plan
# ---------------------------------------------------------------------------


def test_the_starter_plan_is_written_into_an_empty_folder(tmp_path):
    folder = tmp_path / "skill_plans"
    assert planstore.seed_starter_plan(folder) is True
    assert (folder / "Core Ship Skills.txt").is_file()


def test_the_starter_plan_creates_the_folder(tmp_path):
    """First launch has no state directory tree at all, and seeding is
    what makes `Open plans folder` open something rather than fail."""
    folder = tmp_path / "deep" / "skill_plans"
    assert planstore.seed_starter_plan(folder) is True
    assert folder.is_dir()


def test_the_starter_plan_parses_cleanly(tmp_path):
    """A seeded plan with a diagnostic would greet every new user with a
    plan-issues disclosure about a file they did not write."""
    folder = tmp_path / "skill_plans"
    planstore.seed_starter_plan(folder)
    found, issues = planstore.list_plans(folder)
    assert issues == []
    assert len(found) == 1 and found[0].ok
    assert found[0].requirements


def test_seeding_is_skipped_when_the_folder_already_exists(tmp_path):
    """Gated on the directory's EXISTENCE (PlanStore.cs:44), checked
    once at creation -- not on "does it currently hold a .txt". A
    pre-existing folder with the user's own plan in it must not also
    get the starter dropped into it."""
    folder = tmp_path / "skill_plans"
    write_plan(folder, "My Own Plan")
    assert planstore.seed_starter_plan(folder) is False
    assert not (folder / "Core Ship Skills.txt").exists()


def test_seeding_is_skipped_once_the_folder_exists_even_if_emptied(tmp_path):
    """The divergence this corrects: gating on "the folder currently
    holds no .txt" (rather than on its existence) would silently
    resurrect the starter plan the moment a user deletes their last
    plan file, making "I deleted it" indistinguishable from "I never
    had one". PlanStore.cs:44 seeds once, at creation, and never again."""
    folder = tmp_path / "skill_plans"
    folder.mkdir()
    assert planstore.seed_starter_plan(folder) is False
    assert not (folder / "Core Ship Skills.txt").exists()


def test_seeding_twice_writes_once(tmp_path):
    folder = tmp_path / "skill_plans"
    assert planstore.seed_starter_plan(folder) is True
    (folder / "Core Ship Skills.txt").write_text("Mechanics V\n", encoding="utf-8")
    assert planstore.seed_starter_plan(folder) is False
    assert (folder / "Core Ship Skills.txt").read_text(
        encoding="utf-8"
    ) == "Mechanics V\n"


def test_seeding_into_an_unwritable_location_returns_false(tmp_path):
    """A read-only or occupied state directory costs the starter plan,
    not the launch -- the same policy resolve_binary() and
    configure_logging() take with a missing resource."""
    blocker = tmp_path / "skill_plans"
    blocker.write_text("not a directory", encoding="utf-8")
    assert planstore.seed_starter_plan(blocker) is False


def test_the_starter_plan_name_passes_validation():
    """It is written by us and selected by name like any other, so it
    has to satisfy the same rules a user-typed name does."""
    assert planstore.validate_plan_name(planstore.STARTER_PLAN_NAME) == ""
