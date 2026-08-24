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
    got = parse_one("Navigation I\nNavigation2 II\nNavigation3 III\n"
                    "Navigation4 IV\nNavigation5 V\n")
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
    """"#" mid-line is not a comment introducer; a skill named with one
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


def test_an_empty_plan_parses_to_nothing_without_complaint():
    """An empty file is a plan with no requirements, not a broken one --
    the roster shows it Ready for everyone, which is truthful."""
    result = plans.parse("")
    assert result.ok and result.requirements == ()


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
    """Python trap 3. "٥" is ARABIC-INDIC DIGIT FIVE. Its .isdigit()
    is True and int("٥") returns 5, so a naive port silently accepts
    `Navigation ٥` as level V. The guard is
    `token.isascii() and token.isdigit()` -- isascii() is what makes
    isdigit() mean "ASCII 0-9" and nothing wider."""
    assert not plans.parse("Navigation ٥\n").ok


def test_a_whitespace_padded_level_is_rejected():
    """The same NumberStyles.None clause: int(" 1 ") succeeds in Python.
    The line splitter strips before this is reached, so the guard is
    what protects _parse_level() from any future caller that does not."""
    assert plans._parse_level(" 1 ") is None


@pytest.mark.parametrize("token", ["+1", "-1", "1_0", "٥", " 1 ", "١"])
def test_the_level_guard_rejects_every_trap_token(token):
    assert plans._parse_level(token) is None


@pytest.mark.parametrize("token", ["1", "5", "I", "v", "IV"])
def test_the_level_guard_still_accepts_real_levels(token):
    assert plans._parse_level(token) in (1, 4, 5)


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
    assert len(decomposed) == 300          # 2 code points each, un-composed
    got = parse_one(f"{decomposed} V\n")   # 150 once composed
    assert len(got[0].skill_name) == 150


def test_a_control_character_in_a_name_is_rejected():
    """A stray \\x07 or \\x1b comes from a mangled paste or a binary file
    renamed .txt. It cannot be part of a real skill name, and letting it
    through puts an escape sequence into a log line and a bridge
    payload."""
    assert not plans.parse("Navi\x07gation V\n").ok
    assert not plans.parse("Navi\x1bgation V\n").ok


def test_a_tab_inside_a_name_is_rejected():
    """TAB is a control character too. It also cannot survive the
    round trip: rsplit(None, 1) treats it as the separator, so a name
    containing one is already ambiguous before it gets here."""
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
