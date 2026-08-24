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
    line: int       # 1-based, matching the editor the user opens the file in
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
    True for Unicode digits, so "٥".isdigit() passes and
    int("٥") returns 5. `token.isascii()` is what makes the
    isdigit() check mean "ASCII 0-9" and nothing wider.

    A naive port silently accepts `Navigation +5`, `Navigation 1_0`, and
    `Navigation ٥`. Every one of those is a typo the user wants told
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
    diagnostics = []
    requirements = []
    for number, raw in enumerate(contents.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # rsplit(None, 1) splits on the LAST run of whitespace, which is
        # what keeps "Caldari Battlecruiser" whole. Splitting at the
        # first would name the skill "Caldari".
        parts = line.rsplit(None, 1)
        if len(parts) < 2:
            diagnostics.append(Diagnostic(
                number, "Expected a skill name followed by a level."))
            continue
        name, token = parts
        level = _parse_level(token)
        if level is None:
            diagnostics.append(Diagnostic(
                number, f"'{token}' is not a level. Use I-V or 1-5."))
            continue
        requirements.append(Requirement(name, level))
    if diagnostics:
        # All or nothing. Returning the good lines beside the complaints
        # is the partial-success mode this parser refuses to have.
        return ParseResult((), tuple(diagnostics))
    return ParseResult(tuple(requirements), ())
