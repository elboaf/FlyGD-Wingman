"""The plan .txt grammar. Pure text in, requirements out -- runs in CI
on Linux with no filesystem, no network, and no EVE client.

Any diagnostic rejects the whole file. There is no partial-success mode,
because a plan that silently dropped a line would score a character
"Ready" for a ship it cannot fly, and the user has no way to notice.
"""

import pytest

from obs_youtube_uploader.eveskills import plans


def parse_one(text):
    """Parse *text*, assert it was accepted, and return its requirements."""
    result = plans.parse(text)
    assert result.ok, [(d.line, d.message) for d in result.diagnostics]
    return result.requirements


def test_roman_numerals_one_through_five():
    got = parse_one(
        "Navigation I\nNavigation2 II\nNavigation3 III\nNavigation4 IV\nNavigation5 V\n"
    )
    assert [r.level for r in got] == [1, 2, 3, 4, 5]


def test_roman_numerals_are_case_insensitive():
    """Plans are hand-typed and pasted from forums; "navigation iv" is a
    perfectly ordinary way to write a line."""
    assert parse_one("Navigation iv\n")[0].level == 4
    assert parse_one("Navigation Iv\n")[0].level == 4


def test_arabic_digits_one_through_five():
    got = parse_one("Navigation 1\nHull Upgrades 5\n")
    assert [r.level for r in got] == [1, 5]


def test_the_line_splits_at_the_last_whitespace():
    """Splitting at the FIRST whitespace would name this skill "Caldari"
    and score every character Unknown against a skill that exists."""
    got = parse_one("Caldari Battlecruiser V\n")
    assert got[0].skill_name == "Caldari Battlecruiser"
    assert got[0].level == 5


def test_interior_whitespace_runs_survive_in_the_name():
    got = parse_one("Small  Hybrid Turret III\n")
    assert got[0].skill_name == "Small  Hybrid Turret"


def test_blank_lines_and_comments_are_skipped():
    got = parse_one("# Core Ship Skills\n\nNavigation IV\n   \n# trailing\n")
    assert [r.skill_name for r in got] == ["Navigation"]


def test_a_comment_marker_must_start_the_line():
    """ "#" mid-line is not a comment introducer; a skill named with one
    would otherwise be truncated into a name that resolves to nothing."""
    got = parse_one("Sharpshooter #1 III\n")
    assert got[0].skill_name == "Sharpshooter #1"


def test_a_line_with_no_level_is_a_diagnostic():
    result = plans.parse("Navigation\n")
    assert not result.ok
    assert result.diagnostics[0].line == 1


def test_a_level_outside_one_to_five_is_a_diagnostic():
    """EVE skills top out at V. A "6" is a typo, and accepting it would
    make every character permanently Missing with no explanation."""
    assert not plans.parse("Navigation 6\n").ok
    assert not plans.parse("Navigation 0\n").ok


def test_diagnostic_line_numbers_are_one_based():
    """They are rendered straight into the plan-issues disclosure, next
    to a file the user opens in Notepad, which counts from 1."""
    result = plans.parse("Navigation IV\nHull Upgrades nope\n")
    assert [d.line for d in result.diagnostics] == [2]


def test_an_empty_plan_is_a_whole_file_diagnostic():
    """A file yielding no requirements is itself a diagnostic
    (SkillPlanParser.cs:112-114), not a silently-valid plan with zero
    requirements. Without this rule, an empty file lists in list_plans,
    the rail shows a 0/N ratio, and compact_status([]) returns Unknown --
    so every character reads Unknown with nothing explaining why."""
    result = plans.parse("")
    assert not result.ok
    assert result.diagnostics == (
        plans.Diagnostic(0, "Plan contains no skill requirements."),
    )


def test_a_whitespace_only_plan_is_a_whole_file_diagnostic():
    result = plans.parse("   \n\t\n   \n")
    assert not result.ok
    assert result.diagnostics[0].line == 0


def test_a_comments_only_plan_is_a_whole_file_diagnostic():
    """The trickier case: this parses cleanly, line by line, with no
    per-line diagnostic anywhere -- it is the total absence of
    requirements, not any one bad line, that must be reported."""
    result = plans.parse("# Core Ship Skills\n# nothing else here\n")
    assert not result.ok
    assert result.diagnostics[0].line == 0


def test_a_signed_level_is_rejected():
    """Python trap 1, which does not exist in the C#. The source parses
    with int.TryParse(token, NumberStyles.None), and NumberStyles.None
    forbids a leading sign. Python's int("+5") returns 5 and int("-5")
    returns -5, so a naive port accepts `Navigation +5` as level 5 and
    would reject `Navigation -5` only by the 1..5 range check -- an
    accident, not a rule."""
    assert not plans.parse("Navigation +5\n").ok
    assert not plans.parse("Navigation -5\n").ok


def test_an_underscore_separated_level_is_rejected():
    """Python trap 2. int("1_0") is 10 -- PEP 515 digit separators are a
    number format C# has no notion of. The range check catches 1_0, but
    int("_5") raises and int("5_") raises while int("1_0") does not, so
    the behaviour is inconsistent unless the token is screened first.
    `Navigation 1_0` must be a diagnostic, not a silent 10."""
    assert not plans.parse("Navigation 1_0\n").ok


def test_a_unicode_digit_level_is_rejected():
    """Python trap 3. "\u0665" is ARABIC-INDIC DIGIT FIVE. Its .isdigit()
    is True and int("\u0665") returns 5, so a naive port silently accepts
    `Navigation \u0665` as level V. The guard is
    `token.isascii() and token.isdigit()` -- isascii() is what makes
    isdigit() mean "ASCII 0-9" and nothing wider."""
    assert not plans.parse("Navigation \u0665\n").ok


def test_a_whitespace_padded_level_is_rejected():
    """The same NumberStyles.None clause: int(" 1 ") succeeds in Python.
    The line splitter strips before this is reached, so the guard is
    what protects _parse_level() from any future caller that does not."""
    assert plans._parse_level(" 1 ") is None


@pytest.mark.parametrize("token", ["+1", "-1", "1_0", "\u0665", " 1 ", "\u0661"])
def test_the_level_guard_rejects_every_trap_token(token):
    assert plans._parse_level(token) is None


@pytest.mark.parametrize(
    "token,expected",
    [
        ("1", 1),
        ("5", 5),
        ("I", 1),
        ("v", 5),
        ("IV", 4),
    ],
)
def test_the_level_guard_still_accepts_real_levels(token, expected):
    assert plans._parse_level(token) == expected


def test_skill_names_are_nfc_normalised():
    """A name pasted from a browser can arrive decomposed -- "e" plus
    U+0301 rather than U+00E9. Those are different strings, so an
    un-normalised name would miss the skill-id cache and score Unknown
    against a skill that resolves perfectly well when composed."""
    got = parse_one("Café Handling V\n")
    assert got[0].skill_name == "Café Handling"


def test_normalisation_happens_before_the_length_cap():
    """Decomposed text is longer than its composed form, so capping
    first would reject a name that is legal once normalised.

    Built from "é" (LATIN SMALL LETTER E + COMBINING ACUTE ACCENT)
    rather than a literal "é" -- a literal glyph in this source file is
    already precomposed by the editor/toolchain, which would silently
    defeat the point of the test."""
    decomposed = "é" * 150
    assert len(decomposed) == 300  # 2 code points each, un-composed
    got = parse_one(f"{decomposed} V\n")  # 150 once composed
    assert len(got[0].skill_name) == 150


def test_a_control_character_in_a_name_is_rejected():
    """A stray \\x07 or \\x1b comes from a mangled paste or a binary file
    renamed .txt. It cannot be part of a real skill name, and letting it
    through puts an escape sequence into a log line and a bridge
    payload."""
    assert not plans.parse("Navi\x07gation V\n").ok
    assert not plans.parse("Navi\x1bgation V\n").ok


def test_a_tab_inside_a_name_is_rejected():
    """TAB is a control character too. rsplit(None, 1) splits at the LAST
    whitespace run, which here is the space before "V" -- the tab is not
    the separator and survives into the name, where the later
    category(ch) == "Cc" check is what actually rejects it."""
    assert not plans.parse("Navi\tgation V\n").ok


def test_duplicates_fold_case_insensitively_keeping_the_maximum_level():
    """Every name comparison in this subsystem is case-insensitive, and
    the stricter line governs: a plan asking for III and V wants V."""
    got = parse_one("Navigation III\nnavigation V\n")
    assert len(got) == 1
    assert got[0].level == 5


def test_a_lower_duplicate_does_not_lower_the_level():
    got = parse_one("Navigation V\nNAVIGATION I\n")
    assert [(r.skill_name, r.level) for r in got] == [("Navigation", 5)]


def test_the_first_spelling_of_a_duplicate_wins():
    """The name is what the user reads in the expanded row, so keep the
    one they wrote first rather than letting a shouty duplicate rename
    it. The skill-id lookup is case-insensitive either way."""
    got = parse_one("Navigation III\nNAVIGATION V\n")
    assert got[0].skill_name == "Navigation"


def test_requirement_order_follows_first_appearance():
    """The expanded row lists requirements in plan order; re-sorting
    them would scramble a plan the user grouped on purpose."""
    got = parse_one("Hull Upgrades IV\nNavigation III\nHull Upgrades V\n")
    assert [r.skill_name for r in got] == ["Hull Upgrades", "Navigation"]


def test_content_over_512_kib_is_a_whole_file_diagnostic():
    """The cap is checked before splitlines() so a hostile or corrupt
    file cannot make the parser materialise a multi-megabyte list first.
    Whole-file diagnostics carry line 0, which the UI renders without a
    line number."""
    result = plans.parse("A" * (plans.MAX_CONTENT_CHARS + 1))
    assert not result.ok
    assert result.diagnostics[0].line == 0
    assert len(result.diagnostics) == 1


def test_content_exactly_at_the_content_cap_is_accepted():
    """Off-by-one on a cap is the classic way a legal file starts being
    rejected after a refactor.

    Built from many short comment lines plus one real requirement line,
    rather than comment lines alone: a comments-only file has zero
    requirements, which is itself now a whole-file diagnostic (see
    test_a_comments_only_plan_is_a_whole_file_diagnostic above), so an
    all-comment filler would test that rule instead of the content cap.
    A single ~512 KiB line is avoided too -- it would independently trip
    the per-line cap tested separately below."""
    comment_line = "#" + "A" * 510 + "\n"  # 512 raw chars incl. newline
    requirement = "Navigation V"
    last_line = " " * (512 - len(requirement)) + requirement  # 512 chars
    filler = comment_line * 1023 + last_line
    assert len(filler) == plans.MAX_CONTENT_CHARS
    got = parse_one(filler)
    assert [r.skill_name for r in got] == ["Navigation"]


def test_more_than_5000_lines_is_a_whole_file_diagnostic():
    result = plans.parse("Navigation I\n" * (plans.MAX_LINES + 1))
    assert not result.ok
    assert result.diagnostics[0].line == 0


def test_a_line_over_512_characters_is_a_diagnostic():
    """Measured on the RAW line, before stripping: the cap exists to
    bound work per line, and a line padded to a megabyte of spaces is
    exactly the input it is bounding."""
    result = plans.parse("N" * plans.MAX_LINE_CHARS + " V\n")
    assert not result.ok
    assert result.diagnostics[0].line == 1


def test_a_line_exactly_at_the_line_cap_is_accepted():
    """Padded with LEADING whitespace, which strip() discards before the
    name is measured: a name long enough to fill the raw-line cap on
    its own would independently trip the 200-character name cap tested
    separately above, and this test would stop exercising the line cap
    at all."""
    name = "N" * (plans.MAX_SKILL_NAME_CHARS - 1)  # 199, under the name cap
    suffix = " V"
    pad = plans.MAX_LINE_CHARS - len(name) - len(suffix)
    line = " " * pad + name + suffix
    assert len(line) == plans.MAX_LINE_CHARS
    assert plans.parse(line).ok


def test_more_than_2000_requirements_is_a_diagnostic():
    text = "".join(f"Skill{n} I\n" for n in range(plans.MAX_REQUIREMENTS + 1))
    result = plans.parse(text)
    assert not result.ok
    assert any("2000" in d.message for d in result.diagnostics)


def test_exactly_2000_requirements_is_accepted():
    text = "".join(f"Skill{n} I\n" for n in range(plans.MAX_REQUIREMENTS))
    assert len(parse_one(text)) == plans.MAX_REQUIREMENTS


def test_the_requirement_cap_counts_distinct_skills_not_lines():
    """Duplicates fold before the count, so a plan that repeats one
    skill 3000 times is one requirement, not an overflow."""
    assert len(parse_one("Navigation I\n" * 3000)) == 1


def test_a_skill_name_over_200_characters_is_a_diagnostic():
    result = plans.parse("N" * (plans.MAX_SKILL_NAME_CHARS + 1) + " V\n")
    assert not result.ok
    assert result.diagnostics[0].line == 1


def test_one_bad_line_rejects_every_good_line_with_it():
    """The all-or-nothing rule, stated as its own test because it is the
    single behaviour most likely to be "helpfully" relaxed later. A plan
    the user believes has ten requirements must never silently evaluate
    with nine."""
    result = plans.parse("Navigation IV\nHull Upgrades nope\nMechanics V\n")
    assert not result.ok
    assert result.requirements == ()


def test_every_bad_line_is_reported_not_just_the_first():
    """Fixing a plan one diagnostic per save-and-reload cycle is why
    parsing continues past the first complaint."""
    result = plans.parse("A nope\nB 9\nC \u0665\n")
    assert [d.line for d in result.diagnostics] == [1, 2, 3]


def test_non_text_content_is_a_whole_file_diagnostic():
    """list_plans() reads bytes off disk and decodes them, so `contents`
    should always be str -- but parse() is also fed from the clipboard
    import path in a deferred slice, and returning a diagnostic beats
    raising AttributeError into the bridge thread."""
    result = plans.parse(None)
    assert not result.ok and result.diagnostics[0].line == 0
