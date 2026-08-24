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
