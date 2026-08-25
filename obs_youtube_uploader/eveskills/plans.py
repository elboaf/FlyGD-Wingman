"""Plan .txt grammar. Pure: text in, requirements and diagnostics out.

Ported from TriffView's SkillPlanParser. Each line is a skill name,
whitespace, then a level as I-V or 1-5. Blank lines and # comments are
skipped, and the split is at the LAST whitespace so interior spaces stay
in the name.

Any diagnostic rejects the whole file. There is deliberately no
partial-success mode: a plan that silently dropped a malformed line
would score a character Ready for a ship it cannot fly, and nothing in
the UI would say so.
"""

import unicodedata
from dataclasses import dataclass

MAX_CONTENT_CHARS = 512 * 1024
MAX_LINES = 5_000
MAX_LINE_CHARS = 512
MAX_REQUIREMENTS = 2_000
MAX_SKILL_NAME_CHARS = 200

_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}


@dataclass(frozen=True)
class Requirement:
    skill_name: str
    level: int


@dataclass(frozen=True)
class Diagnostic:
    line: int  # 1-based, matching the editor the user opens the file in
    message: str


@dataclass(frozen=True)
class ParseResult:
    requirements: tuple
    diagnostics: tuple

    @property
    def ok(self) -> bool:
        return not self.diagnostics


def _parse_level(token: str):
    """Return 1..5, or None when *token* is not a legal level.

    Three Python traps here, none of which exist in the C# source. It
    parses with int.TryParse(token, NumberStyles.None), which rejects
    signs, whitespace, and separators outright:

      * int("+1") and int("-1") both succeed in Python.
      * int(" 1 ") succeeds -- surrounding whitespace is ignored.
      * int("1_0") is 10 -- PEP 515 digit separators.

    And a fourth, from the obvious screen for them: str.isdigit() is
    True for Unicode digits, so "\u0665".isdigit() passes and
    int("\u0665") returns 5. `token.isascii()` is what makes the
    isdigit() check mean "ASCII 0-9" and nothing wider.

    A naive port silently accepts `Navigation +5`, `Navigation 1_0`, and
    `Navigation \u0665`. Every one of those is a typo the user wants told
    about, not reinterpreted.
    """
    roman = _ROMAN.get(token.upper())
    if roman is not None:
        return roman
    if not (token.isascii() and token.isdigit()):
        return None
    value = int(token)
    return value if 1 <= value <= 5 else None


def parse(contents: str) -> ParseResult:
    """Parse plan text into requirements, or into diagnostics only."""
    # Whole-file guards carry line 0, which the UI renders without a
    # line number. They come first so a corrupt or hostile file never
    # gets as far as materialising a multi-million entry line list.
    if not isinstance(contents, str):
        return ParseResult((), (Diagnostic(0, "Plan content is not text."),))
    if len(contents) > MAX_CONTENT_CHARS:
        return ParseResult(
            (), (Diagnostic(0, f"Plan is larger than {MAX_CONTENT_CHARS} characters."),)
        )
    lines = contents.splitlines()
    if len(lines) > MAX_LINES:
        return ParseResult(
            (), (Diagnostic(0, f"Plan has more than {MAX_LINES} lines."),)
        )

    diagnostics = []
    # Insertion-ordered and keyed on the casefolded name: the first
    # spelling wins, later duplicates only ever raise the level, and
    # dict ordering keeps the user's own grouping intact.
    ordered = {}
    for number, raw in enumerate(lines, start=1):
        # Measured on the RAW line, before stripping. The cap bounds the
        # work done per line, and a line padded to a megabyte of spaces
        # is exactly the input it is there to bound.
        if len(raw) > MAX_LINE_CHARS:
            diagnostics.append(
                Diagnostic(number, f"Line is longer than {MAX_LINE_CHARS} characters.")
            )
            continue
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # rsplit(None, 1) splits on the LAST run of whitespace, which is
        # what keeps "Caldari Battlecruiser" whole. Splitting at the
        # first would name the skill "Caldari".
        parts = line.rsplit(None, 1)
        if len(parts) < 2:
            diagnostics.append(
                Diagnostic(number, "Expected a skill name followed by a level.")
            )
            continue
        name, token = parts
        level = _parse_level(token)
        if level is None:
            diagnostics.append(
                Diagnostic(number, f"'{token}' is not a level. Use I-V or 1-5.")
            )
            continue
        # Normalise BEFORE the length cap: decomposed text is longer
        # than its composed form, so capping first rejects names that
        # are perfectly legal once composed.
        name = unicodedata.normalize("NFC", name)
        if len(name) > MAX_SKILL_NAME_CHARS:
            diagnostics.append(
                Diagnostic(
                    number,
                    f"Skill name is longer than {MAX_SKILL_NAME_CHARS} characters.",
                )
            )
            continue
        if any(unicodedata.category(ch) == "Cc" for ch in name):
            # A stray \x07 or \x1b comes from a mangled paste. It cannot
            # be part of a real skill name and must not reach a log line
            # or a bridge payload as an escape sequence.
            diagnostics.append(
                Diagnostic(number, "Skill name contains a control character.")
            )
            continue
        key = name.casefold()
        previous = ordered.get(key)
        if previous is None:
            ordered[key] = Requirement(name, level)
        elif level > previous.level:
            # Keep the first spelling, raise the level. Two lines for one
            # skill mean the stricter one governs.
            ordered[key] = Requirement(previous.skill_name, level)
        # Counted on distinct skills, after folding: a plan repeating one
        # skill three thousand times is one requirement, not an overflow.
        if len(ordered) > MAX_REQUIREMENTS:
            diagnostics.append(
                Diagnostic(
                    number, f"Plan has more than {MAX_REQUIREMENTS} requirements."
                )
            )
            break
    if diagnostics:
        # All or nothing. Returning the good lines beside the complaints
        # is the partial-success mode this parser refuses to have.
        return ParseResult((), tuple(diagnostics))
    if not ordered:
        # A file with no requirements -- empty, or only blank lines and
        # comments -- parses cleanly and produces nothing. Without this,
        # it is a VALID plan with zero requirements: list_plans lists it,
        # the rail shows a 0/N ratio, and compact_status([]) returns
        # Unknown, so every character reads Unknown with nothing anywhere
        # explaining why. This is what turns that silent poisoning into a
        # message naming the file.
        return ParseResult((), (Diagnostic(0, "Plan contains no skill requirements."),))
    return ParseResult(tuple(ordered.values()), ())
