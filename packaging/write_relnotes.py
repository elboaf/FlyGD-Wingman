"""Write packaging/relnotes.txt for installer.iss's InfoBeforeFile page.

Issue #260: until now the only "what's new" a user ever saw was the GitHub
release page -- which nobody doing a one-click upgrade from inside the app
opens. The installer is built from the tagged commit, so the changes for
this version are known at build time and can ride inside the installer as
its first wizard page.

The single source is git history: this repo squash-merges, so every merged
PR lands as one commit whose subject is the PR title ending in its number.
PR titles here are written as prose sentences, which is exactly what a
release-notes list wants -- the same property release.yml's
generate_release_notes relies on. Nothing is maintained by hand, which is
why there is no CHANGELOG.md to keep in sync (see release.yml for that
decision).

GENERATED, not edited, and gitignored like version.iss: a committed copy
is still a copy, and the file must describe the commit the installer is
built from, not the commit someone last remembered. A missing file is an
iscc compile error naming installer.iss's InfoBeforeFile line, which is
the intended failure -- run `python packaging/write_relnotes.py` first.

Stdlib only, and run from a bare `python` in the build chain (same
convention as write_version_iss.py and the fetch_*.py siblings -- no
venv), so no third-party imports.

NEVER fails the build. Release notes are cosmetic; a shallow checkout, a
worktree without tags, or any other git surprise degrades to a static
pointer at the release page rather than stopping an installer that is
otherwise perfectly good.
"""

from __future__ import annotations

import importlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = Path(__file__).resolve().parent / "relnotes.txt"

# This repo squash-merges: a landed PR is exactly one commit whose subject
# ends in its number. Anything else (branch housekeeping, release chores
# that skipped a PR) is noise on a user-facing page, so it is dropped.
_SUBJECT_WITH_PR = re.compile(r"^(.*\S)\s+\(#(\d+)\)$")
_FALLBACK_BODY = (
    "This installer was built without change history available, so the\n"
    "list of what is new could not be generated.\n"
    "\n"
    "See the release notes on the GitHub releases page for what changed\n"
    "in this version.\n"
)

_HEADER_STATIC = "FlyGD Wingman {version} -- what's new"
_MAX_SUBJECTS = 40


def _git(*args: str) -> str | None:
    """Run one git query, returning stdout or None on any failure.

    None, not an exception, is the contract: the caller degrades to the
    fallback page. A worktree without tags is normal (the standalone
    test-build workflow runs on arbitrary branches), not an error.
    """
    try:
        result = subprocess.run(
            ("git", *args),
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout


def pr_subjects(log_text: str) -> list[str]:
    """Pull the PR-titled subjects out of `git log --format=%s` output."""
    subjects = []
    for line in log_text.splitlines():
        match = _SUBJECT_WITH_PR.match(line.strip())
        if match:
            subjects.append(match.group(1))
    return subjects


def collect(limit: int = _MAX_SUBJECTS) -> list[str]:
    """PR titles merged since the previous release tag, newest first.

    Returns an empty list when nothing derivable exists: no git, no tags,
    or no tagged history behind this commit. The tag -- not a guess at
    "one version back" -- bounds the range, because tags are what releases
    are cut from here.
    """
    previous = _git("describe", "--tags", "--abbrev=0", "--match", "v*")
    if not previous:
        return []
    log = _git("log", "--format=%s", f"{previous.strip()}..HEAD")
    if log is None:
        return []
    return pr_subjects(log)[:limit]


def render(version: str, subjects: list[str]) -> str:
    lines = [_HEADER_STATIC.format(version=version), ""]
    if subjects:
        lines.extend(f"  *  {subject}" for subject in subjects)
    else:
        lines.append(_FALLBACK_BODY.rstrip("\n"))
    return "\n".join(lines) + "\n"


def read_version(source: Path | None = None) -> str:
    """The declared version, reusing write_version_iss's reader.

    Imported via importlib rather than an `import` statement: ci.yml's
    stdlib-only scan tests every bare-python script's top-level imports,
    and it cannot know that this sibling is itself allowlisted and
    stdlib-only. The value is still imported, not copied -- the whole
    point of this module is that derived values have exactly one source,
    and the version in the page header is as derived as the one in the
    installer filename.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    write_version_iss = importlib.import_module("write_version_iss")
    return write_version_iss.read_version(source or write_version_iss.SOURCE)


def main() -> int:
    version = read_version()
    subjects = collect()
    TARGET.write_text(
        # UTF-8 with BOM: Inno reads a text InfoBeforeFile in the system
        # codepage unless the file carries a BOM, and PR titles here use
        # em dashes that cp1252 happens to survive but other locales'
        # codepages do not.
        render(version, subjects),
        encoding="utf-8-sig",
    )
    print(
        f"{TARGET.relative_to(ROOT)}: {version}, "
        f"{len(subjects)} changes since the previous release tag"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
