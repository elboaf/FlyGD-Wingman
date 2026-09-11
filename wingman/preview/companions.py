"""Immutable companion authority. Native identities never cross persistence/UI."""

import ntpath
from collections import Counter
from dataclasses import asdict, dataclass, replace
from uuid import UUID

from .crops import (
    CropSource,
    normalized_fractions,
    source_from_pixels,
    source_to_pixels,
)
from .layout import Rect
from .runtime import SelectionLease

MAX_ENABLED = 8
MAX_DEFINITIONS = 32
MAX_SOURCES = 512
LABEL_MAX_CHARS = 80
TITLE_MAX_CHARS = 512
WINDOW_CLASS_MAX_CHARS = 256
EXECUTABLE_PATH_MAX_CHARS = 32768
SOURCE_TTL_SECONDS = 60.0


@dataclass(frozen=True)
class SourceDescriptor:
    executable_path: str
    executable_name: str
    window_class: str
    title_hint: str
    title_mode: str
    last_title: str


@dataclass(frozen=True)
class SourceBinding:
    hwnd: int
    pid: int
    process_created: int
    executable_path: str
    window_class: str
    title: str
    client_size: tuple[int, int]


@dataclass(frozen=True)
class CompanionRegion:
    x: float
    y: float
    w: float
    h: float
    original_client_w: int
    original_client_h: int


@dataclass(frozen=True)
class CompanionDefinition:
    version: int
    id: str
    label: str
    enabled: bool
    mode: str
    source: SourceDescriptor
    window: Rect
    region: CompanionRegion | None


@dataclass(frozen=True)
class CompanionToken:
    operation_id: int
    id: str
    pump_epoch: int
    family_epoch: int
    generation: int
    selection_lease: SelectionLease | None


@dataclass(frozen=True)
class PickerRequest:
    binding: SourceBinding
    caption: str


@dataclass(frozen=True)
class RegionSelection:
    binding: SourceBinding
    source_size: tuple[int, int]
    region: CompanionRegion


@dataclass(frozen=True)
class PreparedCompanion:
    binding: SourceBinding
    source_size: tuple[int, int]
    window: Rect
    region: CompanionRegion | None


@dataclass(frozen=True)
class GeometryDelta:
    id: str
    generation: int
    binding_revision: int
    sequence: int
    rect: Rect


@dataclass(frozen=True)
class CompanionSelection:
    """Committed session-only source choice; never candidate epoch authority."""

    generation: int
    binding: SourceBinding


@dataclass(frozen=True)
class CompanionSpec:
    definition: CompanionDefinition
    generation: int
    binding_revision: int
    selection: CompanionSelection | None = None


@dataclass(frozen=True)
class CompanionCommand:
    kind: str
    token: CompanionToken | None
    payload: object


@dataclass(frozen=True)
class CompanionEvent:
    kind: str
    token: CompanionToken | None
    payload: object


def bounded_text(value: object, limit: int, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or not value.isprintable()
    ):
        raise ValueError(f"{name} must contain 1-{limit} printable characters")
    return value


def normalize_path(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(path))


def validate_descriptor(raw: object) -> SourceDescriptor:
    if not isinstance(raw, dict):
        raise ValueError("Choose a source window")
    try:
        path = bounded_text(
            raw["executable_path"], EXECUTABLE_PATH_MAX_CHARS, "Application path"
        )
        if not ntpath.isabs(path) or not ntpath.splitdrive(path)[0]:
            raise ValueError("Application path must be absolute")
        path = bounded_text(
            normalize_path(path), EXECUTABLE_PATH_MAX_CHARS, "Application path"
        )
        canonical_name = bounded_text(
            ntpath.basename(path), WINDOW_CLASS_MAX_CHARS, "Application name"
        )
        name = bounded_text(
            raw["executable_name"], WINDOW_CLASS_MAX_CHARS, "Application name"
        )
        if name.casefold() != canonical_name.casefold():
            raise ValueError("Application name does not match its path")
        window_class = bounded_text(
            raw["window_class"], WINDOW_CLASS_MAX_CHARS, "Window class"
        )
        hint = bounded_text(raw["title_hint"], TITLE_MAX_CHARS, "Title hint")
        last = bounded_text(raw["last_title"], TITLE_MAX_CHARS, "Window title")
        mode = raw["title_mode"]
        if mode not in ("exact", "contains"):
            raise ValueError("Choose exact or contains title matching")
    except KeyError as exc:
        raise ValueError("Incomplete source descriptor") from exc
    return SourceDescriptor(path, canonical_name, window_class, hint, mode, last)


def valid_rect(rect: Rect) -> bool:
    return (
        isinstance(rect, Rect)
        and all(type(v) is int and -(2**31) < v < 2**31 for v in rect)
        and rect.w > 0
        and rect.h > 0
    )


def valid_id(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 32:
        return False
    try:
        parsed = UUID(hex=value)
    except ValueError:
        return False
    return parsed.version == 4 and parsed.hex == value


def _region(raw: object) -> CompanionRegion:
    if not isinstance(raw, dict):
        raise ValueError("Select a region")
    try:
        fractions = normalized_fractions(raw["x"], raw["y"], raw["w"], raw["h"])
        size = raw["original_client_w"], raw["original_client_h"]
    except KeyError as exc:
        raise ValueError("Incomplete region") from exc
    # Source client dimensions must fit the signed Win32 RECT/DWM coordinate ABI.
    if any(type(v) is not int or not 0 < v < 2**31 for v in size):
        raise ValueError("Invalid original source dimensions")
    region = CompanionRegion(*fractions, *size)
    if region_to_pixels(region, size) is None:
        raise ValueError("Region is too small")
    return region


def validate_definitions(raw: object) -> tuple[CompanionDefinition, ...]:
    if not isinstance(raw, (list, tuple)):
        return ()
    counts = Counter(
        item.get("id")
        for item in raw
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    )
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            identity = item["id"]
            if (
                not valid_id(identity)
                or counts[identity] != 1
                or type(item["version"]) is not int
                or item["version"] != 1
                or type(item["enabled"]) is not bool
            ):
                continue
            label = bounded_text(item["label"], LABEL_MAX_CHARS, "Label")
            if item["mode"] not in ("whole", "region"):
                continue
            window = Rect(*(item["window"][key] for key in ("x", "y", "w", "h")))
            if not valid_rect(window):
                continue
            source = validate_descriptor(item["source"])
            region = _region(item.get("region")) if item["mode"] == "region" else None
            result.append(
                CompanionDefinition(
                    1,
                    identity,
                    label,
                    item["enabled"],
                    item["mode"],
                    source,
                    window,
                    region,
                )
            )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            continue
        if len(result) >= MAX_DEFINITIONS:
            break
    # An externally edited file cannot enable more relationships than UI admission.
    enabled = 0
    bounded = []
    for item in result:
        enabled += item.enabled
        bounded.append(
            replace(item, enabled=False)
            if item.enabled and enabled > MAX_ENABLED
            else item
        )
    return tuple(bounded)


def serialize_definitions(definitions: tuple[CompanionDefinition, ...]) -> list[dict]:
    result = []
    for definition in definitions:
        value = {
            "version": definition.version,
            "id": definition.id,
            "label": definition.label,
            "enabled": definition.enabled,
            "mode": definition.mode,
            "source": asdict(definition.source),
            "window": definition.window._asdict(),
        }
        if definition.mode == "region":
            value["region"] = asdict(definition.region)
        result.append(value)
    return result


def matching_sources(
    source: SourceDescriptor, candidates: tuple[SourceBinding, ...]
) -> tuple[SourceBinding, ...]:
    return tuple(
        binding
        for binding in candidates
        if normalize_path(binding.executable_path) == source.executable_path
        and binding.window_class == source.window_class
        and (
            binding.title == source.title_hint
            if source.title_mode == "exact"
            else source.title_hint in binding.title
        )
    )


def region_from_pixels(rect: Rect, size: tuple[int, int]) -> CompanionRegion:
    source = source_from_pixels(rect, size)
    return CompanionRegion(source.x, source.y, source.w, source.h, *size)


def region_to_pixels(region: CompanionRegion, size: tuple[int, int]) -> Rect | None:
    source = CropSource(
        region.x,
        region.y,
        region.w,
        region.h,
        region.original_client_w,
        region.original_client_h,
        Rect(0, 0, region.original_client_w, region.original_client_h),
    )
    return source_to_pixels(source, size)
