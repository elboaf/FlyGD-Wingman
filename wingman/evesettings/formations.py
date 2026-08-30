"""Probe formations inside a decoded account settings document.

Pure: dict in, dict out, no I/O. The document is the lossless JSON form of
``core_user_*.dat`` (see docs/eve-settings-decode-design.md, "The format").
Units on this interface are meters — the file's own — so nothing here rounds;
the page converts to km and AU for display.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MAX_PROBES = 8  # the launcher holds eight
UI_KEY = "bytes:ui"
FORMATIONS_KEY = "bytes:probescanning.customFormations"
SELECTED_KEY = "bytes:probescanning.selectedFormationID"

# 100 ns intervals since 1601-01-01, which is what EVE stamps on every value.
_EPOCH_DELTA_S = 11_644_473_600


@dataclass(frozen=True)
class Probe:
    x: float
    y: float
    z: float
    range: float


@dataclass(frozen=True)
class Formation:
    id: int | None  # None: not in the file yet; minted on write
    name: str
    probes: tuple[Probe, ...]


def filetime(now: float) -> int:
    return (int(now) + _EPOCH_DELTA_S) * 10_000_000


def _strip_prefix(text: str) -> str:
    # Split once from the left: "utf8:a:b" -> "a:b". The client writes user
    # names as utf8: and its own scratch entry as bytes:; both are read.
    head, sep, rest = text.partition(":")
    return rest if sep else head


def _entries(doc: dict) -> dict:
    # An absent bytes:ui or absent customFormations key is legitimately "no
    # formations" (a file the client has never touched). A *present* value
    # in an unrecognised shape is different: silently treating it as empty
    # would make read_formations report "no formations" with no error, and
    # write_formations would then rebuild the key as {} on the next save,
    # discarding whatever was actually there. Refuse instead.
    ui = doc.get(UI_KEY)
    if not isinstance(ui, dict) or FORMATIONS_KEY not in ui:
        return {}
    value = ui[FORMATIONS_KEY]
    tuple_ = value.get("tuple") if isinstance(value, dict) else None
    if (
        not isinstance(tuple_, list)
        or len(tuple_) != 2
        or not isinstance(tuple_[1], dict)
    ):
        raise ValueError(
            "This file has a customFormations entry Wingman does not understand."
        )
    return tuple_[1]


def _entry_id(key: str) -> int | None:
    try:
        return int(_strip_prefix(key))
    except ValueError:
        return None


def _probe_from(value) -> Probe | None:
    try:
        (pos, rng) = value["tuple"]
        x, y, z = pos["tuple"]
        return Probe(float(x), float(y), float(z), float(rng))
    except (KeyError, TypeError, ValueError):
        return None


def read_formations(doc: dict) -> list[Formation]:
    """User formations, sorted by id.

    Strict on purpose: write_formations rebuilds the whole key from this
    list, so anything skipped here would be deleted on the next save. A
    shape this parser does not recognise refuses the whole file instead,
    and the editor tells the user rather than opening.
    """
    out = []
    for key, value in _entries(doc).items():
        ident = _entry_id(key)
        if ident is None:
            raise ValueError(
                f"This file has a formation entry Wingman does not understand ({key})."
            )
        # Negative ids are client scratch state (-4 is the launched probes);
        # write carries them through byte-for-byte without parsing them.
        if ident < 0:
            continue
        try:
            name, probes = value["tuple"]
        except (KeyError, TypeError, ValueError):
            name = probes = None
        if not isinstance(name, str) or not isinstance(probes, list):
            raise ValueError(
                f"This file has a formation entry Wingman does not understand (id {ident})."
            )
        parsed = tuple(map(_probe_from, probes))
        if any(p is None for p in parsed):
            raise ValueError(
                f"This file has a probe Wingman does not understand (formation id {ident})."
            )
        out.append(Formation(ident, _strip_prefix(name), parsed))
    out.sort(key=lambda f: f.id)
    return out


def validate(formations: list[Formation]) -> None:
    seen = set()
    for f in formations:
        if not f.name.strip():
            raise ValueError("Every formation needs a name.")
        # Not a file-format rule (the client keys on id, not name) but the
        # editor's list is by name, so two "Pinpoint"s are indistinguishable.
        # Recorded in the design doc's format section.
        if f.name.casefold() in seen:
            raise ValueError(f"The name {f.name!r} is used twice.")
        seen.add(f.name.casefold())
        if not f.probes:
            raise ValueError(f"{f.name}: a formation needs at least one probe.")
        if len(f.probes) > MAX_PROBES:
            raise ValueError(
                f"{f.name}: the launcher holds at most {MAX_PROBES} probes."
            )
        for p in f.probes:
            if not all(math.isfinite(v) for v in (p.x, p.y, p.z, p.range)):
                raise ValueError(f"{f.name}: a probe value is not a number.")
            if p.range <= 0:
                raise ValueError(f"{f.name}: a probe's range must be positive.")


def write_formations(doc: dict, formations: list[Formation], *, now: float) -> dict:
    """Return a copy of *doc* with the user formations replaced by *formations*.

    Scratch entries (negative ids) travel through untouched. Ids travel with
    their formation, so reordering the list never moves the client's selected
    formation — the bug the design names in eve-wrench — and new formations
    are minted above every id the file has ever held, scratch ids included.
    Both keys get the same fresh stamp, which is what the client itself does
    when it creates a formation.
    """
    existing = _entries(doc)
    entries: dict = {k: v for k, v in existing.items() if (_entry_id(k) or 0) < 0}
    read_formations(doc)  # refuse to rebuild a key we could not fully read
    taken = [i for i in map(_entry_id, existing) if i is not None]
    taken += [f.id for f in formations if f.id is not None]
    next_id = max(taken, default=-1) + 1
    ids = []
    for f in formations:
        ident = f.id
        if ident is None:
            ident = next_id
            next_id += 1
        ids.append(ident)
        entries[f"int:{ident}"] = {
            "tuple": [
                f"utf8:{f.name}",
                [{"tuple": [{"tuple": [p.x, p.y, p.z]}, p.range]} for p in f.probes],
            ]
        }

    stamp = f"long:{filetime(now)}"
    ui = dict(doc.get(UI_KEY) or {})
    ui[FORMATIONS_KEY] = {"tuple": [stamp, entries]}
    try:
        current = doc[UI_KEY][SELECTED_KEY]["tuple"][1]
    except (KeyError, IndexError, TypeError):
        current = None
    selected = current if current in ids else (ids[0] if ids else None)
    ui[SELECTED_KEY] = {"tuple": [stamp, selected]}
    out = dict(doc)
    out[UI_KEY] = ui
    return out


def from_payload(items) -> list[Formation]:
    if not isinstance(items, list):
        raise ValueError("Expected a list of formations.")
    out = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ValueError("A formation needs a name.")
        ident = item.get("id")
        if ident is not None and (
            isinstance(ident, bool) or not isinstance(ident, int)
        ):
            raise ValueError("A formation id must be a whole number.")
        # Negative ids are client scratch state (e.g. -4 is tempFormation),
        # carried through write_formations untouched. A page-supplied
        # negative id must never reach that path, or a save would overwrite
        # scratch state the client itself owns.
        if isinstance(ident, int) and ident < 0:
            raise ValueError("A formation id cannot be negative.")
        probes = item.get("probes")
        if not isinstance(probes, list):
            raise ValueError("A formation needs a probe list.")
        parsed = []
        for p in probes:
            try:
                parsed.append(
                    Probe(
                        float(p["x"]), float(p["y"]), float(p["z"]), float(p["range"])
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("A probe needs numeric x, y, z and range.") from error
        out.append(Formation(ident, item["name"], tuple(parsed)))
    return out


def to_payload(formations: list[Formation]) -> list[dict]:
    return [
        {
            "id": f.id,
            "name": f.name,
            "probes": [
                {"x": p.x, "y": p.y, "z": p.z, "range": p.range} for p in f.probes
            ],
        }
        for f in formations
    ]
