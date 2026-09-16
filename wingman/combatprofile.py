"""Frozen Unicode-16 observed names and shared combat limits.

These are log-source labels, not character identity validation or markup parsing.
No host Unicode tables participate: the app also runs on Python 3.11/Unicode 14.
Invalid external inputs return None/False; retention keys require canonical names.
"""

import json
from bisect import bisect_right
from collections.abc import Iterable
from pathlib import Path
from types import MappingProxyType

# The same package-relative layout is used by wheels and PyInstaller's datas.
# A missing/broken resource fails import with its path — never a host fallback.
_profile = json.loads(
    (Path(__file__).with_name("data") / "fleet-combat-v2-profile.json").read_text(
        encoding="utf-8"
    )
)
_limits = dict(_profile["limits"])
_effect_order = tuple(_profile["effect_order"])
_limits.update(
    effect_order=_effect_order,
    effects_per_row=len(_effect_order),
    observations_per_tackle=_limits["named_per_tackle"] + 1,
    named_per_row=sum(kind != "NEUT" for kind in _effect_order)
    * _limits["named_per_tackle"],
)
# One null bucket per kind, one row-activity key per row and one sample key.
_limits["observations_per_row"] = _limits["named_per_row"] + len(_effect_order)
_limits["associations_per_attempt"] = (
    _limits["put_rows"] * (1 + _limits["observations_per_row"]) + 1
)
_limits["association_capacity"] = (
    _limits["activity_ms"] // _limits["signed_interval_ms"] + 1
) * _limits["associations_per_attempt"]
_limits["receiver_capacity"] = (
    _limits["activity_ms"] + _limits["clock_error_ms"] + _limits["request_elapsed_ms"]
) // _limits["signed_interval_ms"] + 1
LIMITS = MappingProxyType(_limits)

_forbidden_ranges = tuple(tuple(pair) for pair in _profile["forbidden_ranges"])
_forbidden_starts = tuple(start for start, _ in _forbidden_ranges)
_trim_characters = "".join(map(chr, _profile["trim_scalars"]))
_decomposition = {
    int(cp): tuple(parts) for cp, parts in _profile["canonical_decomposition"].items()
}
_combining_class = {int(cp): value for cp, value in _profile["combining_class"].items()}
_composition = {
    tuple(map(int, pair.split(","))): cp for pair, cp in _profile["composition"].items()
}
_casefold = {int(cp): tuple(parts) for cp, parts in _profile["full_casefold"].items()}
del _profile, _limits

# UAX #15's algorithmic Hangul constants, not profile-specific combat limits.
_S_BASE, _L_BASE, _V_BASE, _T_BASE = 0xAC00, 0x1100, 0x1161, 0x11A7
_L_COUNT, _V_COUNT, _T_COUNT = 19, 21, 28
_N_COUNT = _V_COUNT * _T_COUNT
_S_COUNT = _L_COUNT * _N_COUNT


def _forbidden(cp: int) -> bool:
    index = bisect_right(_forbidden_starts, cp) - 1
    return index >= 0 and cp <= _forbidden_ranges[index][1]


def _decompose(cp: int, output: list[int]) -> None:
    syllable = cp - _S_BASE
    if 0 <= syllable < _S_COUNT:
        output.extend(
            (_L_BASE + syllable // _N_COUNT, _V_BASE + syllable % _N_COUNT // _T_COUNT)
        )
        if tail := syllable % _T_COUNT:
            output.append(_T_BASE + tail)
    elif parts := _decomposition.get(cp):
        for part in parts:
            _decompose(part, output)
    else:
        output.append(cp)


def _compose(first: int, second: int) -> int | None:
    lead, vowel = first - _L_BASE, second - _V_BASE
    if 0 <= lead < _L_COUNT and 0 <= vowel < _V_COUNT:
        return _S_BASE + (lead * _V_COUNT + vowel) * _T_COUNT
    syllable, tail = first - _S_BASE, second - _T_BASE
    if 0 <= syllable < _S_COUNT and syllable % _T_COUNT == 0 and 0 < tail < _T_COUNT:
        return first + tail
    # The frozen pair table already omits composition exclusions.
    return _composition.get((first, second))


def _nfc(codepoints: Iterable[int]) -> str:
    decomposed: list[int] = []
    for cp in codepoints:
        _decompose(cp, decomposed)
    # Stable canonical ordering: equal classes retain order, and no mark can
    # cross a starter (class zero). Input is bounded before any expansion.
    for index in range(1, len(decomposed)):
        cp = decomposed[index]
        combining = _combining_class.get(cp, 0)
        if combining:
            position = index
            while (
                position > 0
                and _combining_class.get(decomposed[position - 1], 0) > combining
            ):
                decomposed[position] = decomposed[position - 1]
                position -= 1
            decomposed[position] = cp
    if not decomposed:
        return ""
    composed = [decomposed[0]]
    starter = 0
    last_class = _combining_class.get(decomposed[0], 0)
    for cp in decomposed[1:]:
        combining = _combining_class.get(cp, 0)
        composite = (
            _compose(composed[starter], cp)
            if last_class == 0 or last_class < combining
            else None
        )
        if composite is not None:
            composed[starter] = composite
            # A consumed mark does not block a subsequent composition.
        else:
            if combining == 0:
                starter = len(composed)
            composed.append(cp)
            last_class = combining
    return "".join(map(chr, composed))


def normalize_observed_name(value: object) -> str | None:
    """Bound, reject unsafe raw input, trim only Zs, then frozen NFC.

    Internal spaces are neither trimmed nor collapsed (NFC still applies).
    Never truncate a label or coerce a non-string into an observed identity.
    """
    if not isinstance(value, str) or len(value) > LIMITS["source_candidate_scalars"]:
        return None
    if "<" in value or ">" in value or any(_forbidden(ord(char)) for char in value):
        return None
    # Forbidden categories include surrogates, so UTF-8 encoding is now safe.
    if len(value.encode("utf-8")) > LIMITS["source_candidate_utf8"]:
        return None
    normalized = _nfc(map(ord, value.strip(_trim_characters)))
    if not 1 <= len(normalized) <= LIMITS["observed_name_scalars"]:
        return None
    if len(normalized.encode("utf-8")) > LIMITS["observed_name_utf8"]:
        return None
    return normalized


def validate_observed_name(value: object) -> bool:
    """True only for an already canonical, valid observed name on the wire."""
    return isinstance(value, str) and normalize_observed_name(value) == value


def observed_name_key(value: object) -> str | None:
    """Full default casefold then NFC; noncanonical/invalid input returns None.

    Keys are retention identities, not display names. Folding may expand beyond
    the display limits; revalidating or truncating would lose valid identities.
    """
    if not isinstance(value, str) or not validate_observed_name(value):
        return None
    return _nfc(
        part for char in value for part in _casefold.get(ord(char), (ord(char),))
    )
