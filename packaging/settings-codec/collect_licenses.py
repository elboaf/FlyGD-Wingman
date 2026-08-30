# packaging/settings-codec/collect_licenses.py
"""Concatenate every licence the settings codec statically links.

`wingman-settings-codec.exe` is one binary with about twenty crates linked
into it. All of them are MIT or Apache-2.0 (unicode-ident adds Unicode-3.0),
and MIT's condition is that the notice travels WITH the binary -- not that it
exists somewhere in a repository. Shipping only blue-marshal's text, as the
first version of this did, satisfied the condition for one crate out of
eighteen.

The repository's existing shape is one COPYING file per bundled dependency
(AutoHotkey, FFmpeg), with a build-time assertion in
.github/actions/build-installer/action.yml that throws if one is missing.
That shape does not scale to a static link, so the codec gets ONE combined
artefact instead -- packaging/bin/settings-codec-COPYING.txt -- covering
blue-marshal and everything under it. THIRD-PARTY-NOTICES.md points at that
one file, and uploader.spec ships it beside the binaries.

Built from Cargo.lock rather than a hand-kept list: the lock file is what the
`cargo build --locked` in the release actually compiles, so a dependency
added, dropped or bumped upstream cannot leave the notice behind. Reads the
crate sources cargo has already vendored under ~/.cargo/registry/src, so it
must run AFTER `cargo build` (or `cargo fetch`) in the same job.

Fails loudly on anything it cannot account for -- a crate directory it cannot
find, or a crate that ships no licence file at all. A licence collector that
silently skips is worse than none: it produces a file that LOOKS like
compliance.

stdlib only, no venv, the same convention as the packaging/fetch_*.py
scripts: it is invoked with a bare `python` from the release job.
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCK = HERE / "Cargo.lock"
OUT = HERE.parent / "bin" / "settings-codec-COPYING.txt"

# Our own crate. It is in the lock file as the root package and has no
# vendored source directory, and it is not third-party -- Wingman's own
# licence (GPL-3.0-only, LICENSE at the repo root) covers it.
ROOT_CRATE = "wingman-settings-codec"

HEADER = """\
Third-party licences for wingman-settings-codec.exe
===================================================

wingman-settings-codec.exe is a small Rust program bundled with FlyGD
Wingman that reads and writes EVE Online settings files. It is statically
linked, so the crates listed below are compiled INTO that executable and
their licences travel with it. Wingman's own licence (GPL-3.0-only) is in
LICENSE and does not apply to any of them.

Generated from packaging/settings-codec/Cargo.lock by
packaging/settings-codec/collect_licenses.py -- do not edit by hand.

"""


def crate_roots() -> list[Path]:
    """Every vendored-source directory cargo might have used.

    There is normally one, keyed by a hash of the registry URL, but a
    machine that has talked to crates.io under both the git and the sparse
    protocol has two, and the crate can be under either.
    """
    home = Path.home() / ".cargo" / "registry" / "src"
    if not home.is_dir():
        sys.exit(
            f"ERROR: no vendored crate sources at {home}. Run this after "
            "`cargo build` (or `cargo fetch`), not before."
        )
    return sorted(p for p in home.iterdir() if p.is_dir())


def packages(lock_text: str) -> list[tuple[str, str]]:
    """(name, version) for every [[package]] block bar our own."""
    out = []
    for block in lock_text.split("[[package]]")[1:]:
        name = re.search(r'^name = "([^"]+)"', block, re.MULTILINE)
        version = re.search(r'^version = "([^"]+)"', block, re.MULTILINE)
        if not name or not version:
            sys.exit(f"ERROR: a Cargo.lock package block has no name/version:{block}")
        if name.group(1) == ROOT_CRATE:
            continue
        out.append((name.group(1), version.group(1)))
    if not out:
        sys.exit("ERROR: Cargo.lock listed no dependencies at all; refusing to write")
    return sorted(out)


def find_crate(roots: list[Path], name: str, version: str) -> Path:
    for root in roots:
        candidate = root / f"{name}-{version}"
        if candidate.is_dir():
            return candidate
    sys.exit(
        f"ERROR: no vendored source for {name} {version} under "
        f"{', '.join(str(r) for r in roots)}. Run `cargo fetch --locked` first."
    )


def licence_field(crate: Path) -> str:
    """The SPDX expression the crate declares, for the header line.

    Cargo.toml.orig is the author's file; Cargo.toml is the one crates.io
    normalises, and either may carry the field. Not fatal if absent -- the
    licence TEXTS below are the legal artefact; this is a label.
    """
    for name in ("Cargo.toml.orig", "Cargo.toml"):
        path = crate / name
        if not path.is_file():
            continue
        found = re.search(
            r'^license(?:-file)? = "([^"]+)"',
            path.read_text(encoding="utf-8", errors="replace"),
            re.MULTILINE,
        )
        if found:
            return found.group(1)
    return "see the text below"


def licence_files(crate: Path) -> list[Path]:
    # Dual-licensed crates ship LICENSE-MIT *and* LICENSE-APACHE and grant
    # the choice; both are included rather than picking one, because the
    # choice is the recipient's to make, not ours.
    found = sorted(
        p
        for p in crate.iterdir()
        if p.is_file() and p.name.upper().startswith(("LICENSE", "COPYING"))
    )
    if not found:
        sys.exit(
            f"ERROR: {crate.name} ships no LICENSE* or COPYING* file. Its terms "
            "cannot be shipped with the binary, so this build must not proceed "
            "until someone reads that crate's licence and decides what to do."
        )
    return found


def main() -> int:
    if not LOCK.is_file():
        sys.exit(f"ERROR: {LOCK} not found")
    roots = crate_roots()
    parts = [HEADER]
    names = []
    for name, version in packages(LOCK.read_text(encoding="utf-8")):
        crate = find_crate(roots, name, version)
        names.append(f"{name} {version}")
        parts.append("=" * 72)
        parts.append(f"\n{name} {version} -- {licence_field(crate)}\n")
        for path in licence_files(crate):
            parts.append(f"--- {path.name} ---\n")
            parts.append(path.read_text(encoding="utf-8", errors="replace").rstrip())
            parts.append("\n\n")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" so the file is byte-identical whichever OS generates it;
    # the release runs on Windows and this is checked in.
    OUT.write_text("".join(parts), encoding="utf-8", newline="\n")
    print(f"Wrote {OUT} covering {len(names)} crates:")
    for entry in names:
        print(f"  {entry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
