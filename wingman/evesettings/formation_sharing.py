"""Strict, meter-valued probe formation text with no local identity or I/O.

Transport limits belong here, not in the local-file reader: an existing EVE
formation outside these limits must remain editable without becoming shareable.
"""

import json
import unicodedata

from .formations import MAX_PROBES, Formation, Probe, to_payload, validate

AU_METERS = 149_597_870_700
MIN_RANGE_METERS = AU_METERS * 1e-6
MAX_RANGE_METERS = AU_METERS * 65536
MAX_COORDINATE_METERS = 10**16
MAX_BYTES = 64 * 1024
MAX_FORMATIONS = 32
MAX_NAME_CODEPOINTS = 128


def limits_payload() -> dict:
    """The authoritative sharing limits for page controls and feedback."""
    return {
        "max_bytes": MAX_BYTES,
        "max_formations": MAX_FORMATIONS,
        "max_name_codepoints": MAX_NAME_CODEPOINTS,
        "max_probes": MAX_PROBES,
        "au_meters": AU_METERS,
        "min_range_meters": MIN_RANGE_METERS,
        "max_range_meters": MAX_RANGE_METERS,
        "max_coordinate_meters": MAX_COORDINATE_METERS,
    }


def _object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"Repeated JSON field: {key}.")
        out[key] = value
    return out


def _constant(value):
    raise ValueError(f"Invalid JSON number: {value}.")


def _number(value, low, high, label):
    # Compare before conversion: huge ints can overflow float(), and rounding
    # can bring an integer just outside a bound back inside it.
    if type(value) not in (int, float) or not low <= value <= high:
        raise ValueError(
            f"{label}: expected a finite number between {low} and {high} meters."
        )
    return float(value)


def _fields(value, keys, label, *, exact=True):
    if not isinstance(value, dict):
        raise ValueError(f"{label}: expected an object.")
    missing = keys - value.keys()
    if missing:
        raise ValueError(f"{label}: missing fields: {', '.join(sorted(missing))}.")
    if exact and value.keys() - keys:
        raise ValueError(
            f"{label}: unexpected fields; expected only {', '.join(sorted(keys))}."
        )


def _collection(value, maximum, label):
    if not isinstance(value, list):
        raise ValueError(f"{label}: expected a list.")
    if not 1 <= len(value) <= maximum:
        raise ValueError(f"{label}: expected between 1 and {maximum} entries.")


def _name(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label}: name must be text.")
    name = value.strip()
    if not name or len(name) > MAX_NAME_CODEPOINTS:
        raise ValueError(
            f"{label}: name must contain 1 to {MAX_NAME_CODEPOINTS} Unicode code points."
        )
    # Check the original too, so a leading tab or trailing newline is not
    # silently removed and accepted as ordinary whitespace.
    if any(unicodedata.category(ch) == "Cc" for ch in value):
        raise ValueError(f"{label}: name must not contain control characters.")
    try:
        name.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"{label}: name must be valid UTF-8 text.") from error
    return name


def _candidates(items) -> list[Formation]:
    _collection(items, MAX_FORMATIONS, "Formations")
    out = []
    for i, item in enumerate(items, 1):
        label = f"Formation {i}"
        _fields(item, {"name", "probes"}, label)
        name = _name(item["name"], label)
        _collection(item["probes"], MAX_PROBES, f"{label} probes")
        probes = []
        for j, probe in enumerate(item["probes"], 1):
            probe_label = f"{label} ({name!r}), probe {j}"
            _fields(probe, {"x", "y", "z", "range"}, probe_label)
            coordinates = [
                _number(
                    probe[axis],
                    -MAX_COORDINATE_METERS,
                    MAX_COORDINATE_METERS,
                    f"{probe_label} {axis}",
                )
                for axis in ("x", "y", "z")
            ]
            scan_range = _number(
                probe["range"],
                MIN_RANGE_METERS,
                MAX_RANGE_METERS,
                f"{probe_label} range",
            )
            probes.append(Probe(*coordinates, scan_range))
        out.append(Formation(None, name, tuple(probes)))
    # Keep the existing domain's casefold uniqueness and invariants, but only
    # after transport types/bounds are checked without from_payload coercions.
    validate(out)
    return out


def _projection(items: list[dict]) -> list[dict]:
    _collection(items, MAX_FORMATIONS, "Formations")
    out = []
    for i, item in enumerate(items, 1):
        label = f"Formation {i}"
        _fields(item, {"name", "probes"}, label, exact=False)
        ident = item.get("id")
        if isinstance(ident, int) and ident < 0:
            raise ValueError(f"{label}: scratch entries cannot be shared.")
        _collection(item["probes"], MAX_PROBES, f"{label} probes")
        probes = []
        for j, probe in enumerate(item["probes"], 1):
            _fields(probe, {"x", "y", "z", "range"}, f"{label}, probe {j}", exact=False)
            probes.append({key: probe[key] for key in ("x", "y", "z", "range")})
        # Never copy the whole item/probe and delete known metadata: new
        # metadata must be private by default, even if it is not JSON serializable.
        out.append({"name": item["name"], "probes": probes})
    return out


def _check_text_size(text):
    message = f"Shared text exceeds {MAX_BYTES} UTF-8 bytes. Copy fewer formations."
    # Every code point needs at least one byte; reject huge text before
    # allocating an encoded copy, then apply the actual UTF-8 byte ceiling.
    if len(text) > MAX_BYTES:
        raise ValueError(message)
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise ValueError("Shared text must be valid UTF-8.") from error
    if size > MAX_BYTES:
        raise ValueError(message)


def export_text(items: list[dict]) -> str:
    """Export only selected internal payloads; metadata never enters validation."""
    candidates = _candidates(_projection(items))
    text = json.dumps(
        {
            "format": "wingman-preset",
            "version": 1,
            "type": "probe-formations",
            "formations": _projection(to_payload(candidates)),
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    _check_text_size(text)
    return text


def parse_text(text: str) -> list[Formation]:
    """Decode one complete version-1 artifact into new, identity-free formations."""
    if not isinstance(text, str):
        raise ValueError("Shared formation text must be a string.")
    _check_text_size(text)
    try:
        wire = json.loads(text, object_pairs_hook=_object, parse_constant=_constant)
    except (ValueError, RecursionError, OverflowError) as error:
        raise ValueError(f"Invalid formation JSON: {error}") from error
    _fields(wire, {"format", "version", "type", "formations"}, "Preset")
    if wire["format"] != "wingman-preset":
        raise ValueError("Unsupported preset format; expected wingman-preset.")
    if type(wire["version"]) is not int or wire["version"] != 1:
        raise ValueError("Unsupported preset version; expected integer 1.")
    if wire["type"] != "probe-formations":
        raise ValueError("Unsupported preset type; expected probe-formations.")
    return _candidates(wire["formations"])


def prepare_import(
    items: list[dict], existing_names: list[str]
) -> tuple[list[Formation], list[int]]:
    """Revalidate renamed review items and identify, but never resolve, conflicts."""
    _collection(items, MAX_FORMATIONS, "Formations")
    portable = []
    for i, item in enumerate(items, 1):
        label = f"Formation {i}"
        _fields(item, {"id", "name", "probes"}, label)
        if item["id"] is not None:
            raise ValueError(f"{label}: imported id must be null.")
        portable.append({"name": item["name"], "probes": item["probes"]})
    candidates = _candidates(portable)
    if not isinstance(existing_names, list) or any(
        not isinstance(name, str) for name in existing_names
    ):
        raise ValueError("Existing formation names must be a list of text names.")
    # These are draft names, not another artifact. Pre-existing invalid names
    # and any unrelated invalid geometry must not block a valid import.
    names = {name.casefold() for name in existing_names}
    return candidates, [
        i
        for i, candidate in enumerate(candidates)
        if candidate.name.casefold() in names
    ]
